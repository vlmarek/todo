"""Lifecycle composition probes; synthetic after-states never execute commands.

The real adapter probes below consume pinned Sync/completed/comment shapes and
reject wrong requests. Domain fakes isolate order and failure attribution only.
"""
from contextlib import nullcontext
from dataclasses import replace
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from todo_lib import domain as d
from todo_lib.adapter.commands import Outcome
from todo_lib.local import LocalError, StateStore
from todo_lib.local.codec import loads
from todo_lib.local.config import Configuration
from todo_lib.syntax import parse
from todo_lib.syntax.parser import UsageError
from todo_lib.workflows.reads import NoMatch, AmbiguityError
from todo_lib.syntax.input import InputError
from todo_lib.workflows.lifecycle import LifecycleWorkflow
from todo_lib.workflows.sync import Synchronizer, SyncError
from tests.support.commands import before
from tests.support.current import item, note, full, delta, due
from tests.support import sync as fixtures

from tests.support.lifecycle import (
    CURSOR,
    AT,
    END,
    LATER,
    streams,
    recurring,
    FakeSync,
    FakeGateway,
    CommandRequest,
    LifecycleSupport,
)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.lock = patch('todo_lib.workflows.lifecycle.exclusive_lock', return_value=nullcontext())
        self.lock.start()
        self.addCleanup(self.lock.stop)


    def workflow(self, snapshot, *, outcomes=(), after=(), answer='yes\n', tty=True, hidden=()):
        sync, gateway = FakeSync(snapshot, after), FakeGateway(outcomes)
        out = streams(answer, tty)
        workflow = LifecycleWorkflow(sync, gateway=gateway, settings=Configuration('root', ('cat',), hidden), streams=out)
        return workflow, sync, gateway, out

    def test_gateway_refusal_keeps_whole_sequence_unattempted(self):
        from todo_lib.adapter.commands import UnsubmittedOperation
        snapshot = before(d.Item('root-task', 'cat', 'Root'),
                          d.Item('child', 'cat', 'Child', 'root-task')).snapshot
        workflow, sync, gateway, out = self.workflow(snapshot)
        with patch.object(gateway, 'execute', side_effect=UnsubmittedOperation('pre-dispatch refusal')) as execute:
            result = workflow.execute(['done', 'Root', '--comment', 'progress'])
        self.assertEqual(result.status, 1)
        self.assertEqual([o.outcome for o in result.operations], ['unattempted'] * 3)
        self.assertEqual(sync.calls, [('local', {})])
        self.assertEqual(execute.call_count, 1)

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
        self.assertEqual(sync.calls[0][0], 'local')
        self.assertFalse(any(kind == 'refresh' for kind, _ in sync.calls))

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
        self.assertEqual(wf.execute(['done', 'R']).status, 0)
        self.assertEqual(len(gateway.calls), 2)

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
        self.assertEqual(out.stderr.getvalue(), '')
        self.assertEqual([op.type for op, _ in gateway.calls], ['item_delete'])
        wf, _, gateway, out = self.workflow(before(recurring(), occurrences=[d.Occurrence('e', 'R', AT, True)]).snapshot, tty=False)
        self.assertEqual(wf.execute(['delete', '--yes', 'R']).status, 0)
        self.assertEqual(len(gateway.calls), 1)
        self.assertEqual(out.stderr.getvalue(), '')
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
            self.assertEqual(out.stderr.getvalue(), '')
            self.assertFalse(gateway.calls)


class AdapterLifecycleTests(LifecycleSupport, unittest.TestCase):
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
        wf, _ = self.workflow([complete.step(),
            f.sync('delta-token', full(items=[item('A', added_at=fixtures.CREATED)])),
            f.sync('full-token', delta()),
            f.completed([fixtures.completed_b()]),
            f.comments(),
            comment1.step(),
            f.sync('delta-token', delta()),
            self.comments('B', rest),
            f.completed([]),
            comment2.step(),
            f.sync('delta-token', delta()),
            self.comments('B', rest),
            f.sync('delta-token', delta()),
            f.completed([]), f.deletion_activity(),
            self.comments('B', rest)], setup=[f.sync('delta-token', delta())])
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
        wf, http = self.workflow([], setup=[f.sync('delta-token', delta()),
            f.completed([child])], recent=True)
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
        wf, _ = self.workflow([reopen.step(),
            f.sync('delta-token', delta(items=restored))], setup=[f.sync('delta-token', delta()),
            f.completed([a, b, child])], recent=True)
        result = wf.execute(['step', '--undone', 'A', 'B'])
        self.assertEqual(result.status, 0)
        self.assertIn('Also reopened:', result.document.stdout)
        self.assertIn('task: A', result.document.stdout)
        state = self.store.load_consistent_state()
        self.assertFalse(state.snapshot.items['A'].completed)
        self.assertFalse(state.snapshot.items['B'].completed)
        self.assertTrue(state.snapshot.items['D'].completed)
        self.assertEqual(d.instant_text(state.snapshot.comments['own'].added_at), fixtures.COMMENT)

    def test_saved_recent_evidence_uses_exact_cursor_end_and_direct_deletion(self):
        from tests.support.history import Expected
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
        wf, _ = self.workflow([deletion.step(),
            f.sync('delta-token', delta(items=[item('eligible', is_deleted=True)]))], setup=[f.sync('delta-token', delta()),
            (Expected('/tasks/completed/by_completion_date', query), {'items': rows, 'unknown': 1}),
            self.comments('eligible', []),
            self.comments('end', [own])], recent=True, now=END)
        result = wf.execute(['delete', '--yes', 'eligible'])
        self.assertEqual(result.status, 0)
        self.assertEqual(len(deletion.commands), 1)
        self.assertIn('eligible [completed]', self.out.stdout.getvalue())
        self.assertNotIn('Older completed descendants', self.out.stdout.getvalue())
        self.assertEqual(self.out.stderr.getvalue(), '')
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
            f.deletion_activity('end', cursor=CURSOR),
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

    def test_cancelled_deletion_preserves_saved_evidence_for_offline_consumers(self):
        f = self.fixture
        archived = item('C', parent_id='A', checked=True, completed_at=fixtures.DONE,
                        added_at=fixtures.CREATED)
        self.out = streams('no\n')
        wf, http = self.workflow([], setup=[f.sync('delta-token', delta()),
            f.completed([archived]),
            self.comments('C', [])], recent=True)
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

    def test_invalid_required_history_stops_before_remote_mutation(self):
        path = self.store.root / 'history.json'
        path.write_bytes(b'{invalid')
        before = path.read_bytes()
        wf, http = self.workflow([])
        with self.assertRaises(LocalError):
            wf.execute(['delete', '--yes', 'B'])
        self.assertFalse(http.requests)
        self.assertEqual(path.read_bytes(), before)

    def recurring_steps(self, command, normalized, *, include_after=True):
        f = self.fixture
        old = {**fixtures.completed_b(), 'checked': False, 'due': due('2026-10-25', timezone=None, string='every day', is_recurring=True)}
        new = {**fixtures.completed_b(), 'checked': False, 'due': normalized}
        new['completed_at'] = '2026-10-22T12:00:00.123456789012349Z'
        rows = [old, new]
        self.establish([f.sync('delta-token', delta()), f.completed([old]), self.activity()])
        steps = [command.step(), f.sync('delta-token', delta(items=[item('B', parent_id='A', due=normalized, added_at=fixtures.CREATED)])),
            f.completed(rows)]
        if include_after:
            if command.status is None:
                # Unknown outcomes retain the required full read-only recovery.
                steps += [f.sync('delta-token', delta(items=[item('B', parent_id='A', due=normalized, added_at=fixtures.CREATED)])),
                          f.completed(rows)]
            steps += [self.activity()]
        return steps

    def test_recurring_accepted_late_publication_failure_requires_manual_restore_no_replay(self):
        f = self.fixture
        recurrence = self.recurrence_seed()
        normalized = {**recurrence, 'date': '2026-10-26'}
        command = CommandRequest(self, 'item_update_date_complete', {'id': 'B', 'is_forward': 1, 'reset_subtasks': 0})
        wf, http = self.workflow(self.recurring_steps(command, normalized))
        real_replace = os.replace
        destinations, saved = {}, f.bytes()
        binding_count = 0
        def fail_later_binding(source, destination):
            nonlocal binding_count
            name = Path(destination).name
            if name == 'binding.json':
                binding_count += 1
            destinations[name] = Path(source).read_bytes()
            if name == 'binding.json' and binding_count == 1:
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
            if calls == 1:
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

    def test_activity_only_recent_reopen_then_dual_source_discovery_cannot_resurrect(self):
        f = self.fixture
        recurrence = self.recurrence_seed()
        completion = dict(id=901, object_type='item', object_id='B', event_type='completed',
                          event_date='2026-10-21T18:11:14.719113Z')
        undo = dict(id=902, object_type='item', object_id='B', event_type='uncompleted',
                    event_date='2026-10-21T18:11:15Z')
        counterpart = {**fixtures.completed_b(), 'checked': False, 'due': recurrence,
                       'completed_at': '2026-10-21T18:11:14.704186Z'}
        command = CommandRequest(self, 'item_update_date_complete',
            {'id': 'B', 'is_forward': 0, 'reset_subtasks': 0})
        restored = item('B', parent_id='A', due={**recurrence, 'date': '2026-10-24'},
                        added_at=fixtures.CREATED)
        events = [completion, undo]
        wf, http = self.workflow([command.step(),
            f.sync('delta-token', delta(items=[restored])),
            f.completed([counterpart]),
            self.activity(records=events)], setup=[f.sync('delta-token', delta()),
            f.completed([]),
            self.activity(records=[completion]),
            f.completed([])], recent=True)
        result = wf.execute(['reopen', 'B'])
        http.assert_done()
        self.assertEqual(result.status, 0)
        self.assertEqual([o.outcome for o in result.operations], ['accepted'])
        self.assertEqual(len(command.commands), 1)
        self.store = StateStore(self.store.root)
        for _ in range(2):
            again, http = self.workflow([], setup=[f.sync('delta-token', delta()),
            f.completed([counterpart]),
            self.activity(records=events),
            f.completed([counterpart])], recent=True)
            with self.assertRaises(NoMatch):
                again.execute(['reopen', 'B'])
            http.assert_done()
            observed = list(self.store.load_history().snapshot.occurrences.values())
            self.assertEqual(len(observed), 1)
            self.assertTrue(observed[0].undone)
            self.assertEqual(d.instant_text(observed[0].completed_at), completion['event_date'])
            self.assertEqual(observed[0].undo_ids, ('undo:902',))

    def test_anonymous_source_order_latest_reopen_survives_refresh_and_reload(self):
        from todo_lib.workflows.reads import recent_candidates
        f = self.fixture
        self.recurrence_seed()
        completion = dict(object_type='item', object_id='B', event_type='completed',
                          event_date='2026-10-21T18:11:14.719113Z')
        events = [dict(completion) for _ in range(11)]  # omitted IDs and extra_data
        sync, http = f.workflow([f.sync('delta-token', delta()), f.completed([]),
                                 self.activity(records=events)])
        sync.refresh()
        http.assert_done()
        self.store = StateStore(self.store.root)
        state = self.store.load_consistent_state()
        latest = max(state.snapshot.occurrences.values(), key=lambda o: o.source_order)
        self.assertEqual(latest.source_order, 10)
        candidates = recent_candidates(state.snapshot, 'B', fixtures.CURSOR, fixtures.NOW)
        self.assertEqual([c.occurrence_id for c in candidates], [latest.id])
        undo = dict(completion, event_type='uncompleted', event_date='2026-10-21T18:11:15Z')
        for count in (1, 1, 2, 2):
            with self.subTest(undos=count):
                wf, http = self.workflow([], setup=[f.sync('delta-token', delta()),
            f.completed([]),
            self.activity(records=events + [dict(undo) for _ in range(count)]),
            f.completed([])], recent=True)  # bounded discovery must not restore older eligibility
                with self.assertRaises(NoMatch):
                    wf.execute(['reopen', 'B'])
                http.assert_done()  # no mutation request was attempted
                self.store = StateStore(self.store.root)
                state = self.store.load_consistent_state()
                for snapshot in (state.snapshot, state.history.snapshot):
                    observed = sorted(snapshot.occurrences.values(), key=lambda o: o.source_order)
                    self.assertEqual(len(observed), 11)
                    self.assertEqual(sum(o.undone for o in observed), count)
                    self.assertTrue(observed[-1].undone)
                    self.assertEqual(sum(len(o.undo_ids) for o in observed), count)
                    self.assertEqual(recent_candidates(snapshot, 'B', fixtures.CURSOR, fixtures.NOW), ())

    def test_recurring_latest_exact_undo_through_real_adapter(self):
        f = self.fixture
        recurrence = self.recurrence_seed()
        from tests.support.reminders import absolute, FIXED
        before_reminder = self.store.load_consistent_state().snapshot
        reminder = d.Reminder('absolute', 'B', type='absolute',
            due=d.resolve_reminder_due(FIXED, before_reminder.account.timezone), notify_uid='recipient', is_urgent=True)
        # Add via actual Sync, then round-trip the pending model before undo.
        seed = full(items=[item('A', added_at=fixtures.CREATED), item('B', parent_id='A', due=recurrence, added_at=fixtures.CREATED)],
                    notes=[note('own', 'B', posted_at=fixtures.CREATED)], reminders=[absolute('absolute', FIXED, item_id='B')])
        self.seed(seed)
        older = {**fixtures.completed_b(), 'checked': False, 'due': recurrence,
                 'completed_at': '2026-10-21T12:00:00.123456789012348Z'}
        newer = {**older, 'completed_at': fixtures.DONE}
        event = dict(id=None, object_type='item', object_id='B', event_type='uncompleted',
                     event_date='2026-10-21T12:00:00.123456789012350Z', parent_project_id='cat')
        command = CommandRequest(self, 'item_update_date_complete', {'id': 'B', 'is_forward': 0, 'reset_subtasks': 0})
        normalized = {**recurrence, 'date': '2026-10-24'}
        restored = item('B', parent_id='A', due=normalized, added_at=fixtures.CREATED)
        wf, _ = self.workflow([command.step(),
            f.sync('delta-token', delta(items=[restored])),
            f.completed([newer, older]),
            self.activity(records=[event])], setup=[f.sync('delta-token', delta()),
            f.completed([newer, older]),
            self.activity(),
            f.completed([newer, older])], recent=True)
        result = wf.execute(['reopen', 'B'])
        self.assertEqual(result.status, 0)
        self.assertEqual(self.store.load_history().snapshot.reminders['absolute'], reminder)
        occurrences = list(self.store.load_consistent_state().snapshot.occurrences.values())
        self.assertEqual(len(occurrences), 2)
        self.assertEqual({d.instant_text(o.completed_at): o.undone for o in occurrences},
                         {older['completed_at']: False, newer['completed_at']: True})
        self.assertEqual(len(command.commands), 1)
        # A second reopen must not erase the observed undo during bounded
        # discovery, or fall back to the earlier occurrence.
        again, _ = self.workflow([], setup=[f.sync('delta-token', delta()),
            f.completed([newer, older]),
            self.activity(records=[event]),
            f.completed([newer, older])], recent=True)
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
                if binding_count == 1:
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
