from dataclasses import replace
import tempfile
from pathlib import Path
import unittest
from todo_lib import domain as d
from todo_lib.local import StateStore, History, prepare_candidates, exclusive_lock
from todo_lib.local.codec import snapshot_data, snapshot_from, dumps, loads
from tests.support.reminders import observed, FLOATING


class ReminderStorageTests(unittest.TestCase):
    def test_legacy_history_and_mixed_exact_round_trip(self):
        s = observed(self).snapshot
        old = replace(s, reminders={'rel': d.Reminder('rel', 'timed', 0)})
        data = snapshot_data(old)
        data['reminders']['rel'] = {'id': 'rel', 'item_id': 'timed', 'minutes': 0}
        old = snapshot_from(loads(dumps(data)), s.account.timezone)
        self.assertEqual(old.reminders['rel'], d.Reminder('rel', 'timed', 0))
        now = d.instant_from_wire('2026-10-22T12:00:00.123456789012345Z')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / '.todo'
            root.mkdir(mode=0o700)
            store = StateStore(root)
            with exclusive_lock('test', root):
                store.publish_snapshot(prepare_candidates(old, History(old, {'timed': now}),
                    account_display='Person', sync_token='old', synced_at=now, initial_cursor=now))
            # Actual schema-1 pending-history bytes from the old minute-only
            # representation, with unchanged identity/publication association.
            path = root / 'history.json'
            raw = loads(path.read_bytes())
            raw['snapshot']['reminders']['rel'] = {'id': 'rel', 'item_id': 'timed', 'minutes': 0}
            path.write_bytes(dumps(raw))
            legacy = store.load_history()
            self.assertEqual(legacy.snapshot.reminders['rel'].minutes, 0)
            with exclusive_lock('test', root):
                store.publish_snapshot(prepare_candidates(s, History(s, legacy.observations),
                    account_display='Person', sync_token='new', synced_at=now))
            state = store.load_consistent_state()
            for saved in (state.snapshot, state.history.snapshot):
                self.assertEqual(saved.reminders, s.reminders)
                self.assertEqual(saved.reminders['floating'].due.raw_due, FLOATING)
                self.assertEqual(saved.reminders['abs'].notify_uid, 'recipient')
                self.assertTrue(saved.reminders['abs'].is_urgent)
            self.assertEqual(state.history.observations, legacy.observations)
            self.assertNotIn('timezone', snapshot_data(s)['account'])
