"""Real Sync/gateway/workflow boundary, synthetic provider-shaped text.

Raw shapes cite the pinned api-v1.openapi.json components.schemas.ItemSyncView
and NoteSyncView at https://developer.todoist.com/api/v1/ (2026-10-24).
"""
import unittest
from copy import deepcopy
from io import StringIO
from todo_lib import domain as d, presentation as p
from todo_lib.syntax import parse, Cancelled
from todo_lib.workflows.reads import choose, title_candidates, AmbiguityError
from tests.workflows.capture import test_capture as fixtures


class Terminal(StringIO):
    def isatty(self):
        return True


class CoexistenceTests(unittest.TestCase):
    setUp = fixtures.CaptureTests.setUp
    state = fixtures.CaptureTests.state
    seed = fixtures.CaptureTests.seed
    refresh = fixtures.CaptureTests.refresh
    queue_refresh = fixtures.CaptureTests.queue_refresh
    operation = fixtures.CaptureTests.operation
    run_request = fixtures.CaptureTests.run_request

    def duplicates(self):
        self.wire_items[1]['content'] = 'Imported'
        self.wire_items[2]['content'] = 'Imported'

    def test_unrelated_rename_with_duplicates_then_new_collision_refuses(self):
        self.duplicates()
        self.refresh()
        after = deepcopy(self.wire_items)
        after[0]['content'] = 'Unique'
        self.operation('item_update', {'id': 'parent', 'content': 'Unique'}, self.state(items=after), 'parent')
        result = self.run_request(['rename', 'Parent', '--to', 'Unique'])
        self.assertEqual(result.status, 0)
        self.assertEqual([result.snapshot.items[i].title for i in ('precise', 'null')], ['Imported', 'Imported'])
        self.wire_items = after
        self.refresh()
        calls = len(self.http.calls)
        with self.assertRaisesRegex(d.DomainError, 'sibling'):
            self.run_request(['rename', 'Unique', '--to', 'Imported'])
        self.assertTrue(all('commands' not in c for c in self.http.calls[calls:]))
        self.assertEqual(self.store.load_consistent_state().snapshot.items['parent'].title, 'Unique')

    def test_unique_create_with_imported_duplicates_and_batch_refusal(self):
        self.duplicates()
        self.refresh()
        after = self.state(items=self.wire_items + [fixtures.item('new', content='Unique', priority=3)])
        self.operation('item_add', {'project_id': 'cat', 'content': 'Unique', 'priority': 3,
            'description': '', 'labels': [], 'auto_reminder': False, 'due': None}, after)
        result = self.run_request(['add', 'Unique', '--category', 'cat'])
        self.assertEqual(result.status, 0)
        self.wire_items = after['items']
        self.refresh()
        with self.assertRaisesRegex(d.DomainError, 'sibling'):
            self.run_request(['add', 'task', 'cat', '--title', 'New task', 'new task'])

    def test_imported_ambiguity_cancel_and_resolving_rename(self):
        self.duplicates()
        self.seed()
        s = self.store.load_consistent_state().snapshot
        candidates = title_candidates(s, ('Imported',))
        self.assertEqual([i.id for i in candidates], ['null', 'precise'])
        with self.assertRaises(AmbiguityError):
            choose(s, 'Imported', candidates, d.instant_datetime(fixtures.NOW), streams=self.workflow.streams)
        with self.assertRaises(Cancelled):
            choose(s, 'Imported', candidates, d.instant_datetime(fixtures.NOW),
                   streams=p.OriginalStreams(Terminal('q\n'), Terminal(), StringIO()))
        self.workflow.streams = p.OriginalStreams(Terminal('1\n'), Terminal(), StringIO())
        self.refresh()
        after = deepcopy(self.wire_items)
        after[2]['content'] = 'Resolved'
        self.operation('item_update', {'id': 'null', 'content': 'Resolved'}, self.state(items=after), 'null')
        result = self.run_request(['rename', 'Imported', '--to', 'Resolved'])
        self.assertEqual(result.snapshot.items['null'].title, 'Resolved')

    def test_inactive_unhide_preserves_literal_and_reports_real_mutation(self):
        literal = '[todo waiting]\r\nwhy\r\n[/todo waiting]\r\nextra'
        self.wire_items[0].update(content='Parent\\name\r\nline\ttab', labels=['waiting'], description=literal)
        self.refresh()
        after = deepcopy(self.wire_items)
        after[0]['labels'] = []
        self.operation('item_update', {'id': 'parent', 'labels': []}, self.state(items=after), 'parent')
        result = self.run_request(['unhide', 'Parent'])
        self.assertEqual(result.status, 0)
        self.assertIn('Hiding: inactive -> off', result.document.stdout)
        self.assertIn(r'Parent\\name\nline\ttab', result.document.stdout)
        self.assertEqual(result.snapshot.items['parent'].description, literal.replace('\r\n', '\n'))

    def test_unsafe_reason_rewrite_refuses_before_any_command(self):
        self.wire_items[0].update(description='[todo waiting]', labels=['waiting'])
        self.refresh()
        with self.assertRaisesRegex(d.DomainError, 'Parent.*unsafe'):
            self.run_request(['hide', 'Parent', '--due', 'tomorrow', '--reason', 'why'])
        self.assertTrue(all('commands' not in call for call in self.http.calls))

    def test_external_category_rename_and_hidden_schedule_preserve_literal_text(self):
        self.wire_items[0].update(labels=['waiting'], description='[todo waiting]')
        projects = [fixtures.project('root', None), fixtures.project(name='Later')]
        self.refresh(self.state(projects=projects))
        after = deepcopy(self.wire_items)
        after[0]['due'] = fixtures.due('2026-10-23T10:00:00Z', timezone='UTC')
        self.operation('item_update', {'id': 'parent', 'due': {
            'date': '2026-10-23T10:00:00Z', 'lang': 'en'}},
            self.state(items=after, projects=projects), 'parent')
        result = self.run_request(['schedule', 'Parent', '--at', 'tomorrow 10'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertIn('Hiding: inactive -> on', result.document.stdout)
        self.assertEqual(result.snapshot.items['parent'].description, '[todo waiting]')
        self.assertEqual(d.now_queue(result.snapshot, d.instant_datetime(fixtures.NOW), ['Later']), ())
        self.assertIn('Parent', p.render_now(result.snapshot, d.instant_datetime(fixtures.NOW),
                      all_items=True, hidden_names=['Later']).stdout)

    def test_adapter_crlf_blank_comment_and_forbidden_controls(self):
        raw = fixtures.item('parent', content='A\r\nB\tC', description=' \r\n\t')
        from tests.adapter.current.test_current import note
        self.http.read(self.state(items=[raw], notes=[note(item_id='parent', content='\r\n\t')]))
        self.http.read(fixtures.delta())
        actual = fixtures.retrieve(self.http, d.Binding('u', 'root', frozenset({'cat'})))
        self.assertEqual(actual.snapshot.items['parent'].title, 'A\nB\tC')
        self.assertEqual(actual.snapshot.items['parent'].description, '')
        self.assertEqual(next(iter(actual.snapshot.comments.values())).body, '\n\t')
        for value in ('A\rB', '\x1b', '\x00', 5):
            self.http.read(self.state(items=[fixtures.item('parent', content=value)]))
            self.http.read(fixtures.delta())
            with self.assertRaises(d.DomainError):
                fixtures.retrieve(self.http, d.Binding('u', 'root', frozenset({'cat'})))
