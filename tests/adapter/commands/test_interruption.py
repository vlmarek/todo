import unittest

from todo_lib.adapter.commands import (
    Gateway, MutationInterrupted, Operation, Outcome, UnsubmittedOperation,
)
from todo_lib.adapter.transport import Replay
from tests.support.commands import before


class InterruptEvidence(unittest.TestCase):
    def test_reconciliation_interruption_keeps_receipt_and_forbids_replay(self):
        for status, outcome in [('ok', Outcome.ACCEPTED),
                ({'error_code': 20, 'error': 'rejected secret'}, Outcome.REJECTED),
                (None, Outcome.UNKNOWN)]:
            with self.subTest(status=status):
                op = Operation('item_update', {'id': 'task', 'content': 'Changed'})
                class Transport:
                    _secret = 'secret'
                    calls = 0

                    def request(self, *args, **kwargs):
                        self.calls += 1
                        if self.calls == 1:
                            return {'sync_status': {op.uuid: status}}
                        raise KeyboardInterrupt
                transport = Transport()
                gateway = Gateway(transport)
                with self.assertRaises(MutationInterrupted) as caught:
                    gateway.execute(op, before=before())
                partial = caught.exception.result
                self.assertEqual(partial.outcome, outcome)
                self.assertTrue(partial.attempted)
                self.assertEqual(partial.target_id, 'task')
                self.assertNotIn('secret', str(partial.diagnostics))
                with self.assertRaises(UnsubmittedOperation):
                    gateway.execute(op, before=before())
                self.assertEqual(transport.calls, 2)

    def test_contradictory_receipts_remain_unknown_on_interruption(self):
        op = Operation('item_update', {'id': 'task', 'content': 'Changed'})
        class Transport:
            calls = 0

            def request(self, *args, **kwargs):
                self.calls += 1
                status = 'ok' if self.calls == 1 else {'error_code': 20, 'error': 'Rejected'}
                return {'sync_status': {op.uuid: status}}
        def interrupted(transport, *args, **kwargs):
            transport.request('POST', '/sync', replay=Replay.READ)
            raise KeyboardInterrupt
        with self.assertRaises(MutationInterrupted) as caught:
            Gateway(Transport(), retrieve=interrupted).execute(op, before=before())
        self.assertEqual(caught.exception.result.outcome, Outcome.UNKNOWN)

    def test_create_without_temp_id_mapping_does_not_gain_acceptance(self):
        op = Operation('item_add', {'project_id': 'cat', 'content': 'Original'})
        class Transport:
            def request(self, *args, **kwargs):
                return {'sync_status': {op.uuid: 'ok'}}
        def interrupted(*args, **kwargs):
            raise KeyboardInterrupt
        with self.assertRaises(MutationInterrupted) as caught:
            Gateway(Transport(), retrieve=interrupted).execute(op, before=before())
        self.assertEqual(caught.exception.result.outcome, Outcome.UNKNOWN)
        self.assertIsNone(caught.exception.result.target_id)
