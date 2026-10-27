"""Canonical grammar -> real gateway/current adapter -> independently supplied state.

Synthetic fixtures use the retained Sync/Tasks/Reminders contract, not an emulator.
Commands reject wrong fields and ordering. Reads omit optional description/unknown
fields and preserve nullable/precise creation values through real publication.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID

from todo_lib import domain as d, presentation as p
from todo_lib.adapter.commands import Gateway
from todo_lib.adapter.current import retrieve
from todo_lib.adapter.transport import Replay, Transport, HTTPFailure
from todo_lib.local import LocalError, StateStore, prepare_candidates, empty_history, exclusive_lock
from todo_lib.syntax import parse, UsageError
from todo_lib.workflows.sync import Synchronizer, SyncError
from todo_lib.workflows.capture import CaptureWorkflow
from todo_lib.workflows.reads import NoMatch, AmbiguityError
from tests.adapter.current.test_current import full, delta, item, reminder, project, RESOURCES
from tests.support.http import ControlledHTTP, ExpectedRequest, Response
from tests.workflows.lifecycle.test_lifecycle import CommandRequest

NOW = d.instant_from_wire('2026-10-22T12:00:00.123456789012350Z')
PRECISE = '2026-10-20T12:00:00.123456789012349Z'


def due(value, **kwargs):
    return dict(dict(date=value, timezone='UTC' if value.endswith('Z') else None, string='input', lang='en', is_recurring=False), **kwargs)


class Boundary:
    """Scripted responses never derive normalized state from outgoing requests."""
    def __init__(self, case):
        self.case, self.steps, self.calls = case, [], []

    def read(self, response, resources=RESOURCES):
        self.steps.append(('read', resources, deepcopy(response)))

    def completed(self, records=()):
        self.steps.append(('get', '/tasks/completed/by_completion_date', {'items': list(records)}))

    def comments(self, owner):
        self.steps.append(('get', ('/comments', owner), {'results': [], 'next_cursor': None}))

    def command(self, kind, args, identity='new', status='ok'):
        self.steps.append(('command', (kind, args), (identity, status)))

    def request(self, method, path, **kwargs):
        if method == 'GET':
            kind, expected, response = self.steps.pop(0)
            expected_owner = None
            if isinstance(expected, tuple):
                expected, expected_owner = expected
            self.case.assertEqual((kind, path), ('get', expected))
            self.case.assertEqual(kwargs['replay'], Replay.READ)
            if path == '/comments':
                self.case.assertEqual(dict(kwargs['query'])['task_id'], expected_owner)
            else:
                self.case.assertEqual(dict(kwargs['query'])['project_id'], 'cat')
            self.case.assertEqual(dict(kwargs['query'])['limit'], '200')
            return deepcopy(response)
        self.case.assertEqual((method, path), ('POST', '/sync'))
        self.case.assertTrue(self.steps, 'unexpected HTTP request')
        kind, expected, response = self.steps.pop(0)
        form = kwargs['form']
        self.calls.append(deepcopy(form))
        if kind == 'read':
            self.case.assertEqual(kwargs['replay'], Replay.READ)
            self.case.assertEqual(set(form), {'sync_token', 'resource_types'})
            self.case.assertEqual(form['resource_types'], expected)
            self.case.assertIsInstance(form['sync_token'], str)
            if isinstance(response, Exception):
                raise response
            return response
        self.case.assertEqual(kwargs['replay'], Replay.IDEMPOTENT)
        commands = json.loads(form['commands'])
        self.case.assertEqual(len(commands), 1)
        command = commands[0]
        self.case.assertEqual((command['type'], command['args']), expected)
        self.case.assertEqual(str(UUID(command['uuid'])), command['uuid'])
        self.case.assertEqual(kwargs['command_uuids'], (command['uuid'],))
        identity, status = response
        result = {} if status is None else {'sync_status': {command['uuid']: status}}
        if 'temp_id' in command:
            UUID(command['temp_id'])
            self.case.assertNotEqual(command['uuid'], command['temp_id'])
            result['temp_id_mapping'] = {command['temp_id']: identity}
        return result


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / '.todo'
        self.root.mkdir(mode=0o700)
        path = self.root / 'config'
        path.write_text('[main]\nproject=root\ndefault_sections=cat\nhidden_from_now=Later\n')
        path.chmod(0o600)
        self.store = StateStore(self.root)
        self.http = Boundary(self)
        self.wire_items = [item('parent', content='Parent', priority=3),
                           item('precise', content='Known sibling', added_at=PRECISE),
                           item('null', content='Unknown creation', added_at=None)]
        self.wire_reminders = []
        self.seed()
        self.sync = Synchronizer(self.http, self.store, clock=lambda: NOW)
        self.workflow = CaptureWorkflow(self.sync, streams=p.OriginalStreams(StringIO(), StringIO(), StringIO()))

    def state(self, items=None, reminders=None, **kwargs):
        return full(items=self.wire_items if items is None else items,
                    reminders=self.wire_reminders if reminders is None else reminders,
                    user={'id': 'u', 'tz_info': {'timezone': getattr(self, 'account_zone', 'UTC')}}, **kwargs)

    def seed(self):
        self.http.read(self.state())
        self.http.read(delta())
        current = retrieve(self.http, d.Binding('u', 'root', frozenset({'cat'})))
        with exclusive_lock('test', self.root):
            self.store.publish_snapshot(prepare_candidates(current.snapshot, empty_history(current.snapshot),
                account_display='Person', current_snapshot=current.snapshot, sync_token=current.sync_token, synced_at=NOW,
                initial_cursor=NOW if not (self.root / 'cursor').exists() and not (self.root / 'binding.json').exists() else None))

    def refresh(self, state=None, *, synchronize=True):
        state = self.state() if state is None else state
        self.http.read(state)
        self.http.read(delta())
        if synchronize and any(i['due'] and i['due']['is_recurring'] for i in state['items']):
            self.http.completed()

    def operation(self, kind, args, state, identity='new', status='ok'):
        self.http.command(kind, args, identity, status)
        self.refresh(state, synchronize=False)  # gateway's independent authoritative reads
        if status == 'ok':
            self.refresh(state)  # synchronized-state reconciliation/publication

    def run_request(self, argv):
        result = self.workflow.execute(parse(argv))
        self.assertFalse(self.http.steps, 'unconsumed boundary expectations')
        return result

    def test_step_aliases_resolve_parent_before_direct_child(self):
        self.wire_items += [item('other', content='Other'),
                            item('foreign', content='Unique child', parent_id='other', priority=3)]
        self.seed()
        for argv in (['step', '--priority', 'P1', 'Parent', 'Unique child'],
                     ['step', '--rename', 'Changed', 'Parent', 'Unique child'],
                     ['step', '--due', 'tomorrow', 'Parent', 'Unique child']):
            self.refresh()
            with self.assertRaises(NoMatch):
                self.run_request(argv)
        self.wire_items += [item('child', content='Unique child', parent_id='parent', priority=3),
                            item('nested', content='Deep child', parent_id='child')]
        self.seed()
        self.refresh()
        with self.assertRaises(NoMatch):
            self.run_request(['step', '--priority', 'P1', 'Parent', 'Deep child'])
        self.refresh()
        changed = self.state(items=[dict(i, priority=4) if i['id'] == 'child' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'child', 'priority': 4}, changed, 'child')
        result = self.run_request(['step', '--priority', 'P1', 'Parent', 'Unique child'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertEqual(result.outcomes[0].target_id, 'child')
        self.assertEqual(result.snapshot.items['foreign'].priority, 2)
        # A later alias must consume the same scoped identity after publication.
        self.wire_items = changed['items']
        self.refresh()
        changed = self.state(items=[dict(i, content='Changed') if i['id'] == 'child' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'child', 'content': 'Changed'}, changed, 'child')
        result = self.run_request(['step', '--rename', 'Changed', 'Parent', 'Unique child'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertEqual(result.snapshot.items['foreign'].title, 'Unique child')
        self.wire_items.append(item('ambiguous', content='Parent extra'))
        self.seed()
        self.refresh()
        with self.assertRaises(AmbiguityError):
            self.run_request(['step', '--due', 'tomorrow', 'Parent', 'Unique child'])

    def test_archived_completion_failure_preserves_receipts(self):
        parent = item('new', content='New parent', priority=3, added_at=None)
        done = dict(parent, checked=True, completed_at='2026-10-22T12:00:01.123456789012350Z')
        self.workflow.gateway = Gateway(self.http, clock=lambda: datetime(2026, 10, 22, 12, 0, 2, tzinfo=timezone.utc))
        self.refresh()
        state = self.state(items=self.wire_items + [parent])
        self.operation('item_add', dict(project_id='cat', content='New parent', priority=3,
            description='', labels=[], auto_reminder=False, due=None), state)
        self.http.command('item_close', {'id': 'new'}, 'new')
        self.refresh(self.state(), synchronize=False)  # archived owner absent from active Sync
        self.http.completed([done])
        reconcile = self.sync.reconcile_accepted_locked
        calls = []
        def fail_completion_publication():
            calls.append(True)
            if len(calls) == 1:
                return reconcile()
            raise SyncError('local publication', OSError('history replacement'),
                publication_started=True, remote_outcome='accepted')
        with patch.object(self.sync, 'reconcile_accepted_locked', side_effect=fail_completion_publication):
            result = self.run_request(['add', 'cat', '--title', 'New parent', 'Later parent', '--done'])
        self.assertEqual(result.status, 1)
        self.assertEqual([o.outcome for o in result.outcomes],
                         ['accepted', 'accepted', 'unattempted', 'unattempted'])
        self.assertTrue(result.outcomes[1].actual.completed)
        self.assertIsNone(result.outcomes[1].actual.added_at)
        self.assertNotIn('new', result.outcomes[1].receipt.after.snapshot.items)
        self.assertIn('Completed task: New parent', result.document.stdout)
        self.assertIn('Accepted: complete New parent', result.document.stderr)
        self.assertIn('Not attempted: create task Later parent', result.document.stderr)
        self.assertIn('do not replay', result.document.stderr)
        self.assertIn('todo --refresh now', result.document.stderr)

    def test_fixed_time_defaults_to_account_zone_and_later_noop(self):
        self.account_zone = 'Europe/Prague'
        self.seed()
        self.refresh()
        state = self.state(items=[dict(i, due=due('2026-10-23T08:00:00Z', timezone='Europe/Prague'))
                                 if i['id'] == 'parent' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'parent', 'due': {'date': '2026-10-23T08:00:00Z', 'lang': 'en'}}, state, 'parent')
        result = self.run_request(['schedule', 'Parent', '--at', 'tomorrow 10'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertEqual(result.snapshot.items['parent'].attention.zone, 'Europe/Prague')
        self.assertIn('2026-10-23 10:00:00 Europe/Prague', result.document.stdout)
        self.wire_items = state['items']
        self.refresh()
        with self.assertRaisesRegex(d.DomainError, 'no-op'):
            self.run_request(['schedule', 'Parent', '--at', 'tomorrow 10'])
        self.refresh()
        state = self.state(items=self.wire_items + [item('new', content='Timed task', priority=3,
            due=due('2026-10-23T08:00:00Z', timezone='Europe/Prague'))])
        self.operation('item_add', dict(project_id='cat', content='Timed task', priority=3,
            description='', labels=[], auto_reminder=False,
            due={'date': '2026-10-23T08:00:00Z', 'lang': 'en'}), state)
        result = self.run_request(['add', 'cat', 'Timed task', '--at', 'tomorrow 10'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertIn('Due: 2026-10-23 10:00:00 Europe/Prague', result.document.stdout)
        self.assertEqual(self.store.load_consistent_state().snapshot.items['new'].attention.zone, 'Europe/Prague')

    def test_archived_completion_is_reconciled_and_published(self):
        self.workflow.gateway = Gateway(self.http, clock=lambda: datetime(2026, 10, 22, 12, 0, 2, tzinfo=timezone.utc))
        self.sync.clock = lambda: d.instant_from_wire('2026-10-22T12:00:02.123456789012350Z')
        self.refresh()
        parent = item('new', content='New parent', priority=3, added_at=None)
        state = self.state(items=self.wire_items + [parent])
        self.operation('item_add', dict(project_id='cat', content='New parent', priority=3,
            description='', labels=[], auto_reminder=False, due=None), state)
        done = dict(parent, checked=True, completed_at='2026-10-22T12:00:01.123456789012350Z')
        self.http.command('item_close', {'id': 'new'}, 'new')
        self.refresh(self.state(), synchronize=False)
        self.http.completed([done])
        self.refresh(self.state(), synchronize=False)
        self.http.completed([done])
        self.http.comments('new')
        result = self.run_request(['add', 'cat', 'New parent', '--done'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertIn('Completed task: New parent', result.document.stdout)
        self.assertTrue(result.snapshot.items['new'].completed)
        self.assertEqual(d.instant_text(result.snapshot.items['new'].completed_at), done['completed_at'])
        self.assertIsNone(self.store.load_consistent_state().snapshot.items['new'].added_at)

    def test_split_batch_collision_and_inline_multiple_parents_before_mutation(self):
        self.refresh()
        with self.assertRaisesRegex(d.DomainError, 'sibling'):
            self.run_request(['add', 'task', 'cat', '--title', 'New task', 'new task'])
        with self.assertRaises(UsageError):
            self.run_request(['add', 'task', 'cat', '--title', 'One task', 'Other task', '--step', 'Child'])
        self.assertTrue(all('commands' not in c for c in self.http.calls))

    def test_depth_four_and_step_priority_option_refused(self):
        self.wire_items += [item(str(n), parent_id='parent' if n == 1 else str(n-1), content=f'Depth {n}') for n in range(1, 5)]
        self.seed()
        self.refresh()
        with self.assertRaisesRegex(d.DomainError, 'depth 4'):
            self.run_request(['add', 'step', 'Depth 4', '--step', 'Too deep'])
        with self.assertRaises(UsageError):
            self.run_request(['add', 'step', '--p1', 'Parent', 'Child'])

    def test_sibling_steps_copy_effective_priority_and_preserve_precise_null(self):
        self.wire_items.append(item('existing', content='Important', parent_id='parent', priority=4))
        self.seed()
        self.refresh()
        state = self.state(items=self.wire_items + [item('new', content='First step', parent_id='parent')])
        args = dict(project_id='cat', content='First step', description='', priority=4,
                    labels=[], auto_reminder=False, parent_id='parent', due=None)
        self.operation('item_add', args, state)
        state2 = deepcopy(state)
        state2['items'].append(item('next', content='Second step', parent_id='parent'))
        args2 = dict(args, content='Second step')
        self.operation('item_add', args2, state2, 'next')
        result = self.run_request(['add', 'step', 'Parent', '--step', 'First step', '--step', 'Second step'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertEqual(result.snapshot.items['new'].priority, 1)
        self.assertEqual(result.snapshot.items['next'].parent_id, 'parent')
        for snapshot in (result.snapshot, self.store.load_consistent_state().snapshot):
            self.assertEqual(d.instant_text(snapshot.items['precise'].added_at), PRECISE)
            self.assertIsNone(snapshot.items['null'].added_at)

    def test_new_task_defaults_p2_and_late_zero_reminder_failure_stops_batch(self):
        self.refresh()
        state = self.state(items=self.wire_items + [item('new', content='First task', priority=3,
            due=due('2026-10-23T10:00:00Z'))])
        self.operation('item_add', dict(project_id='cat', content='First task', description='',
            priority=3, labels=[], auto_reminder=False, due={'date': '2026-10-23T10:00:00Z', 'lang': 'en'}), state)
        self.operation('reminder_add', {'item_id': 'new', 'type': 'relative', 'minute_offset': 0},
            state, 'r', {'error_code': 1, 'error': 'no reminders'})
        result = self.run_request(['add', 'cat', '--title', 'First task', 'Second task',
            '--at', 'tomorrow 10', '--reminder', '0minutes'])
        self.assertEqual(result.status, 1)
        self.assertEqual([o.outcome for o in result.outcomes], ['accepted', 'rejected', 'unattempted', 'unattempted'])
        self.assertEqual(self.store.load_consistent_state().snapshot.items['new'].priority, 2)
        self.assertIn('Due:', result.document.stdout)
        self.assertIn('Failed', result.document.stderr.replace('Rejected', 'Failed'))

    def test_priority_rename_and_category_noop_collisions(self):
        for args, diagnostic in [(['priority', 'Parent', 'p2'], 'unchanged'),
                                 (['rename', 'Parent', '--to', 'Parent'], 'unchanged'),
                                 (['rename', 'Parent', '--to', 'Known sibling'], 'sibling'),
                                 (['add', 'category', 'CAT'], 'exists')]:
            self.refresh()
            with self.assertRaisesRegex(d.DomainError, diagnostic):
                self.run_request(args)

    def test_priority_outputs_stored_values_with_precise_state(self):
        self.refresh()
        state = self.state(items=[dict(i, priority=2) if i['id'] == 'parent' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'parent', 'priority': 2}, state, 'parent')
        result = self.run_request(['priority', 'Parent', 'P3'])
        self.assertEqual(result.status, 0)
        self.assertIn('P2 -> P3', result.document.stdout)
        self.assertEqual(d.instant_text(result.snapshot.items['precise'].added_at), PRECISE)
        self.assertIsNone(result.snapshot.items['null'].added_at)

    def test_zero_preserve_clear_and_noop(self):
        self.wire_items[0]['due'] = due('2026-10-23T10:00:00Z')
        self.wire_reminders = [reminder('r', 'parent')]
        self.seed()
        self.refresh()
        with self.assertRaisesRegex(d.DomainError, 'no-op'):
            self.run_request(['schedule', 'Parent', '--reminder', '0m'])
        self.refresh()
        with self.assertRaisesRegex(d.DomainError, 'clear or replace'):
            self.run_request(['schedule', 'Parent', '--at', 'tomorrow'])
        self.refresh()
        state = self.state(items=[dict(i, due=due('2026-10-24T10:00:00Z')) if i['id'] == 'parent' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'parent', 'due': {'date': '2026-10-24T10:00:00Z', 'lang': 'en'}}, state, 'parent')
        result = self.run_request(['schedule', 'Parent', '--at', '2026-10-24T10:00:00Z'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertIn('Reminders retained: 0m', result.document.stdout)
        self.wire_items = state['items']
        self.refresh()
        self.operation('reminder_delete', {'id': 'r'}, self.state(reminders=[]), 'r')
        result = self.run_request(['schedule', 'Parent', '--reminder', 'clear'])
        self.assertEqual(result.status, 0)
        self.assertEqual(result.snapshot.items['parent'].attention.instant.hour, 10)
        self.wire_reminders = []
        self.refresh()
        with self.assertRaisesRegex(d.DomainError, 'no-op'):
            self.run_request(['schedule', 'Parent', '--reminder', 'clear'])

    def test_invalid_reminder_spellings_and_equivalent_duplicates(self):
        for value in ('0h', '0d', '0w', '00m', '-1m', '1.5m', '1month'):
            with self.subTest(value=value), self.assertRaises(UsageError):
                parse(['add', 'cat', 'Title', '--at', 'tomorrow 10', '--reminder', value])
        with self.assertRaises(UsageError):
            parse(['add', 'cat', 'Title', '--reminder', '60m', '--reminder', '1h'])

    def test_unknown_hiding_and_today_fail_before_any_mutation(self):
        for command in ('hide', 'schedule'):
            for expression, message in [('banana', 'banana.*ISO'), ('today', 'future.*start')]:
                self.refresh()
                args = [command, 'Parent', '--at', expression]
                if command == 'schedule': args += ['--hide']
                with self.assertRaisesRegex(d.DomainError, message):
                    self.run_request(args)
        self.assertTrue(all('commands' not in c for c in self.http.calls))

    def test_future_reasonless_hide_and_unhide_preserves_exact_date(self):
        self.wire_items[0]['due'] = due('2026-10-23T10:00:00.123456789Z')
        self.wire_reminders = [reminder('r', 'parent')]
        self.seed()
        self.refresh()
        self.http.read({'full_sync': True, 'sync_token': 'labels', 'labels': [{'id': 'l', 'name': 'waiting'}]}, '["labels"]')
        self.http.read({'full_sync': False, 'sync_token': 'lf'}, '["labels"]')
        state = self.state(items=[dict(i, labels=['waiting']) if i['id'] == 'parent' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'parent', 'labels': ['waiting']}, state, 'parent')
        result = self.run_request(['hide', 'Parent'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertIn('Hiding: off -> on', result.document.stdout)
        self.wire_items = state['items']
        self.refresh()
        state2 = self.state(items=[dict(i, labels=[]) if i['id'] == 'parent' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'parent', 'labels': []}, state2, 'parent')
        result = self.run_request(['unhide', 'Parent'])
        self.assertEqual(result.status, 0)
        self.assertEqual(result.snapshot.items['parent'].attention.raw_due['date'], '2026-10-23T10:00:00.123456789Z')
        self.assertEqual(result.snapshot.reminders['r'].minutes, 0)

    def test_missing_waiting_label_advice_only_on_addition(self):
        self.refresh()
        self.http.read({'full_sync': True, 'sync_token': 'labels', 'labels': []}, '["labels"]')
        self.http.read({'full_sync': False, 'sync_token': 'lf'}, '["labels"]')
        with self.assertRaisesRegex(d.DomainError, 'todo init'):
            self.run_request(['hide', 'Parent', '--due', 'tomorrow'])

    def real_boundary(self, label_steps, after_steps=()):
        """Production signature and HTTP encoding for the shared hiding lookup."""
        def read(token, resources, response):
            return ExpectedRequest('POST', '/sync', 'secret', form={
                'sync_token': token, 'resource_types': resources}), response
        steps = [read('delta-token', RESOURCES, self.state()),
                 read('full-token', RESOURCES, delta())]
        steps += [read(token, '["labels"]', response) for token, response in label_steps]
        steps += list(after_steps)
        http = ControlledHTTP([(expected, response if isinstance(response, Response)
            else Response(json.dumps(response).encode())) for expected, response in steps])
        self.addCleanup(http.assert_done)
        sync = Synchronizer(Transport('secret', opener=http, sleep=lambda _: None),
                            self.store, clock=lambda: NOW)
        return CaptureWorkflow(sync, streams=self.workflow.streams), http

    def test_hide_through_production_transport_stores_authoritative_hiding(self):
        self.wire_items[0]['due'] = due('2026-10-23')
        self.seed()
        state = self.state(items=[dict(i, labels=['waiting']) if i['id'] == 'parent'
                                 else i for i in self.wire_items])
        command = CommandRequest(self, 'item_update', {'id': 'parent', 'labels': ['waiting']})
        after = [command.step()]
        for _ in range(2):  # gateway authoritative read, then publication refresh
            for token, response in [('delta-token', state), ('full-token', delta())]:
                after.append((ExpectedRequest('POST', '/sync', 'secret', form={
                    'sync_token': token, 'resource_types': RESOURCES}), response))
        workflow, http = self.real_boundary([
            ('*', {'full_sync': True, 'sync_token': 'labels',
                   'labels': [{'id': 'l', 'name': 'waiting'}]}),
            ('labels', {'full_sync': False, 'sync_token': 'fresh'})], after)
        result = workflow.execute(parse(['hide', 'Parent']))
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertIn('Hiding: off -> on', result.document.stdout)
        self.assertTrue(result.snapshot.items['parent'].waiting)
        self.assertTrue(self.store.load_consistent_state().snapshot.items['parent'].waiting)
        self.assertEqual(len(command.commands), 1)
        http.assert_done()

    def test_real_waiting_label_refusals_before_mutation(self):
        self.wire_items[0]['due'] = due('2026-10-23')
        self.seed()
        present = {'full_sync': True, 'sync_token': 'labels',
                   'labels': [{'id': 'l', 'name': 'waiting'}]}
        cases = [
            ([('*', dict(present, labels=[])),
              ('labels', {'full_sync': False, 'sync_token': 'fresh'})], d.DomainError, 'todo init'),
            ([('*', present), ('labels', {'full_sync': False, 'sync_token': 'fresh',
                'labels': [{'id': 'l', 'is_deleted': True}]})], d.DomainError, 'todo init'),
            ([('*', Response(b'{"error":"denied"}', status=403))], HTTPFailure, 'read waiting label'),
            ([('*', Response(b'not JSON'))], HTTPFailure, 'read waiting label'),
            ([('*', dict(present, labels=None))], d.DomainError, 'invalid waiting label'),
            ([('*', present), ('labels', {'full_sync': True, 'sync_token': 'bad'})],
             d.DomainError, 'invalid waiting label')]
        for steps, error, message in cases:
            with self.subTest(message=message, steps=steps):
                workflow, http = self.real_boundary(steps)
                with self.assertRaisesRegex(error, message):
                    workflow.execute(parse(['hide', 'Parent']))
                http.assert_done()  # script has no mutation response
                self.assertFalse(self.store.load_consistent_state().snapshot.items['parent'].waiting)

    def test_all_descendants_and_ancestor_chain_preflight(self):
        self.wire_items += [item('child', content='Child', parent_id='parent'),
            item('leaf', content='Leaf', parent_id='child', due=due('2026-10-23'))]
        self.seed()
        self.refresh()
        with self.assertRaisesRegex(d.DomainError, 'descendant'):
            self.run_request(['hide', 'Parent', '--at', '2026-10-24'])
        self.wire_items[0].update(labels=['waiting'], due=due('2026-10-23'))
        self.seed()
        self.refresh()
        with self.assertRaisesRegex(d.DomainError, 'descendant'):
            self.run_request(['schedule', 'Leaf', '--at', 'today'])

    def test_unknown_expression_preserves_reminders_and_reconciles_missing_date(self):
        self.refresh()
        state = self.state()
        self.operation('item_update', {'id': 'parent', 'due': {'string': 'next Friday 10:00', 'lang': 'en'}}, state, 'parent')
        result = self.run_request(['schedule', 'Parent', '--at', 'next Friday 10:00'])
        self.assertEqual(result.status, 1)
        self.assertEqual(result.outcomes[0].outcome, 'accepted')
        self.assertIn('actual', result.document.stderr)
        self.assertIn('Read-only recovery', result.document.stderr)

    def test_remote_two_second_tolerance_inclusive_actual_published(self):
        for seconds, status in [(-2, 0), (2, 0), (3, 1)]:
            self.refresh()
            value = f'2026-10-23T10:00:{10+seconds:02}Z'
            state = self.state(items=[dict(i, due=due(value)) if i['id'] == 'parent' else i for i in self.wire_items])
            self.operation('item_update', {'id': 'parent', 'due': {'date': '2026-10-23T10:00:10Z', 'lang': 'en'}}, state, 'parent')
            result = self.run_request(['schedule', 'Parent', '--at', '2026-10-23T10:00:10Z'])
            self.assertEqual(result.status, status, result.document.stderr)
            self.assertEqual(result.snapshot.items['parent'].attention.raw_due['date'], value)
            self.assertEqual(self.store.load_consistent_state().snapshot.items['parent'].attention.raw_due['date'], value)

    def test_unknown_stops_following_creations_without_publication_or_replay(self):
        self.refresh()
        state = self.state(items=self.wire_items + [item('new', content='First task', priority=3)])
        self.operation('item_add', dict(project_id='cat', content='First task', description='',
            priority=3, labels=[], auto_reminder=False, due=None), state, status=None)
        result = self.run_request(['add', 'cat', '--title', 'First task', 'Second task'])
        self.assertEqual([o.outcome for o in result.outcomes], ['unknown', 'unattempted'])
        self.assertNotIn('new', self.store.load_consistent_state().snapshot.items)
        self.assertIn('do not replay', result.document.stderr)

    def test_failed_publication_retains_accepted_and_unattempted(self):
        self.refresh()
        state = self.state(items=self.wire_items + [item('new', content='First task', priority=3)])
        self.http.command('item_add', dict(project_id='cat', content='First task', description='',
            priority=3, labels=[], auto_reminder=False, due=None))
        self.refresh(state)
        failure = SyncError('local publication', OSError('history replacement'), publication_started=True,
                            remote_outcome='accepted')
        with patch.object(self.sync, 'reconcile_accepted_locked', side_effect=failure):
            result = self.run_request(['add', 'cat', '--title', 'First task', 'Second task'])
        self.assertEqual([o.outcome for o in result.outcomes], ['accepted', 'unattempted'])
        self.assertIn('may be partially published', result.document.stderr)
        self.assertIn('do not replay', result.document.stderr)
        self.assertNotIn('usable old', result.document.stderr)

    def test_recurrence_preserving_date_timed_floating_and_fixed_sources(self):
        for source, named_zone, expression, returned in [
            ('2026-10-23', None, 'tomorrow', '2026-10-23'),
            ('2026-10-23T10:00:00', None, 'tomorrow 11', '2026-10-23T11:00:00Z'),
            ('2026-10-23T10:00:00Z', 'Europe/Prague', 'tomorrow 11', '2026-10-23T11:00:00Z'),
            ('2026-10-23T10:00:00Z', 'Europe/Prague', 'tomorrow', '2026-10-23')]:
            with self.subTest(source=source, expression=expression):
                self.wire_items[0]['due'] = due(source, timezone=named_zone,
                    is_recurring=True, string='every day at 10')
                self.seed()
                self.refresh()
                final_zone = None if len(returned) == 10 else named_zone
                after_due = due(returned, timezone=final_zone,
                    is_recurring=True, string='every day at 10')
                state = self.state(items=[dict(i, due=after_due) if i['id'] == 'parent' else i for i in self.wire_items])
                if source == returned and named_zone == final_zone:
                    with self.assertRaisesRegex(d.DomainError, 'no-op'):
                        self.run_request(['schedule', 'Parent', '--due', expression])
                    continue
                self.operation('item_update', {'id': 'parent', 'due': after_due}, state, 'parent')
                result = self.run_request(['schedule', 'Parent', '--due', expression])
                self.assertEqual(result.status, 0, result.document.stderr)
                attention = result.snapshot.items['parent'].attention
                self.assertEqual((attention.recurring, attention.rule, attention.language, attention.zone),
                    (True, 'every day at 10', 'en', final_zone))
                self.assertEqual(attention.raw_due['date'], returned)

    def test_day_crossing_rule_and_zone_are_strict_despite_tolerance(self):
        for returned_due in [due('2026-10-24T00:00:00Z'),
                             due('2026-10-23T23:59:59Z', timezone='Europe/Prague'),
                             due('2026-10-23T23:59:59Z', is_recurring=True, string='every day')]:
            self.refresh()
            state = self.state(items=[dict(i, due=returned_due) if i['id'] == 'parent' else i for i in self.wire_items])
            self.operation('item_update', {'id': 'parent', 'due': {'date': '2026-10-23T23:59:59Z', 'lang': 'en'}}, state, 'parent')
            result = self.run_request(['schedule', 'Parent', '--at', '2026-10-23T23:59:59Z'])
            self.assertEqual(result.status, 1)
            self.assertEqual(result.outcomes[0].outcome, 'accepted')

    def test_inline_steps_unscheduled_on_hidden_parent(self):
        self.refresh()
        self.http.read({'full_sync': True, 'sync_token': 'labels',
            'labels': [{'id': 'waiting', 'name': 'waiting', 'unexpected': []}]}, '["labels"]')
        self.http.read({'full_sync': False, 'sync_token': 'fresh'}, '["labels"]')
        state = self.state(items=self.wire_items + [item('new', content='New parent', priority=3,
            due=due('2026-10-23'), labels=['waiting'])])
        self.operation('item_add', dict(project_id='cat', content='New parent', priority=3,
            description='', labels=['waiting'], auto_reminder=False,
            due={'date': '2026-10-23', 'lang': 'en'}), state)
        state2 = deepcopy(state)
        state2['items'].append(item('child', content='Inline child', parent_id='new', priority=3))
        self.operation('item_add', dict(project_id='cat', content='Inline child', priority=3,
            description='', parent_id='new', labels=[], auto_reminder=False), state2, 'child')
        result = self.run_request(['add', 'cat', 'New parent', '--step', 'Inline child', '--hide', '--at', 'tomorrow'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertIsNone(result.snapshot.items['child'].attention)
        self.assertFalse(result.snapshot.items['child'].waiting)

    def test_creation_completion_inline_before_parent_ordinary_gateway(self):
        self.workflow.gateway = Gateway(self.http, clock=lambda: d.instant_datetime(NOW))
        self.refresh()
        parent = item('new', content='New parent', priority=3, added_at=None)
        child = item('child', content='Inline child', parent_id='new', priority=3, added_at=PRECISE)
        state = self.state(items=self.wire_items + [parent])
        self.operation('item_add', dict(project_id='cat', content='New parent', priority=3,
            description='', labels=[], auto_reminder=False, due=None), state)
        state = self.state(items=self.wire_items + [parent, child])
        self.operation('item_add', dict(project_id='cat', content='Inline child', priority=3,
            description='', parent_id='new', labels=[], auto_reminder=False), state, 'child')
        child_done = dict(child, checked=True, completed_at=PRECISE)
        self.http.command('item_close', {'id': 'child'}, 'child')
        self.refresh(self.state(items=self.wire_items + [parent, child_done]), synchronize=False)
        self.http.completed([child_done])
        self.refresh(self.state(items=self.wire_items + [parent, child_done]))
        parent_done = dict(parent, checked=True, completed_at=d.instant_text(NOW))
        self.http.command('item_close', {'id': 'new'}, 'new')
        self.refresh(self.state(items=self.wire_items + [parent_done, child_done]), synchronize=False)
        self.http.completed([parent_done])
        self.refresh(self.state(items=self.wire_items + [parent_done, child_done]))
        result = self.run_request(['add', 'cat', 'New parent', '--step', 'Inline child', '--done'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertEqual([o.target_id for o in result.outcomes], ['new', 'child', 'child', 'new'])
        self.assertTrue(result.snapshot.items['new'].completed)
        self.assertIsNone(result.snapshot.items['new'].added_at)
        self.assertEqual(d.instant_text(result.snapshot.items['child'].added_at), PRECISE)
        self.assertEqual(d.instant_text(result.snapshot.items['child'].completed_at), PRECISE)

    def test_unhide_inherited_suppression_reason_removal_and_full_clear(self):
        self.wire_items[0].update(labels=['waiting'], due=due('2026-10-23'))
        reason = 'Ordinary\n\n[todo waiting]\nOptional reason\n[/todo waiting]'
        self.wire_items.append(item('child', content='Child', parent_id='parent', labels=['waiting'],
            due=due('2026-10-24T10:00:00.123456789Z'), description=reason))
        self.wire_reminders = [reminder('r', 'child')]
        self.seed()
        self.refresh()
        state = self.state(items=[dict(i, labels=[], description='Ordinary') if i['id'] == 'child' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'child', 'labels': [], 'description': 'Ordinary'}, state, 'child')
        result = self.run_request(['unhide', 'Child'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertIn('Still hidden by an ancestor', result.document.stdout)
        self.assertEqual(result.snapshot.reminders['r'].minutes, 0)
        self.wire_items = state['items']
        self.refresh()
        without_reminders = self.state(reminders=[])
        self.operation('reminder_delete', {'id': 'r'}, without_reminders, 'r')
        state2 = self.state(items=[dict(i, due=None) if i['id'] == 'child' else i for i in self.wire_items], reminders=[])
        self.operation('item_update', {'id': 'child', 'due': None}, state2, 'child')
        result = self.run_request(['schedule', 'Child', 'clear'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertIsNone(result.snapshot.items['child'].attention)
        self.assertEqual(result.snapshot.items['child'].description, 'Ordinary')

    def test_hidden_category_scheduling_allows_unrelated_mutation(self):
        state = self.state(projects=[project('root', None), project(name='Later')],
            items=self.wire_items + [item('child', parent_id='parent', due=due('2026-10-23'))])
        self.refresh(state)
        changed = deepcopy(state)
        changed['items'][0]['priority'] = 4
        self.operation('item_update', {'id': 'parent', 'priority': 4}, changed, 'parent')
        result = self.run_request(['priority', 'Parent', 'P1'])
        self.assertEqual(result.status, 0)
        self.assertIsNotNone(result.snapshot.items['child'].attention)

    def test_parser_expression_normalization_preserves_zero_or_reports_loss(self):
        self.wire_items[0]['due'] = due('2026-10-23T10:00:00Z')
        self.wire_reminders = [reminder('r', 'parent')]
        self.seed()
        for keep in (True, False):
            self.refresh()
            state = self.state(items=[dict(i, due=due('2026-10-24T10:00:00')) if i['id'] == 'parent' else i for i in self.wire_items],
                reminders=self.wire_reminders if keep else [])
            self.operation('item_update', {'id': 'parent', 'due': {'string': 'next Friday 10:00', 'lang': 'en'}}, state, 'parent')
            result = self.run_request(['schedule', 'Parent', '--schedule=next Friday 10:00'])
            self.assertEqual(result.status, 0 if keep else 1, result.document.stderr)
            if keep:
                self.assertIn('Reminders retained: 0m', result.document.stdout)
            else:
                self.assertIn('preserved reminder', result.document.stderr)

    def test_exact_small_change_is_not_noop(self):
        self.wire_items[0]['due'] = due('2026-10-23T10:00:00.123456789012349Z')
        self.seed()
        self.refresh()
        value = '2026-10-23T10:00:00.123456789012350Z'
        state = self.state(items=[dict(i, due=due(value)) if i['id'] == 'parent' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'parent', 'due': {'date': value, 'lang': 'en'}}, state, 'parent')
        result = self.run_request(['schedule', 'Parent', '--at', value])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertEqual(result.snapshot.items['parent'].attention.raw_due['date'], value)
        self.assertIn(value, result.document.stdout)


    def test_successful_zero_creation_and_scalar_receipt(self):
        self.refresh()
        state = self.state(items=self.wire_items + [item('new', content='Timed task', priority=3,
            due=due('2026-10-23T10:00:00Z'))])
        self.operation('item_add', dict(project_id='cat', content='Timed task', description='',
            priority=3, labels=[], auto_reminder=False, due={'date': '2026-10-23T10:00:00Z', 'lang': 'en'}), state)
        state2 = deepcopy(state)
        state2['reminders'] = [reminder('zero', 'new')]
        self.operation('reminder_add', {'item_id': 'new', 'type': 'relative', 'minute_offset': 0}, state2, 'zero')
        result = self.run_request(['add', 'cat', 'Timed task', '--at=tomorrow 10', '--reminder=0m'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertEqual(result.snapshot.reminders['zero'].minutes, 0)
        self.assertIn('  Reminders: 0m', result.document.stdout)

    def test_nested_parent_creation_uses_effective_priority(self):
        self.wire_items += [item('branch', content='Branch', parent_id='parent', priority=2),
                            item('leaf', content='Leaf', parent_id='branch', priority=4)]
        self.seed()
        self.refresh()
        state = self.state(items=self.wire_items + [item('new', content='Nested child', parent_id='branch')])
        self.operation('item_add', dict(project_id='cat', content='Nested child', parent_id='branch',
            priority=4, description='', labels=[], auto_reminder=False, due=None), state)
        result = self.run_request(['add', 'step', 'Branch', 'Nested child'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertEqual(result.snapshot.items['new'].parent_id, 'branch')

    def test_reason_is_optional_metadata_and_ordinary_text_survives(self):
        self.wire_items[0].update(labels=['waiting'], due=due('2026-10-24'),
            description='Ordinary\n\n[todo waiting]\nOriginal reason\n[/todo waiting]')
        self.seed()
        self.refresh()
        state = self.state(items=[dict(i, description='Ordinary') if i['id'] == 'parent' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'parent', 'description': 'Ordinary'}, state, 'parent')
        result = self.run_request(['hide', 'Parent', '--reason='])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertTrue(result.snapshot.items['parent'].waiting)
        self.assertEqual(result.snapshot.items['parent'].description, 'Ordinary')
        self.wire_items = state['items']
        self.refresh()
        state2 = self.state(items=[dict(i, due=due('2026-10-25')) if i['id'] == 'parent' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'parent', 'due': {'date': '2026-10-25', 'lang': 'en'}}, state2, 'parent')
        result = self.run_request(['schedule', 'Parent', '--at=2026-10-25'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertTrue(result.snapshot.items['parent'].waiting)
        self.assertEqual(result.snapshot.items['parent'].description, 'Ordinary')

    def test_category_and_rename_success_use_gateway_and_actual_state(self):
        self.refresh()
        state = self.state(items=[dict(i, content='New title') if i['id'] == 'parent' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'parent', 'content': 'New title'}, state, 'parent')
        result = self.run_request(['rename', 'Parent', '--to', 'New title'])
        self.assertEqual(result.status, 0)
        self.assertIn('Parent -> New title', result.document.stdout)
        self.wire_items = state['items']
        self.refresh()
        state2 = self.state(projects=[project('root', None), project(), project('new-category', name='New category')])
        self.operation('project_add', {'parent_id': 'root', 'name': 'New category'}, state2, 'new-category')
        result = self.run_request(['category', '--add', 'New', 'category'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertIn('Created category: New category', result.document.stdout)

    def test_absolute_reminders_preserved_across_rename_and_date_only_reschedule(self):
        from tests.support.reminders import absolute, FLOATING
        self.wire_reminders = [absolute('absolute', FLOATING, item_id='parent')]
        self.seed()
        original = self.store.load_consistent_state().snapshot.reminders
        self.refresh()
        state = self.state(items=[dict(i, content='Renamed') if i['id'] == 'parent' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'parent', 'content': 'Renamed'}, state, 'parent')
        result = self.run_request(['rename', 'Parent', '--to', 'Renamed'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertEqual(result.snapshot.reminders, original)
        self.wire_items = state['items']
        self.refresh()
        state = self.state(items=[dict(i, due=due('2026-10-25')) if i['id'] == 'parent' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'parent', 'due': {'date': '2026-10-25', 'lang': 'en'}}, state, 'parent')
        result = self.run_request(['schedule', 'Renamed', '--at', '2026-10-25'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertEqual(self.store.load_history().snapshot.reminders, original)

    def test_rename_preserves_semantics_across_reminder_encoding_and_account_zone(self):
        from tests.support.reminders import absolute, FLOATING, FIXED
        # Task floats independently from its fixed and floating reminders.
        self.wire_items[0]['due'] = due('2026-10-30T09:00:00', timezone=None)
        floating = {k: v for k, v in FLOATING.items() if k != 'timezone'}
        self.wire_reminders = [absolute('floating', floating, item_id='parent'),
                               absolute('fixed', FIXED, item_id='parent')]
        self.seed()
        for zone, title in (('UTC', 'First'), ('America/New_York', 'Second')):
            self.refresh()
            self.account_zone = zone
            returned = [absolute('floating', {**floating, 'timezone': None}, item_id='parent'),
                        absolute('fixed', FIXED, item_id='parent')]
            state = self.state(items=[dict(i, content=title) if i['id'] == 'parent' else i for i in self.wire_items],
                               reminders=returned)
            self.operation('item_update', {'id': 'parent', 'content': title}, state, 'parent')
            old_title = self.wire_items[0]['content']
            result = self.run_request(['rename', old_title, '--to', title])
            self.assertEqual(result.status, 0, result.document.stderr)
            self.wire_items, self.wire_reminders = state['items'], returned
            for snapshot in (self.store.load_consistent_state().snapshot, self.store.load_history().snapshot):
                self.assertEqual(snapshot.items['parent'].title, title)
                self.assertEqual(snapshot.reminders['floating'].due.raw_due, returned[0]['due'])
                self.assertEqual(snapshot.reminders['fixed'].due.raw_due, FIXED)
                self.assertEqual(snapshot.items['parent'].attention.instant.hour, 9 if zone == 'UTC' else 13)

    def test_scalar_update_rebases_floating_task_with_unchanged_fixed_reminder(self):
        from tests.support.reminders import absolute, FIXED
        self.wire_items[0]['due'] = due('2026-10-30T09:00:00', timezone=None)
        self.wire_reminders = [absolute('fixed', FIXED, item_id='parent')]
        self.seed()
        self.refresh()
        self.account_zone = 'America/New_York'
        state = self.state(items=[dict(i, content='Renamed') if i['id'] == 'parent' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'parent', 'content': 'Renamed'}, state, 'parent')
        result = self.run_request(['rename', 'Parent', '--to', 'Renamed'])
        self.assertEqual(result.status, 0, result.document.stderr)
        for snapshot in (self.store.load_consistent_state().snapshot, self.store.load_history().snapshot):
            self.assertEqual(snapshot.items['parent'].attention.instant.hour, 13)
            self.assertEqual(snapshot.reminders['fixed'].due.raw_due, FIXED)

    def test_reminder_capability_checked_before_creation(self):
        state = self.state(user_plan_limits={'current': {'activity_log': False,
            'activity_log_limit': 0, 'reminders': False}})
        self.refresh(state)
        with self.assertRaisesRegex(d.DomainError, 'capability'):
            self.run_request(['add', 'cat', 'Task', '--at', 'tomorrow 10', '--reminder', '0m'])
        self.assertTrue(all('commands' not in c for c in self.http.calls))

    def test_real_publication_failure_after_cache_replacement_keeps_receipts(self):
        self.refresh()
        state = self.state(items=self.wire_items + [item('new', content='Timed task', priority=3,
            due=due('2026-10-23T10:00:00Z'))])
        self.operation('item_add', dict(project_id='cat', content='Timed task', description='',
            priority=3, labels=[], auto_reminder=False, due={'date': '2026-10-23T10:00:00Z', 'lang': 'en'}), state)
        real_replace = os.replace
        old_history = []
        def fail_history(source, destination):
            if Path(destination).name == 'history.json' and any('commands' in c for c in self.http.calls):
                old_history.append((self.root / 'history.json').read_bytes())
                raise OSError('controlled late history replacement failure')
            return real_replace(source, destination)
        with patch('todo_lib.local.safety.os.replace', side_effect=fail_history):
            result = self.run_request(['add', 'cat', '--title', 'Timed task', 'Later task', '--at', 'tomorrow 10'])
        self.assertEqual([o.outcome for o in result.outcomes], ['accepted', 'unattempted'])
        self.assertTrue(result.failure.publication_started)
        self.assertEqual((self.root / 'history.json').read_bytes(), old_history[0])
        self.assertIn('Due: 2026-10-23 10:00:00 UTC', result.document.stdout)
        self.assertIn('may be partially published', result.document.stderr)
        self.assertIn('do not replay', result.document.stderr)
        with self.assertRaisesRegex(LocalError, 'mixed'):
            self.store.load_consistent_state()
        cache = json.loads((self.root / 'cache.json').read_text())
        self.assertEqual(cache['snapshot']['items']['precise']['added_at'], PRECISE)
        self.assertIsNone(cache['snapshot']['items']['null']['added_at'])

    def test_convenience_delivery_and_schedule_entry_point(self):
        from todo_lib.workflows.scheduling import execute
        self.refresh()
        state = self.state(items=[dict(i, due=due('2026-10-23')) if i['id'] == 'parent' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'parent', 'due': {'date': '2026-10-23', 'lang': 'en'}}, state, 'parent')
        result = execute(['schedule', 'Parent', '--at', 'tomorrow'], self.sync,
                         streams=self.workflow.streams, deliver=True)
        self.assertEqual(result.status, 0)
        self.assertIn('Updated task: Parent', self.workflow.streams.stdout.getvalue())
        self.assertFalse(self.http.steps)


if __name__ == '__main__':
    unittest.main()
