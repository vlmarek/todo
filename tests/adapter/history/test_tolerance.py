"""Pinned API-v1 NoteSyncView default content and endpoint relevance probes.

Source: docs/design/external/todoist/upstream/api-v1.openapi.json:
GET /comments -> PaginatedList_NoteSyncView_; NoteSyncView.content default ''.
Other rows are synthetic fault isolation, not recorded provider traffic.
"""
import unittest
from todo_lib import domain as d
from todo_lib.adapter.history import HistoryError, Retrieval
from tests.adapter.history import test_history as base


class ToleranceTests(unittest.TestCase):
    boundary = base.HistoryTests.boundary

    test_required_cursors_are_not_completed_exception = base.HistoryTests.test_required_cursors_are_not_completed_exception
    test_missing_or_malformed_page_records_never_become_empty_history = base.HistoryTests.test_missing_or_malformed_page_records_never_become_empty_history

    def test_scoped_default_blank_deleted_and_ignored_metadata(self):
        raw = dict(id='blank', posted_at=base.START, is_deleted=False)
        adapter, _ = self.boundary([('/comments', base.comments_query('step'),
            {'results': [raw, dict(raw, content='', file_attachment={'anything': 12}),
                         dict(id='gone', is_deleted=True)], 'next_cursor': None})])
        result = adapter.comments('step')
        self.assertEqual(len(result.records), 1)
        self.assertEqual((result.records[0].id, result.records[0].item_id, result.records[0].body),
                         ('blank', 'step', ''))
        for changes in ({'content': None}, {'content': '\x00'}, {'posted_at': 'bad'}):
            adapter, _ = self.boundary([('/comments', base.comments_query('step'),
                {'results': [{**raw, **changes}], 'next_cursor': None})])
            with self.assertRaises(HistoryError): adapter.comments('step')

    def test_unused_annotations_any_shape_and_no_request(self):
        for extra in ({'content': {}}, {'content': 12, 'type': []}, [], 'unused', None):
            adapter, _ = self.boundary([('/activities', base.ACTIVITY_QUERY,
                {'results': [base.event(extra_data=extra)], 'next_cursor': None})])
            result = adapter.activities(base.stamp(base.START), base.stamp(base.END))
            self.assertIsNone(result.records[0].annotation)
        self.assertNotIn('annotate_notes', dict(base.ACTIVITY_QUERY))

    def test_interval_before_display_and_deleted_lifecycle_retained(self):
        outside = dict(id='outside', project_id='cat', completed_at=base.START, is_deleted=False)
        deleted = dict(id='dead', project_id='cat', parent_id=None, completed_at=base.END, is_deleted=True)
        adapter, _ = self.boundary([(base.COMPLETED, base.COMPLETED_QUERY, {'items': [outside, deleted]})])
        result = adapter.completed(base.stamp(base.START), base.stamp(base.END))
        self.assertEqual(len(result.records), 1)
        self.assertTrue(result.records[0].deleted)
        self.assertEqual(result.records[0].item.id, 'dead')
        for changes in ({'id': None}, {'project_id': None}, {'completed_at': 'bad'}, {'is_deleted': None}):
            adapter, _ = self.boundary([(base.COMPLETED, base.COMPLETED_QUERY, {'items': [{**outside, **changes}]})])
            with self.assertRaises(HistoryError): adapter.completed(base.stamp(base.START), base.stamp(base.END))

    def test_unneeded_archived_comment_body_does_not_block_required_retrieval(self):
        adapter, _ = self.boundary([
            ('/activities', base.ACTIVITY_QUERY, {'results': [base.event(parent_item_id='archived')], 'next_cursor': None}),
            ('/comments', base.comments_query('archived'), {'results': [dict(id='unrelated', is_deleted=False, content=123)], 'next_cursor': None})])
        events = adapter.activities(base.stamp(base.START), base.stamp(base.END))
        evidence = adapter.required_comments({}, Retrieval((), ()), events)
        self.assertFalse(evidence.owners)
        self.assertFalse(evidence.comments)
