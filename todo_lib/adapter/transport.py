"""Controlled Todoist API-v1 HTTP boundary (stdlib only).

Credentials are resolved by the caller once, then passed to Transport. No HOME,
configuration, environment credentials or endpoint override is consulted here.
request() returns decoded JSON (None for an empty HTTP 204/205 response). Resource
schemas and Sync command outcomes belong to the consuming adapter, not HTTP.

Replay.READ also covers POST /sync reads. Replay.IDEMPOTENT requires caller-owned
UUIDs present in Sync commands. It permits status retries,
but connection loss always returns OutcomeUnknown for reconciliation first. The
caller must retain those same UUIDs if reconciliation later authorizes replay.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from enum import Enum
import json
import re
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
from uuid import UUID

__all__ = ['Transport', 'Replay', 'HTTPFailure', 'Rejected', 'TransportError',
           'ProtocolError', 'OutcomeUnknown', 'redact']

_BASE = 'https://api.todoist.com/api/v1'
_RETRY = frozenset({408, 429, 500, 502, 503, 504})


class Replay(Enum):
    READ = 'read'
    IDEMPOTENT = 'idempotent'
    UNSAFE = 'unsafe'


def redact(text: str, secret: str) -> str:
    """Remove the resolved secret and complete Authorization header values."""
    text = re.sub(r'(?im)(authorization[\"\x27]?\s*[:=]\s*)[^\r\n]+',
                  r'\1[REDACTED]', text)
    return text.replace(secret, '[REDACTED]') if secret else text


class HTTPFailure(Exception):
    """Safe diagnostic; no raw response, Request or original exception retained.

    status is HTTP status or None; attempts counts actual opener calls. outcome is
    rejected, unavailable, protocol, unknown, or unattempted. Structured remote
    error bodies are deliberately not displayed or retained here.
    """
    def __init__(self, message, *, status=None, attempts=0, outcome='unattempted'):
        super().__init__(message)
        self.status, self.attempts, self.outcome = status, attempts, outcome


class Rejected(HTTPFailure):
    """Definitive non-retry HTTP rejection with a structured JSON error body."""


class TransportError(HTTPFailure):
    """Read unavailable, status attempts exhausted, or operator retry required."""


class ProtocolError(HTTPFailure):
    """Invalid HTTP/JSON response; never proves mutation rejection."""


class OutcomeUnknown(HTTPFailure):
    """Mutation requires authoritative reconciliation before replay."""


class _NoRedirect(HTTPRedirectHandler):
    # Never forward a credential or silently turn a POST into a GET.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _uuid(value):
    return isinstance(value, str) and str(UUID(value)) == value.lower()


def _pairs(values):
    """Require explicit string form/query scalars; JSON-in-form is caller encoded."""
    if values is None:
        return None
    pairs = list(values.items()) if isinstance(values, Mapping) else list(values)
    if any(not isinstance(k, str) or not isinstance(v, str) for k, v in pairs):
        raise ValueError('form/query values must be explicit strings')
    return pairs


def _decode(raw):
    # Reject non-standard NaN/Infinity rather than passing invented JSON downstream.
    def invalid_constant(_):
        raise ValueError('invalid JSON constant')
    return json.loads(raw.decode('utf-8'), parse_constant=invalid_constant)


class Transport:
    """opener(request, timeout=30), sleep(seconds), clock()->aware datetime hooks.

    stderr is a text stream, defaulting to current sys.stderr. Hooks are ordinary
    dependency injection, not user configuration. The default urllib opener
    rejects all redirects so authorization cannot be forwarded to another URL.
    """
    def __init__(self, secret: str, *, opener=None, sleep=time.sleep,
                 clock=None, stderr=None):
        if not isinstance(secret, str) or not secret or any(c.isspace() for c in secret):
            raise ValueError('a resolved nonempty credential is required')
        self._secret = secret
        self._opener = opener if opener is not None else build_opener(_NoRedirect()).open
        self._sleep = sleep
        self._clock = clock if clock is not None else lambda: datetime.now(timezone.utc)
        self._stderr = stderr

    def __repr__(self):
        return '<Transport credential=[REDACTED]>'

    def request(self, method: str, path: str, *, operation: str, replay: Replay,
                query=None, form=None, json_body=None, command_uuids=(), request_id=None):
        """Send explicitly encoded request; never infer safety from HTTP method alone.

        path is an API-relative absolute path, e.g. /sync or /comments. command_uuids
        must exactly match the mutation Sync batch. REST requests must carry a
        caller-owned request_id, but the pinned evidence only proves automatic
        replay safety for Sync command UUIDs; REST mutations use Replay.UNSAFE.
        Invalid local arguments fail before any network call with a safe error.
        """
        failure = None
        try:
            if not isinstance(operation, str) or not operation:
                raise ValueError()
            if method not in {'GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD'}:
                raise ValueError()
            if not isinstance(replay, Replay):
                raise ValueError()
            parts = urlsplit(path)
            if (not path.startswith('/') or path.startswith('//') or parts.scheme
                    or parts.netloc or parts.query or parts.fragment
                    or '%' in path or '\\' in path or ':' in path
                    or any(c.isspace() or ord(c) < 32 for c in path)
                    or any(p in {'.', '..'} for p in path.split('/'))):
                raise ValueError()
            if form is not None and json_body is not None:
                raise ValueError()
            if method in {'GET', 'HEAD'} and (form is not None or json_body is not None):
                raise ValueError()
            if method in {'GET', 'HEAD'} and replay is not Replay.READ:
                raise ValueError()
            form_pairs, query_pairs = _pairs(form), _pairs(query)
            if request_id is not None and not _uuid(request_id):
                raise ValueError()
            ids = tuple(command_uuids)
            if any(not _uuid(i) for i in ids) or len(set(ids)) != len(ids):
                raise ValueError()
            if replay is Replay.READ and method not in {'GET', 'HEAD'}:
                if method != 'POST' or path != '/sync' or form_pairs is None:
                    raise ValueError()
                if 'commands' in dict(form_pairs):
                    raise ValueError()
            if replay is not Replay.READ:
                if path == '/sync':
                    if method != 'POST' or form_pairs is None or not ids:
                        raise ValueError()
                    commands = json.loads(dict(form_pairs)['commands'])
                    if (not isinstance(commands, list) or not commands
                            or tuple(c['uuid'] for c in commands) != ids):
                        raise ValueError()
                elif replay is Replay.IDEMPOTENT or request_id is None:
                    raise ValueError()
            url = _BASE + path
            if query_pairs:
                url += '?' + urlencode(query_pairs)
            headers = {'Authorization': 'Bearer ' + self._secret, 'Accept': 'application/json'}
            data = None
            if form_pairs is not None:
                data = urlencode(form_pairs).encode('ascii')
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
            elif json_body is not None:
                data = json.dumps(json_body, ensure_ascii=False, allow_nan=False,
                                  separators=(',', ':')).encode('utf-8')
                headers['Content-Type'] = 'application/json'
            if request_id is not None:
                headers['X-Request-Id'] = request_id
        except Exception:
            failure = HTTPFailure('invalid HTTP request arguments')
        # Raise outside the handler so no exception context can reveal input.
        if failure is not None:
            raise failure
        operation = redact(operation, self._secret).replace('\n', ' ').replace('\r', ' ')
        for attempt in range(1, 5):
            status, response_headers, raw, failed = None, {}, b'', False
            try:
                request = Request(url, data=data, headers=headers, method=method)
                try:
                    response = self._opener(request, timeout=30)
                except HTTPError as error:
                    response = error
                try:
                    status = response.status if hasattr(response, 'status') else response.code
                    response_headers = response.headers
                    raw = response.read()
                finally:
                    response.close()
            except Exception:
                failed = True
            if failed:
                cls = TransportError if replay is Replay.READ else OutcomeUnknown
                raise cls(f'{operation}: transport failure; reconciliation required' if
                          cls is OutcomeUnknown else f'{operation}: transport failure',
                          status=status, attempts=attempt,
                          outcome='unavailable' if cls is TransportError else 'unknown')
            if not isinstance(status, int) or not 100 <= status <= 599:
                raise self._protocol(operation, replay, status, attempt)
            if 200 <= status < 300:
                if not raw and status in {204, 205}:
                    return None
                invalid = False
                try:
                    result = _decode(raw)
                except Exception:
                    invalid = True
                if invalid:
                    raise self._protocol(operation, replay, status, attempt)
                return result
            if status in _RETRY:
                if replay is Replay.UNSAFE:
                    raise OutcomeUnknown(f'{operation}: HTTP {status}; reconcile before replay',
                                         status=status, attempts=attempt, outcome='unknown')
                if attempt == 4:
                    raise self._unavailable(operation, replay, status, attempt, 'attempts exhausted')
                delay = self._delay(response_headers, 2 ** (attempt - 1))
                if delay > 60:
                    raise self._unavailable(operation, replay, status, attempt,
                                            'Retry-After exceeds 60s; operator retry required')
                hook_failed = False
                try:
                    print(f'{operation}: retry after HTTP {status} in {delay:g}s',
                          file=self._stderr if self._stderr is not None else sys.stderr)
                    self._sleep(delay)
                except Exception:
                    hook_failed = True
                if hook_failed:
                    raise self._unavailable(operation, replay, status, attempt, 'retry interrupted')
                continue
            if replay is not Replay.READ and (status >= 500 or status == 408):
                raise OutcomeUnknown(f'{operation}: HTTP {status}; reconcile before replay',
                                     status=status, attempts=attempt, outcome='unknown')
            valid_error = False
            try:
                error_body = _decode(raw)
                valid_error = isinstance(error_body, dict) and bool(error_body)
            except Exception:
                pass
            if not 400 <= status <= 599 or not valid_error:
                raise self._protocol(operation, replay, status, attempt)
            raise Rejected(f'{operation}: HTTP {status} rejection', status=status,
                           attempts=attempt, outcome='rejected')

    def _delay(self, headers, default):
        try:
            value = headers.get('Retry-After')
            if value is None:
                return default
            value = value.strip()
            if re.fullmatch(r'[0-9]+', value):
                return int(value)
            date = parsedate_to_datetime(value)
            now = self._clock()
            if date.tzinfo is None or now.tzinfo is None:
                return default
            return max(0, (date - now).total_seconds())
        except Exception:
            return default

    @staticmethod
    def _protocol(operation, replay, status, attempt):
        cls = ProtocolError if replay is Replay.READ else OutcomeUnknown
        return cls(f'{operation}: invalid HTTP/JSON response', status=status,
                   attempts=attempt, outcome='protocol' if cls is ProtocolError else 'unknown')

    @staticmethod
    def _unavailable(operation, replay, status, attempt, reason):
        cls = TransportError if replay is Replay.READ else OutcomeUnknown
        return cls(f'{operation}: HTTP {status}; {reason}', status=status,
                   attempts=attempt, outcome='unavailable' if cls is TransportError else 'unknown')
