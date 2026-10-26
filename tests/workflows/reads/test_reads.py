"""Public reads composed with persisted state, actual adapters and documents.

Provider-shaped synthetic refresh fixtures reuse the strict HTTP boundary. The
pinned Sync tag and ItemSyncView/NoteSyncView in api-v1.openapi.json establish
nullable creation/posted times and parent IDs; no provider discovery is invented.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from todo_lib import domain as d
from todo_lib import presentation as p
from todo_lib.adapter.transport import Transport
from todo_lib.local import (StateStore, LocalError, History, empty_history,
                            prepare_candidates, exclusive_lock)
from todo_lib.local.codec import loads
from todo_lib.syntax import parse, Cancelled
from todo_lib.workflows import Synchronizer, SyncError
from todo_lib.workflows.reads import (ReadWorkflow, execute, title_candidates,
    select_child, select_title, choose, matches, move_destination_candidates,
    recent_candidates, deletion_candidates, NoMatch, AmbiguityError)
from tests.adapter.current.test_current import RESOURCES, full, delta, item, note
from tests.adapter.history.test_history import Expected
from tests.support.http import ControlledHTTP, ExpectedRequest, Response


NOW = d.instant_from_wire('2026-10-22T12:00:00.123456789012350Z')
CURSOR = d.instant_from_wire('2026-10-20T00:00:00Z')
OLD = d.instant_from_wire('2026-10-21T12:00:00.123456789012348Z')
NEW = d.instant_from_wire('2026-10-21T12:00:00.123456789012349Z')


class Terminal(StringIO):
    def isatty(self):
        return True


class ReadsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / '.todo'
        self.root.mkdir(mode=0o700)
        self.store = StateStore(self.root)
        self.config()
        self.snapshot = d.Snapshot(d.Binding('u', 'root', frozenset({'cat', 'hidden', 'empty'})),
            d.Account('u', 'UTC'), d.Project('root', 'root'),
            {'cat': d.Category('cat', 'Work', 'root'),
             'hidden': d.Category('hidden', 'Later', 'root'),
             'empty': d.Category('empty', 'Alpha', 'root')},
            {'A': d.Item('A', 'cat', 'Root'),
             'B': d.Item('B', 'cat', 'Branch', parent_id='A'),
             'C': d.Item('C', 'cat', 'Leaf', parent_id='B'),
             'D': d.Item('D', 'cat', 'Unmatched sibling', parent_id='A'),
             'H': d.Item('H', 'hidden', 'Hidden task'),
             'J': d.Item('J', 'hidden', 'Hidden child', parent_id='H')},
            {'deep': d.Comment('deep', 'C', 'Needle haystack', NEW)})
        self.publish(self.snapshot)
        self.http = ControlledHTTP([])
        self.addCleanup(self.http.assert_done)
        self.streams = p.OriginalStreams(StringIO(), StringIO(), StringIO())
        self.sync = Synchronizer(Transport('secret', opener=self.http), self.store, clock=lambda: NOW)
        self.workflow = ReadWorkflow(self.sync, streams=self.streams)

    def config(self, hidden='Later'):
        self.put('config', ('[main]\nproject=root\ndefault_sections=Work\nhidden_from_now=' + hidden + '\n').encode())

    def put(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        path.chmod(0o600)

    def publish(self, snapshot, history=None, *, synced_at=NOW):
        with exclusive_lock('test', self.root):
            self.store.publish_snapshot(prepare_candidates(snapshot,
                history or empty_history(snapshot), account_display='Person',
                sync_token='full-token', synced_at=synced_at, initial_cursor=None if (self.root / 'binding.json').exists() else CURSOR))

    def edit(self, **items):
        self.snapshot = replace(self.snapshot, items={**self.snapshot.items, **items})
        self.publish(self.snapshot)

    def read(self, *args, **kwargs):
        return self.workflow.execute(list(args), **kwargs)

    def wire(self, token, response):
        self.http.steps.append((ExpectedRequest('POST', '/sync', 'secret', form={
            'sync_token': token, 'resource_types': RESOURCES}),
            response if isinstance(response, Exception) else Response(json.dumps(response).encode())))

    def seed_wire_tree(self):
        # Start with a provider-observed tree, then let refresh discover completion.
        self.config('')
        self.wire('*', full(items=[item('A', content='Root'),
                                   item('B', parent_id='A', content='Finished branch')]))
        self.wire('full-token', delta())
        from todo_lib.adapter.current import retrieve
        observed = retrieve(self.sync.transport, d.Binding('u', 'root', frozenset({'cat'})))
        self.snapshot = observed.snapshot
        self.publish(observed.snapshot, synced_at=CURSOR)

    def discover_completed_branch(self):
        self.seed_wire_tree()
        self.wire('full-token', full(items=[item('A', content='Root')]))
        self.wire('full-token', delta())
        query = [('project_id', 'cat'), ('since', '2026-10-20T00:00:00Z'),
                 ('until', '2026-10-22T12:00:01Z'), ('limit', '200')]
        self.http.steps.append((Expected('/tasks/completed/by_completion_date', query),
            Response(json.dumps({'items': [item('B', content='Finished branch', parent_id='A',
                checked=True, completed_at=d.instant_text(NEW))]}).encode())))
        self.http.steps.append((Expected('/comments', [('task_id', 'B'), ('limit', '200')]),
            Response(json.dumps({'results': [{'id': 'survivor', 'content': 'Retained owner comment',
                'posted_at': d.instant_text(OLD), 'is_deleted': False, 'file_attachment': None}],
                'next_cursor': None}).encode())))
        self.read('task', '--refresh', 'Root')

    def test_all_public_reads_are_cache_first_and_do_not_mutate(self):
        before = {path.name: path.read_bytes() for path in self.root.iterdir()}
        cases = [([], 'Root'), (['now', '--all'], 'Hidden child'),
                 (['waiting'], 'No waiting items.'), (['someday'], 'Hidden child'),
                 (['task', 'Root'], 'Leaf'), (['step', 'Leaf'], 'Root > Branch'),
                 (['comment', 'Leaf'], 'Needle haystack'),
                 (['search', 'needle'], 'Leaf'), (['category'], 'Alpha\nLater\nWork'),
                 (['Leaf'], 'Needle haystack')]
        for argv, expected in cases:
            with self.subTest(argv=argv):
                self.assertIn(expected, self.read(*argv).document.stdout)
        self.assertEqual(self.http.requests, [])
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.root.iterdir()})

    def test_matching_normalizes_unicode_and_preserves_argument_boundaries(self):
        self.assertTrue(matches('CAFÉ Straße', ('cafe\u0301', 'STRASSE')))
        self.assertFalse(matches('CAFÉ', ('cafe',)))
        self.assertTrue(matches('red very blue', ('blue', 'red')))
        self.assertFalse(matches('red very blue', ('red blue',)))
        self.edit(T=d.Item('T', 'cat', '--task'))
        self.assertEqual(self.read('--literal', '--task').selected.id, 'T')

    def test_no_exact_title_precedence_and_noninteractive_ambiguity(self):
        self.edit(X=d.Item('X', 'cat', 'Root extension'))
        with self.assertRaises(AmbiguityError) as caught:
            self.read('task', 'Root')
        error = caught.exception
        self.assertEqual({i.id for i in error.candidates}, {'A', 'X'})
        self.assertIn('1. task: Root  due:none — Work', error.document.stdout)
        self.assertNotIn('Select ', error.document.stdout)
        self.assertNotIn('Description', error.document.stdout)
        self.assertEqual(self.streams.stdout.getvalue(), '')
        self.assertEqual(error.status, 1)

    def test_task_and_deep_step_compete_with_identical_interactive_candidates(self):
        self.edit(X=d.Item('X', 'cat', 'Leaf plan'))
        self.put('config', (self.root / 'config').read_bytes() + b'\n[colors]\nbase01=#123456\n')
        plain = ('Multiple items match "Leaf":\n'
                 '  1. task: Leaf plan  due:none — Work\n'
                 '  2. step: Leaf  due:none — Root > Branch — Work')
        colored = plain.replace(' — Root > Branch',
                                '\x1b[38;2;18;52;86m — Root > Branch\x1b[0m')
        cases = [('auto', {'TERM': 'xterm'}, True),
                 ('auto', {'TERM': 'xterm', 'NO_COLOR': ''}, False),
                 ('auto', {'TERM': 'dumb'}, False),
                 ('always', {'TERM': 'dumb', 'NO_COLOR': ''}, True),
                 ('never', {'TERM': 'xterm'}, False)]
        for mode, env, enabled in cases:
            with self.subTest(mode=mode, env=env), patch.dict(os.environ, env, clear=True):
                argv = ['--color', mode, 'Leaf']
                # Only stdin differs: both choosers render against original TTY
                # stdout. A pipe legitimately gets different auto-color output.
                noninteractive = p.OriginalStreams(StringIO(), Terminal(), Terminal())
                with self.assertRaises(AmbiguityError) as caught:
                    ReadWorkflow(self.sync, streams=noninteractive).execute(argv)
                doc = caught.exception.document
                self.assertEqual([i.id for i in caught.exception.candidates], ['X', 'C'])
                self.assertEqual(doc.stdout, colored if enabled else plain)
                self.assertEqual(noninteractive.stdout.getvalue(), '')
                self.assertEqual(noninteractive.stderr.getvalue(), '')
                terminal = p.OriginalStreams(Terminal('99\n0\nx\n1\n'), Terminal(), Terminal())
                result = ReadWorkflow(self.sync, streams=terminal).execute(argv)
                self.assertEqual(terminal.stdout.getvalue().split('Select ')[0].rstrip('\n'), doc.stdout)
                self.assertEqual(terminal.stderr.getvalue().count('Enter a number from 1-2, or q.'), 3)
                self.assertEqual(result.selected.id, 'X')
                self.assertIn('Leaf plan', result.document.stdout)
                with self.assertRaises(AmbiguityError) as piped:
                    self.read(*argv)
                self.assertEqual(piped.exception.document.stdout, colored if mode == 'always' else plain)
        self.assertEqual(self.http.requests, [])

    def test_interactive_cancel_blank_q_and_eof(self):
        self.edit(X=d.Item('X', 'cat', 'Root extension'))
        for text in ('q\n', '\n', ''):
            streams = p.OriginalStreams(Terminal(text), Terminal(), Terminal())
            with self.assertRaises(Cancelled):
                ReadWorkflow(self.sync, streams=streams).execute(['Root'])

    def test_nested_parent_alias_resolves_parent_across_tasks_and_steps(self):
        snapshot = self.sync.read_local().snapshot
        self.assertEqual(select_child(snapshot, ('Branch',), ('Leaf',), NOW,
                                      streams=self.streams).id, 'C')
        with self.assertRaises(NoMatch):
            select_child(snapshot, ('Root',), ('Leaf',), NOW, streams=self.streams)
        self.edit(X=d.Item('X', 'cat', 'Branch plan'))
        snapshot = self.sync.read_local().snapshot
        with self.assertRaises(AmbiguityError) as caught:
            select_child(snapshot, ('Branch',), ('Leaf',), NOW, streams=self.streams)
        self.assertEqual({i.id for i in caught.exception.candidates}, {'B', 'X'})
        n = next(n for n, i in enumerate(caught.exception.candidates, 1) if i.id == 'B')
        streams = p.OriginalStreams(Terminal(str(n) + '\n'), Terminal(), Terminal())
        self.assertEqual(select_child(snapshot, ('Branch',), ('Leaf',), NOW, streams=streams).id, 'C')
        # Exercise the parsed parent/direct-child alias through the public workflow.
        request = replace(parse(['step', 'Leaf']), parent=('Branch',))
        streams = p.OriginalStreams(Terminal(str(n) + '\n'), Terminal(), Terminal())
        self.assertEqual(ReadWorkflow(self.sync, streams=streams).execute(request).selected.id, 'C')

    def test_search_one_whole_field_own_comments_and_context_union(self):
        self.edit(B=replace(self.snapshot.items['B'], description='haystack'),
                  C=replace(self.snapshot.items['C'], description='other'))
        # Neither title+description nor two separate comments may combine terms.
        snapshot = replace(self.snapshot, comments={**self.snapshot.comments,
            'one': d.Comment('one', 'D', 'split'), 'two': d.Comment('two', 'D', 'query')})
        self.publish(snapshot)
        for query in [('Branch', 'haystack'), ('split', 'query')]:
            self.assertEqual(self.read('search', *query).document.stdout, 'No matches.')
        text = self.read('search', 'needle').document.stdout
        for title in ('Root', 'Branch', 'Leaf'):
            self.assertEqual(text.count(title), 1)
        self.assertNotIn('Unmatched sibling', text)
        self.assertNotIn('Needle haystack', text)  # Titles only, no excerpts.
        self.assertNotIn('Leaf', self.read('search', 'Root').document.stdout)
        self.assertEqual(self.read('search', 'need hay').document.stdout, 'No matches.')

    def test_search_all_empty_coverage_and_retained_stable_id_merge(self):
        completed = replace(self.snapshot.items['D'], completed=True, completed_at=NEW)
        history = History(replace(self.snapshot, items={**self.snapshot.items, 'D': completed}))
        current = replace(self.snapshot, items={k: v for k, v in self.snapshot.items.items() if k != 'D'})
        self.publish(current, history)
        self.assertEqual(self.read('search', 'Unmatched').document.stdout, 'No matches.')
        result = self.read('search', '--all', 'Unmatched')
        self.assertEqual(result.document.stdout.count('Unmatched sibling'), 1)
        self.assertIn('[x]', result.document.stdout)
        self.assertIn('earliest retained completion:', result.document.stderr)
        empty = self.read('search', '--all', 'absent').document
        self.assertEqual(empty.stdout, 'No matches in open or retained completed items.')
        self.assertIn('coverage may be incomplete', empty.stderr)
        for argv in (['step', 'Unmatched'], ['Unmatched']):
            with self.assertRaises(NoMatch):
                self.read(*argv)
        self.publish(replace(current, items={}, comments={}))
        self.assertIn('earliest retained completion: none', self.read('search', '--all', 'absent').document.stderr)

    def test_recursive_inspection_retains_exact_sibling_and_comment_order_after_reload(self):
        items = {**self.snapshot.items,
            'a-old': d.Item('a-old', 'cat', 'Older', parent_id='B', added_at=OLD,
                            completed=True, completed_at=NEW),
            'z-new': d.Item('z-new', 'cat', 'Newer', parent_id='B', added_at=NEW,
                            completed=True, completed_at=NEW),
            '0-null': d.Item('0-null', 'cat', 'Unknown', parent_id='B'),
            'nested': d.Item('nested', 'cat', 'Below unknown', parent_id='0-null')}
        comments = {'z-old': d.Comment('z-old', 'a-old', 'First owner comment', OLD),
                    'a-new': d.Comment('a-new', 'a-old', 'Second owner comment', NEW),
                    'own': d.Comment('own', 'A', 'Root comment', OLD)}
        history = History(replace(self.snapshot, items=items, comments=comments))
        current = replace(self.snapshot, comments={'own': comments['own']})
        self.publish(current, history)
        result = self.read('task', 'Root')
        text = result.document.stdout
        self.assertLess(text.index('Newer'), text.index('Older'))
        self.assertLess(text.index('Older'), text.index('Unknown'))
        self.assertLess(text.index('Unknown'), text.index('Below unknown'))
        self.assertLess(text.index('First owner comment'), text.index('Second owner comment'))
        self.assertIn('added unknown', text)
        self.assertIn('added 2026-10-21 12:00', text)
        self.assertEqual(text.count('Root comment'), 1)
        self.assertEqual(text.count('First owner comment'), 1)
        self.assertIn('coverage may be incomplete', result.document.stderr)
        self.assertEqual(d.instant_text(result.snapshot.items['z-new'].added_at), d.instant_text(NEW))
        self.assertEqual(self.http.requests, [])

    def test_discovered_completion_and_own_comment_are_readable_after_restart(self):
        self.discover_completed_branch()
        calls = len(self.http.requests)
        fresh = ReadWorkflow(Synchronizer(self.sync.transport, StateStore(self.root), clock=lambda: NOW), streams=self.streams)
        detail = fresh.execute(['Root']).document
        self.assertIn('[x] P1 Finished branch', detail.stdout)
        self.assertEqual(detail.stdout.count('Retained owner comment'), 1)
        self.assertIn('coverage may be incomplete', detail.stderr)
        self.assertIn('Finished branch', fresh.execute(['search', '--all', 'Retained']).document.stdout)
        self.assertEqual(fresh.execute(['search', 'Retained']).document.stdout, 'No matches.')
        with self.assertRaises(NoMatch):
            fresh.execute(['step', 'Finished branch'])
        self.assertEqual(len(self.http.requests), calls)

    def test_search_hierarchy_order_ignores_attention_and_context_is_shared_once(self):
        self.edit(A=replace(self.snapshot.items['A'], title='Needle root', priority=3),
                  B=replace(self.snapshot.items['B'], title='Needle branch', priority=3),
                  C=replace(self.snapshot.items['C'], title='Needle leaf', priority=1),
                  D=replace(self.snapshot.items['D'], title='Needle sibling', priority=1),
                  X=d.Item('X', 'cat', 'Needle top', priority=1),
                  Z=d.Item('Z', 'cat', 'Needle middle', priority=2))
        text = self.read('search', 'needle').document.stdout
        self.assertLess(text.index('Needle top'), text.index('Needle middle'))
        self.assertLess(text.index('Needle middle'), text.index('Needle root'))
        self.assertLess(text.index('Needle sibling'), text.index('Needle branch'))
        self.assertLess(text.index('Needle branch'), text.index('Needle leaf'))
        self.assertEqual(text.count('Needle root'), 1)

    def test_step_detail_preserves_inherited_waiting_and_owner_comments(self):
        attention = d.parse_attention('2026-10-25', d.instant_datetime(NOW), 'UTC')
        self.edit(A=replace(self.snapshot.items['A'], labels=frozenset({'waiting'}), attention=attention,
                  description=d.with_waiting_reason('', 'Waiting for approval')))
        detail = self.read('step', 'Leaf').document
        self.assertIn('Root > Branch', detail.stdout)
        self.assertIn('Inherited from Root: Waiting for approval', detail.stdout)
        self.assertIn('Needle haystack', detail.stdout)
        self.assertIn('Steps: none', detail.stdout)
        self.assertIn('coverage may be incomplete', detail.stderr)
        self.assertNotIn('Needle haystack', self.read('comment', 'Root').document.stdout)
        self.assertIn('Root', self.read('search', 'approval').document.stdout)
        self.assertNotIn('Leaf', self.read('search', 'approval').document.stdout)

    def test_waiting_own_hidden_ancestor_union_and_arrived_day(self):
        attention = d.parse_attention('2026-10-25', d.instant_datetime(NOW), 'UTC')
        self.edit(A=replace(self.snapshot.items['A'], labels=frozenset({'waiting'}), attention=attention),
                  C=replace(self.snapshot.items['C'], labels=frozenset({'waiting'}), attention=attention))
        text = self.read('waiting').document.stdout
        self.assertEqual(text.count('Root'), 1)
        self.assertIn('Branch  [context]', text)
        self.assertIn('Leaf  until:2026-10-25', text)
        self.assertNotIn('Unmatched', text)
        self.assertNotIn('Hidden', text)
        self.assertNotIn('()', text)
        self.sync.clock = lambda: datetime(2026, 10, 25, tzinfo=timezone.utc)
        self.assertEqual(self.read('waiting').document.stdout, 'No waiting items.')
        self.assertEqual(self.http.requests, [])

    def test_someday_all_hidden_categories_hierarchy_and_explicit_empty_setting(self):
        self.config('Later, Work')
        text = self.read('someday').document.stdout
        self.assertIn('      [ ] P2 Leaf', text)
        self.assertIn('Hidden child', text)
        self.config('')
        self.assertEqual(self.read('someday').document.stdout, 'No someday items.')
        self.assertIn('Hidden child', self.read('now').document.stdout)

    def test_now_all_flat_rows_reasons_category_scope_and_invalid_state(self):
        due = d.parse_attention('2026-10-25', d.instant_datetime(NOW), 'UTC')
        self.edit(B=replace(self.snapshot.items['B'], labels=frozenset({'waiting'}), attention=due,
                            description=d.with_waiting_reason('', 'Blocked by review')))
        normal = self.read('now').document.stdout
        self.assertNotIn('Branch', normal)
        self.assertNotIn('Leaf', normal)
        text = self.read('now', '--all').document.stdout
        self.assertIn('Blocked by review', text)
        self.assertIn('Leaf — Root > Branch', text)
        self.assertNotIn('Hidden until:', text)
        self.assertNotIn('Reason:', text)
        self.assertIn('NEXT 7 DAYS (1)', text)
        self.assertEqual(self.read('now', '--category', 'alpha').document.stdout, 'No actionable items.')
        self.assertNotIn('Hidden child', self.read('now', '--all', '--category', 'wOrK').document.stdout)
        with self.assertRaises(d.DomainError):
            self.read('now', '--category', 'missing')
        self.config('Work')  # Existing attention is invalid in a hidden category.
        with self.assertRaises(d.DomainError):
            self.read('now', '--all')

    def test_full_second_before_equal_after_due_all_read_timing_without_http(self):
        due = d.parse_attention('2026-10-22T12:00:00+00:00', d.instant_datetime(NOW), 'UTC')
        self.edit(A=replace(self.snapshot.items['A'], attention=due),
                  X=d.Item('X', 'cat', 'Root extension', attention=due))
        for second, expected in ((-1, '<1m left'), (0, 'now'), (1, '<1m overdue')):
            self.sync.clock = lambda second=second: datetime(2026, 10, 22, 12, tzinfo=timezone.utc) + timedelta(seconds=second)
            for argv in (['now'], ['now', '--all'], ['task', 'Root extension'], ['Root extension']):
                with self.subTest(second=second, argv=argv):
                    self.assertIn(expected, self.read(*argv).document.stdout)
            with self.assertRaises(AmbiguityError) as caught:
                self.read('Root')
            self.assertEqual(caught.exception.document.stdout.count(expected), 2)
        self.assertEqual(self.http.requests, [])

    def test_implicit_complete_query_and_corrupt_cache_preserve_actual_cause(self):
        with self.assertRaises(NoMatch) as caught:
            self.read('schedle', 'some phrase', 'tail')
        self.assertIn('"schedle" "some phrase" "tail"', str(caught.exception))
        self.put('cache.json', b'{corrupt')
        for argv in (['schedle', 'tail'], ['search', 'missing'], ['now', '--all']):
            with self.assertRaises(LocalError) as caught:
                self.read(*argv)
            self.assertNotIn('no matching', str(caught.exception))
        self.assertEqual(self.http.requests, [])
        self.assertEqual(self.streams.stdout.getvalue(), '')

    def test_typed_move_destinations_and_lifecycle_precise_eligibility(self):
        self.edit(X=d.Item('X', 'cat', 'Work extension'))
        snapshot = self.sync.read_local().snapshot
        self.assertEqual([i.id for i in move_destination_candidates(snapshot, ('Work',))], ['cat', 'X'])
        self.assertEqual([i.id for i in move_destination_candidates(snapshot, ('Branch',), kind='parent')], ['B'])
        self.assertEqual(move_destination_candidates(snapshot, ('',), kind='promotion'), ())
        recurring = d.parse_attention('2026-10-25', d.instant_datetime(NOW), 'UTC')
        recurring = replace(recurring, recurring=True, rule='every day')
        snapshot = replace(snapshot, items={**snapshot.items,
            'R': d.Item('R', 'cat', 'Repeat', attention=recurring),
            'F': d.Item('F', 'cat', 'Finished', completed=True, completed_at=NEW)},
            occurrences={'old': d.Occurrence('old', 'R', OLD, recurring=True),
                         'new': d.Occurrence('new', 'R', NEW, recurring=True)})
        candidates = recent_candidates(snapshot, ('Repeat',), CURSOR, NOW)
        self.assertEqual([(c.item_id, c.occurrence_id) for c in candidates], [('R', 'new')])
        self.assertEqual(recent_candidates(snapshot, ('Finished',), NEW, NOW), ())
        self.assertEqual([c.item_id for c in recent_candidates(snapshot, ('Finished',), OLD, NEW)], ['F'])
        self.assertEqual(recent_candidates(snapshot, ('Repeat',), CURSOR, NOW, operation='delete'), ())
        self.assertEqual([c.item_id for c in deletion_candidates(snapshot, ('Finished',), CURSOR, NOW)], ['F'])
        self.assertEqual(title_candidates(snapshot, ('Finished',)), ())

    def test_shared_chooser_displays_typed_destination_and_completion_context(self):
        self.edit(X=d.Item('X', 'cat', 'Work extension'))
        snapshot = self.sync.read_local().snapshot
        candidates = move_destination_candidates(snapshot, ('Work',))
        with self.assertRaises(AmbiguityError) as caught:
            choose(snapshot, ('Work',), candidates, NOW, streams=self.streams)
        self.assertIn('1. category: Work', caught.exception.document.stdout)
        self.assertIn('2. task: Work extension', caught.exception.document.stdout)
        snapshot = replace(snapshot, items={**snapshot.items,
            'B': replace(snapshot.items['B'], completed=True, completed_at=NEW),
            'C': replace(snapshot.items['C'], completed=True, completed_at=NEW),
            'D': replace(snapshot.items['D'], title='Branch finished', completed=True, completed_at=OLD)})
        candidates = recent_candidates(snapshot, ('Branch',), CURSOR, NOW)
        with self.assertRaises(AmbiguityError) as caught:
            choose(snapshot, ('Branch',), candidates, NOW, streams=self.streams)
        self.assertEqual(caught.exception.document.stdout.count(' — completed Wed 21 Oct 2026, 12:00:00'), 2)
        self.assertIn('step: Branch  due:none — Root — Work', caught.exception.document.stdout)
        self.assertLess(d.instant_key(candidates[0].completed_at), d.instant_key(candidates[1].completed_at))

    def test_refresh_uses_actual_adapter_and_authoritative_timezone(self):
        self.seed_wire_tree()
        self.wire('full-token', delta(user={'id': 'u', 'tz_info': {'timezone': 'Pacific/Auckland'}},
                                      items=[item('A', content='Changed root')]))
        result = self.read('task', '--refresh', 'Changed root')
        self.assertEqual(result.snapshot.account.timezone, 'Pacific/Auckland')
        self.assertEqual(result.selected.title, 'Changed root')
        self.assertEqual(len(self.http.requests), 3)
        text = self.read('now').document.stdout
        self.assertIn('Changed root', text)
        self.assertIn('01:00 Pacific/Auckland', text)
        self.assertEqual(len(self.http.requests), 3)

    def test_refresh_failure_no_normal_output_and_older_coherent_snapshot_still_readable(self):
        self.seed_wire_tree()
        before = {name: (self.root / name).read_bytes() for name in ('cache.json', 'history.json', 'binding.json')}
        # Malformed required task field is an adapter mapping failure.
        self.wire('full-token', delta(items=[{'id': 'bad'}]))
        with self.assertRaises(SyncError):
            self.read('Root', '--refresh', deliver=True)
        self.assertEqual(self.streams.stdout.getvalue(), '')
        self.assertEqual(before, {name: (self.root / name).read_bytes() for name in before})
        calls = len(self.http.requests)
        result = self.read('Root')
        self.assertIn('older than 24 hours', result.document.stderr)
        self.assertEqual(len(self.http.requests), calls)

    def test_actual_mixed_publication_refused_offline_without_partial_results(self):
        self.discover_completed_branch()
        before = {name: (self.root / name).read_bytes() for name in ('history.json', 'binding.json', 'report-cursor')}
        self.wire('delta-token', delta(items=[item('A', content='Changed root')]))
        real_replace = os.replace

        def fail_history(source, destination):
            if Path(destination).name == 'history.json':
                raise OSError('controlled history publication failure')
            return real_replace(source, destination)

        with patch('todo_lib.local.safety.os.replace', side_effect=fail_history):
            with self.assertRaises(SyncError) as caught:
                self.read('now', '--refresh', deliver=True)
        self.assertTrue(caught.exception.publication_started)
        self.assertIn('may be unusable', str(caught.exception))
        self.assertEqual(caught.exception.remote_outcome, 'unattempted')
        self.assertEqual(before, {name: (self.root / name).read_bytes() for name in before})
        retained = loads(before['history.json'])['snapshot']
        self.assertEqual(retained['items']['B']['completed_at'], d.instant_text(NEW))
        self.assertEqual(retained['comments']['survivor']['added_at'], d.instant_text(OLD))
        self.assertEqual(loads((self.root / 'cache.json').read_bytes())['snapshot']['items']['A']['title'], 'Changed root')
        calls = len(self.http.requests)
        fresh = ReadWorkflow(Synchronizer(self.sync.transport, StateStore(self.root), clock=lambda: NOW), streams=self.streams)
        for argv in (['Root'], ['search', '--all', 'Root'], ['now']):
            with self.assertRaises(LocalError) as caught:
                fresh.execute(argv, deliver=True)
            self.assertIn('mixed', str(caught.exception))
        self.assertEqual(self.streams.stdout.getvalue(), '')
        self.assertEqual(len(self.http.requests), calls)

    def test_delivery_uses_complete_document_and_correct_view_kind(self):
        with patch('todo_lib.workflows.reads.p.deliver') as deliver:
            result = execute(['now'], self.sync, streams=self.streams, deliver=True)
        self.assertEqual(deliver.call_args.args[0], result.document)
        self.assertEqual(deliver.call_args.kwargs['view_kind'], 'now')
        with patch('todo_lib.workflows.reads.p.deliver') as deliver:
            execute(['Leaf'], self.sync, streams=self.streams, deliver=True)
        self.assertEqual(deliver.call_args.kwargs['view_kind'], 'step')


if __name__ == '__main__':
    unittest.main()
