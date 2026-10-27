"""Selected-root relevance at discovery and retained-note preflight.

Synthetic fixtures follow pinned api-v1.openapi.json PersonalProjectSyncView,
WorkspaceProjectSyncView/is_shared, NoteSyncView.content/default and posted_at.
"""
import unittest
from todo_lib import domain as d
from todo_lib.workflows.init import InitError
from tests.workflows.init import test_init as base
from tests.adapter.current.test_current import full, item, note, project


class ToleranceTests(unittest.TestCase):
    setUp = base.InitTests.setUp
    put = base.InitTests.put
    run_init = base.InitTests.run_init
    initialize_existing = base.InitTests.initialize_existing
    bytes = base.InitTests.bytes

    def test_unrelated_project_label_and_retained_default_note(self):
        initial = full(labels=[base.LABEL], notes=[note()])
        self.initialize_existing(initial)
        blank = dict(id='note', item_id='task', posted_at=base.POSTED, is_deleted=False,
                     file_attachment={'ignored': ['anything']})
        remote = full(items=[], notes=[blank], labels=[base.LABEL, dict(id='irrelevant', name=123, is_deleted=False)],
            projects=[project('root', None), project(), dict(id='unsafe', parent_id=None, name=123, is_deleted=False)])
        self.run_init(base.Boundary([remote, remote]))
        self.assertEqual(self.store.load_history().snapshot.comments['note'].body, '')
        self.assertEqual(self.store.load_history().snapshot.comments['note'].item_id, 'task')
        tombstone = full(items=[], notes=[dict(id='note', is_deleted=True)], labels=[base.LABEL])
        self.run_init(base.Boundary([tombstone, tombstone]))
        self.assertNotIn('note', self.store.load_history().snapshot.comments)

    def test_selected_unsafe_and_unknown_item_ownership_fail_before_provision(self):
        self.put('config', base.CONFIG)
        for response in (full(projects=[project('root', None, is_shared=None), project()], labels=[base.LABEL]),
                         full(items=[dict(id='unknown', content=123)], labels=[base.LABEL])):
            wire = base.Boundary([response])
            with self.assertRaises(InitError): self.run_init(wire)
            self.assertFalse(wire.mutations)
