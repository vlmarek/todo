from io import StringIO
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from todo_lib import cli, domain as d
from todo_lib.local import StateStore, History, prepare_candidates, exclusive_lock
from tests.support.reminders import observed


class PublicReminderReadsTests(unittest.TestCase):
    def test_real_mapping_store_pending_reload_public_offline_detail_now(self):
        current = observed(self)
        now = d.instant_from_wire('2026-10-22T12:00:00Z')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / '.todo'
            root.mkdir(mode=0o700)
            config = root / 'config'
            config.write_text('[main]\nproject=root\ndefault_sections=cat\nhidden_from_now=\n')
            config.chmod(0o600)
            store = StateStore(root)
            with exclusive_lock('test', root):
                store.publish_snapshot(prepare_candidates(current.snapshot,
                    History(current.snapshot, {'undated': now, 'timed': now}),
                    account_display='Person', sync_token=current.sync_token,
                    synced_at=now, initial_cursor=now))
            self.assertEqual(store.load_history().snapshot.reminders, current.snapshot.reminders)
            for args in (['task', 'undated'], ['now'], ['task', 'timed']):
                out, err = StringIO(), StringIO()
                with patch('todo_lib.cli.StateStore', return_value=StateStore(root)), \
                     patch('sys.stdout', out), patch('sys.stderr', err), \
                     patch.dict(os.environ, {'HOME': temp}, clear=True), \
                     patch('todo_lib.adapter.transport.Transport.request', side_effect=AssertionError('offline HTTP')):
                    status = cli.main(args)
                self.assertEqual(status, 0, err.getvalue())
                text = out.getvalue()
                if args[-1] == 'timed':
                    self.assertIn('reminders:at due', text)
                else:
                    self.assertIn('at 2025-02-12 09:00:00 Europe/Prague', text)
                    self.assertIn(' ↻ cada día a las 9', text)
                    self.assertNotIn('undated  due:', text)
