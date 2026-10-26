"""Small request-recording opener, not a provider emulator.

Wire expectations are caller supplied and checked independently of application
serialization. Provider authority (inspected 2026-10-26): retained
 docs/design/external/todoist/upstream/api-v1.openapi.json
 /tags/3/description: Sync intro, Read resources, Write resources, Command UUID;
 /paths/~1api~1v1~1comments/{get,post}: query, JSON body and X-Request-Id example.
 /tags Authorization: Bearer authentication.
Manifest retrieval: 2026-10-24; retained SHA256
9a7c4816042e5c1b66935f2be1cf83da953dc459649ee606ac364d1acbc4764c.
Responses in tests are synthetic provider-shaped examples, not recorded traffic.
"""
from dataclasses import dataclass
from io import BytesIO
import json
from urllib.parse import parse_qs, urlsplit


class Response(BytesIO):
    def __init__(self, body=b'{}', status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}


@dataclass
class ExpectedRequest:
    method: str
    path: str
    token: str
    query: dict | None = None
    form: dict | None = None
    json_body: object = None
    request_id: str | None = None

    def check(self, request, timeout):
        # Assertions intentionally contain no raw headers or request dumps.
        def require(condition, label):
            if not condition:
                raise AssertionError('unexpected HTTP ' + label)
        url = urlsplit(request.full_url)
        require(timeout == 30, 'timeout')
        require(url.scheme == 'https' and url.netloc == 'api.todoist.com', 'origin')
        require(url.path == '/api/v1' + self.path and not url.fragment, 'path')
        require(request.get_method() == self.method, 'method')
        require(parse_qs(url.query, keep_blank_values=True) ==
                {k: [v] for k, v in (self.query or {}).items()}, 'query')
        require(request.get_header('Authorization') == 'Bearer ' + self.token, 'authentication')
        require(request.get_header('X-request-id') == self.request_id, 'UUID')
        content_type = request.get_header('Content-type')
        if self.form is not None:
            require(content_type == 'application/x-www-form-urlencoded', 'form type')
            require(parse_qs(request.data.decode('ascii'), keep_blank_values=True) ==
                    {k: [v] for k, v in self.form.items()}, 'form')
        elif self.json_body is not None:
            require(content_type == 'application/json', 'JSON type')
            require(json.loads(request.data.decode('utf-8')) == self.json_body, 'JSON body')
        else:
            require(request.data is None and content_type is None, 'empty body')


class ControlledHTTP:
    """Script (ExpectedRequest, Response or exception) pairs, count actual calls."""
    def __init__(self, steps):
        self.steps = list(steps)
        self.requests = []
        self.mismatches = []

    def __call__(self, request, *, timeout):
        self.requests.append((request, timeout))
        if not self.steps:
            self.mismatches.append('unexpected extra HTTP call')
            raise AssertionError('unexpected extra HTTP call')
        expected, result = self.steps.pop(0)
        try:
            expected.check(request, timeout)
        except Exception:
            self.mismatches.append("outgoing request failed expectation")
            raise
        if isinstance(result, Exception):
            raise result
        return result

    def assert_done(self):
        if self.mismatches:
            raise AssertionError(self.mismatches[0])
        if self.steps:
            raise AssertionError('missing HTTP calls')
