"""Public report composition through real adapters, renderer and protected stores.

Synthetic endpoint fixtures use the retained API-v1 evidence cited by the shared
adapter fixtures. Expected checks reject query drift and invented endpoints.
"""
from io import StringIO
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from todo_lib import domain as d
from todo_lib.local import LocalError, StateStore, exclusive_lock
from todo_lib.presentation import OriginalStreams, OutputError
from todo_lib.workflows.report import Reporter
from todo_lib.workflows.sync import Synchronizer, SyncError
from tests.workflows.sync.test_sync import SyncTests, NOW, CURSOR, CREATED, completed_b
from tests.adapter.current.test_current import full, delta, item, due
from tests.adapter.history.test_history import Expected

START = '2026-10-22T12:00:00.123456789012341Z'
FIRST = '2026-10-22T12:00:00.123456789012344Z'
LAST = '2026-10-22T12:00:00.123456789012349Z'
END = '2026-10-22T12:00:00.123456789012350Z'
NEWER = '2026-10-22T12:00:00.123456789012351Z'


def event(identity, at, kind='updated', owner='B', obj='own', typ='note'):
    return dict(id=identity, object_type=typ, object_id=obj, event_type=kind,
                event_date=at, parent_item_id=owner, parent_project_id='cat',
                extra_data={'content': 'annotation is not current text'})


def limits(access=True, days=-1):
    return dict(current=dict(activity_log=access, activity_log_limit=days, reminders=False))


class Reports(unittest.TestCase):
    # Shared setup observes actual current endpoints before publishing initialization.
    setUp = SyncTests.setUp
    put = SyncTests.put
    sync = SyncTests.sync
    boundary = SyncTests.boundary
    def streams(self, out=None):
        return OriginalStreams(StringIO(), out or StringIO(), StringIO())

    def requests(self, *, events=(), rows=(), days=-1, access=True, comments=None,
                 cursor=CURSOR, now=NOW, current_items=None, current_notes=None):
        lower = min((cursor, self.store.load_consistent_state().synced_at), key=d.instant_key)
        lo = d.instant_text(d.instant_datetime(lower).replace(microsecond=0))
        hi = '2026-10-22T12:00:01Z'
        cq = [('project_id', 'cat'), ('since', lo), ('until', hi), ('limit', '200')]
        aq = [('date_from', lo), ('date_to', hi),
              ('annotate_notes', 'true'), ('limit', '200')]
        aq += [('object_event_types', x) for x in ('item:completed', 'item:uncompleted', 'note:added', 'note:updated', 'note:deleted')]
        active = current_items if current_items is not None else [item('A'), item('B', parent_id='A')]
        steps = [self.sync('*', full(items=active, notes=current_notes or [], user_plan_limits=limits(access, days))),
                 self.sync('full-token', delta())]
        if access and days != 0:
            steps += [(Expected('/tasks/completed/by_completion_date', cq), {'items': list(rows)}),
                      (Expected('/activities', aq), {'results': list(events), 'next_cursor': None})]
            for owner in ('A', 'B'):
                records = [] if owner == 'A' else (comments if comments is not None else [dict(id='own', content='Current post-boundary text', posted_at=CREATED, is_deleted=False, file_attachment=None)])
                steps.append((Expected('/comments', [('task_id', owner), ('limit', '200')]),
                              {'results': records, 'next_cursor': None}))
        return steps

    def run_report(self, steps, args=(), streams=None, now=NOW):
        transport, _ = self.boundary(steps)
        streams = streams or self.streams()
        result = Reporter(transport, self.store, clock=lambda: now, streams=streams).run(args)
        return result, streams

    def test_preview_latest_edit_current_text_and_exact_window(self):
        self.store.write_cursor(d.instant_from_wire(START))
        before = (self.root / 'report-cursor').read_bytes()
        events = [event(1, LAST), event(900, FIRST), event(2, START), event(3, NEWER)]
        result, streams = self.run_report(self.requests(events=events, cursor=d.instant_from_wire(START)))
        self.assertFalse(result.finalized)
        self.assertEqual((self.root / 'report-cursor').read_bytes(), before)
        self.assertEqual(streams.stdout.getvalue().count('Current post-boundary text'), 1)
        self.assertNotIn('annotation', streams.stdout.getvalue())
        self.assertIn('Finished\n  None.', streams.stdout.getvalue())
        self.assertIn('Hidden\n  None.', streams.stdout.getvalue())
        self.assertIn('own', self.store.load_history().snapshot.comments)

    def test_final_output_flush_cursor_cleanup_and_newer_pending_context(self):
        # Produce pending observations through T08, then finalize within that same
        # microsecond. No preseeded history/eligibility substitutes for discovery.
        transport, _ = self.boundary([self.sync('delta-token', full(items=[item('A'), item('B', parent_id='A')], user_plan_limits=limits())), self.sync('full-token', delta())])
        Synchronizer(transport, self.store, clock=lambda: d.instant_from_wire(NEWER)).refresh()
        self.store.write_cursor(d.instant_from_wire(START))
        self.assertEqual(d.instant_text(self.store.load_history().observations['B']), NEWER)
        # Preview must retain this T08-produced context and the exact cursor bytes.
        cursor_bytes = (self.root / 'report-cursor').read_bytes()
        with patch('todo_lib.workflows.report.prune_history', side_effect=AssertionError('preview pruning')):
            self.run_report(self.requests(events=[event(900, FIRST), event(1, LAST), event(3, NEWER)],
                cursor=d.instant_from_wire(START)))
        self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor_bytes)
        preview_history = self.store.load_history()
        self.assertEqual(d.instant_text(preview_history.observations['B']), NEWER)
        self.assertIn('own', preview_history.snapshot.comments)
        # New synchronization does not reduce the newer pending observation.
        steps = self.requests(events=[event(900, FIRST), event(1, LAST), event(3, NEWER)], cursor=d.instant_from_wire(START))
        steps[0] = (self.sync('*', full())[0], steps[0][1])
        order = []
        original_cursor = self.store.write_cursor
        original_history = self.store.save_history
        class Output(StringIO):
            def flush(out):
                order.append('flush')
                return super().flush()
        def cursor(value):
            self.assertIn('Hidden', streams.stdout.getvalue())
            self.assertIn('flush', order)
            order.append('cursor')
            original_cursor(value)
        def history(value, **kw):
            self.assertEqual(order[-1], 'cursor')
            order.append('cleanup')
            return original_history(value, **kw)
        streams = self.streams(Output())
        with patch.object(self.store, 'write_cursor', cursor), patch.object(self.store, 'save_history', history):
            result, _ = self.run_report(steps, ['--final'], streams)
        self.assertTrue(result.finalized)
        loaded = StateStore(self.root).load_consistent_state()
        self.assertEqual(d.instant_text(loaded.cursor), END)
        self.assertEqual(d.instant_text(loaded.history.observations['B']), NEWER)
        self.assertEqual(set(loaded.history.snapshot.items), {'A', 'B'})

    def test_empty_final_advances_and_prunes(self):
        result, streams = self.run_report(self.requests(comments=[]), ['--final'])
        self.assertTrue(result.finalized)
        self.assertEqual(d.instant_key(self.store.load_cursor()), d.instant_key(NOW))
        self.assertFalse(self.store.load_history().snapshot.items)
        self.assertEqual(streams.stdout.getvalue().count('None.'), 3)

    def test_failures_before_finalization_preserve_cursor_and_pending(self):
        for failure in ('render', 'write', 'flush', 'pipe', 'cursor', 'interrupt'):
            with self.subTest(failure=failure):
                before = (self.root / 'report-cursor').read_bytes()
                streams = self.streams()
                target = 'todo_lib.workflows.report.render_report'
                error = ValueError('render')
                if failure == 'cursor':
                    target, error = 'todo_lib.local.store.StateStore.write_cursor', LocalError('cursor')
                elif failure == 'interrupt':
                    error = KeyboardInterrupt()
                elif failure in ('write', 'flush', 'pipe'):
                    method = 'flush' if failure == 'flush' else 'write'
                    setattr(streams.stdout, method, lambda *a: (_ for _ in ()).throw(BrokenPipeError('output')))
                    target, error = 'todo_lib.workflows.report.prune_history', AssertionError('must not prune')
                with patch(target, side_effect=error):
                    with self.assertRaises((ValueError, LocalError, OutputError, KeyboardInterrupt)):
                        self.run_report(self.requests(events=[event(1, LAST)]), ['--final'], streams)
                self.assertEqual((self.root / 'report-cursor').read_bytes(), before)
                pending = self.store.load_history()
                self.assertIn('B', pending.snapshot.items)
                self.assertIn('own', pending.snapshot.comments)

    def test_cleanup_failure_keeps_successful_output_cursor(self):
        with patch.object(self.store, 'save_history', side_effect=LocalError('injected cleanup')):
            result, streams = self.run_report(self.requests(), ['--final'])
        self.assertTrue(result.finalized)
        self.assertTrue(result.warnings)
        self.assertIn('extra retained data is safe', streams.stderr.getvalue())
        self.assertEqual(d.instant_key(self.store.load_cursor()), d.instant_key(NOW))
        self.assertIn('B', self.store.load_history().snapshot.items)

    def test_capabilities_and_retention(self):
        for access, days, success in ((False, -1, False), (False, 7, False), (True, 0, False), (True, -1, True), (True, 7, True)):
            with self.subTest(access=access, days=days):
                steps = self.requests(access=access, days=days)
                if success:
                    result, streams = self.run_report(steps)
                    self.assertEqual('keeps 7 days' in streams.stderr.getvalue(), days == 7)
                else:
                    with self.assertRaises(SyncError) as caught:
                        self.run_report(steps)
                    self.assertIn('history', str(caught.exception))
        # Suppression never changes the hard retention failure. No history call.
        self.put('config', b'[main]\nproject=root\ndefault_sections=cat\nhidden_from_now=\n[report]\nwarn_limited_history=false\n')
        steps = self.requests(days=1)[:2]
        with self.assertRaisesRegex(SyncError, 'earlier than retained'):
            self.run_report(steps)
        # Exactly one elapsed day is valid, including all fractional precision.
        start = '2026-10-21T12:00:00.123456789012350Z'
        _, streams = self.run_report(self.requests(days=1), ['--since', start])
        self.assertNotIn('warning', streams.stderr.getvalue())

    def test_local_set_missing_corrupt_noop_and_show_without_cache(self):
        (self.root / 'cache.json').unlink()
        for old, label in ((None, 'none'), (b'broken\n', 'corrupted')):
            if old is None:
                (self.root / 'report-cursor').unlink()
            else:
                self.put('report-cursor', old)
            before = (self.root / 'history.json').read_bytes()
            _, streams = self.run_report([], ['--set-cursor', START, '--yes'])
            self.assertIn('Previous report cursor: ' + label, streams.stdout.getvalue())
            self.assertEqual(streams.stderr.getvalue().count('warning:'), 1)
            self.assertEqual((self.root / 'history.json').read_bytes(), before)
            with self.assertRaisesRegex(LocalError, 'already'):
                self.run_report([], ['--set-cursor', START, '--yes'])
            _, streams = self.run_report([], ['--show-cursor'])
            self.assertIn('Report cursor:', streams.stdout.getvalue())


    def test_recurring_pairing_deep_comments_and_current_roles(self):
        active = [item('A'), item('B', parent_id='A', due=due(is_recurring=True)),
                  item('C', parent_id='B'), item('D', parent_id='C'), item('E', parent_id='D')]
        rows = [item('B', parent_id='A', completed_at=FIRST, due=due(is_recurring=True)),
                item('B', parent_id='A', completed_at=LAST, due=due(is_recurring=True))]
        events = [event(900, FIRST, 'completed', obj='B', typ='item'),
                  event(1, LAST, 'completed', obj='B', typ='item'),
                  event(2, END, 'uncompleted', obj='B', typ='item'),
                  event(3, LAST, owner='E', obj='deep')]
        steps = self.requests(events=events, rows=rows, current_items=active, comments=[])
        steps[4], steps[5] = steps[5], steps[4]
        for owner in ('C', 'D', 'E'):
            comments = [] if owner != 'E' else [dict(id='deep', content='Deep current comment',
                posted_at=CREATED, is_deleted=False, file_attachment=None)]
            steps.append((Expected('/comments', [('task_id', owner), ('limit', '200')]),
                          {'results': comments, 'next_cursor': None}))
        _, streams = self.run_report(steps)
        text = streams.stdout.getvalue()
        self.assertEqual(text.count('Completed step:'), 1)
        self.assertIn('Finished\n  None.', text)
        self.assertIn('Deep current comment', text)
        self.assertIn('B', text)
        self.assertIn('E', text)

    def test_nonrecurring_reopen_omitted_and_completed_deep_step_progress(self):
        active = [item('A'), item('B', parent_id='A'),
                  item('C', parent_id='B', checked=True, completed_at=LAST),
                  item('D', parent_id='C', checked=True, completed_at=FIRST)]
        steps = self.requests(current_items=active, rows=[item('B', parent_id='A', checked=True, completed_at=FIRST),
            item('C', parent_id='B', checked=True, completed_at=LAST)], comments=[])
        steps[4], steps[5] = steps[5], steps[4]
        steps.insert(5, (Expected('/comments', [('task_id', 'C'), ('limit', '200')]), {'results': [], 'next_cursor': None}))
        for owner in ('D',):
            steps.append((Expected('/comments', [('task_id', owner), ('limit', '200')]),
                          {'results': [], 'next_cursor': None}))
        _, streams = self.run_report(steps)
        text = streams.stdout.getvalue()
        self.assertEqual(text.count('Completed step:'), 1)
        self.assertIn('Finished\n  None.', text)

    def test_hidden_snapshot_context_once_and_explicit_interval_is_preview(self):
        active = [item('A'), item('B', parent_id='A'),
                  item('C', parent_id='B', labels=['waiting'], due=due()),
                  item('D', parent_id='C', labels=['waiting'], due=due())]
        steps = self.requests(current_items=active, comments=[])
        for owner in ('C', 'D'):
            steps.append((Expected('/comments', [('task_id', owner), ('limit', '200')]),
                          {'results': [], 'next_cursor': None}))
        before = (self.root / 'report-cursor').read_bytes()
        with patch('todo_lib.workflows.report.prune_history', side_effect=AssertionError('preview cleanup')):
            _, streams = self.run_report(steps, ['--since', '2026-10-21', '--until', '2026-10-21'])
        text = streams.stdout.getvalue()
        self.assertEqual(text.count('A  [context]'), 1)
        self.assertEqual(text.count('B  [context]'), 1)
        self.assertEqual(text.count('Until:'), 2)
        self.assertNotIn('Reason:', text)
        self.assertEqual((self.root / 'report-cursor').read_bytes(), before)

    def test_unresolved_archived_owner_and_parent_fail_without_output(self):
        for parent in (False, True):
            with self.subTest(parent=parent):
                rows = [item('X', parent_id='unknown', checked=True, completed_at=LAST)] if parent else []
                steps = self.requests(events=[event(1, LAST, owner='X', obj='xnote')], rows=rows)
                x = (Expected('/comments', [('task_id', 'X'), ('limit', '200')]),
                    {'results': [dict(id='xnote', content='surviving', posted_at=CREATED,
                                     is_deleted=False, file_attachment=None)], 'next_cursor': None})
                steps.insert(4, x) if parent else steps.append(x)
                streams = self.streams()
                before = (self.root / 'report-cursor').read_bytes()
                history = (self.root / 'history.json').read_bytes()
                with self.assertRaisesRegex(SyncError, 'unresolved archived owner/parent'):
                    self.run_report(steps, ['--final'], streams)
                self.assertEqual(streams.stdout.getvalue(), '')
                self.assertEqual((self.root / 'report-cursor').read_bytes(), before)
                self.assertEqual((self.root / 'history.json').read_bytes(), history)

    def test_archived_owner_with_known_parent_requires_current_own_comments(self):
        # T08 reconciliation discovers B's completion, including its own comments.
        steps = self.requests(rows=[completed_b()], events=[event(1, LAST)],
                              current_items=[item('A')])
        # Reconciliation requests B first; required_comments then requests A/B.
        b_comments = steps.pop()
        a_comments = steps.pop()
        steps.extend([b_comments, b_comments, a_comments])
        _, streams = self.run_report(steps, ['--since', START])
        self.assertIn('Current post-boundary text', streams.stdout.getvalue())
        self.assertIn('Comment on step: B', streams.stdout.getvalue())
        self.assertNotIn('Completed step:', streams.stdout.getvalue())

    def test_pagination_failures_and_partial_publication(self):
        for kind in ('missing', 'repeated', 'publication'):
            with self.subTest(kind=kind):
                steps = self.requests()
                streams = self.streams()
                before = {name: (self.root / name).read_bytes() for name in ('report-cursor', 'history.json', 'binding.json')}
                if kind == 'missing':
                    steps = steps[:4]
                    steps[3] = (steps[3][0], {'results': []})
                elif kind == 'repeated':
                    steps = steps[:4]
                    request = steps[3][0]
                    steps[3] = (request, {'results': [], 'next_cursor': 'a.b'})
                    steps.append((Expected('/activities', request.query + [('cursor', 'a.b')]),
                                  {'results': [], 'next_cursor': 'a.b'}))
                import todo_lib.local.store as storage
                original = storage.atomic_write
                def publish(path, content, validate):
                    if Path(path).name == 'history.json':
                        raise LocalError('injected publication')
                    return original(path, content, validate)
                target = 'todo_lib.local.store.atomic_write' if kind == 'publication' else 'todo_lib.workflows.report.prune_history'
                with patch(target, side_effect=publish if kind == 'publication' else AssertionError('must not clean')):
                    with self.assertRaises(SyncError) as caught:
                        self.run_report(steps, ['--final'], streams)
                self.assertEqual(streams.stdout.getvalue(), '')
                for name, content in before.items():
                    self.assertEqual((self.root / name).read_bytes(), content)
                if kind == 'publication':
                    self.assertTrue(caught.exception.publication_started)
                    with self.assertRaisesRegex(LocalError, 'mixed'):
                        self.store.load_consistent_state()

    def test_final_bypasses_pager_and_preview_early_quit_preserves_history(self):
        self.put('config', b'[main]\nproject=root\ndefault_sections=cat\nhidden_from_now=\npager=unavailable-pager\n')
        class TTY(StringIO):
            def isatty(self):
                return True
        streams = OriginalStreams(TTY(), TTY(), TTY())
        with patch('todo_lib.presentation.delivery.subprocess.Popen', side_effect=AssertionError('final pager')):
            self.run_report(self.requests(), ['--final'], streams)
        # Reset the boundary explicitly; setter is not allowed to release data.
        self.store.write_cursor(CURSOR)
        streams = OriginalStreams(TTY(), TTY(), TTY())
        child = unittest.mock.Mock()
        child.wait.return_value = 0
        with patch.dict('os.environ', {'TERM': 'xterm'}), patch('todo_lib.presentation.delivery.subprocess.Popen', return_value=child) as pager, \
             patch('todo_lib.workflows.report.prune_history', side_effect=AssertionError('preview cleanup')):
            self.run_report(self.requests(events=[event(1, LAST)]), streams=streams)
        pager.assert_called_once()
        self.assertEqual(d.instant_key(self.store.load_cursor()), d.instant_key(CURSOR))
        self.assertIn('B', self.store.load_history().snapshot.items)

    def test_local_confirmation_safety_syntax_and_process_lock(self):
        from todo_lib.syntax.parser import UsageError
        from todo_lib.syntax.input import InputError
        from todo_lib.local import LockBusy
        with self.assertRaises(InputError):
            self.run_report([], ['--set-cursor', START])
        with exclusive_lock('held', self.root):
            with patch.object(self.store, 'load_binding', side_effect=AssertionError('syntax read local state')):
                with self.assertRaises(UsageError):
                    self.run_report([], ['--since', 'next monday'])
            script = """
import sys
from todo_lib.workflows.report import Reporter
from todo_lib.local import StateStore, LockBusy
store = StateStore(sys.argv[1])
store.load_cursor = lambda: (_ for _ in ()).throw(AssertionError('read before lock'))
try:
    Reporter(None, store).run(['--show-cursor'])
except LockBusy:
    print('locked before cursor read')
else:
    raise AssertionError('lock not held')
"""
            result = subprocess.run([sys.executable, '-B', '-c', script, str(self.root)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('locked before cursor read', result.stdout)
        cursor = self.root / 'report-cursor'
        cursor.unlink()
        cursor.symlink_to(self.root / 'config')
        with self.assertRaisesRegex(LocalError, 'symlink'):
            self.run_report([], ['--set-cursor', START, '--yes'])


    def test_successful_pagination_and_exact_latest_edit_evidence(self):
        from todo_lib.presentation import render_report
        events = [event(900, FIRST), event(1, LAST)]
        steps = self.requests(events=events)
        request = steps[3][0]
        steps[3] = (request, {'results': [events[0]], 'next_cursor': 'a.b'})
        steps.insert(4, (Expected('/activities', request.query + [('cursor', 'a.b')]),
                         {'results': [events[1], event(2, NEWER)], 'next_cursor': None}))
        # Comments use their own required continuation, without a wire owner field.
        comment_request, payload = steps[-1]
        steps[-1] = (comment_request, {'results': [], 'next_cursor': 'c.d'})
        steps.append((Expected('/comments', comment_request.query + [('cursor', 'c.d')]), payload))
        captured = []
        def render(*args, **kwargs):
            captured.extend(kwargs['progress'])
            return render_report(*args, **kwargs)
        with patch('todo_lib.workflows.report.render_report', side_effect=render):
            self.run_report(steps)
        self.assertEqual(len(captured), 1)
        self.assertEqual(d.instant_text(captured[0].instant), LAST)
        self.assertEqual(captured[0].body, 'Current post-boundary text')

    def test_finished_root_and_post_boundary_recurring_undo(self):
        # Current active text wins over bounded occurrence text. A later undo
        # remains next-period activity even in an explicit preview interval.
        active = [item('A', content='Current root', due=due(is_recurring=True)), item('B', parent_id='A')]
        rows = [item('A', content='Old title', completed_at=FIRST, due=due(is_recurring=True))]
        undo = event(1, LAST, 'uncompleted', obj='A', typ='item')
        steps = self.requests(current_items=active, rows=rows, events=[undo], comments=[])
        _, streams = self.run_report(steps, ['--until', FIRST])
        self.assertIn('— Current root', streams.stdout.getvalue())
        self.assertNotIn('Old title', streams.stdout.getvalue())

    def test_sigint_during_retrieval_preserves_pending_bytes(self):
        from todo_lib.workflows.sync import SyncInterrupted
        steps = self.requests()[:2]
        before = {name: (self.root / name).read_bytes() for name in ('history.json', 'report-cursor')}
        with patch('todo_lib.workflows.report.HistoryAdapter.completed', side_effect=KeyboardInterrupt):
            with self.assertRaises(SyncInterrupted):
                self.run_report(steps, ['--final'])
        for name, content in before.items():
            self.assertEqual((self.root / name).read_bytes(), content)


    def test_current_scope_includes_old_scope_event_and_excludes_departure(self):
        old_event = event(1, LAST)
        old_event['parent_project_id'] = 'former-unmanaged-category'
        unrelated = event(2, LAST, owner='outside', obj='unrelated')
        unrelated['parent_project_id'] = 'unmanaged'
        _, streams = self.run_report(self.requests(events=[old_event, unrelated]))
        self.assertIn('Current post-boundary text', streams.stdout.getvalue())
        # Known departures are authoritative; old qualifying events cannot bring
        # them or their comments back into the managed report population.
        active = [item('A'), item('B', project_id='unmanaged')]
        steps = self.requests(events=[event(1, LAST)], current_items=active)
        steps.pop()  # Only A still needs comments.
        _, streams = self.run_report(steps)
        self.assertNotIn('Current post-boundary text', streams.stdout.getvalue())


    def test_history_replaced_before_binding_failure_preserves_required_content(self):
        import todo_lib.local.store as storage
        from todo_lib.local.codec import loads
        original = storage.atomic_write
        before_cursor = (self.root / 'report-cursor').read_bytes()
        def publish(path, content, validate):
            if Path(path).name == 'binding.json':
                raise LocalError('injected binding replacement')
            return original(path, content, validate)
        streams = self.streams()
        with patch('todo_lib.local.store.atomic_write', side_effect=publish):
            with self.assertRaises(SyncError) as caught:
                self.run_report(self.requests(events=[event(1, LAST)]), ['--final'], streams)
        self.assertTrue(caught.exception.publication_started)
        self.assertEqual(streams.stdout.getvalue(), '')
        self.assertEqual((self.root / 'report-cursor').read_bytes(), before_cursor)
        pending = loads((self.root / 'history.json').read_bytes())
        self.assertIn('B', pending['observations'])
        # Do not restore/reset the candidate history association to accept a mixed
        # set. A fresh reader must fail and the available history bytes survive.
        before_history = (self.root / 'history.json').read_bytes()
        with self.assertRaisesRegex(LocalError, 'mixed|required history'):
            StateStore(self.root).load_consistent_state(require_cache=False)
        self.assertEqual((self.root / 'history.json').read_bytes(), before_history)

    def test_default_fixed_end_is_captured_once_before_first_http(self):
        transport, _ = self.boundary(self.requests(events=[event(1, LAST), event(2, NEWER)]))
        called = []
        def clock():
            called.append('clock')
            self.assertEqual(len(called), 1)
            return NOW
        original = transport.request
        def request(*args, **kwargs):
            self.assertEqual(called, ['clock'])
            return original(*args, **kwargs)
        with patch.object(transport, 'request', side_effect=request):
            result = Reporter(transport, self.store, clock=clock, streams=self.streams()).run(['--final'])
        self.assertEqual(d.instant_text(result.end), END)
        self.assertEqual(d.instant_text(self.store.load_cursor()), END)


    def test_later_unknown_owner_event_is_left_for_next_interval(self):
        events = [event(1, FIRST), event(2, LAST, owner='archived-next-period', obj='next')]
        _, streams = self.run_report(self.requests(events=events), ['--until', FIRST])
        self.assertEqual(streams.stdout.getvalue().count('Current post-boundary text'), 1)

    def test_unresolved_completion_owner_is_not_silently_omitted(self):
        steps = self.requests(events=[event(1, LAST, 'completed', obj='unknown', typ='item')])[:4]
        with self.assertRaisesRegex(SyncError, 'unresolved archived owner/parent unknown'):
            self.run_report(steps, ['--final'])


    def test_retained_archived_metadata_is_not_current_owner_evidence(self):
        # Discover the archived step via supported evidence, then repeat with a
        # completed response that no longer supplies it. Pending bytes are context,
        # never authority for the surviving comment's current role or parent.
        first = self.requests(rows=[completed_b()], events=[event(1, LAST)],
                              current_items=[item('A')])
        b, a = first.pop(), first.pop()
        first.extend([b, b, a])
        self.run_report(first)
        self.assertIn('B', self.store.load_history().snapshot.items)
        cursor = (self.root / 'report-cursor').read_bytes()
        pending = (self.root / 'history.json').read_bytes()
        steps = self.requests(events=[event(1, LAST)], current_items=[item('A')])
        steps.insert(4, steps[-1])  # reconciliation still retrieves B's own comments
        streams = self.streams()
        with self.assertRaisesRegex(SyncError, 'unresolved archived owner/parent B'):
            self.run_report(steps, ['--final'], streams)
        self.assertEqual(streams.stdout.getvalue(), '')
        self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)
        self.assertEqual((self.root / 'history.json').read_bytes(), pending)
        # Completion-only activity has the same provenance requirement; a
        # retained owner must not make the occurrence silently disappear.
        steps = self.requests(events=[event(2, LAST, 'completed', obj='B', typ='item')],
                              current_items=[item('A')])
        steps = steps[:4] + [steps[-1]]
        with self.assertRaisesRegex(SyncError, 'unresolved archived owner/parent B'):
            self.run_report(steps, ['--final'], streams)
        self.assertEqual(streams.stdout.getvalue(), '')
        self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)
        self.assertEqual((self.root / 'history.json').read_bytes(), pending)
        # Recovery preview with no eligible B event can proceed, but must retain
        # the pending archived context rather than erase it during publication.
        steps = self.requests(current_items=[item('A')])
        steps.pop()  # no report-level B comment request without eligible activity
        steps.insert(4, (Expected('/comments', [('task_id', 'B'), ('limit', '200')]),
            {'results': [dict(id='own', content='still surviving', posted_at=CREATED,
                             is_deleted=False, file_attachment=None)], 'next_cursor': None}))
        self.run_report(steps)
        pending = self.store.load_history()
        self.assertIn('B', pending.snapshot.items)
        self.assertEqual(pending.snapshot.comments['own'].body, 'still surviving')
        self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)

    def test_retained_archived_parent_cannot_resolve_current_comment_role(self):
        first = self.requests(rows=[completed_b()], current_items=[item('A')])
        b, a = first.pop(), first.pop()
        first.extend([b, b, a])
        self.run_report(first)
        before = {name: (self.root / name).read_bytes()
                  for name in ('report-cursor', 'history.json')}
        steps = self.requests(rows=[item('X', parent_id='B', checked=True, completed_at=LAST)],
                              events=[event(1, LAST, owner='X', obj='xnote')],
                              current_items=[item('A')])
        b, a = steps.pop(), steps.pop()
        x = (Expected('/comments', [('task_id', 'X'), ('limit', '200')]),
             {'results': [dict(id='xnote', content='Needs current ancestry', posted_at=CREATED,
                              is_deleted=False, file_attachment=None)], 'next_cursor': None})
        steps.extend([b, x, x, a])
        streams = self.streams()
        with self.assertRaisesRegex(SyncError, 'unresolved archived owner/parent B'):
            self.run_report(steps, ['--final'], streams)
        self.assertEqual(streams.stdout.getvalue(), '')
        for name, content in before.items():
            self.assertEqual((self.root / name).read_bytes(), content)

    def test_calendar_boundaries_use_synchronized_timezone(self):
        events = [event(1, '2026-10-20T23:00:00Z'),
                  event(2, '2026-10-21T01:00:00Z', obj='eligible')]
        comments = [dict(id=identity, content=text, posted_at=CREATED,
                         is_deleted=False, file_attachment=None)
                    for identity, text in [('own', 'Outside UTC interval'),
                                           ('eligible', 'Inside UTC interval')]]
        steps = self.requests(events=events, comments=comments)
        steps[0][1]['user']['tz_info']['timezone'] = 'UTC'
        result, streams = self.run_report(steps, ['--since', '2026-10-21', '--until', '2026-10-22'])
        self.assertEqual(d.instant_text(result.start), '2026-10-21T00:00:00Z')
        self.assertEqual(d.instant_text(result.end), '2026-10-22T00:00:00Z')
        self.assertNotIn('Outside UTC interval', streams.stdout.getvalue())
        self.assertIn('Inside UTC interval', streams.stdout.getvalue())
        self.assertEqual(self.store.load_binding().last_synced_account_timezone, 'UTC')

    def test_same_instant_completion_multiplicity_and_undo(self):
        for identities, undo, count in [((None, None), False, 2),
                                        ((None, None), True, 1),
                                        ((1, 2), False, 2)]:
            with self.subTest(identities=identities, undo=undo):
                active = [item('A', due=due(is_recurring=True)), item('B', parent_id='A')]
                events = [event(identity, FIRST, 'completed', obj='A', typ='item')
                          for identity in identities]
                for row in events:
                    if row['id'] is None:
                        del row['id']  # provider-valid omitted identity
                if undo:
                    events.append(event(3, LAST, 'uncompleted', obj='A', typ='item'))
                rows = [item('A', completed_at=FIRST, due=due(is_recurring=True))]
                steps = self.requests(current_items=active, events=events, rows=rows)
                _, streams = self.run_report(steps)
                finished = streams.stdout.getvalue().split('Progress')[0]
                self.assertEqual(finished.count(' — A'), count)

    def test_anonymous_same_instant_undo_respects_source_order(self):
        active = [item('A', due=due(is_recurring=True)), item('B', parent_id='A')]
        events = [event(None, FIRST, kind, obj='A', typ='item')
                  for kind in ('uncompleted', 'completed', 'completed')]
        for row in events:
            del row['id']
        _, streams = self.run_report(self.requests(current_items=active, events=events))
        self.assertEqual(streams.stdout.getvalue().split('Progress')[0].count(' — A'), 2)

    def test_unrelated_optional_activity_owner_is_filtered_before_mapping(self):
        unrelated = event(None, LAST, owner=None)
        unrelated.pop('parent_item_id')
        unrelated['parent_project_id'] = 'unmanaged'
        managed = event(1, FIRST)
        managed['parent_project_id'] = 'before-scope-entry'
        steps = self.requests(events=[unrelated, managed])
        result, streams = self.run_report(steps, ['--final'])
        self.assertTrue(result.finalized)
        self.assertIn('Current post-boundary text', streams.stdout.getvalue())
        self.assertEqual(d.instant_key(self.store.load_cursor()), d.instant_key(NOW))

    def test_potentially_managed_activity_still_requires_owner(self):
        row = event(None, LAST)
        row.pop('parent_item_id')
        steps = self.requests(events=[row])[:4]
        cursor = (self.root / 'report-cursor').read_bytes()
        pending = (self.root / 'history.json').read_bytes()
        streams = self.streams()
        with self.assertRaisesRegex(SyncError, 'parent_item_id'):
            self.run_report(steps, ['--final'], streams)
        self.assertEqual(streams.stdout.getvalue(), '')
        self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)
        self.assertEqual((self.root / 'history.json').read_bytes(), pending)


del SyncTests
