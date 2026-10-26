"""Synthetic, request-rejecting boundary fixtures, not a provider emulator.

Pinned authority: docs/design/external/todoist/upstream/api-v1.openapi.json,
Sync command UUID/temp mapping, Tasks, Task comments, Reminders and Projects.
Actual Current, Retrieval, CompletedRecord, Activity and precise domain values
exercise the dependency interfaces. Independent deltas are deliberately supplied
rather than inferring server state from outgoing commands. Workflow publication
and complete move-tree validation remain the consuming workflows' responsibility.
"""
from dataclasses import replace
from datetime import datetime, timezone
import json
import unittest
from uuid import UUID

from todo_lib.adapter.commands import Gateway, Operation, Outcome, due_arguments
from todo_lib.adapter.current import Current
from todo_lib.adapter.history import Activity, CompletedRecord, HistoryError, Retrieval
from todo_lib.adapter.transport import OutcomeUnknown, Replay, Transport
from todo_lib.domain import (
    Account, Binding, Capabilities, Comment, DomainError, Item, Occurrence, Project,
    Snapshot, instant_from_wire as stamp, instant_key, instant_text,
    parse_attention, resolve_remote_due, validate,
)
from tests.adapter.current.test_current import item, reminder, project, full, delta, RESOURCES
from tests.support.http import ControlledHTTP, ExpectedRequest, Response


AT = '2026-10-20T12:00:00.123456789Z'
NEXT = '2026-10-20T12:00:00.123456790Z'
START = stamp('2026-10-20T12:00:00.123456780Z')
END = stamp('2026-10-20T12:00:00.123456799Z')
NOW = datetime(2026, 10, 20, 12, 1, tzinfo=timezone.utc)


def due(date='2026-10-21T10:00:00.123456789Z', **kw):
    return dict(date=date, timezone=None, string='tomorrow at 10', lang='en', is_recurring=False, **kw)


def before(*items, comments=(), occurrences=()):
    binding = Binding('u', 'root', frozenset({'cat', 'other'}))
    snapshot = Snapshot(binding, Account('u', 'UTC', Capabilities(True, True, -1)),
        Project('root', 'Root'), {'cat': Project('cat', 'Category', 'root'),
        'other': Project('other', 'Other', 'root')},
        {i.id: i for i in items or (Item('task', 'cat', 'Original', added_at=stamp(AT)),)},
        {c.id: c for c in comments}, {}, {o.id: o for o in occurrences})
    return Current(validate(snapshot), 'prior-token')


class Wire:
    """Checks one command, then consumes independently supplied read responses."""
    def __init__(self, case, kind, args, read, status='ok', mapping='new', lost=False):
        self.case, self.kind, self.args = case, kind, args
        self.read = list(read)
        self.status, self.mapping, self.lost = status, mapping, lost
        self.commands, self.reads = [], []
        self.command = None

    def request(self, method, path, **kw):
        self.case.assertEqual((method, path), ('POST', '/sync'))
        form = kw['form']
        if 'commands' in form:
            self.case.assertEqual(kw['replay'], Replay.IDEMPOTENT)
            commands = json.loads(form['commands'])
            self.case.assertEqual(len(commands), 1)
            command = commands[0]
            self.case.assertEqual(command['type'], self.kind)
            self.case.assertEqual(command['args'], self.args)
            self.case.assertEqual(str(UUID(command['uuid'])), command['uuid'])
            self.case.assertEqual(kw['command_uuids'], (command['uuid'],))
            if self.kind.endswith('_add'):
                self.case.assertEqual(str(UUID(command['temp_id'])), command['temp_id'])
                self.case.assertNotEqual(command['uuid'], command['temp_id'])
            else:
                self.case.assertNotIn('temp_id', command)
            self.commands.append(command)
            self.case.assertEqual(len(self.commands), 1, 'no replay or compensation')
            self.command = command
            if self.lost:
                raise OutcomeUnknown('lost response', outcome='unknown')
            return self.receipt()
        self.case.assertEqual(kw['replay'], Replay.READ)
        self.case.assertEqual(set(form), {'sync_token', 'resource_types'})
        self.reads.append(form)
        self.case.assertTrue(self.read, 'unexpected extra read')
        result = self.read.pop(0)
        return result(self) if callable(result) else result

    def receipt(self):
        result = {}
        if self.status is not None:
            result['sync_status'] = {self.command['uuid']: self.status}
        if 'temp_id' in self.command and self.mapping is not None:
            result['temp_id_mapping'] = {self.command['temp_id']: self.mapping}
        return result

    def done(self):
        self.case.assertFalse(self.read, 'missing reconciliation reads')
        self.case.assertEqual(len(self.commands), 1)


class History:
    def __init__(self, records=(), comments=(), activities=(), failure=False):
        self.records, self.notes, self.events = records, comments, activities
        self.calls, self.failure = [], failure

    def completed(self, start, end, scope):
        self.calls.append(('completed', instant_key(start), instant_key(end), scope))
        if self.failure:
            raise HistoryError('incomplete bounded history')
        return Retrieval(tuple(self.records), (), start, end)

    def comments(self, owner):
        self.calls.append(('comments', owner))
        return Retrieval(tuple(self.notes), ())

    def activities(self, start, end, scope):
        self.calls.append(('activities', scope))
        return Retrieval(tuple(self.events), (), start, end)


class CommandsTests(unittest.TestCase):
    def gateway(self, kind, args, read=None, history=None, **kw):
        wire = Wire(self, kind, args, [delta()] if read is None else read, **kw)
        self.addCleanup(wire.done)
        return Gateway(wire, history=history, clock=lambda: NOW), wire

    def test_lost_response_reads_exact_receipt_and_preserves_precise_after(self):
        row = item(content='Changed', added_at=NEXT, completed_at=None)
        g, w = self.gateway('item_update', {'id': 'task', 'content': 'Changed'},
            read=[lambda w: delta(items=[row], **w.receipt())], lost=True)
        result = g.update_task('task', title='Changed', before=before())
        self.assertEqual(result.outcome, Outcome.ACCEPTED)
        self.assertEqual(instant_text(result.actual.added_at), NEXT)
        self.assertIsNone(result.actual.completed_at)
        self.assertIs(result.actual, result.after.snapshot.items['task'])
        self.assertFalse(result.issues)
        self.assertEqual(w.reads[0]['sync_token'], 'prior-token')

    def test_unknown_and_rejected_also_preserve_precise_values_and_null(self):
        for status, outcome in [(None, Outcome.UNKNOWN),
                                ({'error_code': 20, 'error': 'Invalid argument'}, Outcome.REJECTED)]:
            with self.subTest(status=status):
                old = Item('task', 'cat', 'Original', added_at=stamp(AT),
                           completed=True, completed_at=stamp(AT))
                g, _ = self.gateway('item_update', {'id': 'task', 'priority': 4},
                    read=[delta(items=[item(content='Original', added_at=None,
                         checked=False, completed_at=None)])], status=status)
                r = g.update_task('task', priority=1, before=before(old))
                self.assertEqual(r.outcome, outcome)
                self.assertIsNone(r.actual.added_at)
                self.assertIsNone(r.actual.completed_at)
                self.assertFalse(r.actual.completed)

    def test_missing_malformed_foreign_status_stops_without_state_guess(self):
        for status in (None, {}, {'ok': True}, [], True, 0, 'success'):
            with self.subTest(status=status):
                g, _ = self.gateway('item_update', {'id': 'task', 'content': 'Changed'},
                    read=[delta(items=[item(content='Changed')], sync_status={'foreign': 'ok'})], status=status)
                op = Operation('item_update', {'id': 'task', 'content': 'Changed'})
                r = g.execute(op, before=before())
                self.assertEqual(r.outcome, Outcome.UNKNOWN)
                self.assertEqual(r.actual.title, 'Changed')
                with self.assertRaises(DomainError):
                    g.execute(op, before=before())

    def test_create_requires_temp_mapping_even_with_matching_existing_text(self):
        for mapping in (None, 'new'):
            with self.subTest(mapping=mapping):
                g, _ = self.gateway('item_add', {'project_id': 'cat', 'content': 'Original',
                    'description': '', 'priority': 3, 'labels': [], 'auto_reminder': False},
                    read=[full(items=[item(content='Original'), item('new', content='Original', parent_id='task')],
                        projects=[project('root', None), project(), project('other')],
                        user={'id': 'u', 'tz_info': {'timezone': 'UTC'}}), delta()], mapping=mapping)
                r = g.create_task('cat', 'Original', before=before())
                self.assertEqual(r.outcome, Outcome.UNKNOWN if mapping is None else Outcome.ACCEPTED)
                self.assertEqual(r.target_id, mapping)

    def test_unique_operation_uuid_and_temp_id(self):
        operations = [Operation('note_add', {'item_id': 'task', 'content': 'Done'}) for _ in range(20)]
        ids = [value for op in operations for value in (op.uuid, op.temp_id)]
        self.assertEqual(len(set(ids)), 40)

    def test_one_destination_nested_move_and_promotion(self):
        task = Item('task', 'cat', 'Task')
        child = Item('child', 'cat', 'Child', 'task')
        parent = Item('parent', 'other', 'Parent')
        step = Item('step', 'other', 'Step', 'parent')
        for dest, args, rows in [
            ({'parent_id': 'step'}, {'id': 'task', 'parent_id': 'step'},
             [item('task', content='Task', project_id='other', parent_id='step'),
              item('child', content='Child', project_id='other', parent_id='task')]),
            ({'project_id': 'other'}, {'id': 'task', 'project_id': 'other'},
             [item('task', content='Task', project_id='other', parent_id=None),
              item('child', content='Child', project_id='other', parent_id='task')])]:
            with self.subTest(dest=dest):
                g, _ = self.gateway('item_move', args, read=[delta(items=rows)])
                r = g.move('task', **dest, before=before(task, child, parent, step))
                self.assertTrue(r.accepted)
                self.assertFalse(r.issues)
                self.assertEqual(r.after.snapshot.items['child'].parent_id, 'task')
                self.assertEqual(r.after.snapshot.items['child'].category_id, 'other')
        with self.assertRaises(DomainError):
            Operation('item_move', {'id': 'task', 'project_id': 'cat', 'parent_id': 'step'})
        with self.assertRaises(DomainError):
            Operation('item_update', {'id': 'task', 'parent_id': 'step'})

    def test_plain_ok_reopen_restored_ancestors_and_completed_step_preserved(self):
        root = Item('root-task', 'cat', 'Parent', completed=True, completed_at=stamp(AT))
        task = Item('task', 'cat', 'Step', 'root-task', completed=True, completed_at=stamp(NEXT))
        sibling = Item('sibling', 'cat', 'Other step', 'root-task', completed=True, completed_at=stamp(AT))
        g, _ = self.gateway('item_uncomplete', {'id': 'task'}, read=[delta(items=[
            item('root-task', content='Parent', checked=False, completed_at=None),
            item('task', content='Step', parent_id='root-task', checked=False, completed_at=None)])])
        r = g.reopen('task', before=before(root, task, sibling))
        self.assertTrue(r.accepted)
        self.assertEqual([i.id for i in r.restored_ancestors], ['root-task'])
        self.assertIsNone(r.actual.completed_at)
        self.assertTrue(r.after.snapshot.items['sibling'].completed)
        self.assertEqual(instant_text(r.after.snapshot.items['sibling'].completed_at), AT)

    def test_recurring_forward_undo_no_reset_and_exact_occurrence_proof(self):
        recurring = due()
        recurring.update(is_recurring=True, string='every day at 10')
        task = Item('task', 'cat', 'Recurring', attention=resolve_remote_due(recurring, 'UTC'))
        old = Occurrence('old', 'task', stamp(AT), True)
        latest = Occurrence('new', 'task', stamp(NEXT), True)
        record = CompletedRecord(replace(task, completed_at=stamp(NEXT)), latest)
        for forward in (True, False):
            hist = History([record])
            g, _ = self.gateway('item_update_date_complete', {'id': 'task',
                'is_forward': int(forward), 'reset_subtasks': 0}, history=hist, status=None)
            r = (g.complete if forward else g.reopen)('task', recurring=True,
                before=before(task, occurrences=[old]), start=START, end=END)
            self.assertEqual(r.outcome, Outcome.UNKNOWN)
            self.assertEqual(r.occurrences, (latest,))
            new = next(e[1] for e in r.evidence if isinstance(e, tuple) and e[0] == 'new completion occurrences')
            self.assertEqual(new, (latest,))
            self.assertEqual(instant_text(new[0].completed_at), NEXT)
            self.assertEqual(hist.calls[0][-1], {'project_id': 'cat'})

    def test_unchanged_recurring_without_command_receipt_is_unknown(self):
        raw = due()
        raw.update(is_recurring=True, string='every day')
        task = Item('task', 'cat', 'Recurring', attention=resolve_remote_due(raw, 'UTC'))
        g, _ = self.gateway('item_update_date_complete', {'id': 'task', 'is_forward': 1,
            'reset_subtasks': 0}, history=History(), status=None)
        r = g.complete('task', recurring=True, before=before(task))
        self.assertEqual(r.outcome, Outcome.UNKNOWN)

    def test_archive_disappearance_completion_then_multiple_own_comments(self):
        for parent_id in (None, 'parent'):
            with self.subTest(parent=parent_id):
                parent = Item('parent', 'cat', 'Parent')
                task = Item('task', 'cat', 'Task', parent_id)
                initial = before(parent, task)
                archived = replace(task, completed=True, completed_at=stamp(NEXT), added_at=None)
                hist = History([CompletedRecord(archived, Occurrence('occ', 'task', stamp(NEXT)))])
                replacement = full(items=[item('parent', content='Parent')], projects=[project('root', None), project(), project('other')],
                    user={'id': 'u', 'tz_info': {'timezone': 'UTC'}})
                g, _ = self.gateway('item_close', {'id': 'task'},
                    read=[replacement, delta()], history=hist)
                r = g.complete('task', before=initial, start=START, end=END)
                self.assertTrue(r.accepted)
                self.assertFalse(r.issues)
                self.assertIs(r.actual, archived)
                self.assertNotIn('task', r.after.snapshot.items)
                self.assertEqual(instant_text(r.actual.completed_at), NEXT)
                for body in ('Done: first', 'Done: second'):
                    comment = Comment('new', 'task', body, stamp(NEXT))
                    g2, _ = self.gateway('note_add', {'item_id': 'task', 'content': body},
                        history=History(comments=[comment]))
                    note_result = g2.create_comment('task', body, before=r.after, known_owners={'task': r.actual})
                    self.assertTrue(note_result.accepted)
                    self.assertFalse(note_result.issues)
                    self.assertIs(note_result.actual, comment)

    def test_completion_empty_or_failed_history_is_accepted_partial(self):
        for hist in (History(), History(failure=True)):
            replacement = full(items=[], projects=[project('root', None), project(), project('other')],
                user={'id': 'u', 'tz_info': {'timezone': 'UTC'}})
            g, _ = self.gateway('item_complete', {'id': 'task'},
                read=[replacement, delta()], history=hist)
            r = g.complete('task', close=False, before=before())
            self.assertTrue(r.partial)

    def test_comment_update_and_direct_delete_without_owner_reopen(self):
        c = Comment('note', 'task', 'Old', stamp(AT))
        for kind, args, comments in [
            ('note_update', {'id': 'note', 'content': 'Edited'}, [Comment('note', 'task', 'Edited', stamp(NEXT))]),
            ('note_delete', {'id': 'note'}, [])]:
            g, _ = self.gateway(kind, args, history=History(comments=comments))
            if kind == 'note_update':
                r = g.update_comment('note', 'Edited', before=before(comments=[c]))
                self.assertEqual(instant_text(r.actual.added_at), NEXT)
            else:
                r = g.delete_comment('note', before=before(comments=[c]))
            self.assertTrue(r.accepted)
            self.assertFalse(r.issues)

    def test_zero_reminder_then_rejection_no_compensating_delete(self):
        att = resolve_remote_due(due(), 'UTC')
        task = Item('task', 'cat', 'Original', attention=att)
        g, _ = self.gateway('reminder_add', {'item_id': 'task', 'type': 'relative', 'minute_offset': 0},
            read=[delta(reminders=[reminder('new')])])
        first = g.create_reminder('task', 0, before=before(task))
        self.assertTrue(first.accepted)
        self.assertEqual(first.actual.minutes, 0)
        g2, _ = self.gateway('reminder_update', {'id': 'new', 'type': 'relative', 'minute_offset': 5},
            status={'error_code': 20, 'error': 'Rejected'})
        second = g2.update_reminder('new', 5, before=first.after)
        self.assertEqual(second.outcome, Outcome.REJECTED)
        self.assertEqual(second.actual.minutes, 0)
        g3, _ = self.gateway('reminder_delete', {'id': 'new'}, read=[delta(reminders=[{'id': 'new', 'is_deleted': True}])])
        third = g3.delete_reminder('new', before=first.after)
        self.assertTrue(third.accepted)
        self.assertIsNone(third.actual)

    def test_direct_task_and_step_delete(self):
        for parent_id in (None, 'parent'):
            p = Item('parent', 'cat', 'Parent')
            t = Item('task', 'cat', 'Task', parent_id)
            g, _ = self.gateway('item_delete', {'id': 'task'}, read=[delta(items=[{'id': 'task', 'is_deleted': True}])])
            r = g.delete_task('task', before=before(p, t))
            self.assertTrue(r.accepted)
            self.assertIsNone(r.actual)

    def test_attention_inclusive_slack_and_actual_precision_preserved(self):
        requested = resolve_remote_due(due(), 'UTC')
        for date, partial in [
            ('2026-10-21T10:00:02.123456789Z', False),
            ('2026-10-21T09:59:58.123456789Z', False),
            ('2026-10-21T10:00:02.123456790Z', True), (None, True)]:
            with self.subTest(date=date):
                returned = due(date) if date else None
                g, _ = self.gateway('item_update', {'id': 'task', 'due': due_arguments(requested)},
                    read=[delta(items=[item(content='Original', due=returned)])])
                r = g.update_task('task', attention=requested, before=before())
                self.assertTrue(r.accepted)
                self.assertEqual(r.partial, partial)
                self.assertEqual(r.actual.attention.raw_due['date'] if date else r.actual.attention, date)
                if partial:
                    self.assertIn('requested attention', r.issues[0])
                    self.assertIn('actual attention', r.issues[0])

    def test_provider_resolves_english_expressions_on_create_and_update(self):
        cases = [
            ('next Wednesday', '2026-10-21', False, None),
            ('next Wednesday at 10', '2026-10-21T10:00:00', False, None),
            ('next Wednesday at 10 Europe/Prague', '2026-10-21T08:00:00Z', False, 'Europe/Prague'),
            ('every day at 10', '2026-10-21T10:00:00', True, None),
            ('every day at 10', None, True, None),
        ]
        for create in (False, True):
            for expression, date, recurring, zone in cases:
                with self.subTest(create=create, expression=expression, date=date):
                    proposed = parse_attention(expression, NOW, 'UTC')
                    self.assertEqual(proposed.kind, 'unresolved')
                    wire_due = {'string': expression, 'lang': 'en'}
                    returned = None if date is None else {
                        'date': date, 'string': expression, 'lang': 'en',
                        'is_recurring': recurring, 'timezone': zone}
                    target = 'new' if create else 'task'
                    args = ({'project_id': 'cat', 'content': 'Scheduled', 'description': '',
                             'priority': 3, 'labels': [], 'auto_reminder': False}
                            if create else {'id': target})
                    args['due'] = wire_due
                    row = item(target, content='Scheduled' if create else 'Original',
                               priority=3, description='', due=returned)
                    reads = ([full(items=[item(content='Original'), row],
                                   projects=[project('root', None), project(), project('other')]), delta()]
                             if create else [delta(items=[row])])
                    g, _ = self.gateway('item_add' if create else 'item_update', args, read=reads)
                    result = (g.create_task('cat', 'Scheduled', attention=proposed, before=before())
                              if create else g.update_task('task', attention=proposed, before=before()))
                    self.assertTrue(result.accepted)
                    self.assertEqual(result.partial, date is None)
                    self.assertIs(result.actual, result.after.snapshot.items[target])
                    if date is not None:
                        self.assertEqual(dict(result.actual.attention.raw_due), returned)
                        self.assertEqual(result.actual.recurring, recurring)

    def test_attention_day_rule_timezone_strict(self):
        proposed = resolve_remote_due(due('2026-10-21T23:59:59Z'), 'UTC')
        for raw in [due('2026-10-22T00:00:00Z'), due('2026-10-21'),
                    {**due('2026-10-21T23:59:59Z'), 'is_recurring': True, 'string': 'every day'},
                    {**due('2026-10-21T23:59:59Z'), 'timezone': 'Europe/Prague'}]:
            g, _ = self.gateway('item_update', {'id': 'task', 'due': due_arguments(proposed)},
                read=[delta(items=[item(content='Original', due=raw)])])
            r = g.update_task('task', attention=proposed, before=before())
            self.assertTrue(r.partial)

    def test_recurrence_preserving_raw_english_due(self):
        old = due()
        old.update(is_recurring=True, string='every day at 10', timezone='Europe/Prague', extra='retained')
        prior = resolve_remote_due(old, 'UTC')
        proposed = resolve_remote_due(due('2026-10-25T10:00:00.000000009Z'), 'UTC')
        wire_due = due_arguments(proposed, prior)
        self.assertEqual(wire_due, {'date': '2026-10-25T10:00:00.000000009Z',
            'timezone': 'Europe/Prague', 'string': 'every day at 10', 'lang': 'en',
            'is_recurring': True, 'extra': 'retained'})
        self.assertEqual(old['date'], '2026-10-21T10:00:00.123456789Z')

    def test_provision_root_category_and_label(self):
        for method, kind, args, resources, target in [
            ('provision_root', 'project_add', {'name': 'New root', 'parent_id': None},
             {'projects': [project('new', None, name='New root')], 'labels': []}, ('New root',)),
            ('provision_category', 'project_add', {'name': 'New category', 'parent_id': 'root'},
             {'projects': [project('new', 'root', name='New category')], 'labels': []}, ('root', 'New category')),
            ('provision_label', 'label_add', {'name': 'waiting'},
             {'projects': [], 'labels': [{'id': 'new', 'name': 'waiting', 'is_deleted': False}]}, ('waiting',))]:
            g, _ = self.gateway(kind, args, read=[{'full_sync': True, 'sync_token': 'full', **resources}, delta()])
            r = getattr(g, method)(*target)
            self.assertTrue(r.accepted)
            self.assertFalse(r.issues)
            self.assertEqual(r.actual.id, 'new')

    def test_lost_create_response_exact_status_and_mapping_on_read(self):
        g, _ = self.gateway('item_add', {'project_id': 'cat', 'content': 'Step',
            'description': '', 'priority': 3, 'labels': [], 'auto_reminder': False, 'parent_id': 'task'},
            lost=True, read=[lambda w: full(items=[item(content='Original'),
                item('new', content='Step', parent_id='task', priority=3)],
                projects=[project('root', None), project(), project('other')],
                user={'id': 'u', 'tz_info': {'timezone': 'UTC'}}, **w.receipt()), delta()])
        r = g.create_step('cat', 'Step', parent_id='task', before=before())
        self.assertTrue(r.accepted)
        self.assertFalse(r.issues)
        self.assertEqual(r.actual.parent_id, 'task')
        self.assertEqual(instant_text(r.actual.added_at), AT)

    def test_lost_response_without_receipt_remains_unknown(self):
        g, _ = self.gateway('item_update', {'id': 'task', 'description': 'Description'},
            lost=True, read=[delta(items=[item(content='Original', description='Description', added_at=NEXT)])])
        r = g.update_task('task', description='Description', before=before())
        self.assertEqual(r.outcome, Outcome.UNKNOWN)
        self.assertEqual(instant_text(r.actual.added_at), NEXT)

    def test_accepted_invalid_after_state_is_partial_without_compensation(self):
        g, _ = self.gateway('item_update', {'id': 'task', 'content': 'Changed'},
            read=[delta(items=[item(content='Changed', priority=99)])])
        r = g.update_task('task', title='Changed', before=before())
        self.assertTrue(r.partial)
        self.assertIsNone(r.after)
        self.assertEqual(r.target_id, 'task')
        self.assertIn('current reconciliation unavailable', r.issues[0])

    def test_same_occurrence_is_not_new_and_accepted_receipt_remains_accepted(self):
        raw = due()
        raw.update(is_recurring=True, string='every day')
        task = Item('task', 'cat', 'Recurring', attention=resolve_remote_due(raw, 'UTC'))
        old = Occurrence('old', 'task', stamp(AT), True)
        hist = History([CompletedRecord(replace(task, completed_at=stamp(AT)), old)])
        g, _ = self.gateway('item_update_date_complete', {'id': 'task', 'is_forward': 1,
            'reset_subtasks': 0}, history=hist)
        r = g.complete('task', before=before(task, occurrences=[old]), start=START, end=END)
        self.assertTrue(r.accepted)
        new = next(e[1] for e in r.evidence if isinstance(e, tuple) and e[0] == 'new completion occurrences')
        self.assertEqual(new, ())
        self.assertEqual(instant_text(r.occurrences[0].completed_at), AT)

    def test_provision_delta_omissions_preserve_full_fields(self):
        g, _ = self.gateway('label_add', {'name': 'waiting'}, read=[
            {'full_sync': True, 'sync_token': 'first', 'projects': [],
             'labels': [{'id': 'new', 'name': 'waiting', 'is_deleted': False}]},
            delta(labels=[{'id': 'new', 'unknown': True}])])
        r = g.provision_label('waiting')
        self.assertTrue(r.accepted)
        self.assertFalse(r.issues)
        self.assertEqual(r.actual.name, 'waiting')

    def test_gateway_through_actual_history_completion_and_archived_comment(self):
        op = Operation('item_close', {'id': 'task'})
        replacement = full(items=[], projects=[project('root', None), project(), project('other')],
            user={'id': 'u', 'tz_info': {'timezone': 'Europe/Prague'}})
        archived = item(content='Original', checked=True, added_at=None, completed_at=NEXT,
                        due=due('2026-10-21T14:00:00.123456789'))
        def response(value):
            return Response(json.dumps(value).encode())
        sync = lambda token: ExpectedRequest('POST', '/sync', 'secret', form={
            'sync_token': token, 'resource_types': RESOURCES})
        http = ControlledHTTP([
            (ExpectedRequest('POST', '/sync', 'secret', form={'commands': json.dumps([op.command()], separators=(',', ':'))}),
             response({'sync_status': {op.uuid: 'ok'}})),
            (sync('prior-token'), response(replacement)),
            (sync('full-token'), response(delta())),
            (ExpectedRequest('GET', '/tasks/completed/by_completion_date', 'secret', query={
                'project_id': 'cat', 'since': '2026-10-20T12:00:00Z',
                'until': '2026-10-20T12:00:01Z', 'limit': '200'}),
             response({'items': [archived], 'unknown': []}))])
        self.addCleanup(http.assert_done)
        r = Gateway(Transport('secret', opener=http), clock=lambda: NOW).execute(
            op, before=before(), start=START, end=END)
        self.assertTrue(r.accepted)
        self.assertFalse(r.issues)
        self.assertIsNone(r.actual.added_at)
        self.assertEqual(instant_text(r.actual.completed_at), NEXT)
        self.assertEqual(r.after.account.timezone, 'Europe/Prague')
        self.assertEqual(r.actual.attention.kind, 'floating')
        self.assertEqual(r.actual.attention.raw_due['date'], '2026-10-21T14:00:00.123456789')
        self.assertEqual(instant_text(r.actual.attention.instant), '2026-10-21T12:00:00.123456Z')
        note_op = Operation('note_add', {'item_id': 'task', 'content': 'Done: finished'})
        # Current scoped REST comments have no required item_id field; posted_at
        # is authoritative null, terminal cursor is explicitly null.
        http2 = ControlledHTTP([
            (ExpectedRequest('POST', '/sync', 'secret', form={'commands': json.dumps([note_op.command()], separators=(',', ':'))}),
             response({'sync_status': {note_op.uuid: 'ok'}, 'temp_id_mapping': {note_op.temp_id: 'comment'}})),
            (sync('delta-token'), response(delta())),
            (ExpectedRequest('GET', '/comments', 'secret', query={'task_id': 'task', 'limit': '200'}),
             response({'results': [{'id': 'comment', 'content': 'Done: finished',
                 'is_deleted': False, 'posted_at': None, 'file_attachment': None}], 'next_cursor': None}))])
        self.addCleanup(http2.assert_done)
        result = Gateway(Transport('secret', opener=http2), clock=lambda: NOW).execute(
            note_op, before=r.after, known_owners={'task': r.actual})
        self.assertTrue(result.accepted)
        self.assertFalse(result.issues)
        self.assertEqual(result.actual.item_id, 'task')
        self.assertIsNone(result.actual.added_at)

    def test_archived_reopen_uses_known_owner_and_ancestor_context(self):
        parent = Item('parent', 'cat', 'Parent', completed=True, completed_at=stamp(AT))
        child = Item('child', 'cat', 'Child', 'parent', completed=True, completed_at=stamp(NEXT))
        initial = before()
        initial = replace(initial, snapshot=replace(initial.snapshot, items={}))
        replacement = full(items=[item('parent', content='Parent', completed_at=None),
            item('child', content='Child', parent_id='parent', completed_at=None)],
            projects=[project('root', None), project(), project('other')],
            user={'id': 'u', 'tz_info': {'timezone': 'UTC'}})
        g, _ = self.gateway('item_uncomplete', {'id': 'child'}, read=[replacement, delta()])
        r = g.reopen('child', before=initial, known_owners={'parent': parent, 'child': child})
        self.assertTrue(r.accepted)
        self.assertFalse(r.issues)
        self.assertEqual([i.id for i in r.restored_ancestors], ['parent'])
        self.assertIsNone(r.actual.completed_at)

    def test_unknown_and_rejected_preserve_nonnull_precise_after(self):
        for status, outcome in [(None, Outcome.UNKNOWN),
            ({'error_code': 20, 'error': 'Rejected'}, Outcome.REJECTED)]:
            g, _ = self.gateway('item_update', {'id': 'task', 'description': 'Text'},
                status=status, read=[delta(items=[item(content='Original', description='Text', added_at=NEXT)])])
            r = g.update_task('task', description='Text', before=before())
            self.assertEqual(r.outcome, outcome)
            self.assertEqual(instant_text(r.actual.added_at), NEXT)
            self.assertIs(r.actual, r.after.snapshot.items['task'])

    def test_local_attention_serialization_keeps_fraction_and_offset_instant(self):
        for expression, expected in [
            ('2026-10-21T12:00:00.123456789+02:00', '2026-10-21T10:00:00.123456789Z'),
            ('1969-12-31T23:59:59.123456789Z', '1969-12-31T23:59:59.123456789Z')]:
            value = parse_attention(expression, NOW, 'UTC')
            self.assertEqual(due_arguments(value)['date'], expected)

    def test_undo_activity_keeps_precise_event_value(self):
        raw = due()
        raw.update(is_recurring=True, string='every day')
        task = Item('task', 'cat', 'Recurring', attention=resolve_remote_due(raw, 'UTC'))
        event = Activity('7', 'item', 'task', 'uncompleted', stamp(NEXT), 'task', 'cat')
        hist = History(activities=[event])
        g, _ = self.gateway('item_update_date_complete', {'id': 'task', 'is_forward': 0,
            'reset_subtasks': 0}, history=hist)
        r = g.reopen('task', before=before(task), start=START, end=END)
        self.assertTrue(r.accepted)
        events = next(e for e in r.evidence if isinstance(e, Retrieval) and e.records == (event,))
        self.assertIs(events.records[0].event_date, event.event_date)
        self.assertEqual(instant_text(events.records[0].event_date), NEXT)

    def test_direct_operation_nonclearing_due_missing_after_is_partial(self):
        op = Operation('item_update', {'id': 'task', 'due': {'string': 'tomorrow'}})
        g, _ = self.gateway('item_update', {'id': 'task', 'due': {'string': 'tomorrow', 'lang': 'en'}})
        r = g.execute(op, before=before())
        self.assertTrue(r.partial)
        self.assertIsNone(r.actual.attention)
        self.assertIn('returned no attention', r.issues[0])

    def test_recurring_requested_occurrence_preserves_rule_in_expected_state(self):
        old = due()
        old.update(is_recurring=True, string='every day at 10')
        task = Item('task', 'cat', 'Recurring', attention=resolve_remote_due(old, 'UTC'))
        requested = resolve_remote_due(due('2026-10-22T10:00:00.123456789Z'), 'UTC')
        returned = {**old, 'date': '2026-10-22T10:00:00.123456789Z'}
        g, _ = self.gateway('item_update_date_complete', {'id': 'task', 'is_forward': 1,
            'reset_subtasks': 0, 'due': returned}, history=History(),
            read=[delta(items=[item(content='Recurring', due=returned)])])
        r = g.complete('task', attention=requested, before=before(task), start=START, end=END)
        self.assertTrue(r.accepted)
        self.assertFalse(r.issues)
        self.assertTrue(r.actual.recurring)

    def test_real_http_transport_serializes_single_uuid_command(self):
        op = Operation('item_update', {'id': 'task', 'content': 'Changed'})
        script = [
            (ExpectedRequest('POST', '/sync', 'secret', form={'commands': json.dumps([op.command()], separators=(',', ':'))}),
             Response(json.dumps({'sync_status': {op.uuid: 'ok'}, 'unknown': True}).encode())),
            (ExpectedRequest('POST', '/sync', 'secret', form={'sync_token': 'prior-token', 'resource_types': RESOURCES}),
             Response(json.dumps(delta(items=[item(content='Changed')])).encode()))]
        http = ControlledHTTP(script)
        self.addCleanup(http.assert_done)
        r = Gateway(Transport('secret', opener=http), clock=lambda: NOW).execute(op, before=before())
        self.assertTrue(r.accepted)
        self.assertEqual(r.actual.title, 'Changed')


if __name__ == '__main__':
    unittest.main()
