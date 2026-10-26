"""Lifecycle composition probes; synthetic after-states never execute commands.

The real adapter probes below consume pinned Sync/completed/comment shapes and
reject wrong requests. Domain fakes isolate order and failure attribution only.
"""
from contextlib import nullcontext
from dataclasses import replace
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from todo_lib import domain as d, presentation as p
from todo_lib.adapter.commands import Gateway, Result, Outcome
from todo_lib.adapter.current import retrieve
from todo_lib.local import empty_history, prepare_candidates, exclusive_lock, LocalError
from todo_lib.local.codec import loads
from todo_lib.syntax import parse
from todo_lib.syntax.parser import UsageError
from todo_lib.workflows.reads import NoMatch, AmbiguityError
from todo_lib.syntax.input import InputError
from todo_lib.workflows.lifecycle import LifecycleWorkflow
from todo_lib.workflows.sync import Synchronizer, SyncError
from tests.adapter.commands.test_commands import before
from tests.adapter.current.test_current import item, note, full, delta, due, BINDING
from tests.workflows.sync import test_sync as fixtures

stamp = d.instant_from_wire
CURSOR = stamp('2026-10-22T12:00:00.123456781Z')
AT = stamp('2026-10-22T12:00:00.123456782Z')
END = stamp('2026-10-22T12:00:00.123456783Z')
LATER = stamp('2026-10-22T12:00:00.123456784Z')


class TTY(io.StringIO):
    def isatty(self):
        return True


def streams(answer='yes\n', tty=True):
    stream = TTY if tty else io.StringIO
    return p.OriginalStreams(stream(answer), stream(), io.StringIO())


def recurring(identity='R', parent=None, labels=()):
    return d.Item(identity, 'cat', identity, parent_id=parent,
        labels=frozenset(labels), attention=d.resolve_remote_due(
            due('2026-10-25', timezone=None, string='every day', is_recurring=True), 'UTC'))


class FakeSync:
    def __init__(self, snapshot, after=()):
        self.store = SimpleNamespace(root=Path('/unused'))
        self.transport = None
        self.snapshot = snapshot
        self.after = iter(after)
        self.calls = []

    def value(self):
        return SimpleNamespace(snapshot=self.snapshot, now=END,
            state=SimpleNamespace(cursor=CURSOR, sync_token='token'))

    def refresh_locked(self, **kwargs):
        self.calls.append(('refresh', kwargs))
        return self.value()

    def reconcile_accepted_locked(self):
        self.calls.append(('accepted', {}))
        value = next(self.after, self.snapshot)
        if isinstance(value, Exception):
            raise value
        self.snapshot = value
        return self.value()


class FakeGateway:
    def __init__(self, outcomes=()):
        self.outcomes = iter(outcomes)
        self.calls = []

    def execute(self, op, **kwargs):
        self.calls.append((op, kwargs))
        value = next(self.outcomes, Outcome.ACCEPTED)
        if isinstance(value, Result):
            return replace(value, operation=op)
        return Result(value, op, actual=(d.Comment('created', op.args['item_id'], op.args['content'])
                                        if op.type == 'note_add' and value == Outcome.ACCEPTED else None))


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.lock = patch('todo_lib.workflows.lifecycle.exclusive_lock', return_value=nullcontext())
        self.lock.start()
        self.addCleanup(self.lock.stop)
        self.history = patch('todo_lib.workflows.lifecycle._recent_snapshot', side_effect=lambda sync, result, hidden: result.snapshot)
        self.history.start()
        self.addCleanup(self.history.stop)

    def workflow(self, snapshot, *, outcomes=(), after=(), answer='yes\n', tty=True, hidden=()):
        sync, gateway = FakeSync(snapshot, after), FakeGateway(outcomes)
        out = streams(answer, tty)
        workflow = LifecycleWorkflow(sync, gateway=gateway, settings=SimpleNamespace(hidden_from_now=hidden), streams=out)
        return workflow, sync, gateway, out

    def test_exact_nested_preview_postorder_and_root_only_comments(self):
        root = d.Item('root-task', 'cat', 'Root')
        z = d.Item('z', 'cat', 'Newest', root.id, added_at=LATER)
        a = d.Item('a', 'cat', 'Older', root.id, added_at=AT)
        deep = d.Item('deep', 'cat', 'Deep', z.id)
        u = d.Item('u', 'cat', 'Unknown', root.id)
        done = d.Item('done', 'cat', 'Already completed', root.id, completed=True, completed_at=AT)
        snapshot = before(root, a, z, u, deep, done).snapshot
        wf, sync, gateway, out = self.workflow(snapshot)
        result = wf.execute(['done', 'Root', '--comment', ' first body ', 'second body'])
        self.assertEqual(result.status, 0)
        self.assertEqual(out.stdout.getvalue(), 'Root\n  Newest\n    Deep\n  Older\n  Unknown\nComplete this open subtree? [y/yes]: ')
        self.assertEqual([op.args.get('id') for op, _ in gateway.calls[:5]], ['deep', 'z', 'a', 'u', root.id])
        self.assertEqual([op.type for op, _ in gateway.calls[:5]], ['item_complete'] * 5)
        self.assertEqual([op.args for op, _ in gateway.calls[5:]], [
            {'item_id': root.id, 'content': 'Done: first body'},
            {'item_id': root.id, 'content': 'Done: second body'}])
        self.assertEqual(len([c for c in sync.calls if c[0] == 'accepted']), 7)

    def test_known_and_null_time_ties_use_stable_ids(self):
        s = before(d.Item('P', 'cat', 'Parent'),
            d.Item('z', 'cat', 'Known Z', 'P', added_at=AT),
            d.Item('a', 'cat', 'Known A', 'P', added_at=AT),
            d.Item('y', 'cat', 'Unknown Y', 'P'),
            d.Item('b', 'cat', 'Unknown B', 'P')).snapshot
        wf, _, gateway, out = self.workflow(s)
        self.assertEqual(wf.execute(['done', 'Parent']).status, 0)
        self.assertEqual([op.args['id'] for op, _ in gateway.calls], ['a', 'z', 'b', 'y', 'P'])
        self.assertTrue(out.stdout.getvalue().startswith('Parent\n  Known A\n  Known Z\n  Unknown B\n  Unknown Y\n'))

    def test_all_recurring_descendants_block_before_prompt(self):
        s = before(d.Item('P', 'cat', 'Parent'), d.Item('C', 'cat', 'Child', 'P'),
                   recurring('R', 'C'), recurring('S', 'P')).snapshot
        wf, _, gateway, out = self.workflow(s)
        with self.assertRaises(d.DomainError) as error:
            wf.execute(['done', 'Parent'])
        self.assertIn('Child\n    R', str(error.exception))
        self.assertIn('S', str(error.exception))
        self.assertNotIn('[y/yes]', out.stdout.getvalue())
        self.assertFalse(gateway.calls)

    def test_nonleaf_explicit_confirmation_no_bypass_and_leaf_no_prompt(self):
        s = before(d.Item('P', 'cat', 'Parent'), d.Item('C', 'cat', 'Child', 'P')).snapshot
        for answer, tty in [('\n', True), ('no\n', True), ('', True), ('yes\n', False)]:
            with self.subTest(answer=answer, tty=tty):
                wf, _, gateway, _ = self.workflow(s, answer=answer, tty=tty)
                with self.assertRaises(InputError):
                    wf.execute(['done', 'Parent'])
                self.assertFalse(gateway.calls)
        wf, _, gateway, out = self.workflow(s, tty=False)
        result = wf.execute(['done', 'Child'])
        self.assertEqual(result.status, 0)
        self.assertEqual(out.stdout.getvalue(), '')
        with self.assertRaises(UsageError):
            wf.execute(['done', 'Parent', '--yes'])
        self.assertEqual(len(gateway.calls), 1)

    def test_all_comment_bodies_validate_before_first_mutation(self):
        request = parse(['done', 'Original'])
        from todo_lib.syntax.parser import TextGroup
        request = replace(request, groups=(TextGroup('comment', (), ('valid', '\x00bad')),))
        wf, sync, gateway, _ = self.workflow(before().snapshot)
        with self.assertRaises(d.DomainError):
            wf.execute(request)
        self.assertEqual(sync.calls, [])
        self.assertFalse(gateway.calls)

    def test_tree_rejection_and_unknown_stop_and_classify(self):
        s = before(d.Item('P', 'cat', 'Parent'), d.Item('A', 'cat', 'First', 'P'),
                   d.Item('B', 'cat', 'Second', 'P')).snapshot
        for outcome in [Outcome.REJECTED, Outcome.UNKNOWN]:
            wf, _, gateway, _ = self.workflow(s, outcomes=[Outcome.ACCEPTED, outcome])
            result = wf.execute(['done', 'Parent', '--comment', 'body'])
            self.assertEqual(result.status, 1)
            self.assertEqual([o.outcome for o in result.operations], ['accepted', outcome.value, 'unattempted', 'unattempted'])
            self.assertEqual(len(gateway.calls), 2)

    def test_later_comment_failure_keeps_completion_and_earlier_comment(self):
        s = before().snapshot
        wf, _, gateway, _ = self.workflow(s, outcomes=[Outcome.ACCEPTED, Outcome.ACCEPTED, Outcome.REJECTED])
        result = wf.execute(['done', 'Original', '--comment', 'one body', 'two body', 'three body'])
        self.assertEqual([o.outcome for o in result.operations], ['accepted', 'accepted', 'rejected', 'unattempted'])
        self.assertIn('Done: one body', result.document.stdout)
        self.assertNotIn('Done: two body', result.document.stdout)
        self.assertEqual(len(gateway.calls), 3)

    def test_recurring_root_with_ordinary_child_and_visible_waiting_sibling(self):
        s = before(recurring(labels=['waiting']), recurring('S', labels=['waiting']), d.Item('C', 'cat', 'Child', 'R')).snapshot
        wf, _, gateway, _ = self.workflow(s)
        result = wf.execute(['done', 'R'])
        self.assertEqual(result.status, 0)
        self.assertEqual([op.type for op, _ in gateway.calls], ['item_complete', 'item_update_date_complete'])
        self.assertEqual(gateway.calls[-1][0].args, {'id': 'R', 'is_forward': 1, 'reset_subtasks': 0})
        wf, _, gateway, _ = self.workflow(s, hidden=['Category'])
        with self.assertRaises(d.DomainError):
            wf.execute(['done', 'R'])
        self.assertFalse(gateway.calls)

    def test_waiting_recurring_parent_predicts_completed_ordinary_children(self):
        parent = recurring(labels=['waiting'])
        child = d.Item('C', 'cat', 'Child', 'R', attention=d.resolve_remote_due(
            due('2026-10-25', timezone=None), 'UTC'))
        s = before(parent, child).snapshot
        wf, _, gateway, _ = self.workflow(s)
        self.assertEqual(wf.execute(['done', 'R']).status, 0)
        self.assertEqual(len(gateway.calls), 2)

    def test_predictable_undo_waiting_parent_conflict_is_preflight(self):
        parent = recurring('P', labels=['waiting'])
        child = recurring('R', 'P')
        event = d.Occurrence('event', 'R', AT, recurring=True)
        s = before(parent, child, occurrences=[event]).snapshot
        wf, _, gateway, _ = self.workflow(s)
        with self.assertRaisesRegex(d.DomainError, 'precedes waiting ancestor'):
            wf.execute(['reopen', 'R'])
        self.assertFalse(gateway.calls)

    def test_reopen_exact_interval_latest_undo_and_literal_selector(self):
        ordinary = [d.Item(k, 'cat', k, completed=True, completed_at=t) for k, t in
                    [('cursor', CURSOR), ('eligible', AT), ('end', END), ('future', LATER)]]
        s = before(*ordinary, d.Item('open', 'cat', 'open')).snapshot
        for title in ['cursor', 'future', 'open']:
            wf, _, gateway, _ = self.workflow(s)
            with self.assertRaises(NoMatch):
                wf.execute(['reopen', title])
            self.assertFalse(gateway.calls)
        for title in ['eligible', 'end']:
            wf, _, gateway, _ = self.workflow(s)
            self.assertEqual(wf.execute(['reopen', title]).status, 0)
            self.assertEqual(gateway.calls[0][0].type, 'item_uncomplete')
        r = replace(recurring(), title='--unusual')
        # Reverse lexical IDs and two instants within one microsecond.
        events = [d.Occurrence('z-old', 'R', AT, True), d.Occurrence('a-new', 'R', END, True)]
        s = before(r, occurrences=events).snapshot
        wf, _, gateway, _ = self.workflow(s)
        self.assertEqual(wf.execute(['reopen', '--literal', '--unusual']).status, 0)
        self.assertEqual(gateway.calls[0][0].args, {'id': 'R', 'is_forward': 0, 'reset_subtasks': 0})
        for latest in [replace(events[-1], completed_at=LATER), replace(events[-1], undone=True)]:
            wf, _, gateway, _ = self.workflow(before(r, occurrences=[events[0], latest]).snapshot)
            with self.assertRaises(NoMatch):
                wf.execute(['reopen', '--literal', '--unusual'])
            self.assertFalse(gateway.calls)

    def test_complete_reopen_ancestor_chain_collision(self):
        parent = d.Item('P', 'cat', 'Parent', completed=True, completed_at=AT)
        child = d.Item('C', 'cat', 'Child', 'P', completed=True, completed_at=AT)
        collision = d.Item('other', 'cat', 'PARENT')
        wf, _, gateway, _ = self.workflow(before(parent, child, collision).snapshot)
        with self.assertRaises(d.DomainError):
            wf.execute(['reopen', 'Child'])
        self.assertFalse(gateway.calls)

    def test_ordinary_reopen_validates_selected_and_restored_ancestor_hiding(self):
        waiting = d.Item('W', 'cat', 'Waiting', labels=frozenset({'waiting'}),
            attention=d.resolve_remote_due(due('2026-10-25', timezone=None), 'UTC'))
        for dated_owner in ('C', 'P'):
            for day, valid in [('2026-10-24', False), ('2026-10-25', True)]:
                with self.subTest(dated_owner=dated_owner, day=day):
                    parent = d.Item('P', 'cat', 'Parent', 'W', completed=True, completed_at=AT)
                    child = d.Item('C', 'cat', 'Child', 'P', completed=True, completed_at=AT)
                    items = {i.id: i for i in (waiting, parent, child)}
                    items[dated_owner] = replace(items[dated_owner], attention=d.resolve_remote_due(
                        due(day, timezone=None), 'UTC'))
                    snapshot = before(*items.values()).snapshot
                    d.validate(snapshot)
                    wf, _, gateway, _ = self.workflow(snapshot)
                    if valid:
                        self.assertEqual(wf.execute(['reopen', 'Child']).status, 0)
                        self.assertEqual(gateway.calls[0][0].type, 'item_uncomplete')
                    else:
                        with self.assertRaisesRegex(d.DomainError, 'precedes waiting ancestor'):
                            wf.execute(['reopen', 'Child'])
                        self.assertFalse(gateway.calls)
                    self.assertTrue(snapshot.items['C'].completed)
                    self.assertTrue(snapshot.items['P'].completed)

    def test_step_lifecycle_completed_parent_context_and_child_eligibility(self):
        # Parent context may predate the cursor; only the selected child needs
        # an eligible occurrence. Canonical and retained forms select the same ID.
        parent = d.Item('P', 'cat', 'Parent', completed=True, completed_at=CURSOR)
        for action, command, operation in [('undone', 'reopen', 'item_uncomplete'),
                                            ('delete', 'delete', 'item_delete')]:
            for at in (AT, CURSOR, LATER):
                for alias in (False, True):
                    with self.subTest(action=action, at=at, alias=alias):
                        child = d.Item('C', 'cat', 'Child', 'P', completed=True, completed_at=at)
                        wf, _, gateway, _ = self.workflow(before(parent, child).snapshot, tty=False)
                        argv = (['step', '--' + action, 'Parent', 'Child'] if alias else [command, 'Child'])
                        if command == 'delete':
                            argv.append('--yes')
                        if at == AT:
                            self.assertEqual(wf.execute(argv).status, 0)
                            self.assertEqual([(op.type, op.args) for op, _ in gateway.calls],
                                             [(operation, {'id': 'C'})])
                        else:
                            with self.assertRaises(NoMatch):
                                wf.execute(argv)
                            self.assertFalse(gateway.calls)
        other = replace(parent, id='Q')
        child = d.Item('C', 'cat', 'Child', 'P', completed=True, completed_at=AT)
        wf, _, gateway, _ = self.workflow(before(parent, other, child).snapshot, tty=False)
        with self.assertRaises(AmbiguityError):
            wf.execute(['step', '--undone', 'Parent', 'Child'])
        self.assertFalse(gateway.calls)
        wf, _, gateway, _ = self.workflow(before(parent, child).snapshot)
        with self.assertRaises(NoMatch):
            wf.execute(['step', '--done', 'Parent', 'Child'])
        self.assertFalse(gateway.calls)

    def test_delete_yes_preview_bounds_recurring_once_and_direct_only(self):
        root = d.Item('P', 'cat', 'Parent')
        children = [d.Item(k, 'cat', k, 'P', completed=True, completed_at=t) for k, t in
                    [('cursor', CURSOR), ('eligible', AT), ('end', END), ('future', LATER)]]
        s = before(root, *children, d.Item('open', 'cat', 'open', 'P')).snapshot
        wf, _, gateway, out = self.workflow(s, tty=False)
        self.assertEqual(wf.execute(['delete', '--yes', 'Parent']).status, 0)
        text = out.stdout.getvalue()
        self.assertIn('eligible [completed]', text)
        self.assertIn('end [completed]', text)
        self.assertIn('open', text)
        self.assertNotIn('cursor [completed]', text)
        self.assertNotIn('future [completed]', text)
        self.assertNotIn('Older completed descendants', text)
        self.assertIn('Older completed descendants', out.stderr.getvalue())
        self.assertEqual([op.type for op, _ in gateway.calls], ['item_delete'])
        wf, _, gateway, out = self.workflow(before(recurring(), occurrences=[d.Occurrence('e', 'R', AT, True)]).snapshot, tty=False)
        self.assertEqual(wf.execute(['delete', '--yes', 'R']).status, 0)
        self.assertEqual(len(gateway.calls), 1)
        self.assertIn('Older completed descendants', out.stderr.getvalue())
        for title in ['cursor', 'future']:
            wf, _, gateway, _ = self.workflow(s)
            with self.assertRaises(NoMatch):
                wf.execute(['delete', '--yes', title])
            self.assertFalse(gateway.calls)

    def test_delete_cancellation_and_noninteractive_never_mutate(self):
        for answer, tty in [('', True), ('n\n', True), ('yes\n', False)]:
            wf, _, gateway, out = self.workflow(before().snapshot, answer=answer, tty=tty)
            with self.assertRaises(InputError):
                wf.execute(['delete', 'Original'])
            self.assertIn('Older completed descendants', out.stderr.getvalue())
            self.assertFalse(gateway.calls)


class CommandRequest:
    """Dynamic UUID only; semantic request and response state are independent."""
    def __init__(self, case, kind, args, status='ok', target=None):
        from tests.support.http import Response
        self.case, self.kind, self.args = case, kind, args
        self.status, self.target = status, target
        self.response = Response()
        self.commands = []

    def check(self, request, timeout):
        from urllib.parse import parse_qs
        from uuid import UUID
        from tests.support.http import ExpectedRequest
        wire = parse_qs(request.data.decode())
        self.case.assertEqual(set(wire), {'commands'})
        commands = json.loads(wire['commands'][0])
        self.case.assertEqual(len(commands), 1)
        op = commands[0]
        self.case.assertEqual(op['type'], self.kind)
        self.case.assertEqual(op['args'], self.args)
        self.case.assertEqual(str(UUID(op['uuid'])), op['uuid'])
        self.case.assertEqual(set(op), {'type', 'uuid', 'args'} | ({'temp_id'} if self.kind.endswith('_add') else set()))
        ExpectedRequest('POST', '/sync', 'secret', form={'commands': wire['commands'][0]}).check(request, timeout)
        self.commands.append(op)
        response = {} if self.status is None else {'sync_status': {op['uuid']: self.status}}
        if self.target:
            self.case.assertEqual(str(UUID(op['temp_id'])), op['temp_id'])
            response['temp_id_mapping'] = {op['temp_id']: self.target}
        self.response.write(json.dumps(response).encode())
        self.response.seek(0)

    def step(self):
        return self, self.response


class AdapterLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SyncTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.store
        self.out = streams()

    def seed(self, raw, cursor=fixtures.CURSOR):
        transport, _ = self.fixture.boundary([self.fixture.sync('*', raw),
                                             self.fixture.sync('full-token', delta())])
        observed = retrieve(transport, BINDING)
        with exclusive_lock('setup', self.store.root):
            self.store.publish_snapshot(prepare_candidates(observed.snapshot,
                empty_history(observed.snapshot), account_display='Person',
                sync_token=observed.sync_token, synced_at=fixtures.INITIAL))
            self.store.write_cursor(cursor)

    def workflow(self, steps, *, now=fixtures.NOW):
        sync, http = self.fixture.workflow(steps, now=now)
        return LifecycleWorkflow(sync, gateway=Gateway(sync.transport, clock=lambda: now), streams=self.out), http

    def comments(self, owner, records):
        from tests.adapter.history.test_history import Expected
        return Expected('/comments', [('task_id', owner), ('limit', '200')]), {'results': records, 'next_cursor': None}

    def activity(self, identity='B', records=()):
        from tests.adapter.history.test_history import Expected
        query = [('object_type', 'item'), ('object_id', identity),
            ('date_from', '2026-10-20T00:00:00Z'), ('date_to', '2026-10-22T12:00:01Z'),
            ('annotate_notes', 'true'), ('limit', '200'),
            ('object_event_types', 'item:completed'), ('object_event_types', 'item:uncompleted'),
            ('object_event_types', 'note:added'), ('object_event_types', 'note:updated'),
            ('object_event_types', 'note:deleted')]
        return Expected('/activities', query), {'results': list(records), 'next_cursor': None}

    def test_archived_disappearance_done_comments_sequential_partial_failure(self):
        f = self.fixture
        complete = CommandRequest(self, 'item_complete', {'id': 'B'})
        comment1 = CommandRequest(self, 'note_add', {'item_id': 'B', 'content': 'Done: first body'}, target='new-comment')
        comment2 = CommandRequest(self, 'note_add', {'item_id': 'B', 'content': 'Done: second body'},
                                  status={'error_code': 22, 'error': 'rejected'})
        # Scoped REST notes deliberately have no invented item_id field.
        rest = [dict(id='new-comment', content='Done: first body', posted_at=fixtures.COMMENT,
                     file_attachment=None, is_deleted=False)]
        current_note = note('new-comment', 'B', content='Done: first body', posted_at=fixtures.COMMENT)
        wf, _ = self.workflow([
            f.sync('delta-token', delta()),
            complete.step(), f.sync('delta-token', full(items=[item('A', added_at=fixtures.CREATED)])),
            f.sync('full-token', delta()), f.completed([fixtures.completed_b()]),
            *f.external(),
            comment1.step(), f.sync('delta-token', delta()), self.comments('B', rest),
            f.sync('delta-token', delta(notes=[current_note])),
            comment2.step(), f.sync('delta-token', delta()), self.comments('B', rest),
            f.sync('delta-token', delta())])
        result = wf.execute(['done', 'B', '--comment', 'first body', 'second body', 'third body'])
        self.assertEqual(result.status, 1)
        self.assertEqual([o.outcome for o in result.operations], ['accepted', 'accepted', 'rejected', 'unattempted'])
        state = self.store.load_consistent_state()
        for s in (state.snapshot, state.history.snapshot):
            self.assertTrue(s.items['B'].completed)
            self.assertFalse(s.items['A'].completed)
            self.assertEqual(d.instant_text(s.items['A'].added_at), fixtures.CREATED)
            self.assertEqual(d.instant_text(s.comments['new-comment'].added_at), fixtures.COMMENT)
            self.assertEqual(s.comments['new-comment'].item_id, 'B')
        self.assertEqual(len(comment2.commands), 1)
        self.assertIn('Completed step: B', result.document.stdout)

    def test_ordinary_reopen_hiding_preflight_preserves_real_store(self):
        f = self.fixture
        parent = item('A', labels=['waiting'], due=due('2026-10-25', timezone=None))
        child = item('B', parent_id='A', checked=True, completed_at=fixtures.DONE,
                     due=due('2026-10-24', timezone=None))
        self.seed(full(items=[parent, child]))
        wf, http = self.workflow([f.sync('delta-token', delta()), f.completed([child])])
        with self.assertRaisesRegex(d.DomainError, 'precedes waiting ancestor'):
            wf.execute(['reopen', 'B'])
        http.assert_done()
        # A subsequent offline consumer sees the coherent completed child;
        # no accepted mutation or repair/replay is needed.
        saved = wf.synchronizer.read_local().snapshot
        self.assertTrue(saved.items['B'].completed)
        self.assertFalse(saved.items['A'].completed)

    def test_plain_ok_reopen_reports_actual_ancestors_and_preserves_completed_descendant(self):
        f = self.fixture
        a = item('A', checked=True, completed_at=fixtures.DONE, added_at=fixtures.CREATED)
        b = fixtures.completed_b()
        child = item('D', parent_id='B', checked=True, completed_at=fixtures.DONE)
        self.seed(full(items=[a, b, child], notes=[note('own', 'B', posted_at=fixtures.COMMENT)]))
        reopen = CommandRequest(self, 'item_uncomplete', {'id': 'B'})
        restored = [item('A', added_at=fixtures.CREATED), item('B', parent_id='A', added_at=fixtures.CREATED)]
        wf, _ = self.workflow([f.sync('delta-token', delta()), f.completed([a, b, child]),
            reopen.step(), f.sync('delta-token', delta(items=restored)),
            f.sync('delta-token', delta(items=restored))])
        result = wf.execute(['step', '--undone', 'A', 'B'])
        self.assertEqual(result.status, 0)
        self.assertIn('Also reopened:', result.document.stdout)
        self.assertIn('task: A', result.document.stdout)
        state = self.store.load_consistent_state()
        self.assertFalse(state.snapshot.items['A'].completed)
        self.assertFalse(state.snapshot.items['B'].completed)
        self.assertTrue(state.snapshot.items['D'].completed)
        self.assertEqual(d.instant_text(state.snapshot.comments['own'].added_at), fixtures.COMMENT)

    def test_real_recent_discovery_uses_exact_cursor_end_and_direct_deletion(self):
        from tests.adapter.history.test_history import Expected
        f = self.fixture
        self.store.write_cursor(CURSOR)
        rows = [item(k, checked=True, completed_at=d.instant_text(t), added_at=None) for k, t in
                [('at-cursor', CURSOR), ('eligible', AT), ('end', END), ('future', LATER)]]
        rows[2].update(parent_id='A', added_at=fixtures.CREATED)
        own = dict(id='surviving', content='Keep for report', posted_at=fixtures.COMMENT,
                   file_attachment=None, is_deleted=False)
        query = [('project_id', 'cat'), ('since', '2026-10-22T12:00:00Z'),
                 ('until', '2026-10-22T12:00:01Z'), ('limit', '200')]
        deletion = CommandRequest(self, 'item_delete', {'id': 'eligible'})
        wf, _ = self.workflow([f.sync('delta-token', delta()),
            (Expected('/tasks/completed/by_completion_date', query), {'items': rows, 'unknown': 1}),
            self.comments('eligible', []), self.comments('end', [own]),
            deletion.step(), f.sync('delta-token', delta(items=[item('eligible', is_deleted=True)])),
            f.sync('delta-token', delta(items=[item('eligible', is_deleted=True)])),
            (Expected('/tasks/completed/by_completion_date', query), {'items': []}),
            self.comments('end', [own])], now=END)
        result = wf.execute(['delete', '--yes', 'eligible'])
        self.assertEqual(result.status, 0)
        self.assertEqual(len(deletion.commands), 1)
        self.assertIn('eligible [completed]', self.out.stdout.getvalue())
        self.assertNotIn('Older completed descendants', self.out.stdout.getvalue())
        self.assertIn('Older completed descendants', self.out.stderr.getvalue())
        saved = self.store.load_consistent_state()
        for snapshot in (saved.snapshot, saved.history.snapshot):
            self.assertIn('end', snapshot.items)
            self.assertNotIn('eligible', snapshot.items)
            self.assertNotIn('at-cursor', snapshot.items)
            self.assertNotIn('future', snapshot.items)
            self.assertEqual(snapshot.items['end'].parent_id, 'A')
            self.assertEqual(d.instant_text(snapshot.items['end'].completed_at), d.instant_text(END))
            self.assertEqual(d.instant_text(snapshot.items['end'].added_at), fixtures.CREATED)
            self.assertEqual(snapshot.comments['surviving'].body, 'Keep for report')
            self.assertEqual(d.instant_text(snapshot.comments['surviving'].added_at), fixtures.COMMENT)
            self.assertTrue(any(o.item_id == 'end' and d.instant_text(o.completed_at) == d.instant_text(END)
                                for o in snapshot.occurrences.values()))
        self.assertEqual(d.instant_text(saved.cursor), d.instant_text(CURSOR))
        # A fresh Synchronizer, with no mutation gateway, retains the observation
        # even when active state and the next bounded page both omit the archive.
        sync, http = f.workflow([f.sync('*', fixtures.open_tree()),
            f.sync('full-token', delta()),
            (Expected('/tasks/completed/by_completion_date', query), {'items': []}),
            self.comments('end', [own])], now=END)
        recovered = sync.refresh(clear_cache=True)
        http.assert_done()
        self.assertIn('end', recovered.history.snapshot.items)
        self.assertIn('surviving', Synchronizer(None, self.store, clock=lambda: END).read_local().snapshot.comments)

    def recurrence_seed(self):
        recurrence = due('2026-10-25', timezone=None, string='every day', is_recurring=True)
        self.seed(full(items=[item('A', added_at=fixtures.CREATED),
            item('B', parent_id='A', added_at=fixtures.CREATED, due=recurrence)],
            notes=[note('own', 'B', posted_at=fixtures.CREATED)]))
        return recurrence

    def test_cancelled_deletion_retains_bounded_discovery_for_offline_consumers(self):
        f = self.fixture
        archived = item('C', parent_id='A', checked=True, completed_at=fixtures.DONE,
                        added_at=fixtures.CREATED)
        self.out = streams('no\n')
        wf, http = self.workflow([f.sync('delta-token', delta()),
            f.completed([archived]), self.comments('C', [])])
        from todo_lib.syntax.input import Cancelled
        with self.assertRaises(Cancelled):
            wf.execute(['delete', 'C'])
        http.assert_done()
        saved = Synchronizer(None, self.store, clock=lambda: fixtures.NOW).read_local()
        self.assertTrue(saved.history.snapshot.items['C'].completed)
        self.assertEqual(saved.history.snapshot.items['C'].parent_id, 'A')
        self.assertIn('own', saved.history.snapshot.comments)
        self.assertEqual(d.instant_text(saved.history.snapshot.items['C'].added_at), fixtures.CREATED)
        self.assertEqual(d.instant_text(saved.state.cursor), d.instant_text(fixtures.CURSOR))

    def test_discovery_publication_failure_stops_before_remote_mutation(self):
        f = self.fixture
        archived = item('C', parent_id='A', checked=True, completed_at=fixtures.DONE,
                        added_at=fixtures.CREATED)
        # Reset between the two actual-store fault boundaries; do not infer a
        # usable old set once destination replacement has begun.
        original = f.bytes()
        for late in (False, True):
            with self.subTest(late=late):
                for name, content in original.items():
                    f.put(name, content)
                wf, http = self.workflow([f.sync('delta-token', delta()),
                    f.completed([archived]), self.comments('C', [])])
                real_replace = os.replace
                saved, destinations = {}, {}
                refreshed = False
                def fail_discovery(source, destination):
                    nonlocal refreshed
                    name = Path(destination).name
                    if refreshed:
                        destinations[name] = Path(source).read_bytes()
                        if name == ('binding.json' if late else 'cache.json'):
                            raise OSError('controlled discovery replacement failure')
                    result = real_replace(source, destination)
                    if name == 'binding.json' and not refreshed:
                        saved.update(f.bytes())
                        refreshed = True
                    return result
                with patch('todo_lib.local.safety.os.replace', side_effect=fail_discovery):
                    with self.assertRaises(SyncError) as caught:
                        wf.execute(['delete', '--yes', 'C'])
                http.assert_done()  # No delete, reopen, completion or undo sent.
                failure = caught.exception
                self.assertEqual(failure.remote_outcome, 'unattempted')
                self.assertEqual(failure.publication_started, late)
                self.assertEqual(failure.refresh_permitted, not late)
                if not late:
                    self.assertEqual(f.bytes(), saved)
                    self.assertIn('own', wf.synchronizer.read_local().history.snapshot.comments)
                else:
                    after = f.bytes()
                    for name in ('cache.json', 'history.json'):
                        self.assertEqual(after[name], destinations[name])
                        data = loads(after[name])  # Complete individual files.
                        self.assertIn('C', data['snapshot']['items'])
                        self.assertIn('own', data['snapshot']['comments'])
                    self.assertEqual(after['binding.json'], saved['binding.json'])
                    self.assertEqual(after['report-cursor'], saved['report-cursor'])
                    with self.assertRaises(LocalError):
                        Synchronizer(None, self.store).read_local()
                    self.assertIn('restore a consistent saved set', str(failure))

    def recurring_steps(self, command, normalized, *, include_after=True):
        f = self.fixture
        old = {**fixtures.completed_b(), 'checked': False, 'due': due('2026-10-25', timezone=None, string='every day', is_recurring=True)}
        new = {**fixtures.completed_b(), 'checked': False, 'due': normalized}
        new['completed_at'] = '2026-10-22T12:00:00.123456789012349Z'
        rows = [old, new]
        steps = [f.sync('delta-token', delta()), f.completed([old]), self.activity(),
            command.step(), f.sync('delta-token', delta(items=[item('B', parent_id='A', due=normalized, added_at=fixtures.CREATED)])),
            f.completed(rows)]
        if include_after:
            steps += [f.sync('delta-token', delta(items=[item('B', parent_id='A', due=normalized, added_at=fixtures.CREATED)])),
                      f.completed(rows), self.activity()]
        return steps

    def test_recurring_accepted_late_publication_failure_requires_manual_restore_no_replay(self):
        f = self.fixture
        recurrence = self.recurrence_seed()
        normalized = {**recurrence, 'date': '2026-10-26'}
        command = CommandRequest(self, 'item_update_date_complete', {'id': 'B', 'is_forward': 1, 'reset_subtasks': 0})
        wf, http = self.workflow(self.recurring_steps(command, normalized))
        real_replace = os.replace
        destinations, saved = {}, {}
        binding_count = 0
        def fail_later_binding(source, destination):
            nonlocal binding_count
            name = Path(destination).name
            if name == 'binding.json':
                binding_count += 1
            if binding_count == 1 and name == 'binding.json':
                value = real_replace(source, destination)
                saved.update(f.bytes())
                return value
            if binding_count >= 1:
                destinations[name] = Path(source).read_bytes()
            if name == 'binding.json' and binding_count == 2:
                raise OSError('controlled later binding replacement')
            return real_replace(source, destination)
        with patch('todo_lib.local.safety.os.replace', side_effect=fail_later_binding):
            result = wf.execute(['done', 'B', '--comment', 'later body'])
        self.assertEqual(result.status, 1)
        self.assertEqual([o.outcome for o in result.operations], ['accepted', 'unattempted'])
        self.assertIsInstance(result.failure, SyncError)
        self.assertTrue(result.failure.publication_started)
        self.assertFalse(result.failure.refresh_permitted)
        self.assertEqual(result.failure.remote_outcome, 'accepted')
        self.assertIn('restore a consistent saved set', str(result.failure))
        self.assertNotIn('previous cache was not replaced', str(result.failure).lower())
        after = f.bytes()
        self.assertEqual(after['binding.json'], saved['binding.json'])
        self.assertEqual(after['report-cursor'], saved['report-cursor'])
        for name in ['cache.json', 'history.json']:
            self.assertEqual(after[name], destinations[name])
            raw = loads(after[name])
            self.assertEqual(raw['snapshot']['items']['A']['added_at'], fixtures.CREATED)
            self.assertEqual(raw['snapshot']['comments']['own']['added_at'], fixtures.CREATED)
            self.assertEqual(raw['snapshot']['comments']['own']['body'], 'own note')
        self.assertIn('refused mixed set', f.child_process(mixed=True))
        count = len(http.requests)
        with self.assertRaises(SyncError) as error:
            wf.synchronizer.refresh()
        self.assertEqual(error.exception.phase, 'local validation')
        self.assertEqual(len(http.requests), count)
        # Explicit manual restoration is modeled by the operator restoring the
        # saved consistent files. Read-only refresh then observes remote truth.
        for name, data in saved.items():
            f.put(name, data)
        recovery, recovery_http = f.workflow([
            f.sync('delta-token', delta(items=[item('B', parent_id='A', due=normalized, added_at=fixtures.CREATED)])),
            f.completed([{**fixtures.completed_b(), 'checked': False, 'due': normalized}]), self.activity()])
        recovery.refresh()
        self.assertEqual(len(command.commands), 1)
        self.assertEqual(len(recovery_http.requests), 3)
        self.assertEqual(self.store.load_consistent_state().snapshot.items['B'].attention.date_value.isoformat(), '2026-10-26')

    def test_recurring_accepted_prepublication_failure_preserves_prior_files(self):
        recurrence = self.recurrence_seed()
        normalized = {**recurrence, 'date': '2026-10-26'}
        command = CommandRequest(self, 'item_update_date_complete', {'id': 'B', 'is_forward': 1, 'reset_subtasks': 0})
        wf, _ = self.workflow(self.recurring_steps(command, normalized))
        original_prepare = __import__('todo_lib.workflows.sync', fromlist=['prepare_candidates']).prepare_candidates
        saved, calls = {}, 0
        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                saved.update(self.fixture.bytes())
                raise LocalError('controlled candidate failure')
            return original_prepare(*args, **kwargs)
        with patch('todo_lib.workflows.sync.prepare_candidates', side_effect=fail_second):
            result = wf.execute(['done', 'B', '--comment', 'later body'])
        self.assertEqual([o.outcome for o in result.operations], ['accepted', 'unattempted'])
        self.assertEqual(self.fixture.bytes(), saved)
        self.assertFalse(result.failure.publication_started)
        self.assertTrue(result.failure.saved_state_available)
        self.assertEqual(result.failure.remote_outcome, 'accepted')
        self.assertEqual(len(command.commands), 1)
        self.assertFalse(wf.synchronizer.read_local().snapshot.items['B'].completed)

    def test_recurring_latest_exact_undo_through_real_adapter(self):
        f = self.fixture
        recurrence = self.recurrence_seed()
        older = {**fixtures.completed_b(), 'checked': False, 'due': recurrence,
                 'completed_at': '2026-10-21T12:00:00.123456789012348Z'}
        newer = {**older, 'completed_at': fixtures.DONE}
        event = dict(id=None, object_type='item', object_id='B', event_type='uncompleted',
                     event_date='2026-10-21T12:00:00.123456789012350Z', parent_project_id='cat')
        command = CommandRequest(self, 'item_update_date_complete', {'id': 'B', 'is_forward': 0, 'reset_subtasks': 0})
        normalized = {**recurrence, 'date': '2026-10-24'}
        restored = item('B', parent_id='A', due=normalized, added_at=fixtures.CREATED)
        wf, _ = self.workflow([f.sync('delta-token', delta()), f.completed([newer, older]), self.activity(),
            f.completed([newer, older]), command.step(), f.sync('delta-token', delta(items=[restored])),
            f.completed([newer, older]), self.activity(records=[event]),
            f.sync('delta-token', delta(items=[restored])), f.completed([newer, older]), self.activity(records=[event])])
        result = wf.execute(['reopen', 'B'])
        self.assertEqual(result.status, 0)
        occurrences = list(self.store.load_consistent_state().snapshot.occurrences.values())
        self.assertEqual(len(occurrences), 2)
        self.assertEqual({d.instant_text(o.completed_at): o.undone for o in occurrences},
                         {older['completed_at']: False, newer['completed_at']: True})
        self.assertEqual(len(command.commands), 1)
        # A second reopen must not erase the observed undo during bounded
        # discovery, or fall back to the earlier occurrence.
        again, _ = self.workflow([f.sync('delta-token', delta()), f.completed([newer, older]),
            self.activity(records=[event]), f.completed([newer, older])])
        with self.assertRaises(NoMatch):
            again.execute(['reopen', 'B'])
        self.assertEqual(len(command.commands), 1)

    def test_invalid_server_normalization_preserves_acceptance_and_stops_comments(self):
        f = self.fixture
        recurrence = due('2026-10-25', timezone=None, string='every day', is_recurring=True)
        parent = item('A', added_at=fixtures.CREATED, labels=['waiting'],
                      due=due('2026-10-24', timezone=None))
        self.seed(full(items=[parent, item('B', parent_id='A', due=recurrence, added_at=fixtures.CREATED)],
                       notes=[note('own', 'B', posted_at=fixtures.CREATED)]))
        normalized = {**recurrence, 'date': '2026-10-23'}
        command = CommandRequest(self, 'item_update_date_complete', {'id': 'B', 'is_forward': 1, 'reset_subtasks': 0})
        # Gateway and synchronizer independently see the invalid normalization;
        # the accepted UUID receipt remains accepted in both failure domains.
        steps = self.recurring_steps(command, normalized, include_after=False)
        steps += [f.sync('delta-token', delta(items=[item('B', parent_id='A', due=normalized, added_at=fixtures.CREATED)]))]
        wf, _ = self.workflow(steps)
        result = wf.execute(['done', 'B', '--comment', 'later body'])
        self.assertEqual(result.status, 1)
        self.assertEqual([o.outcome for o in result.operations], ['accepted', 'unattempted'])
        self.assertIn('repair the reported remote state externally', result.document.stderr)
        self.assertEqual(result.failure.remote_outcome, 'accepted')
        self.assertEqual(len(command.commands), 1)
        self.assertEqual(self.store.load_consistent_state().snapshot.items['B'].attention.date_value.isoformat(), '2026-10-25')
        repaired = {**recurrence, 'date': '2026-10-26'}
        recovery, _ = f.workflow([f.sync('delta-token', delta(items=[item('B', parent_id='A', due=repaired, added_at=fixtures.CREATED)])),
            f.completed([{**fixtures.completed_b(), 'checked': False, 'due': repaired}]), self.activity()])
        recovery.refresh()
        self.assertEqual(len(command.commands), 1)
        self.assertEqual(self.store.load_consistent_state().snapshot.items['B'].attention.date_value.isoformat(), '2026-10-26')

    def test_unknown_recurring_outcome_survives_actual_late_publication_failure(self):
        recurrence = self.recurrence_seed()
        normalized = {**recurrence, 'date': '2026-10-26'}
        # An observed occurrence is not UUID proof of this command's acceptance.
        command = CommandRequest(self, 'item_update_date_complete',
            {'id': 'B', 'is_forward': 1, 'reset_subtasks': 0}, status=None)
        wf, http = self.workflow(self.recurring_steps(command, normalized))
        real_replace, binding_count = os.replace, 0
        def fail_second_binding(source, destination):
            nonlocal binding_count
            if Path(destination).name == 'binding.json':
                binding_count += 1
                if binding_count == 2:
                    raise OSError('controlled late unknown-outcome publication failure')
            return real_replace(source, destination)
        with patch('todo_lib.local.safety.os.replace', side_effect=fail_second_binding):
            result = wf.execute(['done', 'B', '--comment', 'later body'])
        self.assertEqual(result.status, 1)
        self.assertEqual([o.outcome for o in result.operations], ['unknown', 'unattempted'])
        self.assertEqual(result.failure.remote_outcome, 'unknown')
        self.assertTrue(result.failure.publication_started)
        self.assertIn('refused mixed set', self.fixture.child_process(mixed=True))
        count = len(http.requests)
        with self.assertRaises(SyncError):
            wf.synchronizer.refresh()
        self.assertEqual(len(http.requests), count)
        self.assertEqual(len(command.commands), 1)
