"""Report-only recovery through real adapters, protected bytes and delivery."""
import unittest
from unittest.mock import patch
from dataclasses import replace
from todo_lib import domain as d
from todo_lib.local import LocalError
from todo_lib.presentation import OutputError
from todo_lib.workflows.report import Reporter
from todo_lib.syntax import CommandRequest, UsageError
from tests.support.report import ReportSupport, LAST, END, event, NOW
from tests.support.sync import completed_b
from tests.support.current import item
from tests.support.history import Expected


class Recovery(ReportSupport, unittest.TestCase):
    def bytes(self):
        return {n: (self.root / n).read_bytes() for n in ('cache.json', 'history.json', 'binding.json')}

    def test_mixed_unresolved_and_valid_with_and_without_override(self):
        for override in (False, True):
            with self.subTest(override=override):
                before = self.bytes()
                cursor = self.store.load_cursor()
                steps = self.requests(events=[event(1, LAST), event(2, LAST, 'completed', obj='missing', typ='item')])
                result, streams = self.run_report(steps, ['--final'] + (['--override'] if override else []))
                self.assertEqual(result.status, 0 if override else 1)
                self.assertEqual(result.finalized, override)
                self.assertIn('Current post-boundary text', streams.stdout.getvalue())
                self.assertIn('missing', streams.stderr.getvalue())
                self.assertIn('None. does not prove zero', streams.stderr.getvalue())
                self.assertEqual(self.bytes(), before)
                self.assertEqual(d.instant_text(self.store.load_cursor()), END if override else d.instant_text(cursor))

    def test_entire_history_unavailable_accepts_unknown_loss(self):
        before = self.bytes()
        result, streams = self.run_report(self.requests(access=False, completed_when_unavailable=True), ['--final', '--override'])
        self.assertEqual(result.status, 0)
        self.assertTrue(result.finalized)
        self.assertIn('Finished\n  None.', streams.stdout.getvalue())
        self.assertIn('activity history is unavailable', streams.stderr.getvalue())
        self.assertIn('unknown', streams.stderr.getvalue())
        self.assertIn('override accepted loss', streams.stderr.getvalue())
        self.assertEqual(self.bytes(), before)
        self.assertEqual(d.instant_text(self.store.load_cursor()), END)

    def test_later_activity_page_failure_preserves_first_page_and_saved_provenance(self):
        steps = self.requests(events=[event(1, LAST)])
        request, payload = steps[-1]
        steps[-1] = (request, dict(payload, next_cursor='later.page'))
        steps.append((Expected('/activities', request.query + [('cursor', 'later.page')]), {'results': []}))
        before = self.bytes()
        result, streams = self.run_report(steps, ['--final', '--override'])
        self.assertTrue(result.finalized)
        self.assertIn('Current post-boundary text', streams.stdout.getvalue())
        self.assertIn('page 2', streams.stderr.getvalue())
        self.assertIn('next_cursor', streams.stderr.getvalue())
        self.assertEqual(self.bytes(), before)

    def test_owner_failure_keeps_other_owner(self):
        steps = self.requests(rows=[completed_b()], current_items=[item('A')],
            current_notes=[dict(id='active', item_id='A', content='Independent comment', posted_at=LAST, is_deleted=False)],
            events=[event(1, LAST), event(2, LAST, owner='A', obj='active')])
        steps[-1] = (steps[-1][0], {'results': []})
        before = self.bytes()
        result, streams = self.run_report(steps, ['--final', '--override'])
        self.assertTrue(result.finalized)
        self.assertIn('Independent comment', streams.stdout.getvalue())
        self.assertIn('/comments', streams.stderr.getvalue())
        self.assertIn('B', streams.stderr.getvalue())
        self.assertEqual(self.bytes(), before)

    def test_current_mapping_failure_still_reads_independent_history_publicly(self):
        from tests.support.cli import invoke
        cursor = self.store.load_cursor()
        for response_kind in ('full', 'incremental'):
            with self.subTest(response_kind=response_kind):
                self.store.write_cursor(cursor)
                steps = self.requests(current_items=[item('A')], rows=[completed_b()],
                                      events=[event(1, LAST)])
                steps[0][1]['user_plan_limits']['current']['reminders'] = 'malformed'
                if response_kind == 'incremental':
                    # Valid delta omission inherits the proven bound identity.
                    steps[0] = (steps[0][0], dict(full_sync=False, sync_token='delta-token',
                        user_plan_limits=steps[0][1]['user_plan_limits']))
                del steps[1]  # Mapping fails before a freshness read is possible.
                before = self.bytes()
                transport, _ = self.boundary(steps)
                status, out, err, _ = invoke(self, ['report', '--final', '--override'], transport, now=NOW)
                self.assertEqual(status, 0, err)
                self.assertIn('Completed step: B', out)
                self.assertIn('Current post-boundary text', out)
                self.assertIn('reminders', err)
                self.assertIn('cached fallback', out)  # A's saved ancestry is explicit.
                self.assertEqual(self.bytes(), before)
                self.assertEqual(d.instant_text(self.store.load_cursor()), END)

    def test_conflicting_comment_versions_are_excluded_individually(self):
        from tests.support.cli import invoke
        for override in (False, True):
            with self.subTest(override=override):
                steps = self.requests(current_items=[item('A')], rows=[completed_b()],
                    events=[event(1, LAST), event(2, LAST, obj='safe')],
                    comments=[dict(id='own', content='Rejected first version', posted_at=LAST, is_deleted=False)])
                request, payload = steps[-1]
                steps[-1] = (request, dict(payload, next_cursor='next.page'))
                steps.append((Expected('/comments', request.query + [('cursor', 'next.page')]),
                    {'results': [dict(id='own', content='Rejected second version', posted_at=LAST, is_deleted=False)],
                     'next_cursor': 'last.page'}))
                steps.append((Expected('/comments', request.query + [('cursor', 'last.page')]),
                    {'results': [dict(id='safe', content='Independent safe text', posted_at=LAST, is_deleted=False),
                                 dict(id='invalid', content=None, posted_at=LAST, is_deleted=False)],
                     'next_cursor': None}))
                before, cursor = self.bytes(), (self.root / 'report-cursor').read_bytes()
                transport, _ = self.boundary(steps)
                status, out, err, _ = invoke(self, ['report', '--final'] + (['--override'] if override else []), transport, now=NOW)
                self.assertEqual(status, 0 if override else 1, err)
                self.assertNotIn('Rejected first version', out)
                self.assertNotIn('Rejected second version', out)
                self.assertIn('Independent safe text', out)
                if override:
                    self.assertIn(self.store.load_consistent_state().snapshot.comments['own'].body, out)
                    self.assertIn('cached fallback; observed', out)
                self.assertIn('own', err)
                self.assertIn('contradictory', err)
                self.assertEqual(self.bytes(), before)
                if override:
                    self.assertEqual(d.instant_text(self.store.load_cursor()), END)
                else:
                    self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)

    def test_cross_owner_comment_conflicts_are_omitted_publicly(self):
        from tests.support.cli import invoke
        from tests.support.history import item as completed_item
        original_cursor = self.store.load_cursor()
        for source in ('owners', 'sync', 'saved', 'invalid-owner', 'strict'):
            for override in ((True,) if source == 'strict' else (False, True)):
                with self.subTest(source=source, override=override):
                    self.store.write_cursor(original_cursor)
                    invalid = event(99, LAST)
                    del invalid['parent_item_id']  # Select recovery before strict composition.
                    identity = 'own' if source == 'saved' else 'collision'
                    shared = dict(id=identity, content='Conflicting REST text', posted_at=LAST, is_deleted=False)
                    steps = self.requests(current_items=[item('A')],
                        current_notes=([dict(shared, item_id='A', content='Conflicting Sync text')] if source == 'sync' else []),
                        rows=[completed_b(), completed_item('C', at=LAST)],
                        events=[event(2 if source == 'saved' else 1, LAST, owner='B', obj=identity),
                                event(1 if source == 'saved' else 2, LAST, owner='C', obj=identity),
                                event(3, LAST, owner='C', obj='safe')] + ([] if source == 'strict' else [invalid]), comments=[shared])
                    if source == 'invalid-owner':
                        steps[-2][1]['results'][0] = dict(shared, content=None)
                    steps[-1] = (steps[-1][0], {'results': [shared,
                        dict(id='safe', content='Independent safe text', posted_at=LAST, is_deleted=False)], 'next_cursor': None})
                    before, cursor = self.bytes(), (self.root / 'report-cursor').read_bytes()
                    transport, _ = self.boundary(steps)
                    status, out, err, _ = invoke(self, ['report', '--final'] + (['--override'] if override else []), transport, now=NOW)
                    self.assertEqual(status, 0 if override else 1, err)
                    self.assertNotIn('Conflicting REST text', out)
                    self.assertNotIn('Conflicting Sync text', out)
                    self.assertIn('Independent safe text', out)
                    self.assertIn('Completed step: B', out)
                    self.assertIn('incompatible comment ownership ' + identity, err)
                    if source == 'saved' and override:
                        self.assertIn(self.store.load_consistent_state().snapshot.comments['own'].body, out)
                        self.assertIn('cached fallback; observed', out)
                    self.assertIn('B, C', err)
                    self.assertEqual(self.bytes(), before)
                    if override:
                        self.assertEqual(d.instant_text(self.store.load_cursor()), END)
                    else:
                        self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)
                    self.store.write_cursor(d.instant_from_wire(cursor.decode().strip()))

    def test_unavailable_activity_still_reads_completed_scopes_publicly(self):
        from tests.support.cli import invoke
        original_cursor = self.store.load_cursor()
        for capability in ('access', 'zero'):
            with self.subTest(capability=capability):
                self.store.write_cursor(original_cursor)
                steps = self.requests(current_items=[item('A')], rows=[completed_b()],
                    access=capability != 'access', days=0 if capability == 'zero' else -1,
                    completed_when_unavailable=True)
                before, cursor = self.bytes(), (self.root / 'report-cursor').read_bytes()
                transport, http = self.boundary(steps)
                status, out, err, _ = invoke(self, ['report', '--final', '--override'], transport, now=NOW)
                self.assertEqual(status, 0, err)
                self.assertIn('Completed step: B', out)
                self.assertNotIn('Current post-boundary text', out)  # No proven comment add/edit activity.
                self.assertIn('/activities', err)
                self.assertIn('amount unknown', err)
                self.assertIn('override accepted loss', err)
                self.assertEqual(len(http.requests), 4)  # Two Sync, completed, scoped comments.
                self.assertEqual(self.bytes(), before)
                self.assertEqual(d.instant_text(self.store.load_cursor()), END)
                self.store.write_cursor(d.instant_from_wire(cursor.decode().strip()))
                # Ordinary final still refuses before any history request.
                transport, _ = self.boundary(steps[:2])
                status, out, err, _ = invoke(self, ['report', '--final'], transport, now=NOW)
                self.assertNotEqual(status, 0)
                self.assertEqual(out, '')
                self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)

    def test_invalid_rows_keep_independent_same_page_events(self):
        from tests.support.cli import invoke
        for override in (False, True):
            with self.subTest(override=override):
                invalid = event(2, LAST, obj='missing-owner')
                del invalid['parent_item_id']
                steps = self.requests(events=[event(1, LAST), invalid, None])
                before, cursor = self.bytes(), (self.root / 'report-cursor').read_bytes()
                transport, _ = self.boundary(steps)
                status, out, err, _ = invoke(self, ['report', '--final'] + (['--override'] if override else []), transport, now=NOW)
                self.assertEqual(status, 0 if override else 1, err)
                self.assertIn('Current post-boundary text', out)
                self.assertIn('parent_item_id', err)
                self.assertIn('/activities', err)
                self.assertIn('omitted record 2', err)
                self.assertEqual(self.bytes(), before)
                if override:
                    self.assertEqual(d.instant_text(self.store.load_cursor()), END)
                else:
                    self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)

    def test_invalid_completed_row_keeps_independent_same_page_occurrence(self):
        invalid = completed_b()
        invalid['id'] = 'invalid'
        del invalid['parent_id']
        before = self.bytes()
        steps = self.requests(current_items=[item('A')], rows=[completed_b()])
        steps[2][1]['items'].insert(0, invalid)
        result, streams = self.run_report(steps, ['--final', '--override'])
        self.assertTrue(result.finalized)
        self.assertIn('Completed step: B', streams.stdout.getvalue())
        self.assertIn('parent_id', streams.stderr.getvalue())
        self.assertIn('omitted record invalid', streams.stderr.getvalue())
        self.assertEqual(self.bytes(), before)
        self.assertEqual(d.instant_text(self.store.load_cursor()), END)

    def test_bound_cached_occurrence_and_unknown_observation(self):
        self.run_report(self.requests(rows=[completed_b()], current_items=[item('A')]))
        history = self.store.load_history()
        self.store.save_history(replace(history, observations={k: None for k in history.snapshot.items}))
        before = self.bytes()
        # A mismatch discards the full remote payload, including its private title.
        steps = self.requests()[:1]
        steps[0][1]['user']['id'] = 'foreign-account'
        steps[0][1]['items'][0]['content'] = 'Foreign private title'
        steps[0][1]['items'][0]['parent_id'] = {}  # Reject identity before foreign mapping/diagnostics.
        result, streams = self.run_report(steps, ['--final', '--override'])
        self.assertTrue(result.finalized)
        self.assertIn('Completed step: B', streams.stdout.getvalue())
        self.assertIn('cached fallback; observed unknown', streams.stdout.getvalue())
        self.assertIn('authenticated account differs', streams.stderr.getvalue())
        self.assertNotIn('Foreign private title', streams.stdout.getvalue() + streams.stderr.getvalue())
        self.assertIn('add/edit activity timing unproved', streams.stderr.getvalue())
        self.assertEqual(self.bytes(), before)

    def test_override_output_diagnostics_flush_cursor_failure_and_interrupt(self):
        for failure in ('stdout-write', 'stdout-flush', 'stderr-write', 'stderr-flush', 'stdout-short', 'stderr-short', 'cursor', 'interrupt'):
            with self.subTest(failure=failure):
                streams = self.streams()
                before = (self.root / 'report-cursor').read_bytes()
                def broken(*args):
                    if failure.endswith('short'):
                        return 0
                    raise KeyboardInterrupt() if failure == 'interrupt' else OSError('controlled failure')
                if failure == 'cursor':
                    target, name = self.store, 'write_cursor'
                else:
                    target = streams.stderr if failure.startswith('stderr') else streams.stdout
                    name = 'flush' if failure.endswith('flush') else 'write'
                with patch.object(target, name, side_effect=broken):
                    with self.assertRaises((OutputError, OSError, KeyboardInterrupt)):
                        self.run_report(self.requests(access=False, completed_when_unavailable=True), ['--final', '--override'], streams)
                self.assertEqual((self.root / 'report-cursor').read_bytes(), before)

    def test_diagnostics_and_stdout_flush_precede_same_fixed_end_cursor(self):
        streams = self.streams()
        original = self.store.write_cursor
        with patch.object(streams.stdout, 'flush', wraps=streams.stdout.flush) as out, patch.object(streams.stderr, 'flush', wraps=streams.stderr.flush) as err:
            def save(end):
                self.assertTrue(out.called and err.called)
                self.assertIn('override accepted loss', streams.stderr.getvalue())
                self.assertIn('Hidden\n', streams.stdout.getvalue())
                self.assertEqual(d.instant_text(end), END)
                original(end)
            with patch.object(self.store, 'write_cursor', side_effect=save):
                self.run_report(self.requests(access=False, completed_when_unavailable=True), ['--final', '--override'], streams)

    def test_programmatic_invalid_options_before_local_work(self):
        with patch.object(self.store, 'load_binding', side_effect=AssertionError('local work')):
            for options in ((('override', True),), (('final', True), ('override', True), ('yes', True)),
                            (('final', True), ('override', True), ('until', LAST)),
                            (('final', True), ('override', True), ('override', True)), (('unknown', True),)):
                with self.assertRaises(UsageError):
                    Reporter(None, self.store).run(CommandRequest('report', options=options))

    def test_expired_start_retrieves_supported_portion(self):
        steps = self.requests(days=1, events=[event(1, LAST)])
        # Fixed-end minus one elapsed UTC day, rounded only for request coverage.
        cq = [('project_id', 'cat'), ('since', '2026-10-21T12:00:00Z'), ('until', '2026-10-22T12:00:01Z'), ('limit', '200')]
        aq = [('date_from', '2026-10-21T12:00:00Z'), ('date_to', '2026-10-22T12:00:01Z'), ('limit', '200'), steps[3][0].query[-1]]
        steps[2] = (Expected('/tasks/completed/by_completion_date', cq), steps[2][1])
        steps[3] = (Expected('/activities', aq), steps[3][1])
        result, streams = self.run_report(steps, ['--final', '--override'])
        self.assertTrue(result.finalized)
        self.assertIn('Current post-boundary text', streams.stdout.getvalue())
        self.assertIn('expired range from', streams.stderr.getvalue())

    def test_failed_completed_page_keeps_valid_records_and_activity(self):
        steps = self.requests(current_items=[item('A')], rows=[completed_b()], events=[event(1, LAST)])
        request, payload = steps[2]
        steps[2] = (request, dict(payload, next_cursor='later.page'))
        steps.insert(3, (Expected('/tasks/completed/by_completion_date', request.query + [('cursor', 'later.page')]), {'items': 'invalid'}))
        before = self.bytes()
        result, streams = self.run_report(steps, ['--final', '--override'])
        self.assertTrue(result.finalized)
        self.assertIn('Completed step: B', streams.stdout.getvalue())
        self.assertIn('Current post-boundary text', streams.stdout.getvalue())
        self.assertIn('page 2', streams.stderr.getvalue())
        self.assertEqual(self.bytes(), before)

    def test_authentication_failure_known_observation_and_no_new_activity(self):
        from urllib.error import HTTPError
        from io import BytesIO
        steps = self.requests()[:1]
        steps[0] = (steps[0][0], HTTPError('https://api.todoist.com/api/v1/sync', 401, 'Unauthorized', {}, BytesIO(b'{"error":"Unauthorized","error_code":401}')))
        before = self.bytes()
        result, streams = self.run_report(steps, ['--final', '--override'])
        self.assertTrue(result.finalized)
        self.assertIn('401', streams.stderr.getvalue())
        self.assertIn('observed 2026-10-20T13:00:00Z', streams.stderr.getvalue())
        self.assertIn('Finished\n  None.', streams.stdout.getvalue())
        self.assertEqual(self.bytes(), before)

    def test_fresh_delete_and_reopen_defeat_saved_occurrence(self):
        for kind in ('deleted', 'uncompleted'):
            with self.subTest(kind=kind):
                self.run_report(self.requests(rows=[completed_b()], current_items=[item('A')]))
                events = [event(1, LAST, kind, obj='B', typ='item')]
                steps = self.requests(current_items=[item('A')], events=events)
                # Force recovery with a separate unresolved completion.
                steps[3][1]['results'].append(event(2, LAST, 'completed', obj='missing', typ='item'))
                if kind == 'deleted':
                    steps = steps[:4]
                # Reopen without current metadata cannot safely resurrect B;
                # completion eligibility still loses to the fresh undo.
                result, streams = self.run_report(steps, ['--final', '--override'])
                self.assertTrue(result.finalized)
                self.assertNotIn('Completed step: B', streams.stdout.getvalue())
                # Restore boundary for the next independent source case.
                from tests.support.sync import CURSOR
                self.store.write_cursor(CURSOR)

    def test_fresh_departure_beats_cached_completed_owner(self):
        self.run_report(self.requests(rows=[completed_b()], current_items=[item('A')]))
        outside = item('B', project_id='unmanaged')
        steps = self.requests(current_items=[item('A'), outside],
            events=[event(9, LAST, 'completed', obj='missing', typ='item')])
        before = self.bytes()
        result, streams = self.run_report(steps, ['--final', '--override'])
        self.assertTrue(result.finalized)
        self.assertNotIn('Completed step: B', streams.stdout.getvalue())
        self.assertNotIn('cached fallback task B', streams.stderr.getvalue())
        self.assertEqual(self.bytes(), before)

    def test_override_required_cursor_and_history_and_unsafe_cache_still_fail(self):
        for name, value in (('report-cursor', b'corrupt'), ('history.json', b'{}')):
            original = (self.root / name).read_bytes()
            self.put(name, value)
            with self.assertRaises(LocalError):
                self.run_report([], ['--final', '--override'])
            self.assertEqual((self.root / name).read_bytes(), value)
            self.put(name, original)
        cache = self.root / 'cache.json'
        original = cache.read_bytes()
        cache.unlink()
        cache.symlink_to(self.root / 'config')
        with self.assertRaises(LocalError):
            self.run_report([], ['--final', '--override'])
        cache.unlink()
        self.put('cache.json', original)

    def test_corrupt_disposable_cache_supplies_no_fallback_and_is_preserved(self):
        self.put('cache.json', b'corrupt-disposable-cache')
        # requests() deliberately needs a valid fixture cache, so form the known
        # first Sync request directly. No corrupt content can establish context.
        from todo_lib.adapter.transport import HTTPFailure
        # Reject before a response body; a partial report can use required history
        # (empty here), while the corrupt cache remains untouched.
        transport = unittest.mock.Mock()
        transport.request.side_effect = HTTPFailure('current Sync: unavailable')
        streams = self.streams()
        result = Reporter(transport, self.store, clock=lambda: NOW, streams=streams).run(['--final', '--override'])
        self.assertTrue(result.finalized)
        self.assertEqual((self.root / 'cache.json').read_bytes(), b'corrupt-disposable-cache')
        self.assertNotIn('cached fallback task', streams.stderr.getvalue())
        self.assertIn('Finished\n  None.', streams.stdout.getvalue())

    def test_incompleteness_cannot_be_suppressed_by_warning_preference(self):
        self.put('config', b'[main]\nproject=root\ndefault_sections=cat\nhidden_from_now=\n[report]\nwarn_limited_history=false\n')
        result, streams = self.run_report(self.requests(events=[event(1, LAST, 'completed', obj='missing', typ='item')]), ['--final'])
        self.assertEqual(result.status, 1)
        self.assertIn('incomplete report', streams.stderr.getvalue())
        self.assertIn('finalization refused', streams.stderr.getvalue())
