import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from todo_lib.local.publication import PublicationObserver
from todo_lib.local.safety import LocalError


class PublicationObservation(unittest.TestCase):
    def test_initial_cursor_is_a_publication_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Mock(root=Path(directory))
            observer = PublicationObserver(store, ('report-cursor', 'binding.json'))
            observer.capture()
            path = store.root / 'report-cursor'
            path.write_bytes(b'2026-10-23T00:00:00Z\n')
            path.chmod(0o600)
            self.assertEqual(observer.changed_destinations(), ('report-cursor',))

    def test_unreadable_bytes_and_secondary_probe_failure_remain_conservative(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Mock(root=Path(directory))
            path = store.root / 'cache.json'
            path.write_bytes(b'cached')
            path.chmod(0o600)
            observer = PublicationObserver(store)
            observer.capture()
            store.load_consistent_state.side_effect = RuntimeError('secondary failure')
            with patch('todo_lib.local.publication.read_bytes', side_effect=LocalError('unreadable')):
                facts = observer.failure_facts()
            self.assertTrue(facts.started)
            self.assertFalse(facts.required_state_usable)
            self.assertFalse(facts.saved_snapshot_available)

    def test_failure_before_capture_cannot_have_started_publication(self):
        store = Mock()
        self.assertFalse(PublicationObserver(store).failure_facts().started)
