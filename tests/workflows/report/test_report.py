"""Public report composition through real adapters, renderer and protected stores.

Synthetic endpoint fixtures use the retained API-v1 evidence cited by the shared
adapter fixtures. Expected checks reject query drift and invented endpoints.
"""
from io import StringIO
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit
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
from tests.adapter.current.test_current import full, delta, item, due, note
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
              ('limit', '200')]
        aq += [('object_event_types', '["item:completed", "item:uncompleted", "note:added", "note:updated", "note:deleted"]')]
        active = current_items if current_items is not None else [item('A'), item('B', parent_id='A')]
        own = comments if comments is not None else [dict(id='own', content='Current post-boundary text', posted_at=CREATED, is_deleted=False)]
        notes = current_notes if current_notes is not None else [dict(c, item_id='B') for c in own if any(i['id'] == 'B' for i in active)]
        token = self.store.load_consistent_state().sync_token
        steps = [self.sync(token, full(items=active, notes=notes, user_plan_limits=limits(access, days))),
                 self.sync('full-token', delta())]
        if access and days != 0:
            steps += [(Expected('/tasks/completed/by_completion_date', cq), {'items': list(rows)}),
                      (Expected('/activities', aq), {'results': list(events), 'next_cursor': None})]
            # Reconciliation needs all missing known owners. Only uncovered owners
            # have REST expectations; active notes above are complete Sync evidence.
            missing = (set(self.store.load_consistent_state().snapshot.items) | set(self.store.load_history().snapshot.items)) - {i['id'] for i in active}
            archived = {r['id'] for r in rows if r.get('checked')} - {i['id'] for i in active}
            for owner in sorted(missing | archived):
                steps.append((Expected('/comments', [('task_id', owner), ('limit', '200')]),
                    {'results': own if owner == 'B' else [], 'next_cursor': None}))
        return steps

    def run_report(self, steps, args=(), streams=None, now=NOW):
        transport, self.last_http = self.boundary(steps)
        streams = streams or self.streams()
        result = Reporter(transport, self.store, clock=lambda: now, streams=streams).run(args)
        return result, streams

    def test_saved_baseline_reload_delta_and_shared_archived_comments(self):
        # Synthetic responses at the real Transport boundary, per retained Sync,
        # scoped comments, completed and ActivityEvents contracts. No live bytes.
        from tests.adapter.current.test_current import note
        from todo_lib.local import StateStore
        transport, _ = self.boundary([
            self.sync('delta-token', full(items=[item('A'), item('C'), item('D')],
                notes=[note('active', 'A', content='Before edit', posted_at=CREATED)],
                user_plan_limits=limits())),
            self.sync('full-token', delta(sync_token='external-token')),
            (Expected('/tasks/completed/by_completion_date',
                [('project_id', 'cat'), ('since', '2026-10-20T00:00:00Z'),
                 ('until', '2026-10-22T12:00:01Z'), ('limit', '200')]),
                {'items': [completed_b()]}),
            (Expected('/comments', [('task_id', 'B'), ('limit', '200')]),
                {'results': [dict(id='own', content='Archived observed', posted_at=CREATED,
                                  is_deleted=False)], 'next_cursor': None})])
        Synchronizer(transport, self.store, clock=lambda: NOW).refresh()
        self.store = StateStore(self.root)
        loaded = self.store.load_consistent_state()
        self.assertIn('B', loaded.snapshot.items)
        self.assertNotIn('B', loaded.current_snapshot.items)
        cursor = (self.root / 'report-cursor').read_bytes()
        steps = [self.sync('external-token', delta(items=[item('A', content='Current parent'),
                    dict(id='C', is_deleted=True)],
                notes=[note('active', 'A', content='Fresh active text', posted_at=CREATED)],
                sync_token='report-token')),
            (Expected('/tasks/completed/by_completion_date',
                [('project_id', 'cat'), ('since', '2026-10-20T00:00:00Z'),
                 ('until', '2026-10-22T12:00:01Z'), ('limit', '200')]),
                {'items': [completed_b(content='Current archived step')]}),
            (Expected('/activities', [('date_from', '2026-10-20T00:00:00Z'),
                ('date_to', '2026-10-22T12:00:01Z'), ('limit', '200'),
                ('object_event_types', '["item:completed", "item:uncompleted", "note:added", "note:updated", "note:deleted"]')]),
                {'results': [event(1, LAST), event(2, LAST, owner='A', obj='active')], 'next_cursor': None}),
            (Expected('/comments', [('task_id', 'B'), ('limit', '200')]),
                {'results': [dict(id='own', content='Fresh archived text', posted_at=CREATED,
                                  is_deleted=False)], 'next_cursor': None})]
        transport, http = self.boundary(steps)
        streams = self.streams()
        Reporter(transport, self.store, clock=lambda: NOW, streams=streams).run()
        http.assert_done()
        self.assertEqual(len(http.requests), 4)
        self.assertEqual(parse_qs(http.requests[0][0].data.decode())['sync_token'], ['external-token'])
        comment_owners = [parse_qs(urlsplit(request.full_url).query)['task_id'][0]
            for request, _ in http.requests if urlsplit(request.full_url).path.endswith('/comments')]
        self.assertEqual(comment_owners, ['B'])
        text = streams.stdout.getvalue()
        for value in ('Current parent', 'Current archived step', 'Fresh active text', 'Fresh archived text'):
            self.assertIn(value, text)
        loaded = self.store.load_consistent_state()
        self.assertEqual(loaded.sync_token, 'report-token')
        self.assertEqual(set(loaded.current_snapshot.items), {'A', 'D'})
        self.assertEqual(loaded.snapshot.items['B'].parent_id, 'A')
        self.assertIn('B', loaded.history.snapshot.items)
        self.assertNotIn('C', loaded.snapshot.items)
        self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)

    def test_comment_progress_counts_actual_pages_across_shared_and_filtered_owners(self):
        self.comment_progress(7)

    def test_comment_progress_does_not_count_reused_or_sync_covered_owners(self):
        self.comment_progress(9)

    def comment_progress(self, extra_archives):
        # Synthetic scoped comments/Sync/completed/ActivityEvents responses use
        # the retained contracts cited above. B is read during reconciliation;
        # the other archives and the filtered unknown owner are read afterwards.
        archived = ['B', *['arch' + str(k) for k in range(extra_archives)]]
        rows = [completed_b(), *[completed_b(id=owner, content=owner)
                                 for owner in archived[1:]]]
        steps = self.requests(rows=rows, current_items=[item('A')],
            events=[event(1, LAST),
                    event(2, LAST, owner='unknown', obj='gone')])[:4]
        for owner in archived:
            query = [('task_id', owner), ('limit', '200')]
            steps.append((Expected('/comments', query), {'results': [dict(
                id='own' if owner == 'B' else 'note-' + owner,
                content='Fresh ' + owner, posted_at=CREATED, is_deleted=False)],
                'next_cursor': 'b.next' if owner == 'B' else None}))
            if owner == 'B':
                steps.append((Expected('/comments', query + [('cursor', 'b.next')]),
                              {'results': [], 'next_cursor': None}))
        # Relevance-only lookup: the deleted note needs no owner metadata and
        # must still contribute its actual REST page to endpoint-wide progress.
        steps.append((Expected('/comments', [('task_id', 'unknown'), ('limit', '200')]),
                      {'results': [dict(id='gone', is_deleted=True)], 'next_cursor': None}))
        cursor = (self.root / 'report-cursor').read_bytes()
        _, streams = self.run_report(steps)
        self.last_http.assert_done()
        owners = [parse_qs(urlsplit(request.full_url).query)['task_id'][0]
                  for request, _ in self.last_http.requests
                  if urlsplit(request.full_url).path.endswith('/comments')]
        self.assertEqual(owners, ['B', *archived, 'unknown'])
        self.assertEqual(len(self.last_http.requests), 7 + extra_archives)
        self.assertEqual(streams.stderr.getvalue(), 'todo: loading comments: 10 pages\n')
        self.assertIn('Fresh B', streams.stdout.getvalue())
        self.assertIn('Comment on step: B', streams.stdout.getvalue())
        self.assertNotIn('annotation is not current text', streams.stdout.getvalue())
        state = self.store.load_consistent_state()
        self.assertEqual(set(state.current_snapshot.items), {'A'})
        self.assertTrue(set(archived) <= set(state.history.snapshot.items))
        self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)

    def test_consecutive_delta_reports_cover_empty_blank_deleted_and_unchanged_owners(self):
        # Saved setup baseline contains a live own note. These are actual deltas,
        # including its eventual tombstone, rather than full responses at a token.
        self.run_report(self.requests(current_items=[item('A'), item('B', parent_id='A'),
            *[item('extra' + str(k)) for k in range(12)]]))
        self.assertEqual(len(self.last_http.requests), 4)
        cursor = (self.root / 'report-cursor').read_bytes()
        previous = 12
        for extras, body in ((12, ''), (3, 'Next command text'), (0, None)):
            with self.subTest(active_owners=2 + extras):
                planned = self.requests(events=[event(900, FIRST), event(1, LAST),
                    event(2, LAST, owner='A', obj='absent')])
                changed = ([dict(id='own', is_deleted=True)] if body is None else
                           [note('own', 'B', content=body, posted_at=CREATED)])
                steps = [self.sync('delta-token', delta(
                    user_plan_limits=limits(), notes=changed,
                    items=[dict(id='extra' + str(k), is_deleted=True)
                           for k in range(extras, previous)])),
                    *planned[2:4]]
                streams = self.streams()
                transport, http = self.boundary(steps)
                Reporter(transport, self.store, clock=lambda: NOW, streams=streams).run()
                http.assert_done()
                self.assertEqual(len(http.requests), 3)
                self.assertFalse(any(urlsplit(r.full_url).path.endswith('/comments')
                                     for r, _ in http.requests))
                text = streams.stdout.getvalue()
                state = StateStore(self.root).load_consistent_state()
                self.assertEqual(len(state.current_snapshot.items), 2 + extras)
                if body is None:
                    self.assertNotIn('own', state.current_snapshot.comments)
                    self.assertNotIn('Next command text', text)
                    self.assertIn('Progress\n  None.', text)
                else:
                    self.assertEqual(text.count(body or '[no text]'), 1)
                self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)
                previous = extras

    def test_both_archived_reminder_types_survive_pending_only_report_publication(self):
        from tests.support.reminders import absolute
        rows = [completed_b(due=due())]
        steps = self.requests(rows=rows, current_items=[item('A')])
        steps[0][1]['user_plan_limits']['current']['reminders'] = True
        steps[0][1]['reminders'] = [absolute('absolute', item_id='B'),
            dict(id='relative', item_id='B', type='relative', minute_offset=0, is_deleted=False)]
        self.run_report(steps)
        for _ in range(2):
            planned = self.requests(current_items=[item('A')])
            steps = [self.sync('delta-token', delta()), *planned[2:]]
            self.run_report(steps)
            state = self.store.load_consistent_state()
            self.assertEqual(state.current_reminder_ids, {'absolute', 'relative'})
            self.assertNotIn('B', state.current_snapshot.items)
            self.assertEqual(set(state.history.snapshot.reminders), {'absolute', 'relative'})
            self.assertEqual(set(state.snapshot.reminders), {'absolute', 'relative'})
        # Final cleanup can discard old pending owner evidence. Necessary cache
        # context still pairs the archived reminder bodies with the actual token.
        self.store.write_cursor(NOW)
        planned = self.requests(current_items=[item('A')], cursor=NOW)
        self.run_report([self.sync('delta-token', delta()), *planned[2:]], ['--final'])
        state = self.store.load_consistent_state()
        self.assertNotIn('B', state.history.snapshot.items)
        self.assertEqual(state.current_reminder_ids, {'absolute', 'relative'})
        planned = self.requests(current_items=[item('A')], cursor=NOW)
        self.run_report([self.sync('delta-token', delta()), *planned[2:]])
        self.assertEqual(self.store.load_consistent_state().current_reminder_ids,
                         {'absolute', 'relative'})

    def test_legacy_and_invalid_disposable_provenance_hydrate_without_reset(self):
        from todo_lib.local.codec import loads, dumps
        for provenance in (None, {'items': ['B'], 'reminders': []}):
            with self.subTest(provenance=provenance):
                raw = loads((self.root / 'cache.json').read_bytes())
                if provenance is None:
                    raw.pop('current_resources')
                else:
                    raw['current_resources'] = provenance  # missing active ancestor
                self.put('cache.json', dumps(raw))
                cursor = (self.root / 'report-cursor').read_bytes()
                if provenance is None:
                    self.assertIsNone(self.store.load_consistent_state().current_snapshot)
                    steps = self.requests()
                    steps[0] = (self.sync('*', steps[0][1])[0], steps[0][1])
                else:
                    # Build the expected replacement explicitly; invalid cache is
                    # disposable but protected history remains required.
                    steps = [self.sync('*', full(items=[item('A'), item('B', parent_id='A')],
                        user_plan_limits=limits())), self.sync('full-token', delta()),
                        (Expected('/tasks/completed/by_completion_date',
                            [('project_id', 'cat'), ('since', '2026-10-20T00:00:00Z'),
                             ('until', '2026-10-22T12:00:01Z'), ('limit', '200')]), {'items': []}),
                        (Expected('/activities', [('date_from', '2026-10-20T00:00:00Z'),
                            ('date_to', '2026-10-22T12:00:01Z'), ('limit', '200'),
                            ('object_event_types', '["item:completed", "item:uncompleted", "note:added", "note:updated", "note:deleted"]')]),
                            {'results': [], 'next_cursor': None})]
                self.run_report(steps)
                self.assertIsNotNone(self.store.load_consistent_state().current_snapshot)
                self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)
                self.assertIn('B', self.store.load_history().snapshot.items)
                # Reload the hydrated cache and prove the very next report uses
                # a delta only, preserving protected state and complete queries.
                self.store = StateStore(self.root)
                planned = self.requests()
                self.run_report([self.sync('delta-token', delta()), *planned[2:4]])
                self.assertEqual(len(self.last_http.requests), 3)
                self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)
                # Invalid required history must still refuse without any HTTP.
                refreshed_history = (self.root / 'history.json').read_bytes()
                self.put('history.json', b'{broken')
                with self.assertRaises(LocalError):
                    self.run_report([])
                self.assertEqual((self.root / 'history.json').read_bytes(), b'{broken')
                self.put('history.json', refreshed_history)

    def test_saved_token_errors_refuse_replacement_and_protect_pending(self):
        from tests.support.http import Response
        for response in (Response(b'{"error":"invalid_token"}', status=401),
                         Response(b'{"error":"INVALID_SYNC_TOKEN"}', status=400),
                         TimeoutError('offline controlled timeout')):
            with self.subTest(response=type(response).__name__):
                before = {name: (self.root / name).read_bytes() for name in
                          ('cache.json', 'binding.json', 'history.json', 'report-cursor')}
                streams = self.streams()
                with self.assertRaisesRegex(SyncError, 'automatic sync-token recognition unavailable'):
                    self.run_report([self.sync('delta-token', response)], ['--final'], streams)
                self.last_http.assert_done()
                self.assertEqual(len(self.last_http.requests), 1)
                self.assertEqual(streams.stdout.getvalue(), '')
                for name, content in before.items():
                    self.assertEqual((self.root / name).read_bytes(), content)

    def test_active_malformed_sync_notes_fail_before_output(self):
        for changes in ({'content': None}, {'posted_at': 'malformed'}):
            with self.subTest(changes=changes):
                steps = self.requests(current_notes=[note('own', 'B', **changes)])[:2]
                streams = self.streams()
                before = {name: (self.root / name).read_bytes() for name in ('report-cursor', 'history.json')}
                with self.assertRaises(SyncError):
                    self.run_report(steps, ['--final'], streams)
                self.assertEqual(streams.stdout.getvalue(), '')
                for name, value in before.items():
                    self.assertEqual((self.root / name).read_bytes(), value)

    def test_archived_extra_comment_page_failure_preserves_pending_and_cursor(self):
        steps = self.requests(rows=[completed_b()], current_items=[item('A')], events=[event(1, LAST)])
        request, payload = steps[-1]
        steps[-1] = (request, dict(payload, next_cursor='second.page'))
        steps.append((Expected('/comments', request.query + [('cursor', 'second.page')]),
            {'results': []}))
        before = {name: (self.root / name).read_bytes() for name in ('report-cursor', 'history.json')}
        streams = self.streams()
        with self.assertRaisesRegex(SyncError, 'page 2.*next_cursor'):
            self.run_report(steps, ['--final'], streams)
        self.assertEqual(streams.stdout.getvalue(), '')
        for name, value in before.items():
            self.assertEqual((self.root / name).read_bytes(), value)

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
        active = [item('A'), item('B', parent_id='A', due=due(is_recurring=True))]
        transport, _ = self.boundary([
            self.sync('delta-token', full(items=active, user_plan_limits=limits())),
            self.sync('full-token', delta()),
            (Expected('/tasks/completed/by_completion_date',
                [('project_id', 'cat'), ('since', '2026-10-20T00:00:00Z'),
                 ('until', '2026-10-22T12:00:01Z'), ('limit', '200')]), {'items': []}),
            (Expected('/activities', [('object_type', 'item'), ('object_id', 'B'),
                ('date_from', '2026-10-20T00:00:00Z'), ('date_to', '2026-10-22T12:00:01Z'),
                ('limit', '200'), ('object_event_types',
                 '["item:completed", "item:uncompleted", "note:added", "note:updated", "note:deleted"]')]),
                {'results': [event(77, NEWER, 'completed', obj='B', typ='item')], 'next_cursor': None})])
        Synchronizer(transport, self.store, clock=lambda: d.instant_from_wire(NEWER)).refresh()
        self.store.write_cursor(d.instant_from_wire(START))
        self.assertEqual(d.instant_text(self.store.load_history().observations['B']), NEWER)
        # Preview must retain this T08-produced context and the exact cursor bytes.
        cursor_bytes = (self.root / 'report-cursor').read_bytes()
        with patch('todo_lib.workflows.report.prune_history', side_effect=AssertionError('preview pruning')):
            self.run_report(self.requests(events=[event(900, FIRST), event(1, LAST), event(3, NEWER)],
                cursor=d.instant_from_wire(START), current_items=active))
        self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor_bytes)
        preview_history = self.store.load_history()
        self.assertEqual(d.instant_text(preview_history.observations['B']), NEWER)
        self.assertIn('own', preview_history.snapshot.comments)
        # New synchronization does not reduce the newer pending observation.
        steps = self.requests(events=[event(900, FIRST), event(1, LAST), event(3, NEWER)], cursor=d.instant_from_wire(START), current_items=active)
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
        newer = list(loaded.history.snapshot.occurrences.values())
        self.assertEqual(len(newer), 1)
        self.assertEqual(newer[0].activity_id, '77')
        self.assertEqual(d.instant_text(newer[0].completed_at), NEWER)

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
        steps[0][1]['notes'] = [note('deep', 'E', content='Deep current comment', posted_at=CREATED)]
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
        _, streams = self.run_report(steps)
        text = streams.stdout.getvalue()
        self.assertEqual(text.count('Completed step:'), 1)
        self.assertIn('Finished\n  None.', text)

    def test_hidden_snapshot_context_once_and_explicit_interval_is_preview(self):
        active = [item('A'), item('B', parent_id='A'),
                  item('C', parent_id='B', labels=['waiting'], due=due()),
                  item('D', parent_id='C', labels=['waiting'], due=due())]
        steps = self.requests(current_items=active, comments=[])
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
                if parent:
                    steps[-1] = x
                else:
                    steps.append(x)
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
        # Reconciliation exhausts B once; preparation reuses it and Sync covers A.
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
        steps = self.requests(events=events, rows=[completed_b()], current_items=[item('A')])
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
            captured.extend(e for e in kwargs['progress'] if e.kind == 'comment')
            return render_report(*args, **kwargs)
        with patch('todo_lib.workflows.report.render_report', side_effect=render):
            self.run_report(steps)
        self.assertEqual(len(captured), 1)
        self.assertEqual(d.instant_text(captured[0].instant), LAST)
        self.assertEqual(captured[0].body, 'Current post-boundary text')
        paths = [urlsplit(request.full_url).path for request, _ in self.last_http.requests]
        self.assertEqual(paths.count('/api/v1/comments'), 2)
        self.assertEqual(paths.count('/api/v1/activities'), 2)
        self.assertEqual(len(paths), 7)

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
        self.run_report(first)
        self.store = StateStore(self.root)
        state = self.store.load_consistent_state()
        self.assertIn('B', state.history.snapshot.items)
        self.assertNotIn('B', state.current_snapshot.items)
        from todo_lib.local import Coverage
        with exclusive_lock('retained coverage fixture', self.root):
            history = self.store.load_history()
            self.store.save_history(replace(history, coverage=(Coverage(CURSOR, NOW),)))
        cursor = (self.root / 'report-cursor').read_bytes()
        pending = (self.root / 'history.json').read_bytes()
        steps = self.requests(events=[event(1, LAST)], current_items=[item('A')])
        steps = [self.sync('delta-token', delta()), *steps[2:]]
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
        steps = [self.sync('delta-token', delta()), *steps[2:]]
        with self.assertRaisesRegex(SyncError, 'unresolved archived owner/parent B'):
            self.run_report(steps, ['--final'], streams)
        self.assertEqual(streams.stdout.getvalue(), '')
        self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)
        self.assertEqual((self.root / 'history.json').read_bytes(), pending)
        # Recovery preview with no eligible B event can proceed, but must retain
        # the pending archived context rather than erase it during publication.
        steps = self.requests(current_items=[item('A')])
        steps[-1] = (Expected('/comments', [('task_id', 'B'), ('limit', '200')]),
            {'results': [dict(id='own', content='still surviving', posted_at=CREATED,
                             is_deleted=False, file_attachment=None)], 'next_cursor': None})
        self.run_report([self.sync('delta-token', delta()), *steps[2:]])
        self.assertNotIn('B', StateStore(self.root).load_consistent_state().current_snapshot.items)
        pending = self.store.load_history()
        self.assertIn('B', pending.snapshot.items)
        self.assertEqual(pending.snapshot.comments['own'].body, 'still surviving')
        self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)

    def test_retained_archived_parent_cannot_resolve_current_comment_role(self):
        first = self.requests(rows=[completed_b()], current_items=[item('A')])
        self.run_report(first)
        before = {name: (self.root / name).read_bytes()
                  for name in ('report-cursor', 'history.json')}
        steps = self.requests(rows=[item('X', parent_id='B', checked=True, completed_at=LAST)],
                              events=[event(1, LAST, owner='X', obj='xnote')],
                              current_items=[item('A')])
        x = (Expected('/comments', [('task_id', 'X'), ('limit', '200')]),
             {'results': [dict(id='xnote', content='Needs current ancestry', posted_at=CREATED,
                              is_deleted=False, file_attachment=None)], 'next_cursor': None})
        steps[-1] = x
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

    def test_unequal_completion_sources_use_activity_for_task_step_and_cutoffs(self):
        completed_at = '2026-10-21T18:11:14.704186Z'
        activity_at = '2026-10-21T18:11:14.719113Z'
        midpoint = '2026-10-21T18:11:14.710000Z'
        from todo_lib.workflows.report import render_report
        for parent in (None, 'A'):
            for args, expected in (([], 1), (['--since', midpoint], 1),
                                   (['--until', midpoint], 0)):
                with self.subTest(parent=parent, args=args):
                    row = item('B', parent_id=parent, checked=True,
                               completed_at=completed_at)
                    completion = event(601, activity_at, 'completed', obj='B', typ='item')
                    with patch('todo_lib.workflows.report.render_report', wraps=render_report) as render:
                        _, streams = self.run_report(self.requests(current_items=[item('A')],
                            rows=[row], events=[completion], comments=[]), args)
                    entries = render.call_args.kwargs['progress' if parent else 'finished']
                    self.assertEqual(len(entries), expected)
                    self.assertEqual(len(render.call_args.kwargs['finished' if parent else 'progress']), 0)
                    if expected:
                        self.assertEqual(d.instant_text(entries[0].instant), activity_at)
                        self.assertEqual(streams.stdout.getvalue().count(' — '), 1)

    def test_recurring_partial_overlap_fallback_and_dual_source_undo(self):
        from todo_lib.workflows.report import render_report
        active = [item('A', due=due(is_recurring=True)), item('B', parent_id='A')]
        older = '2026-10-21T10:00:00Z'
        completed_at = '2026-10-21T18:11:14.704186Z'
        activity_at = '2026-10-21T18:11:14.719113Z'
        rows = [item('A', completed_at=value, due=due(is_recurring=True))
                for value in (older, completed_at)]
        completion = event(602, activity_at, 'completed', obj='A', typ='item')
        for records, events, expected in (
                (rows, [completion], [older, activity_at]),
                (rows, [], [older, completed_at]),
                (rows[1:], [completion, event(603, FIRST, 'uncompleted', obj='A', typ='item')], [])):
            with self.subTest(expected=expected):
                with patch('todo_lib.workflows.report.render_report', wraps=render_report) as render:
                    self.run_report(self.requests(current_items=active, rows=records, events=events))
                self.assertEqual(sorted(d.instant_text(e.instant) for e in render.call_args.kwargs['finished']), expected)

    def test_activity_only_recurring_omitted_metadata_distinct_close_events(self):
        active = [item('A', due=due(is_recurring=True)), item('B', parent_id='A')]
        for identities, times in (((701, 702), (FIRST, LAST)),
                                  ((701, 702), (FIRST, FIRST)),
                                  ((None, None), (FIRST, FIRST)),
                                  ((701, 701), (FIRST, FIRST))):
            with self.subTest(identities=identities, times=times):
                events = [event(identity, time, 'completed', obj='A', typ='item')
                          for identity, time in zip(identities, times)]
                for row in events:
                    row.pop('extra_data')
                _, streams = self.run_report(self.requests(current_items=active, events=events))
                self.assertEqual(streams.stdout.getvalue().split('Progress')[0].count(' — A'),
                                 1 if identities == (701, 701) else 2)

    def test_anonymous_pending_identity_survives_scoped_and_global_evidence_reuse(self):
        active = [item('A'), item('B', parent_id='A', due=due(is_recurring=True))]
        events = [event(50, CREATED),
                  event(None, FIRST, 'completed', obj='B', typ='item'),
                  event(None, FIRST, 'completed', obj='B', typ='item'),
                  event(None, LAST, 'uncompleted', obj='B', typ='item')]
        from todo_lib.workflows.report import render_report
        for _ in range(2):
            with patch('todo_lib.workflows.report.render_report', wraps=render_report) as render:
                self.run_report(self.requests(current_items=active, events=events))
            self.assertEqual(sum(e.kind == 'completed' for e in render.call_args.kwargs['progress']), 1)
            observed = list(StateStore(self.root).load_history().snapshot.occurrences.values())
            self.assertEqual(len(observed), 2)
            self.assertEqual(sum(o.undone for o in observed), 1)
            self.assertEqual(sum(len(o.undo_ids) for o in observed), 1)

    def test_final_cleanup_retains_newer_activity_backed_ordinary_context(self):
        # Cleanup at a boundary between the source times must preserve context
        # for the activity-backed occurrence, including its ancestor.
        from todo_lib.local import prune_history
        completed_at = '2026-10-21T18:11:14.704186Z'
        activity_at = '2026-10-21T18:11:14.719113Z'
        boundary = d.instant_from_wire('2026-10-21T18:11:14.710000Z')
        row = item('B', parent_id='A', checked=True, completed_at=completed_at)
        completion = event(601, activity_at, 'completed', obj='B', typ='item')
        self.run_report(self.requests(current_items=[item('A')], rows=[row],
                                     events=[completion], comments=[]))
        pending = StateStore(self.root).load_history()
        observed = list(pending.snapshot.occurrences.values())
        self.assertEqual(len(observed), 1)
        self.assertEqual(d.instant_text(observed[0].completed_at), activity_at)
        # Remove observation-time retention to distinguish the occurrence-time
        # rule itself, then use the existing authorized cleanup boundary.
        pending = replace(pending, observations={})
        cleaned = prune_history(pending, boundary, output_finalized=True, saved_cursor=boundary)
        self.assertEqual(set(cleaned.snapshot.items), {'A', 'B'})
        self.assertEqual(list(cleaned.snapshot.occurrences.values()), observed)

    def test_anonymous_same_instant_undo_respects_source_order(self):
        active = [item('A', due=due(is_recurring=True)), item('B', parent_id='A')]
        events = [event(None, FIRST, kind, obj='A', typ='item')
                  for kind in ('uncompleted', 'completed', 'completed')]
        for row in events:
            del row['id']
        _, streams = self.run_report(self.requests(current_items=active, events=events))
        self.assertEqual(streams.stdout.getvalue().split('Progress')[0].count(' — A'), 2)

    def test_unknown_activity_owner_cannot_be_assumed_unrelated(self):
        unrelated = event(None, LAST, owner=None)
        unrelated.pop('parent_item_id')
        unrelated['parent_project_id'] = 'unmanaged'
        steps = self.requests(events=[unrelated])[:4]
        before = (self.root / 'report-cursor').read_bytes()
        streams = self.streams()
        with self.assertRaisesRegex(SyncError, 'parent_item_id'):
            self.run_report(steps, ['--final'], streams)
        self.assertEqual(streams.stdout.getvalue(), '')
        self.assertEqual((self.root / 'report-cursor').read_bytes(), before)

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
