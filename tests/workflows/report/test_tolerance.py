"""One comment identity through refresh/reload/editor/report, using real consumers.

Source: pinned api-v1.openapi.json NoteSyncView.content/default and GET /comments;
synthetic lifecycle/scope wrappers. No live preservation claim.
"""
import unittest
from unittest.mock import patch
from todo_lib import domain as d
from todo_lib import presentation as p
from todo_lib.workflows.sync import Synchronizer
from todo_lib.workflows.comments import CommentWorkflow
from tests.workflows.report import test_report as base
from tests.adapter.current.test_current import full, delta, item


class ToleranceTests(unittest.TestCase):
    setUp = base.Reports.setUp
    put = base.Reports.put
    sync = base.Reports.sync
    boundary = base.Reports.boundary
    streams = base.Reports.streams
    requests = base.Reports.requests
    run_report = base.Reports.run_report

    test_unresolved_archived_owner_and_parent_fail_without_output = base.Reports.test_unresolved_archived_owner_and_parent_fail_without_output
    test_unknown_activity_owner_cannot_be_assumed_unrelated = base.Reports.test_unknown_activity_owner_cannot_be_assumed_unrelated

    def test_refresh_reload_unchanged_editor_qualifying_blank_report(self):
        blank = dict(id='own', item_id='B', posted_at=base.CREATED, is_deleted=False)
        transport, _ = self.boundary([
            self.sync('delta-token', full(items=[item('A'), item('B', parent_id='A')],
                notes=[blank], user_plan_limits=base.limits())), self.sync('full-token', delta())])
        Synchronizer(transport, self.store, clock=lambda: base.NOW).refresh()
        restored = self.store.load_consistent_state().snapshot
        original = restored.comments['own']
        self.assertEqual((original.item_id, original.body), ('B', ''))
        from todo_lib.workflows.reads import search_candidates
        self.assertEqual(search_candidates(restored, '[no text]', all_items=True), ())
        self.assertIn('[no text]', p.render_comments(restored, restored.items['B']).stdout)
        transport, _ = self.boundary([])
        workflow = CommentWorkflow(Synchronizer(transport, self.store, clock=lambda: base.NOW), streams=self.streams())
        def unchanged(text):
            self.assertIn('[id: own posted:', text)
            self.assertNotIn('[no text]', text)
            return text.replace('\n', '\r\n')
        with patch.object(workflow, '_edit', side_effect=unchanged):
            result = workflow.execute(['comment', '--edit', 'B'])
        self.assertEqual(result.status, 0)
        self.assertEqual(self.store.load_consistent_state().snapshot.comments['own'], original)
        before = (self.root / 'report-cursor').read_bytes()
        result, streams = self.run_report(self.requests(events=[base.event(1, base.LAST)],
            current_notes=[blank], comments=[{k: v for k, v in blank.items() if k != 'item_id'}]))
        self.assertEqual(streams.stdout.getvalue().count('[no text]'), 1)
        self.assertFalse(result.finalized)
        self.assertEqual((self.root / 'report-cursor').read_bytes(), before)

    def test_blank_report_incomplete_page_keeps_cursor_and_no_output(self):
        blank = dict(id='own', posted_at=base.CREATED, is_deleted=False)
        steps = self.requests(events=[base.event(1, base.LAST)], comments=[blank],
            current_items=[item('A')], rows=[base.completed_b()])
        steps[-1][1].pop('next_cursor')
        streams = self.streams()
        before = (self.root / 'report-cursor').read_bytes()
        with self.assertRaisesRegex(base.SyncError, 'next_cursor'):
            self.run_report(steps, ['--final'], streams)
        self.assertEqual(streams.stdout.getvalue(), '')
        self.assertEqual((self.root / 'report-cursor').read_bytes(), before)
