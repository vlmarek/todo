"""Independent synthetic endpoint pages, not recorded provider traffic.

Authority inspected 2026-10-26: retained api-v1.openapi.json GET completed by
completion date (items, omitted terminal next_cursor, <=3 months, [since,until)),
activities (separate object/event fields, integer/null ID, string extra_data),
comments (task_id, NoteSyncView without item_id), paginated results/null cursor.
The documented full-page terminal omission is distinct from our synthetic pages.
Wire expectations below are literal independently chosen bounds and filters.
"""
from datetime import datetime, timezone
from io import StringIO
import json
import unittest
from urllib.parse import parse_qsl, urlsplit

from todo_lib.adapter.history import HistoryAdapter, HistoryError, Retrieval
from todo_lib.adapter.transport import Transport
from todo_lib.domain import Item, instant_from_wire as stamp, instant_text, instant_key
from tests.support.http import ControlledHTTP, Response


START = '2026-10-20T12:00:00.123456701Z'
END = '2026-10-20T12:00:00.123456709Z'
AFTER = '2026-10-20T12:00:00.123456710Z'
COMPLETED = '/tasks/completed/by_completion_date'
COMPLETED_QUERY = [('since', '2026-10-20T12:00:00Z'),
                   ('until', '2026-10-20T12:00:01Z'), ('limit', '200')]
ACTIVITY_QUERY = [('date_from', '2026-10-20T12:00:00Z'),
                  ('date_to', '2026-10-20T12:00:01Z'),
                  ('annotate_notes', 'true'), ('limit', '200'),
                  ('object_event_types', 'item:completed'),
                  ('object_event_types', 'item:uncompleted'),
                  ('object_event_types', 'note:added'),
                  ('object_event_types', 'note:updated'),
                  ('object_event_types', 'note:deleted')]


def item(identity='task', at=END, **kw):
    raw = dict(id=identity, project_id='cat', parent_id=None, content='Title',
               priority=4, checked=True, labels=[], due=None, added_at=None,
               completed_at=at, is_deleted=False)
    raw.update(kw)
    return raw


def event(identity=1, at=END, **kw):
    raw = dict(id=identity, object_type='note', object_id='note',
               event_type='updated', event_date=at, parent_item_id='step',
               parent_project_id='cat', extra_data={'content': 'Observed old text', 'unknown': 123})
    raw.update(kw)
    return raw


def comment(identity='note', **kw):
    # No item_id: the scoped request supplies ownership.
    raw = dict(id=identity, content='Current text', posted_at=START,
               is_deleted=False, file_attachment=None)
    raw.update(kw)
    return raw


def comments_query(owner):
    return [('task_id', owner), ('limit', '200')]


class Expected:
    """Small repeated-query-aware request check used with the shared opener."""
    def __init__(self, path, query):
        self.path, self.query = path, list(query)

    def check(self, request, timeout):
        url = urlsplit(request.full_url)
        assert url.scheme == 'https' and url.netloc == 'api.todoist.com'
        assert url.path == '/api/v1' + self.path
        assert request.get_method() == 'GET' and request.data is None
        assert request.get_header('Authorization') == 'Bearer secret'
        assert timeout == 30
        assert parse_qsl(url.query, keep_blank_values=True) == self.query, 'query drift or unsupported keys'


class HistoryTests(unittest.TestCase):
    def boundary(self, steps, stderr=None):
        http = ControlledHTTP([(Expected(path, query), response if isinstance(response, Response)
            else Response(json.dumps(response).encode())) for path, query, response in steps])
        self.addCleanup(http.assert_done)
        return HistoryAdapter(Transport('secret', opener=http), stderr=stderr), http

    def test_completed_cursorless_full_page_is_documented_terminal(self):
        rows = [item(str(n)) for n in range(200)]
        adapter, _ = self.boundary([(COMPLETED, COMPLETED_QUERY, {'items': rows, 'unknown': True})])
        result = adapter.completed(stamp(START), stamp(END))
        self.assertEqual(len(result.records), 200)
        self.assertTrue(result.pages[0].terminal_omission)
        self.assertTrue(result.pages[0].terminal)
        self.assertIsNone(result.records[0].item.added_at)
        self.assertEqual(instant_text(result.records[0].occurrence.completed_at), END)

    def test_completed_short_nonterminal_pages_exact_fraction_and_occurrence_dedupe(self):
        eligible = item(at='2026-10-20T12:00:00.123456705Z', added_at=START)
        adapter, _ = self.boundary([
            (COMPLETED, COMPLETED_QUERY, {'items': [item(at=START), eligible], 'next_cursor': 'a.b'}),
            (COMPLETED, COMPLETED_QUERY + [('cursor', 'a.b')],
             {'items': [eligible, item(), item(at=AFTER)]})])
        result = adapter.completed(stamp(START), stamp(END))
        self.assertEqual([instant_text(r.occurrence.completed_at) for r in result.records],
                         ['2026-10-20T12:00:00.123456705Z', END])
        self.assertEqual(instant_text(result.records[0].item.added_at), START)
        self.assertEqual(len(result.pages), 2)

    def test_completed_split_wire_windows_and_exact_boundary(self):
        first = [('since', '2026-01-01T00:00:00Z'), ('until', '2026-03-22T00:00:00Z'), ('limit', '200')]
        second = [('since', '2026-03-22T00:00:00Z'), ('until', '2026-04-03T00:00:01Z'), ('limit', '200')]
        edge = '2026-03-22T00:00:00Z'
        adapter, _ = self.boundary([
            (COMPLETED, first, {'items': [item(at=edge)]}),
            (COMPLETED, second, {'items': [item(at=edge), item(at='2026-04-03T00:00:00Z')]})])
        result = adapter.completed(stamp('2026-01-01T00:00:00Z'), stamp('2026-04-03T00:00:00Z'))
        self.assertEqual(len(result.records), 2)
        for page in result.pages:
            q = dict(page.parameters)
            self.assertLessEqual((datetime.fromisoformat(q['until']) - datetime.fromisoformat(q['since'])).days, 80)

    def test_activities_string_annotations_ids_source_order_and_precise_bounds(self):
        a = event(None, '2026-10-20T12:00:00.123456705Z')
        adapter, _ = self.boundary([
            ('/activities', ACTIVITY_QUERY, {'results': [event(0, START), a, event(2)], 'next_cursor': 'a.b'}),
            ('/activities', ACTIVITY_QUERY + [('cursor', 'a.b')], {'results': [a, event(2),
                event(3, AFTER), event(4, event_type='deleted', extra_data=None),
                event(5, object_type='item', object_id='task', event_type='completed',
                      parent_item_id=None, extra_data={'content': 'task title'})], 'next_cursor': None})])
        result = adapter.activities(stamp(START), stamp(END), None)
        self.assertEqual([r.id for r in result.records], [None, '2', None, '4', '5'])
        self.assertEqual(result.records[0].owner_id, 'step')
        self.assertEqual(result.records[0].object_id, 'note')
        self.assertEqual(result.records[-1].annotation, 'task title')
        self.assertIsNone(result.records[-2].annotation)
        self.assertEqual(instant_text(result.records[1].event_date), END)

    def test_activity_omitted_id_and_content_free_deletion(self):
        raw = event(event_type='deleted')
        del raw['id'], raw['extra_data']
        adapter, _ = self.boundary([('/activities', ACTIVITY_QUERY,
                                    {'results': [raw], 'next_cursor': None})])
        result = adapter.activities(stamp(START), stamp(END))
        self.assertIsNone(result.records[0].id)
        self.assertIsNone(result.records[0].annotation)

    def test_scoped_step_comments_all_pages_preserve_creation_and_null(self):
        query = comments_query('step')
        adapter, _ = self.boundary([
            ('/comments', query, {'results': [comment()], 'next_cursor': 'a.b'}),
            ('/comments', query + [('cursor', 'a.b')], {'results': [comment(),
                comment('unknown-time', posted_at=None), {'id': 'deleted', 'is_deleted': True, 'posted_at': None}], 'next_cursor': None})])
        result = adapter.comments('step')
        self.assertEqual([c.item_id for c in result.records], ['step', 'step'])
        self.assertEqual(instant_text(result.records[0].added_at), START)
        self.assertIsNone(result.records[1].added_at)
        self.assertEqual(result.records[0].body, 'Current text')

    def test_current_comments_do_not_accept_sync_item_owner_substitution(self):
        adapter, _ = self.boundary([('/comments', comments_query('step'),
            {'results': [comment(item_id='wrong-owner', file_name='ignored')], 'next_cursor': None})])
        self.assertEqual(adapter.comments('step').records[0].item_id, 'step')

    def test_attachment_uses_documented_field(self):
        adapter, _ = self.boundary([('/comments', comments_query('step'),
            {'results': [comment(file_attachment={'file_name': 'a.png'})], 'next_cursor': None})])
        with self.assertRaisesRegex(HistoryError, 'attachments are unsupported'):
            adapter.comments('step')

    def test_required_cursors_are_not_completed_exception(self):
        for path, query, field in [('/activities', ACTIVITY_QUERY, 'results'),
                                   ('/comments', comments_query('step'), 'results')]:
            with self.subTest(path=path):
                adapter, _ = self.boundary([(path, query, {field: []})])
                with self.assertRaisesRegex(HistoryError, 'missing required next_cursor'):
                    adapter.activities(stamp(START), stamp(END)) if path == '/activities' else adapter.comments('step')

    def test_supplied_malformed_and_repeated_cursors_all_endpoints(self):
        for path, query, field in [(COMPLETED, COMPLETED_QUERY, 'items'),
            ('/activities', ACTIVITY_QUERY, 'results'), ('/comments', comments_query('step'), 'results')]:
            def fetch(adapter):
                if path == COMPLETED:
                    return adapter.completed(stamp(START), stamp(END))
                if path == '/activities':
                    return adapter.activities(stamp(START), stamp(END))
                return adapter.comments('step')
            for cursor in ['', 'bad cursor', 'opaque-without-dot', 1, False, [], {}] + ([None] if path == COMPLETED else []):
                with self.subTest(path=path, cursor=cursor):
                    adapter, _ = self.boundary([(path, query, {field: [], 'next_cursor': cursor})])
                    with self.assertRaisesRegex(HistoryError, 'malformed next_cursor'):
                        fetch(adapter)
            adapter, _ = self.boundary([
                (path, query, {field: [], 'next_cursor': 'a.b'}),
                (path, query + [('cursor', 'a.b')], {field: [], 'next_cursor': 'c.d'}),
                (path, query + [('cursor', 'c.d')], {field: [], 'next_cursor': 'a.b'})])
            with self.assertRaisesRegex(HistoryError, 'repeated next_cursor'):
                fetch(adapter)

    def test_malformed_required_event_data_fails_explicitly(self):
        variants = [event(id=True), event(id='1'), event(object_id=5), event(parent_item_id=None),
                    event(event_date=None), event(event_date='2026-10-20T12:00:00'),
                    event(extra_data={'content': {'note': 'invented shape'}})]
        for key in ('object_type', 'object_id', 'event_type', 'event_date', 'parent_item_id'):
            raw = event(); del raw[key]; variants.append(raw)
        for raw in variants:
            with self.subTest(raw=raw):
                adapter, _ = self.boundary([('/activities', ACTIVITY_QUERY, {'results': [raw], 'next_cursor': None})])
                with self.assertRaisesRegex(HistoryError, 'history /activities page 1'):
                    adapter.activities(stamp(START), stamp(END))

    def test_malformed_completion_time_required_but_creation_nullable(self):
        for changes in ({'completed_at': None}, {'completed_at': 'bad'}, {'added_at': 5}, {'id': 1}):
            with self.subTest(changes=changes):
                adapter, _ = self.boundary([(COMPLETED, COMPLETED_QUERY, {'items': [item(**changes)]})])
                with self.assertRaisesRegex(HistoryError, 'history /tasks/completed'):
                    adapter.completed(stamp(START), stamp(END))

    def test_malformed_current_comment_data(self):
        for changes in ({'posted_at': 'bad'}, {'posted_at': False}, {'id': None},
                        {'is_deleted': 0}, {'content': '\r'}, {'content': {'text': 'bad'}}):
            with self.subTest(changes=changes):
                adapter, _ = self.boundary([('/comments', comments_query('task'),
                    {'results': [comment(**changes)], 'next_cursor': None})])
                with self.assertRaises(HistoryError):
                    adapter.comments('task')

    def test_no_local_result_limit_and_tenth_page_progress_before_failure(self):
        stream = StringIO()
        steps = []
        for n in range(11):
            query = ACTIVITY_QUERY + ([] if n == 0 else [('cursor', f'p{n}.x')])
            result = {'results': [event(n * 200 + j) for j in range(200)],
                      'next_cursor': None if n == 10 else f'p{n+1}.x'}
            steps.append(('/activities', query, result))
        adapter, _ = self.boundary(steps, stream)
        self.assertEqual(len(adapter.activities(stamp(START), stamp(END)).records), 2200)
        self.assertEqual(stream.getvalue(), 'todo: loading report activity: 10 pages\n')
        steps[-1] = ('/activities', ACTIVITY_QUERY + [('cursor', 'p10.x')], {'results': []})
        stream = StringIO()
        adapter, _ = self.boundary(steps, stream)
        with self.assertRaisesRegex(HistoryError, 'page 11.*next_cursor'):
            adapter.activities(stamp(START), stamp(END))
        self.assertEqual(stream.getvalue(), 'todo: loading report activity: 10 pages\n')

    def test_scope_snapshot_and_no_parameter_override(self):
        scope = {'project_id': 'cat'}
        query = [('project_id', 'cat')] + COMPLETED_QUERY
        adapter, http = self.boundary([
            (COMPLETED, query, {'items': [], 'next_cursor': 'a.b'}),
            (COMPLETED, query + [('cursor', 'a.b')], {'items': []})])
        original = http.__call__
        def opener(request, **kw):
            result = original(request, **kw)
            scope['project_id'] = 'other'
            return result
        adapter.transport._opener = opener
        adapter.completed(stamp(START), stamp(END), scope)
        for scope in ({'cursor': 'a.b'}, {'until': END}, {'limit': '1'}):
            with self.assertRaises(HistoryError):
                adapter.completed(stamp(START), stamp(END), scope)

    def test_current_text_separate_from_annotations_for_active_and_archived_steps(self):
        adapter, _ = self.boundary([
            (COMPLETED, COMPLETED_QUERY, {'items': [item('archived', parent_id='task')]}),
            ('/activities', ACTIVITY_QUERY, {'results': [event(parent_item_id='archived')], 'next_cursor': None}),
            ('/comments', comments_query('archived'), {'results': [comment()], 'next_cursor': None}),
            ('/comments', comments_query('task'), {'results': [], 'next_cursor': None}),
            ('/comments', comments_query('open-step'), {'results': [comment('own-open')], 'next_cursor': None})])
        completed = adapter.completed(stamp(START), stamp(END))
        activity = adapter.activities(stamp(START), stamp(END))
        current = {'task': Item('task', 'cat', 'Current task'),
                   'open-step': Item('open-step', 'cat', 'Current step', 'task')}
        result = adapter.required_comments(current, completed, activity)
        self.assertEqual(result.comments['note'].item_id, 'archived')
        self.assertEqual(result.comments['note'].body, 'Current text')
        self.assertEqual(activity.records[0].annotation, 'Observed old text')
        self.assertEqual(result.owners['task'].title, 'Current task')
        self.assertEqual(result.comments['own-open'].item_id, 'open-step')

    def test_unresolved_archived_owner_or_parent_no_all_history_backfill(self):
        for parent in (False, True):
            with self.subTest(parent=parent):
                # Unknown old owner is discovered from a new edit, not preseeded.
                completed_rows = [item('step', parent_id='old-parent')] if parent else []
                owner = 'step' if parent else 'old-owner'
                adapter, _ = self.boundary([
                    (COMPLETED, COMPLETED_QUERY, {'items': completed_rows}),
                    ('/activities', ACTIVITY_QUERY, {'results': [event(parent_item_id=owner)], 'next_cursor': None}),
                    ('/comments', comments_query(owner), {'results': [comment()], 'next_cursor': None})])
                completed = adapter.completed(stamp(START), stamp(END))
                activity = adapter.activities(stamp(START), stamp(END))
                with self.assertRaisesRegex(HistoryError, 'unresolved archived owner/parent ' + ('old-parent' if parent else 'old-owner')):
                    adapter.required_comments({}, completed, activity)

    def test_404_is_incompleteness_not_owner_deletion(self):
        adapter, _ = self.boundary([('/comments', comments_query('old-owner'),
                                   Response(b'{"error":"not found"}', status=404))])
        with self.assertRaisesRegex(HistoryError, 'history /comments.*404'):
            adapter.comments('old-owner')

    def test_fake_rejects_wrong_query(self):
        expected = Expected('/comments', comments_query('step'))
        from urllib.request import Request
        request = Request('https://api.todoist.com/api/v1/comments?item_id=step&limit=200',
                          headers={'Authorization': 'Bearer secret'})
        with self.assertRaisesRegex(AssertionError, 'query drift'):
            expected.check(request, 30)

    def test_mixed_datetime_exact_boundary_inputs_and_integral_fixed_end(self):
        query = [('since', '2026-10-20T12:00:00Z'), ('until', '2026-10-20T12:00:02Z'), ('limit', '200')]
        adapter, _ = self.boundary([(COMPLETED, query, {'items': [item(at='2026-10-20T12:00:01Z'),
                                                                 item(at='2026-10-20T12:00:01.000000001Z')]})])
        end = datetime(2026, 10, 20, 12, 0, 1, tzinfo=timezone.utc)
        result = adapter.completed(stamp(START), end)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(instant_key(result.records[0].occurrence.completed_at), instant_key(end))

    def test_documented_recurring_due_omits_timezone_and_checked_is_not_current_state(self):
        due = {'date': '2026-10-21', 'is_recurring': True, 'lang': 'en', 'string': 'every day'}
        adapter, _ = self.boundary([(COMPLETED, COMPLETED_QUERY,
            {'items': [item(checked=False, due=due, description=None)]})])
        record = adapter.completed(stamp(START), stamp(END)).records[0]
        self.assertFalse(record.item.completed)
        self.assertTrue(record.occurrence.recurring)
        self.assertEqual(record.item.attention.raw_due, due)
        self.assertEqual(record.item.description, '')

    def test_missing_or_malformed_page_records_never_become_empty_history(self):
        for path, query, field in [(COMPLETED, COMPLETED_QUERY, 'items'),
                ('/activities', ACTIVITY_QUERY, 'results'), ('/comments', comments_query('task'), 'results')]:
            for raw in ({'next_cursor': None}, {field: None, 'next_cursor': None},
                        {field: {}, 'next_cursor': None}, {field: [None], 'next_cursor': None}, []):
                with self.subTest(path=path, raw=raw):
                    adapter, _ = self.boundary([(path, query, raw)])
                    with self.assertRaises(HistoryError):
                        if path == COMPLETED:
                            adapter.completed(stamp(START), stamp(END))
                        elif path == '/activities':
                            adapter.activities(stamp(START), stamp(END))
                        else:
                            adapter.comments('task')

    def test_missing_required_comment_timestamp_and_attachment(self):
        for field in ('posted_at', 'file_attachment'):
            raw = comment(); del raw[field]
            adapter, _ = self.boundary([('/comments', comments_query('task'),
                                       {'results': [raw], 'next_cursor': None})])
            with self.assertRaisesRegex(HistoryError, 'missing required ' + field):
                adapter.comments('task')

    def test_no_partial_comment_evidence_on_later_owner_failure(self):
        adapter, _ = self.boundary([
            ('/comments', comments_query('task'), {'results': [comment()], 'next_cursor': None}),
            ('/comments', comments_query('step'), {'results': [], 'next_cursor': 'a.b'}),
            ('/comments', comments_query('step') + [('cursor', 'a.b')], {'results': []})])
        with self.assertRaisesRegex(HistoryError, 'missing required next_cursor'):
            adapter.required_comments({'task': Item('task', 'cat', 'Task'),
                'step': Item('step', 'cat', 'Step', 'task')}, Retrieval((), ()), Retrieval((), ()))

    def test_absent_qualifying_comment_does_not_invent_owner_deletion_or_require_unrelated_owner(self):
        adapter, _ = self.boundary([
            ('/activities', ACTIVITY_QUERY, {'results': [event(parent_item_id='old-owner')], 'next_cursor': None}),
            ('/comments', comments_query('old-owner'), {'results': [comment('unrelated')], 'next_cursor': None})])
        events = adapter.activities(stamp(START), stamp(END))
        result = adapter.required_comments({}, Retrieval((), ()), events)
        self.assertEqual(result.owners, {})
        self.assertEqual(result.comments, {})

    def test_comments_progress_counts_endpoint_pages_across_scoped_owners(self):
        stream = StringIO()
        current = {str(n): Item(str(n), 'cat', 'Task ' + str(n)) for n in range(10)}
        adapter, _ = self.boundary([('/comments', comments_query(owner),
            {'results': [], 'next_cursor': None}) for owner in current], stream)
        result = adapter.required_comments(current, Retrieval((), ()), Retrieval((), ()))
        self.assertEqual(len(result.pages), 10)
        self.assertEqual(stream.getvalue(), 'todo: loading comments: 10 pages\n')

    def test_completed_tenth_page_progress_then_failure(self):
        stream = StringIO()
        steps = [(COMPLETED, COMPLETED_QUERY + ([] if n == 0 else [('cursor', f'p{n}.x')]),
                  {'items': [], 'next_cursor': f'p{n+1}.x'}) for n in range(10)]
        steps.append((COMPLETED, COMPLETED_QUERY + [('cursor', 'p10.x')],
                      {'items': [item(completed_at=None)]}))
        adapter, _ = self.boundary(steps, stream)
        with self.assertRaisesRegex(HistoryError, 'page 11'):
            adapter.completed(stamp(START), stamp(END))
        self.assertEqual(stream.getvalue(), 'todo: loading completed tasks: 10 pages\n')

    def test_composed_evidence_rejects_different_fixed_intervals_before_comments(self):
        adapter, _ = self.boundary([])
        with self.assertRaisesRegex(HistoryError, 'interval mismatch: end'):
            adapter.required_comments({}, Retrieval((), (), stamp(START), stamp(END)),
                Retrieval((), (), stamp(START), stamp(AFTER)))
