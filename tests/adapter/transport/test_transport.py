"""Offline API-v1 evidence; source pointers and inspection date: tests.support.http.

Policy expectations derive from docs/design/todoist-adapter.md REQ-NET-001.
Literal wire fixtures below are independent of transport encoding. Resource
mapping/pagination is the consuming adapters' responsibility; HTTP preserves
omitted, null, empty, alternate and unknown JSON values without inventing fields.
"""
from datetime import datetime, timezone
from io import StringIO
import json
import traceback
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request

from todo_lib.adapter.transport import (
    Transport, Replay, HTTPFailure, Rejected, TransportError, ProtocolError,
    OutcomeUnknown, redact, _NoRedirect,
)
from tests.support.http import ControlledHTTP, ExpectedRequest, Response

TOKEN = 'synthetic-transport-secret'
UUID = 'ed1ce597-e4c7-4a88-ba48-e048d827c067'
COMMANDS = '[{"type":"item_move","uuid":"ed1ce597-e4c7-4a88-ba48-e048d827c067","args":{"id":"task-A","project_id":"project-B"}}]'


class TransportTests(unittest.TestCase):
    def make(self, results, expected=None):
        expected = expected or ExpectedRequest('GET', '/comments', TOKEN,
                                               query={'task_id': 'task-A'})
        self.http = ControlledHTTP([(expected, result) for result in results])
        self.addCleanup(self.http.assert_done)
        self.delays, self.stderr = [], StringIO()
        return Transport(TOKEN, opener=self.http, sleep=self.delays.append,
                         clock=lambda: datetime(2026, 10, 26, tzinfo=timezone.utc),
                         stderr=self.stderr)

    def read(self, transport, **kwargs):
        return transport.request('GET', '/comments', operation='read comments',
                                 replay=Replay.READ, query={'task_id': 'task-A'}, **kwargs)

    def mutation(self, transport, replay=Replay.IDEMPOTENT):
        return transport.request('POST', '/sync', operation='move task', replay=replay,
                                 form={'commands': COMMANDS}, command_uuids=(UUID,))

    def move_expected(self):
        return ExpectedRequest('POST', '/sync', TOKEN, form={'commands': COMMANDS})

    def test_read_query_and_provider_variants(self):
        payloads = [b'{"results":[],"next_cursor":null}',
                    b'{"items":[],"extra":true}',
                    b'{"added_at":null,"id":"task-A"}', b'[]', b'null']
        t = self.make([Response(p) for p in payloads])
        for p in payloads:
            self.assertEqual(self.read(t), json.loads(p))
        self.http.assert_done()

    def test_sync_form_read_is_explicit_json_string(self):
        t = self.make([Response(b'{"sync_token":"next","items":[]}')],
                      ExpectedRequest('POST', '/sync', TOKEN,
                                      form={'sync_token': '*', 'resource_types': '["items","projects"]'}))
        result = t.request('POST', '/sync', operation='sync current', replay=Replay.READ,
                           form={'sync_token': '*', 'resource_types': '["items","projects"]'})
        self.assertEqual(result['items'], [])
        self.assertIn(b'resource_types=%5B%22items%22%2C%22projects%22%5D',
                      self.http.requests[0][0].data)

    def test_rest_json_and_caller_uuid(self):
        body = {'task_id': 'task-A', 'content': 'café + &'}
        t = self.make([Response(b'{"id":"note-A","content":"saved"}')],
                      ExpectedRequest('POST', '/comments', TOKEN, json_body=body, request_id=UUID))
        result = t.request('POST', '/comments', operation='add comment',
                           replay=Replay.UNSAFE, json_body=body, request_id=UUID)
        self.assertEqual(result['id'], 'note-A')
        self.assertIn('café'.encode(), self.http.requests[0][0].data)

    def test_query_escaping_and_empty_form_value(self):
        t = self.make([Response()], ExpectedRequest('POST', '/sync', TOKEN,
                      query={'cursor': 'a+b/c=&'}, form={'sync_token': '', 'resource_types': '[]'}))
        t.request('POST', '/sync', operation='sync', replay=Replay.READ,
                  query={'cursor': 'a+b/c=&'}, form={'sync_token': '', 'resource_types': '[]'})
        self.assertIn('cursor=a%2Bb%2Fc%3D%26', self.http.requests[0][0].full_url)

    def test_each_retry_status_and_exact_four_attempt_budget(self):
        for status in (408, 429, 500, 502, 503, 504):
            with self.subTest(status=status):
                t = self.make([Response(status=status) for _ in range(4)])
                with self.assertRaises(TransportError) as caught:
                    self.read(t)
                self.assertEqual(caught.exception.attempts, 4)
                self.assertEqual(caught.exception.outcome, 'unavailable')
                self.assertEqual(self.delays, [1, 2, 4])
                self.assertEqual(len(self.http.requests), 4)
                self.assertEqual(len(self.stderr.getvalue().splitlines()), 3)
                self.assertIn('read comments', self.stderr.getvalue())
                self.http.assert_done()

    def test_nonretry_statuses_structured_rejection(self):
        for status in (400, 401, 403, 404, 409, 422, 501, 505):
            with self.subTest(status=status):
                t = self.make([Response(b'{"error":"bad request","error_code":20}', status)])
                with self.assertRaises(Rejected) as caught:
                    self.read(t)
                self.assertEqual(caught.exception.status, status)
                self.assertEqual(caught.exception.outcome, 'rejected')
                self.assertEqual(self.delays, [])
                self.assertEqual(len(self.http.requests), 1)

    def test_usable_retry_after_seconds_and_date(self):
        for header, delay in [('0', 0), ('60', 60), ('Mon, 26 Oct 2026 00:00:12 GMT', 12),
                              ('Sun, 25 Oct 2026 00:00:00 GMT', 0)]:
            with self.subTest(header=header):
                t = self.make([Response(status=429, headers={'Retry-After': header}), Response()])
                self.read(t)
                self.assertEqual(self.delays, [delay])

    def test_unusable_retry_after_fallback(self):
        for value in ('nope', '-1', '1.5', '', 'Mon, 26 Oct 2026 00:00:01'):
            with self.subTest(value=value):
                t = self.make([Response(status=503, headers={'Retry-After': value}), Response()])
                self.read(t)
                self.assertEqual(self.delays, [1])

    def test_retry_after_cap_operator_retry(self):
        for header in ('61', 'Mon, 26 Oct 2026 00:01:01 GMT'):
            t = self.make([Response(status=429, headers={'Retry-After': header})])
            with self.assertRaisesRegex(TransportError, 'operator retry'):
                self.read(t)
            self.assertEqual(self.delays, [])
            self.assertEqual(self.stderr.getvalue(), '')

    def test_urllib_http_error_uses_same_policy_and_closes_body(self):
        from io import BytesIO
        body = BytesIO(b'{}')
        error = HTTPError('https://api.todoist.com/api/v1/comments', 503,
                          'unavailable', {'Retry-After': '2'}, body)
        t = self.make([error, Response()])
        self.read(t)
        self.assertTrue(body.closed)
        self.assertEqual(self.delays, [2])

    def test_status_retry_reuses_idempotent_sync_bytes_and_uuid(self):
        t = self.make([Response(status=503), Response(b'{"sync_status":{"' +
                      UUID.encode() + b'":"ok"}}')], self.move_expected())
        self.assertEqual(self.mutation(t)['sync_status'][UUID], 'ok')
        self.assertEqual(self.delays, [1])
        self.assertEqual(self.http.requests[0][0].data, self.http.requests[1][0].data)

    def test_unsafe_mutation_no_status_retry(self):
        for status in (408, 429, 500, 502, 503, 504, 501):
            t = self.make([Response(status=status)], self.move_expected())
            with self.assertRaises(OutcomeUnknown) as caught:
                self.mutation(t, Replay.UNSAFE)
            self.assertEqual(caught.exception.outcome, 'unknown')
            self.assertEqual(len(self.http.requests), 1)
            self.assertEqual(self.delays, [])

    def test_network_loss_never_rejection_or_automatic_replay(self):
        for replay in (Replay.READ, Replay.IDEMPOTENT, Replay.UNSAFE):
            for error in (URLError('connection lost'), TimeoutError('timed out'),
                          OSError('reset'), RuntimeError('unexpected')):
                with self.subTest(replay=replay, error=type(error)):
                    t = self.make([error], None if replay is Replay.READ else self.move_expected())
                    with self.assertRaises(TransportError if replay is Replay.READ else OutcomeUnknown):
                        self.read(t) if replay is Replay.READ else self.mutation(t, replay)
                    self.assertEqual(len(self.http.requests), 1)
                    self.assertEqual(self.delays, [])

    def test_invalid_json_protocol_or_mutation_unknown(self):
        for body in (b'', b'<html>bad</html>', b'{', b'\xff', b'{"x":NaN}'):
            for mutation in (False, True):
                t = self.make([Response(body)], self.move_expected() if mutation else None)
                with self.assertRaises(OutcomeUnknown if mutation else ProtocolError):
                    self.mutation(t) if mutation else self.read(t)
                self.assertEqual(self.delays, [])

    def test_unstructured_errors_and_redirect_are_protocol_errors(self):
        for status, body in [(400, b'not json'), (400, b'{}'), (302, b'{}')]:
            t = self.make([Response(body, status)])
            with self.assertRaises(ProtocolError):
                self.read(t)
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.invalid'))

    def test_success_empty_and_resource_close(self):
        response = Response(b'', 204)
        self.assertIsNone(self.read(self.make([response])))
        self.assertTrue(response.closed)

    def test_redaction_in_errors_repr_warnings_and_tracebacks(self):
        hostile = 'Authorization: Bearer ' + TOKEN + '\nelse ' + TOKEN
        for response in (RuntimeError(hostile), Response(hostile.encode(), 400),
                         Response(hostile.encode()), Response(status=503)):
            t = self.make([response, Response()] if getattr(response, 'status', 0) == 503 else [response])
            try:
                t.request('GET', '/comments', operation=hostile, replay=Replay.READ,
                          query={'task_id': 'task-A'})
            except HTTPFailure as error:
                rendered = ''.join(traceback.format_exception(error))
                self.assertNotIn(TOKEN, rendered)
                self.assertNotIn('Bearer ' + TOKEN, repr(error))
                self.assertIsNone(error.__context__)
            self.assertNotIn(TOKEN, self.stderr.getvalue() + repr(t))
        self.assertNotIn('other-secret', redact('Authorization: Bearer other-secret', TOKEN))

    def test_invalid_arguments_fail_before_network_and_redact(self):
        cases = [dict(path='https://evil.invalid/'), dict(path='//evil.invalid/'),
                 dict(path='/../sync'), dict(path='/sync?token=' + TOKEN),
                 dict(path='/sync%2f..'), dict(method='TRACE'), dict(form={'x': []}),
                 dict(form={'x': 'v'}, json_body={}), dict(request_id='bad-' + TOKEN),
                 dict(replay='read'), dict(replay=Replay.IDEMPOTENT),
                 dict(method='POST', path='/comments'),
                 dict(method='POST', path='/sync', form={'commands': COMMANDS}),
                 dict(command_uuids=('invalid',)),
                 dict(method='POST', path='/sync', replay=Replay.UNSAFE, form={'commands': COMMANDS}),
                 dict(method='POST', path='/comments', replay=Replay.UNSAFE, json_body={})]
        for changes in cases:
            with self.subTest(keys=list(changes)):
                t = self.make([])
                args = dict(method='GET', path='/comments', operation='bad ' + TOKEN, replay=Replay.READ)
                args.update(changes)
                with self.assertRaises(HTTPFailure) as caught:
                    t.request(**args)
                self.assertEqual(self.http.requests, [])
                self.assertNotIn(TOKEN, ''.join(traceback.format_exception(caught.exception)))

    def test_mismatched_sync_uuid_cannot_claim_safe_replay(self):
        t = self.make([])
        with self.assertRaises(HTTPFailure):
            t.request('POST', '/sync', operation='move', replay=Replay.IDEMPOTENT,
                      form={'commands': COMMANDS},
                      command_uuids=('ac417051-1cdc-4dc3-b4f8-14526d5bfd16',))
        self.assertEqual(self.http.requests, [])

    def test_partial_read_loss_is_unknown_for_mutation(self):
        class BrokenResponse(Response):
            def read(self):
                raise OSError('Authorization: Bearer ' + TOKEN)
        response = BrokenResponse()
        t = self.make([response], self.move_expected())
        with self.assertRaises(OutcomeUnknown) as caught:
            self.mutation(t)
        self.assertTrue(response.closed)
        self.assertNotIn(TOKEN, ''.join(traceback.format_exception(caught.exception)))
        self.assertEqual(self.delays, [])

    def test_mutation_budget_cap_and_malformed_rejection_remain_unknown(self):
        for responses in ([Response(status=503) for _ in range(4)],
                          [Response(status=429, headers={'Retry-After': '61'})],
                          [Response(b'bad JSON', status=400)]):
            t = self.make(responses, self.move_expected())
            with self.assertRaises(OutcomeUnknown) as caught:
                self.mutation(t)
            self.assertEqual(caught.exception.outcome, 'unknown')

    def test_warning_precedes_sleep_and_next_attempt(self):
        t = self.make([Response(status=503), Response()])
        def sleep(delay):
            self.assertIn('read comments: retry after HTTP 503 in 1s', self.stderr.getvalue())
            self.assertEqual(len(self.http.requests), 1)
            self.delays.append(delay)
        t._sleep = sleep
        self.read(t)
        self.assertEqual(self.delays, [1])

    def test_sleep_hook_failure_cannot_leak_or_replay(self):
        t = self.make([Response(status=503)])
        def fail_sleep(delay):
            raise RuntimeError('Authorization: Bearer ' + TOKEN)
        t._sleep = fail_sleep
        with self.assertRaises(TransportError) as caught:
            self.read(t)
        self.assertEqual(len(self.http.requests), 1)
        self.assertIsNone(caught.exception.__context__)
        self.assertNotIn(TOKEN, ''.join(traceback.format_exception(caught.exception)))

    def test_rest_request_id_is_not_invented_replay_guarantee(self):
        t = self.make([])
        with self.assertRaises(HTTPFailure):
            t.request('POST', '/comments', operation='add comment',
                      replay=Replay.IDEMPOTENT, request_id=UUID,
                      json_body={'task_id': 'task-A', 'content': 'text'})
        self.assertEqual(self.http.requests, [])

    def test_controlled_helper_rejects_wrong_requests(self):
        expected = self.move_expected()
        good = dict(url='https://api.todoist.com/api/v1/sync',
                    data=b'commands=%5B%7B%22type%22%3A%22item_move%22%2C%22uuid%22%3A%22ed1ce597-e4c7-4a88-ba48-e048d827c067%22%2C%22args%22%3A%7B%22id%22%3A%22task-A%22%2C%22project_id%22%3A%22project-B%22%7D%7D%5D',
                    method='POST', headers={'Authorization': 'Bearer ' + TOKEN,
                     'Content-Type': 'application/x-www-form-urlencoded'})
        expected.check(Request(**good), 30)
        for change in (dict(method='PUT'), dict(url='https://api.todoist.com/api/v1/tasks'),
                       dict(data=b'commands=[]'),
                       dict(data=good['data'].replace(UUID.encode(), b'wrong-uuid')),
                       dict(data=good['data'].replace(b'project-B', b'wrong-project'))):
            bad = good | change
            with self.assertRaises(AssertionError):
                expected.check(Request(**bad), 30)


if __name__ == '__main__':
    unittest.main()
