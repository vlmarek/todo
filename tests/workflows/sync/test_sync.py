"""Composed real adapter/store probes, using synthetic provider-shaped responses.

Pinned offline authority: api-v1.openapi.json Sync tag; completed/by_completion_date
items with omitted terminal cursor; scoped REST comments without item_id. The
shared controlled HTTP boundary checks exact forms, filters and pagination.
"""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from todo_lib import domain as d
from todo_lib.adapter.current import retrieve
from todo_lib.adapter.transport import Transport
from todo_lib.local import (StateStore, LocalError, empty_history, prepare_candidates,
                            exclusive_lock)
from todo_lib.local.codec import loads
from todo_lib.workflows import Synchronizer, SyncError, SyncInterrupted
from tests.adapter.current.test_current import (BINDING, RESOURCES, full, delta,
                                               item, note, project)
from tests.adapter.history.test_history import Expected
from tests.support.http import ControlledHTTP, ExpectedRequest, Response

CREATED = '2026-10-20T12:00:00.123456789012345Z'
DONE = '2026-10-21T12:00:00.123456789012349Z'
COMMENT = '2026-10-21T12:00:00.123456789012348Z'
NOW = d.instant_from_wire('2026-10-22T12:00:00.123456789012350Z')
INITIAL = d.instant_from_wire('2026-10-20T13:00:00Z')
CURSOR = d.instant_from_wire('2026-10-20T00:00:00Z')
COMPLETED_QUERY = [('project_id', 'cat'), ('since', '2026-10-20T00:00:00Z'),
                   ('until', '2026-10-22T12:00:01Z'), ('limit', '200')]


def open_tree(**changes):
    return full(items=[item('A', added_at=CREATED),
                       item('B', parent_id='A', added_at=CREATED)],
                notes=[note('own', 'B', posted_at=CREATED)], **changes)


def completed_b(**changes):
    return item('B', parent_id='A', checked=True, completed_at=DONE,
                added_at=CREATED, **changes)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / '.todo'
        self.root.mkdir(mode=0o700)
        self.store = StateStore(self.root)
        self.put('config', b'[main]\nproject=root\ndefault_sections=cat\nhidden_from_now=\n')
        # Observe the open tree through real adapter mapping. No completed seed.
        transport, _ = self.boundary([self.sync('*', open_tree()),
                                     self.sync('full-token', delta())])
        observed = retrieve(transport, BINDING)
        with exclusive_lock('init', self.root):
            self.store.publish_snapshot(prepare_candidates(observed.snapshot,
                empty_history(observed.snapshot), account_display='Person',
                waiting_label_ids=observed.waiting_label_ids, current_snapshot=observed.snapshot, sync_token=observed.sync_token, synced_at=INITIAL, initial_cursor=CURSOR))

    def put(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        path.chmod(0o600)

    def sync(self, token, data):
        return (ExpectedRequest('POST', '/sync', 'secret', form={
            'sync_token': token, 'resource_types': RESOURCES}), data)

    def completed(self, rows):
        return (Expected('/tasks/completed/by_completion_date', COMPLETED_QUERY), {'items': rows})

    def comments(self, body='Surviving own comment', **changes):
        raw = dict(id='own', content=body, posted_at=COMMENT,
                   is_deleted=False, file_attachment=None, **changes)
        return (Expected('/comments', [('task_id', 'B'), ('limit', '200')]),
                {'results': [raw], 'next_cursor': None})

    def boundary(self, steps):
        http = ControlledHTTP([(request, value if isinstance(value, (Response, Exception))
                     else Response(json.dumps(value).encode())) for request, value in steps])
        self.addCleanup(http.assert_done)
        return Transport('secret', opener=http, sleep=lambda _: None), http

    def workflow(self, steps=(), now=NOW):
        transport, http = self.boundary(steps)
        return Synchronizer(transport, self.store, clock=lambda: now), http

    def external(self):
        return [self.sync('delta-token', full(items=[item('A', added_at=CREATED)])),
                self.sync('full-token', delta()), self.completed([completed_b()]), self.comments()]

    def retained(self, *, c=False):
        steps = [self.completed([]), self.comments()]
        if c:
            steps.append((Expected('/comments', [('task_id', 'C'), ('limit', '200')]),
                          {'results': [], 'next_cursor': None}))
        return steps

    def bytes(self):
        return {name: (self.root / name).read_bytes() for name in
                ('cache.json', 'history.json', 'binding.json', 'report-cursor')}

    def child_process(self, mixed=False):
        # Separate interpreter uses the public workflow/store. Any HTTP is fatal.
        script = '''
import json, sys
from todo_lib.workflows import Synchronizer
from todo_lib.local import StateStore, LocalError
from todo_lib.domain import instant_from_wire, instant_text, instant_key
class NoHTTP:
    def request(self, *a, **k):
        raise AssertionError('offline HTTP')
w = Synchronizer(NoHTTP(), StateStore(sys.argv[1]), clock=lambda: instant_from_wire('2026-10-24T12:00:00Z'))
try:
    r = w.read_local()
except LocalError as error:
    if sys.argv[2] != 'mixed': raise
    assert 'mixed' in str(error) or 'required history' in str(error), str(error)
    print('refused mixed set with zero HTTP')
else:
    assert sys.argv[2] != 'mixed'
    b = r.history.snapshot.items['B']
    c = r.history.snapshot.comments['own']
    assert b.parent_id == 'A' and b.completed
    assert instant_text(b.added_at) == sys.argv[3]
    assert instant_key(b.added_at) == instant_key(instant_from_wire(sys.argv[3]))
    assert instant_text(b.completed_at) == sys.argv[4]
    assert instant_text(c.added_at) == sys.argv[5]
    assert c.body == 'Surviving own comment' and c.item_id == 'B'
    assert r.warnings
    print('coherent precise state with zero HTTP')
'''
        result = subprocess.run([sys.executable, '-B', '-c', script, str(self.root),
                'mixed' if mixed else 'coherent', CREATED, DONE, COMMENT],
                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def assert_precise(self):
        state = StateStore(self.root).load_consistent_state()
        for s in (state.snapshot, state.history.snapshot):
            self.assertEqual(set(s.items), {'A', 'B'})
            b, c = s.items['B'], s.comments['own']
            self.assertFalse(s.items['A'].completed)
            self.assertTrue(b.completed)
            self.assertEqual(b.parent_id, 'A')
            for value, expected in ((b.added_at, CREATED), (b.completed_at, DONE),
                                    (c.added_at, COMMENT)):
                self.assertEqual(d.instant_text(value), expected)
                self.assertEqual(d.instant_key(value), d.instant_key(d.instant_from_wire(expected)))
            self.assertEqual(c.body, 'Surviving own comment')
        return state

    def reminder_hydration(self, final, *, resolved=True):
        # Synthetic Sync NotificationSyncView due shapes from pinned upstream
        # api-v1.openapi.json. C is absent from current and not yet scope-resolved.
        from tests.support.reminders import absolute
        first = absolute('historical', item_id='C')
        conflicting = absolute('historical', {'date': '2025-02-12T10:00:00',
            'lang': 'en', 'timezone': 'Europe/Madrid'}, item_id='C')
        steps = [self.sync('delta-token', delta(items=[item('entrant')],
                    reminders=[first, conflicting])),
                 self.sync('*', full(items=[item('A', added_at=CREATED), item('entrant')],
                                      reminders=final)),
                 self.sync('full-token', delta()),
                 self.completed([completed_b()] + ([item('C', checked=True,
                    completed_at=DONE, added_at=CREATED)] if resolved else [])),
                 self.comments()]
        if resolved:
            steps.append((Expected('/comments', [('task_id', 'C'), ('limit', '200')]),
                          {'results': [], 'next_cursor': None}))
        return steps

    def test_authoritative_reminder_replacement_before_history_owner_resolution(self):
        from tests.support.reminders import absolute, MINIMAL
        replacement = absolute('historical', item_id='C')
        workflow, _ = self.workflow(self.reminder_hydration([replacement]))
        workflow.refresh()
        state = self.store.load_consistent_state()
        for snapshot in (state.snapshot, state.history.snapshot):
            self.assertTrue(snapshot.items['C'].completed)
            self.assertEqual(snapshot.reminders['historical'].due.raw_due, MINIMAL)
            self.assertEqual(snapshot.reminders['historical'].notify_uid, 'recipient')
        offline, _ = self.workflow()
        self.assertEqual(offline.read_local().snapshot.reminders, state.snapshot.reminders)

    def test_deferred_reminder_duplicates_normalize_optional_defaults(self):
        from tests.support.reminders import absolute
        minimal = {'date': '2026-10-30T09:00:00', 'lang': 'en'}
        explicit = {**minimal, 'timezone': None, 'is_recurring': False}
        workflow, _ = self.workflow(self.reminder_hydration([
            absolute('historical', explicit, item_id='C'),
            absolute('historical', minimal, item_id='C')]))
        workflow.refresh()
        offline, _ = self.workflow()
        result = offline.read_local()
        for snapshot in (result.snapshot, result.history.snapshot):
            self.assertEqual(snapshot.reminders['historical'].due.raw_due, minimal)
            self.assertTrue(snapshot.items['C'].completed)

    def test_reminder_final_invalid_contradictory_or_unresolved_owner_preserves_state(self):
        from tests.support.reminders import absolute
        cases = [([absolute('historical', {'date': '2025-02-12'}, item_id='C')], True),
                 ([absolute('historical', item_id='C'), absolute('historical',
                    {'date': '2025-02-12T10:00:00', 'timezone': 'Europe/Madrid'}, item_id='C')], True)]
        for final, resolved in cases:
            with self.subTest(final=final, resolved=resolved):
                before = self.bytes()
                workflow, _ = self.workflow(self.reminder_hydration(final, resolved=resolved))
                with self.assertRaisesRegex(SyncError, 'exact time|contradictory|unresolved reminder owner'):
                    workflow.refresh()
                self.assertEqual(self.bytes(), before)

    def test_never_known_final_owner_is_silently_discarded_after_required_history(self):
        from tests.support.reminders import absolute
        raw = absolute('historical', item_id='C', type='unsupported', due={'private': 'unused'})
        workflow, http = self.workflow(self.reminder_hydration([raw], resolved=False))
        result = workflow.refresh()
        self.assertFalse(result.warnings)
        state = StateStore(self.root).load_consistent_state()
        self.assertNotIn('C', state.snapshot.items)
        self.assertFalse(state.snapshot.reminders)
        self.assertEqual(state.current_reminder_ids, frozenset())
        self.assertEqual(state.sync_token, 'delta-token')
        self.assertEqual(len(http.requests), 5)

    def test_full_unrelated_owner_then_reminder_only_delta_saves_managed_baseline(self):
        from tests.support.reminders import absolute
        outside = item('private-owner', project_id='elsewhere', content='Unrelated private title')
        ignored = absolute('private-reminder', item_id='private-owner', type='unsupported',
                           due={'unrelated': 'unused payload'})
        workflow, http = self.workflow([
            self.sync('delta-token', full(
                items=[item('A', added_at=CREATED), item('B', parent_id='A', added_at=CREATED), outside],
                reminders=[ignored])), self.sync('full-token', delta(sync_token='managed-baseline'))])
        self.assertFalse(workflow.refresh().warnings)
        self.assertEqual(len(http.requests), 2)
        state = StateStore(self.root).load_consistent_state()
        self.assertNotIn('private-owner', state.snapshot.items)
        self.assertNotIn('private-owner', state.history.snapshot.items)
        self.assertEqual(state.current_reminder_ids, frozenset())
        workflow, http = self.workflow([self.sync('managed-baseline', delta(
            reminders=[ignored], sync_token='ignored-delta-token'))])
        self.assertFalse(workflow.refresh().warnings)
        self.assertEqual(len(http.requests), 1)
        state = StateStore(self.root).load_consistent_state()
        self.assertEqual(state.sync_token, 'ignored-delta-token')
        self.assertEqual(state.current_reminder_ids, frozenset())
        for data in self.bytes().values():
            for text in (b'private-owner', b'private-reminder', b'Unrelated private', b'unused payload'):
                self.assertNotIn(text, data)

    def test_known_owner_reminder_cannot_hide_unresolved_lifecycle(self):
        from tests.support.reminders import absolute
        before = self.bytes()
        workflow, http = self.workflow([
            self.sync('delta-token', full(items=[item('A', added_at=CREATED)],
                reminders=[absolute('known-reminder', item_id='B')])),
            self.sync('full-token', delta()), self.completed([])])
        with self.assertRaises(SyncError) as caught:
            workflow.refresh()
        for value in ('unresolved disappeared managed item B', 'supported lifecycle evidence required',
                      'reminder known-reminder', 'cached title B', 'cached category cat', 'type absolute'):
            self.assertIn(value, str(caught.exception))
        self.assertNotIn('Read-only recovery:', str(caught.exception))
        self.assertEqual(self.bytes(), before)
        self.assertEqual(len(http.requests), 3)

    def test_cached_managed_reminder_failure_keeps_reason_context_and_files(self):
        from tests.support.reminders import absolute
        workflow, _ = self.workflow(self.reminder_hydration([absolute('historical', item_id='C')]))
        workflow.refresh()
        before = self.bytes()
        raw = absolute('historical', {'date': {'private': 'do not dump'}}, item_id='C')
        workflow, http = self.workflow([self.sync('delta-token', delta(reminders=[raw])), *self.retained(c=True)])
        with self.assertRaises(SyncError) as caught:
            workflow.refresh()
        message = str(caught.exception)
        for text in ('due.date must be', 'reminder historical', 'owner C', 'cached title C',
                     'cached category cat', 'type absolute', 'date=<malformed object>'):
            self.assertIn(text, message)
        self.assertNotIn('do not dump', message)
        self.assertNotIn('Read-only recovery:', message)
        self.assertEqual(len(http.requests), 4)
        self.assertEqual(self.bytes(), before)

    def test_reminder_delta_update_delete_and_full_omission_after_history_resolution(self):
        from tests.support.reminders import absolute, MINIMAL
        workflow, _ = self.workflow(self.reminder_hydration([absolute('historical', item_id='C')]))
        workflow.refresh()
        workflow, _ = self.workflow([self.sync('delta-token', delta()), *self.retained(c=True)])
        workflow.refresh()
        self.assertIn('historical', self.store.load_consistent_state().snapshot.reminders)
        update = {**MINIMAL, 'date': '2025-02-12T11:00:00'}
        workflow, _ = self.workflow([self.sync('delta-token', delta(reminders=[absolute('historical', update, item_id='C')])), *self.retained(c=True)])
        workflow.refresh()
        self.assertEqual(self.store.load_history().snapshot.reminders['historical'].due.raw_due, update)
        # Full omission of the now-known completed owner's reminder is authoritative.
        steps = [self.sync('delta-token', full(items=[item('A', added_at=CREATED), item('entrant')])),
                 self.sync('full-token', delta()),
                 self.completed([completed_b(), item('C', checked=True, completed_at=DONE, added_at=CREATED)]),
                 self.comments(), (Expected('/comments', [('task_id', 'C'), ('limit', '200')]),
                                   {'results': [], 'next_cursor': None})]
        workflow, _ = self.workflow(steps)
        workflow.refresh()
        self.assertNotIn('historical', self.store.load_history().snapshot.reminders)
        workflow, _ = self.workflow([self.sync('delta-token', delta(reminders=[absolute('historical', item_id='C')])), *self.retained(c=True)])
        workflow.refresh()
        workflow, _ = self.workflow([self.sync('delta-token', delta(reminders=[{'id': 'historical', 'is_deleted': True}])), *self.retained(c=True)])
        workflow.refresh()
        self.assertNotIn('historical', self.store.load_history().snapshot.reminders)

    def test_floating_reminder_tombstone_with_timezone_change_retains_pending_history(self):
        from tests.support.reminders import absolute, FLOATING
        workflow, _ = self.workflow(self.reminder_hydration([absolute('historical', FLOATING, item_id='C')]))
        workflow.refresh()
        before = self.store.load_history()
        workflow, _ = self.workflow([self.sync('delta-token', delta(
            reminders=[{'id': 'historical', 'is_deleted': True}],
            user={'id': 'u', 'tz_info': {'timezone': 'America/New_York'}})), *self.retained(c=True)])
        workflow.refresh()
        for snapshot in (self.store.load_consistent_state().snapshot, self.store.load_history().snapshot):
            self.assertNotIn('historical', snapshot.reminders)
            self.assertEqual(set(snapshot.items), set(before.snapshot.items))
            self.assertEqual(snapshot.account.timezone, 'America/New_York')
        self.assertEqual(self.store.load_history().coverage, before.coverage)
        workflow, _ = self.workflow([self.sync('delta-token', delta()), *self.retained(c=True)])
        workflow.refresh()
        self.assertNotIn('historical', self.store.load_history().snapshot.reminders)

    def test_absolute_reminder_through_external_completion_and_reopen(self):
        from tests.support.reminders import absolute
        raw = absolute('absolute', item_id='B')
        workflow, _ = self.workflow([self.sync('delta-token', delta(reminders=[raw]))], now=INITIAL)
        workflow.refresh()
        original = self.store.load_history().snapshot.reminders
        steps = self.external()
        steps[0][1]['reminders'] = [raw]
        workflow, _ = self.workflow(steps)
        workflow.refresh()
        state = self.store.load_consistent_state()
        self.assertTrue(state.snapshot.items['B'].completed)
        self.assertEqual(state.history.snapshot.reminders, original)
        workflow, _ = self.workflow([self.sync('delta-token', delta(items=[item('B', parent_id='A', added_at=CREATED)])),
            self.sync('*', open_tree(reminders=[raw])), self.sync('full-token', delta())])
        workflow.refresh()
        state = self.store.load_consistent_state()
        self.assertFalse(state.snapshot.items['B'].completed)
        self.assertEqual(state.snapshot.reminders, original)
        self.assertEqual(state.history.snapshot.reminders, original)

    def test_external_completion_restart_refresh_and_clear_rebuild_precise(self):
        workflow, _ = self.workflow([self.sync('delta-token', delta())], now=INITIAL)
        workflow.refresh()  # protected open observations, not completed history
        self.assertFalse(self.store.load_history().snapshot.items['B'].completed)
        workflow, _ = self.workflow(self.external())
        workflow.refresh()
        self.assert_precise()
        self.assertIn('coherent', self.child_process())
        workflow, _ = self.workflow([self.sync('delta-token', delta()), *self.retained()])
        workflow.refresh()
        self.assert_precise()
        workflow, _ = self.workflow([self.sync('*', full(items=[item('A', added_at=CREATED)])),
            self.sync('full-token', delta()), self.completed([completed_b()]), self.comments()])
        result = workflow.refresh(clear_cache=True)
        self.assertTrue(result.cache_cleared)
        self.assertIn('unreported history', result.warnings[0])
        self.assert_precise()
        self.child_process()
        raw = loads((self.root / 'cache.json').read_bytes())
        self.assertNotIn('timezone', raw)
        self.assertEqual(raw['sync_token'], 'delta-token')

    def test_stored_project_seed_then_shared_change_preserves_state(self):
        # setUp retrieved is_shared-only projects through full plus freshness,
        # then published them. Refresh reloads the internal saved representation.
        workflow, _ = self.workflow([self.sync('delta-token', delta())])
        workflow.refresh()
        state = StateStore(self.root).load_consistent_state()
        self.assertFalse(state.snapshot.root.shared)
        self.assertFalse(state.snapshot.categories['cat'].shared)
        before = self.bytes()
        workflow, _ = self.workflow([self.sync('delta-token', delta(projects=[
            project(is_shared=True, shared=False)]))])
        with self.assertRaises(SyncError) as caught:
            workflow.refresh()
        self.assertEqual(caught.exception.phase, 'current retrieval')
        self.assertEqual(self.bytes(), before)

    def test_authoritative_null_and_reopen_replace_both_stores(self):
        workflow, _ = self.workflow(self.external())
        workflow.refresh()
        workflow, _ = self.workflow([self.sync('delta-token', delta(items=[
            item('B', parent_id='A', added_at=None)], notes=[note('own', 'B', posted_at=None)])),
            self.sync('*', full(items=[item('A', added_at=CREATED), item('B', parent_id='A', added_at=None)],
                notes=[note('own', 'B', posted_at=None)])), self.sync('full-token', delta())])
        workflow.refresh()
        state = self.store.load_consistent_state()
        for s in (state.snapshot, state.history.snapshot):
            self.assertIsNone(s.items['B'].added_at)
            self.assertIsNone(s.comments['own'].added_at)
            self.assertFalse(s.items['B'].completed)
            self.assertIsNone(s.items['B'].completed_at)
            self.assertFalse(s.occurrences)
        workflow, _ = self.workflow([self.sync('delta-token', delta())])
        workflow.refresh(clear_cache=False)
        self.assertIsNone(self.store.load_history().snapshot.items['B'].added_at)

    def test_unresolved_absence_failed_retrieval_and_invalid_remote_preserve_bytes(self):
        cases = [([self.sync('delta-token', Response(b'{}', status=401))], 'current retrieval'),
            ([self.sync('delta-token', delta(items=[{'id': 'A', 'parent_id': 'B'}]))], 'current retrieval'),
            ([self.sync('delta-token', full(items=[item('A')])),
              self.sync('full-token', delta()), self.completed([])], 'lifecycle reconciliation')]
        for steps, phase in cases:
            with self.subTest(phase=phase, steps=len(steps)):
                before = self.bytes()
                workflow, _ = self.workflow(steps)
                with self.assertRaises(SyncError) as caught:
                    workflow.refresh()
                self.assertEqual(caught.exception.phase, phase)
                self.assertTrue(caught.exception.saved_state_available)
                self.assertFalse(caught.exception.publication_started)
                self.assertEqual(self.bytes(), before)
                offline, http = self.workflow(now=d.instant_from_wire('2026-10-25T00:00:00Z'))
                self.assertFalse(offline.read_local().snapshot.items['B'].completed)
                self.assertTrue(offline.read_local().warnings)
                self.assertEqual(http.requests, [])

    def test_candidate_preparation_and_first_replacement_preserve_files(self):
        for boundary in ('prepare', 'replace'):
            with self.subTest(boundary=boundary):
                before = self.bytes()
                workflow, _ = self.workflow(self.external())
                target = ('todo_lib.workflows.sync.prepare_candidates' if boundary == 'prepare'
                          else 'todo_lib.local.safety.os.replace')
                with patch(target, side_effect=LocalError('controlled first failure')):
                    with self.assertRaises(SyncError) as caught:
                        workflow.refresh()
                self.assertEqual(self.bytes(), before)
                self.assertFalse(caught.exception.publication_started)
                self.assertEqual(caught.exception.phase,
                    'candidate preparation' if boundary == 'prepare' else 'local publication')
                self.assertEqual(list(self.root.glob('.todo-candidate-*')), [])

    def test_later_history_replacement_leaves_complete_cache_and_old_pending_history(self):
        workflow, _ = self.workflow(self.external())
        workflow.refresh()
        self.assert_precise()
        before = self.bytes()
        real_replace = os.replace
        destinations = {}
        def fail_history(source, destination):
            destinations[Path(destination).name] = Path(source).read_bytes()
            if Path(destination).name == 'history.json':
                raise OSError('controlled later history failure')
            return real_replace(source, destination)
        workflow, _ = self.workflow([self.sync('delta-token', delta()), *self.retained()])
        with patch('todo_lib.local.safety.os.replace', side_effect=fail_history):
            with self.assertRaises(SyncError) as caught:
                workflow.refresh()
        after = self.bytes()
        self.assertEqual(after['cache.json'], destinations['cache.json'])
        for name in ('history.json', 'binding.json', 'report-cursor'):
            self.assertEqual(after[name], before[name])
        for data in (after['history.json'], destinations['history.json']):
            raw = loads(data)
            self.assertEqual(raw['snapshot']['items']['B']['added_at'], CREATED)
            self.assertEqual(raw['snapshot']['comments']['own']['body'], 'Surviving own comment')
        error = caught.exception
        self.assertTrue(error.publication_started)
        self.assertTrue(error.refresh_permitted)  # history still matches binding
        self.assertFalse(error.saved_state_available)
        self.assertIn('new cache file may already', str(error))
        self.child_process(mixed=True)

    def test_later_binding_failure_accepted_reconciliation_and_clear_disclosure(self):
        workflow, _ = self.workflow(self.external())
        workflow.refresh()
        before = self.bytes()
        real_replace = os.replace
        destinations = {}
        def fail_binding(source, destination):
            destinations[Path(destination).name] = Path(source).read_bytes()
            if Path(destination).name == 'binding.json':
                raise OSError('controlled binding failure')
            return real_replace(source, destination)
        workflow, _ = self.workflow([self.sync('*', full(items=[item('A', added_at=CREATED)])),
            self.sync('full-token', delta()), self.completed([completed_b()]), self.comments()])
        with exclusive_lock('mutation', self.root):
            with patch('todo_lib.local.safety.os.replace', side_effect=fail_binding):
                with self.assertRaises(SyncError) as caught:
                    workflow.refresh_locked(clear_cache=True, remote_outcome='accepted')
        after = self.bytes()
        self.assertEqual(after['cache.json'], destinations['cache.json'])
        self.assertEqual(after['history.json'], destinations['history.json'])
        self.assertEqual(after['binding.json'], before['binding.json'])
        self.assertEqual(after['report-cursor'], before['report-cursor'])
        self.assertEqual(loads(after['history.json'])['snapshot']['comments']['own']['body'],
                         'Surviving own comment')
        error = caught.exception
        self.assertEqual(error.remote_outcome, 'accepted')
        self.assertTrue(error.cache_cleared)
        self.assertTrue(error.publication_started)
        self.assertFalse(error.refresh_permitted)
        self.assertIn('Explicit cache clearing occurred', str(error))
        self.assertIn('restore a consistent', str(error))
        self.assertNotIn('no new cache', str(error))
        self.assertNotIn('previous cache was not replaced', str(error))
        self.child_process(mixed=True)
        offline, http = self.workflow()
        with self.assertRaises(SyncError):
            offline.refresh(clear_cache=True)
        self.assertEqual(http.requests, [])
        self.assertEqual(self.bytes(), after)

    def test_clear_validation_and_failed_rebuild_disclose_actual_deletion(self):
        for name, data in [('history.json', b'{broken'), ('binding.json', b'{}'),
                           ('report-cursor', b'bad'), ('config', b'bad')]:
            with self.subTest(name=name):
                saved = (self.root / name).read_bytes()
                self.put(name, data)
                before = self.bytes()
                workflow, http = self.workflow()
                with self.assertRaises(SyncError) as caught:
                    workflow.refresh(clear_cache=True)
                self.assertFalse(caught.exception.cache_cleared)
                self.assertFalse(caught.exception.refresh_permitted)
                self.assertEqual(self.bytes(), before)
                self.assertFalse(http.requests)
                self.put(name, saved)
        workflow, _ = self.workflow([self.sync('*', Response(b'{}', status=401))])
        before = self.bytes()
        with self.assertRaises(SyncError) as caught:
            workflow.refresh(clear_cache=True)
        self.assertTrue(caught.exception.cache_cleared)
        self.assertFalse((self.root / 'cache.json').exists())
        for name in ('history.json', 'binding.json', 'report-cursor'):
            self.assertEqual((self.root / name).read_bytes(), before[name])
        self.assertIn('Explicit cache clearing occurred', str(caught.exception))

    def test_confirmed_delete_departure_and_comment_removal(self):
        for evidence in ({'id': 'B', 'is_deleted': True},
                         {'id': 'B', 'project_id': 'outside'}):
            with self.subTest(evidence=evidence):
                workflow, _ = self.workflow(self.external())
                workflow.refresh()
                workflow, _ = self.workflow([self.sync('delta-token', delta(items=[evidence]))])
                workflow.refresh()
                state = self.store.load_consistent_state()
                for s in (state.snapshot, state.history.snapshot):
                    self.assertNotIn('B', s.items)
                    self.assertNotIn('own', s.comments)
                    self.assertFalse(s.occurrences)
                # Restore the open observed tree for the next independent transition.
                workflow, _ = self.workflow([self.sync('delta-token', full(**{
                    'items': open_tree()['items'], 'notes': open_tree()['notes']})),
                    self.sync('full-token', delta())])
                workflow.refresh()
        workflow, _ = self.workflow([self.sync('delta-token', delta(notes=[{'id': 'own', 'is_deleted': True}]))])
        workflow.refresh()
        self.assertNotIn('own', self.store.load_history().snapshot.comments)

    def test_no_timezone_account_or_publication_bypass(self):
        before = self.bytes()
        workflow, _ = self.workflow([self.sync('delta-token', delta(user={
            'id': 'foreign', 'tz_info': {'timezone': 'UTC'}}))])
        with self.assertRaises(SyncError):
            workflow.refresh()
        self.assertEqual(self.bytes(), before)
        raw = loads(before['history.json'])
        raw['association']['publication'] = 'other'
        self.put('history.json', json.dumps(raw).encode())
        workflow, http = self.workflow()
        with self.assertRaises(SyncError):
            workflow.refresh(clear_cache=True)
        self.assertFalse(http.requests)
        self.assertEqual((self.root / 'cache.json').read_bytes(), before['cache.json'])

    def test_age_warning_uses_elapsed_exact_seconds(self):
        for now, warned in [(d.instant_from_wire('2026-10-21T13:00:00Z'), False),
                            (d.instant_from_wire('2026-10-21T13:00:00.000000001Z'), True)]:
            workflow, http = self.workflow(now=now)
            self.assertEqual(bool(workflow.read_local().warnings), warned)
            self.assertFalse(http.requests)

    def test_interruption_preserves_remote_outcome_and_releases_lock(self):
        workflow, _ = self.workflow([self.sync('delta-token', delta())])
        before = self.bytes()
        with exclusive_lock('mutation', self.root):
            with patch('todo_lib.workflows.sync.prepare_candidates', side_effect=KeyboardInterrupt):
                with self.assertRaises(SyncInterrupted) as caught:
                    workflow.reconcile_accepted_locked()
        self.assertEqual(caught.exception.failure.remote_outcome, 'accepted')
        self.assertEqual(self.bytes(), before)
        with exclusive_lock('refresh', self.root):
            pass

    def test_completed_evidence_authoritative_null_survives_reload(self):
        workflow, _ = self.workflow(self.external())
        workflow.refresh()
        unknown = completed_b()
        unknown['added_at'] = None
        response = self.comments()
        response[1]['results'][0]['posted_at'] = None
        workflow, _ = self.workflow([self.sync('*', full(items=[item('A', added_at=CREATED)])),
            self.sync('full-token', delta()), self.completed([unknown]), response])
        workflow.refresh(clear_cache=True)
        state = StateStore(self.root).load_consistent_state()
        for snapshot in (state.snapshot, state.history.snapshot):
            self.assertIsNone(snapshot.items['B'].added_at)
            self.assertIsNone(snapshot.comments['own'].added_at)
            self.assertEqual(d.instant_text(snapshot.items['B'].completed_at), DONE)

    def test_history_is_independent_of_cache_and_scope_data_is_minimized(self):
        workflow, _ = self.workflow(self.external())
        workflow.refresh()
        (self.root / 'cache.json').unlink()
        # Supported completion omitted from a later bounded window: established
        # completion and its surviving own comments still survive the rebuild.
        workflow, _ = self.workflow([self.sync('*', full(items=[item('A', added_at=CREATED),
                item('unmanaged', project_id='outside', content='private sentinel')],
                projects=[project('root', None), project(), project('outside', None)],
                notes=[note('unmanaged-note', 'unmanaged', content='private sentinel')])),
            self.sync('full-token', delta()), self.completed([]), self.comments()])
        workflow.refresh()
        self.assert_precise()
        for path in self.root.iterdir():
            if path.is_file():
                self.assertNotIn(b'private sentinel', path.read_bytes())
                self.assertNotIn(b'unmanaged', path.read_bytes())
        self.child_process()

    def test_missing_history_symlink_and_lock_prevent_clearing(self):
        before = self.bytes()
        (self.root / 'history.json').unlink()
        workflow, http = self.workflow()
        with self.assertRaises(SyncError):
            workflow.refresh(clear_cache=True)
        self.assertEqual((self.root / 'cache.json').read_bytes(), before['cache.json'])
        self.assertFalse((self.root / 'history.json').exists())
        self.assertFalse(http.requests)
        self.put('history.json', before['history.json'])
        (self.root / 'cache.json').unlink()
        (self.root / 'cache.json').symlink_to(self.root / 'history.json')
        with self.assertRaises(LocalError):
            workflow.refresh(clear_cache=True)
        self.assertTrue((self.root / 'cache.json').is_symlink())
        self.assertEqual((self.root / 'history.json').read_bytes(), before['history.json'])
        (self.root / 'cache.json').unlink()
        self.put('cache.json', before['cache.json'])
        with exclusive_lock('other operation', self.root):
            with self.assertRaises(LocalError):
                workflow.refresh(clear_cache=True)
        self.assertEqual(self.bytes(), before)

    def test_current_moves_names_timezone_and_comment_ownership_override_history(self):
        workflow, _ = self.workflow(self.external())
        workflow.refresh()
        workflow, _ = self.workflow([self.sync('delta-token', delta(items=[item('B', parent_id=None,
            content='Reopened and promoted', added_at=None)],
            notes=[note('own', 'A', content='Now belongs to parent', posted_at=None)],
            projects=[project(name='Renamed')],
            user={'id': 'u', 'tz_info': {'timezone': 'America/New_York'}})),
            self.sync('*', full(items=[item('A', added_at=CREATED), item('B', parent_id=None,
                content='Reopened and promoted', added_at=None)],
                notes=[note('own', 'A', content='Now belongs to parent', posted_at=None)],
                projects=[project('root', None), project(name='Renamed')],
                user={'id': 'u', 'tz_info': {'timezone': 'America/New_York'}})),
            self.sync('full-token', delta())])
        workflow.refresh()
        state = self.store.load_consistent_state()
        self.assertEqual(state.binding.last_synced_account_timezone, 'America/New_York')
        for s in (state.snapshot, state.history.snapshot):
            self.assertEqual(s.categories['cat'].name, 'Renamed')
            self.assertEqual(s.items['B'].title, 'Reopened and promoted')
            self.assertIsNone(s.items['B'].parent_id)
            self.assertIsNone(s.items['B'].added_at)
            self.assertEqual(s.comments['own'].item_id, 'A')
            self.assertEqual(s.comments['own'].body, 'Now belongs to parent')

    def check_retained_attention_timezone_change(self, due_value, expected, *, clear_cache):
        from tests.adapter.current.test_current import due

        raw_due = due(due_value, timezone=None)
        # Observe open B with due metadata, then establish completion remotely.
        workflow, _ = self.workflow([self.sync('delta-token', delta(items=[
            item('B', parent_id='A', added_at=CREATED, due=raw_due)]))], now=INITIAL)
        workflow.refresh()
        steps = self.external()
        steps[2] = self.completed([completed_b(due=raw_due)])
        workflow, _ = self.workflow(steps)
        workflow.refresh()
        before = self.assert_precise()
        old_attention = before.history.snapshot.items['B'].attention
        self.assertEqual(old_attention.raw_due, raw_due)
        with exclusive_lock('set cursor', self.root):
            self.store.write_cursor(NOW)  # Deliberately does not prune pending B.
        cursor_bytes = (self.root / 'report-cursor').read_bytes()

        later = d.instant_from_wire('2026-10-23T11:00:00Z')
        query = [('project_id', 'cat'), ('since', '2026-10-22T12:00:00Z'),
                 ('until', '2026-10-23T11:00:01Z'), ('limit', '200')]
        workflow, _ = self.workflow([
            self.sync('*' if clear_cache else 'delta-token', full(
                items=[item('A', added_at=CREATED)],
                user={'id': 'u', 'tz_info': {'timezone': 'America/New_York'}})),
            self.sync('full-token', delta()),
            # Completion predates this window: omission legitimately retains B.
            (Expected('/tasks/completed/by_completion_date', query), {'items': []}),
            self.comments()], now=later)
        workflow.refresh(clear_cache=clear_cache)
        state = self.assert_precise()  # Public store reload validates both files.
        self.assertEqual(state.binding.last_synced_account_timezone, 'America/New_York')
        self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor_bytes)
        for snapshot in (state.snapshot, state.history.snapshot):
            attention = snapshot.items['B'].attention
            self.assertEqual(attention.raw_due, raw_due)
            self.assertEqual(d.instant_text(attention.instant), expected)
            self.assertEqual(attention.kind, old_attention.kind)
        self.child_process()  # Fresh interpreter, consistent saved state, zero HTTP.
        # A subsequent delta must seed from the preserved floating representation.
        workflow, _ = self.workflow([self.sync('delta-token', delta()),
            (Expected('/tasks/completed/by_completion_date', query), {'items': []}), self.comments()], now=later)
        workflow.refresh()
        self.assertEqual(d.instant_text(self.store.load_history().snapshot.items['B'].attention.instant),
                         expected)

    def test_retained_floating_attention_uses_new_timezone_on_refresh(self):
        self.check_retained_attention_timezone_change(
            '2026-10-25T10:00:00', '2026-10-25T14:00:00Z', clear_cache=False)

    def test_retained_floating_attention_uses_new_timezone_on_rebuild(self):
        self.check_retained_attention_timezone_change(
            '2026-10-25T10:00:00', '2026-10-25T14:00:00Z', clear_cache=True)

    def test_retained_fixed_attention_keeps_instant_on_timezone_change(self):
        self.check_retained_attention_timezone_change(
            '2026-10-25T10:00:00Z', '2026-10-25T10:00:00Z', clear_cache=True)

    def test_real_gateway_acceptance_survives_later_publication_failure_without_replay(self):
        from todo_lib.adapter.commands import Gateway, Operation, Outcome
        from todo_lib.adapter.current import Current
        operation = Operation('item_update', {'id': 'A', 'content': 'Changed A'},
                              uuid='11111111-1111-4111-8111-111111111111')
        command = '[{"type":"item_update","uuid":"11111111-1111-4111-8111-111111111111","args":{"id":"A","content":"Changed A"}}]'
        transport, http = self.boundary([
            (ExpectedRequest('POST', '/sync', 'secret', form={'commands': command, 'sync_token': 'delta-token', 'resource_types': RESOURCES}),
             {'sync_status': {operation.uuid: 'ok'}}),
            self.sync('delta-token', delta(items=[item('A', content='Changed A', added_at=CREATED)])),
            self.sync('delta-token', delta(items=[item('A', content='Changed A', added_at=CREATED)]))])
        workflow = Synchronizer(transport, self.store, clock=lambda: NOW)
        real_replace = os.replace
        def fail_binding(source, destination):
            if Path(destination).name == 'binding.json':
                raise OSError('controlled late failure')
            return real_replace(source, destination)
        with exclusive_lock('mutation', self.root):
            state = self.store.load_consistent_state()
            result = Gateway(transport, clock=lambda: datetime(2026, 10, 22, tzinfo=timezone.utc)).execute(
                operation, before=Current(state.snapshot, state.sync_token, current_snapshot=state.current_snapshot))
            self.assertEqual(result.outcome, Outcome.ACCEPTED)
            self.assertFalse(result.issues)
            with patch('todo_lib.local.safety.os.replace', side_effect=fail_binding):
                with self.assertRaises(SyncError) as caught:
                    workflow.reconcile_accepted_locked()
        self.assertEqual(caught.exception.remote_outcome, 'accepted')
        self.assertIn('do not replay', str(caught.exception))
        self.assertTrue(caught.exception.publication_started)
        self.assertEqual(len(http.requests), 3)
        self.child_process(mixed=True)

    def test_external_recurring_completion_and_undo_preserve_current_null(self):
        from tests.adapter.current.test_current import due
        recurrence = due('2026-10-25', timezone=None, is_recurring=True)
        # The object stays open; completion is an occurrence, with historical
        # nonnull creation that must not overwrite authoritative current null.
        recurring = item('B', parent_id='A', due=recurrence, added_at=None)
        occurrence = completed_b()
        occurrence.update(checked=False, due=recurrence)
        activity_query = [('object_type', 'item'), ('object_id', 'B'),
            ('date_from', '2026-10-20T00:00:00Z'), ('date_to', '2026-10-22T12:00:01Z'),
            ('limit', '200'),
            ('object_event_types', '["item:completed", "item:uncompleted", "note:added", "note:updated", "note:deleted"]')]
        for undone in (False, True):
            with self.subTest(undone=undone):
                event = dict(id=None, object_type='item', object_id='B', event_type='uncompleted',
                    event_date='2026-10-21T12:00:00.123456789012350Z', parent_project_id='cat')
                workflow, _ = self.workflow([self.sync('delta-token', delta(items=[recurring])),
                    self.completed([occurrence]),
                    (Expected('/activities', activity_query),
                     {'results': [event] if undone else [], 'next_cursor': None})])
                workflow.refresh()
                state = self.store.load_consistent_state()
                for s in (state.snapshot, state.history.snapshot):
                    self.assertIsNone(s.items['B'].added_at)
                    self.assertFalse(s.items['B'].completed)
                    self.assertEqual(len(s.occurrences), 1)
                    observed = next(iter(s.occurrences.values()))
                    self.assertEqual(d.instant_text(observed.completed_at), DONE)
                    self.assertEqual(observed.undone, undone)

    def test_activity_only_recurring_reloads_and_each_undo_is_applied_once(self):
        from tests.adapter.current.test_current import due
        recurrence = due('2026-10-25', timezone=None, is_recurring=True)
        recurring = item('B', parent_id='A', due=recurrence, added_at=None)
        times = ['2026-10-21T18:11:14.719113Z', '2026-10-21T18:11:14.719114Z']
        events = [dict(id=identity, object_type='item', object_id='B',
                       event_type='completed', event_date=value, parent_project_id='cat')
                  for identity, value in zip((801, 802), times)]
        query = [('object_type', 'item'), ('object_id', 'B'),
            ('date_from', '2026-10-20T00:00:00Z'), ('date_to', '2026-10-22T12:00:01Z'),
            ('limit', '200'),
            ('object_event_types', '["item:completed", "item:uncompleted", "note:added", "note:updated", "note:deleted"]')]
        counterpart = {**completed_b(), 'checked': False, 'due': recurrence,
                       'completed_at': '2026-10-21T18:11:14.704186Z'}
        for count in (0, 1, 2, 2):
            with self.subTest(undos=count):
                undos = [dict(id=803 + i, object_type='item', object_id='B',
                    event_type='uncompleted', event_date=f'2026-10-21T18:11:15.{i}Z')
                    for i in range(count)]
                workflow, http = self.workflow([self.sync('delta-token', delta(items=[recurring])),
                    self.completed([counterpart] if count else []),
                    (Expected('/activities', query),
                     {'results': events + [events[0]] + undos, 'next_cursor': None})])
                workflow.refresh()
                http.assert_done()
                self.store = StateStore(self.root)  # actual protected JSON reload
                state = self.store.load_consistent_state()
                for snapshot in (state.snapshot, state.history.snapshot):
                    observed = sorted(snapshot.occurrences.values(), key=lambda o: d.instant_key(o.completed_at))
                    self.assertEqual([d.instant_text(o.completed_at) for o in observed], times)
                    self.assertEqual(sum(o.undone for o in observed), count)
                    self.assertEqual(observed[-1].undone, count > 0)
                    self.assertEqual(sum(len(o.undo_ids) for o in observed), count)
                    self.assertIsNone(snapshot.items['B'].added_at)
                    self.assertFalse(snapshot.items['B'].completed)
                    self.assertEqual(len(d.recent_reopen_candidates(snapshot, CURSOR, NOW)), 0 if count else 1)

    def test_activity_only_recurring_required_read_failure_preserves_files(self):
        from tests.adapter.current.test_current import due
        recurring = item('B', parent_id='A', due=due(is_recurring=True))
        query = [('object_type', 'item'), ('object_id', 'B'),
            ('date_from', '2026-10-20T00:00:00Z'), ('date_to', '2026-10-22T12:00:01Z'),
            ('limit', '200'),
            ('object_event_types', '["item:completed", "item:uncompleted", "note:added", "note:updated", "note:deleted"]')]
        before = self.bytes()
        workflow, http = self.workflow([self.sync('delta-token', delta(items=[recurring])),
            self.completed([]), (Expected('/activities', query),
                                 {'results': [], 'next_cursor': 'malformed'})])
        with self.assertRaisesRegex(SyncError, 'malformed next_cursor'):
            workflow.refresh()
        http.assert_done()
        self.assertEqual(self.bytes(), before)

    def test_new_bounded_historical_observation_joins_pending_context(self):
        other = item('C', parent_id='A', checked=True, completed_at=DONE, added_at=CREATED)
        workflow, _ = self.workflow([self.sync('delta-token', full(items=[item('A', added_at=CREATED)])),
            self.sync('full-token', delta()), self.completed([completed_b(), other]), self.comments(),
            (Expected('/comments', [('task_id', 'C'), ('limit', '200')]),
             {'results': [], 'next_cursor': None})])
        workflow.refresh()
        state = self.store.load_consistent_state()
        for s in (state.snapshot, state.history.snapshot):
            self.assertEqual(set(s.items), {'A', 'B', 'C'})
            self.assertTrue(s.items['C'].completed)
            self.assertEqual(s.items['C'].parent_id, 'A')
            self.assertEqual(d.instant_text(s.items['C'].completed_at), DONE)

    def test_historical_parent_deletion_removes_known_descendants(self):
        deleted_parent = item('A', checked=True, completed_at=DONE, is_deleted=True)
        workflow, _ = self.workflow([self.sync('delta-token', full(items=[])),
            self.sync('full-token', delta()), self.completed([deleted_parent])])
        workflow.refresh()
        state = self.store.load_consistent_state()
        for snapshot in (state.snapshot, state.history.snapshot):
            self.assertFalse(snapshot.items)
            self.assertFalse(snapshot.comments)

    def test_failed_required_comments_retains_saved_pending_bytes(self):
        workflow, _ = self.workflow(self.external())
        workflow.refresh()
        before = self.bytes()
        workflow, _ = self.workflow([self.sync('delta-token', full(items=[item('A')])),
            self.sync('full-token', delta()), self.completed([completed_b()]),
            (Expected('/comments', [('task_id', 'B'), ('limit', '200')]),
             {'results': [], 'next_cursor': 'malformed'})])
        with self.assertRaises(SyncError) as caught:
            workflow.refresh()
        self.assertEqual(caught.exception.phase, 'lifecycle reconciliation')
        self.assertFalse(caught.exception.publication_started)
        self.assertEqual(self.bytes(), before)
        self.child_process()

    def test_current_promoted_descendant_survives_old_parent_deletion(self):
        workflow, _ = self.workflow([self.sync('delta-token', delta(items=[
            {'id': 'A', 'is_deleted': True}, item('B', parent_id=None, added_at=None)]))])
        workflow.refresh()
        state = self.store.load_consistent_state()
        for snapshot in (state.snapshot, state.history.snapshot):
            self.assertEqual(set(snapshot.items), {'B'})
            self.assertIsNone(snapshot.items['B'].parent_id)
            self.assertIsNone(snapshot.items['B'].added_at)
            self.assertEqual(snapshot.comments['own'].item_id, 'B')

    def test_explicit_clear_of_already_missing_cache_does_not_claim_deletion(self):
        (self.root / 'cache.json').unlink()
        workflow, _ = self.workflow([self.sync('*', Response(b'{}', status=401))])
        with self.assertRaises(SyncError) as caught:
            workflow.refresh(clear_cache=True)
        self.assertFalse(caught.exception.cache_cleared)
        self.assertNotIn('Explicit cache clearing occurred', str(caught.exception))


class MutationReuseTests(unittest.TestCase):
    """Revisions 17/18 strict HTTP composition, using actual adapter/store/workflows.

    Shapes/queries follow the pinned Sync, completed, activities and comments
    contracts cited above. No response is computed from a production mapper.
    """
    setUp = SyncTests.setUp
    put = SyncTests.put
    sync = SyncTests.sync
    boundary = SyncTests.boundary
    bytes = SyncTests.bytes

    def recurring(self):
        from tests.adapter.current.test_current import due
        return item('R', content='Deferred recurring work', due=due('2026-10-25', timezone=None,
                    string='every day', is_recurring=True))

    def archived(self):
        return item('X', checked=True, completed_at=DONE, content='Archived pending')

    def own(self, owner, text):
        return (Expected('/comments', [('task_id', owner), ('limit', '200')]),
                {'results': [dict(id=owner.lower() + '-note', content=text, posted_at=COMMENT,
                                 is_deleted=False)], 'next_cursor': None})

    def completed(self, rows, cursor=None, *, upper='2026-10-22T12:00:01Z'):
        return (Expected('/tasks/completed/by_completion_date', [(key, upper if key == 'until' else value) for key, value in COMPLETED_QUERY] +
                         ([] if cursor is None else [('cursor', cursor)])),
                {'items': rows})

    def activities(self, rows, *, owner=None, upper='2026-10-22T12:00:01Z'):
        scope = [] if owner is None else [('object_type', 'item'), ('object_id', owner)]
        return (Expected('/activities', scope + [
            ('date_from', '2026-10-20T00:00:00Z'),
            ('date_to', upper), ('limit', '200'),
            ('object_event_types', '["item:completed", "item:uncompleted", "note:added", "note:updated", "note:deleted"]')]),
                {'results': rows, 'next_cursor': None})

    def establish_pending(self, *, second=False):
        raw = open_tree(user_plan_limits={'current': {'activity_log': True,
            'activity_log_limit': -1, 'reminders': True}})
        raw['items'].append(self.recurring())
        archived = [self.archived()]
        if second:
            archived.append(item('Y', checked=True, completed_at=DONE, content='Unaffected archived'))
        baseline = d.instant_from_wire('2026-10-21T13:00:00Z')
        upper = '2026-10-21T13:00:01Z'
        transport, _ = self.boundary([self.sync('delta-token', raw),
            self.sync('full-token', delta()), self.completed(archived, upper=upper),
            self.own('X', 'Last established text'),
            *([self.own('Y', 'Unaffected pending text')] if second else []),
            self.activities([], owner='R', upper=upper)])
        Synchronizer(transport, self.store, clock=lambda: baseline).refresh()
        return self.store.load_consistent_state()

    def compose(self, *, invalid=False, archived_completion=False):
        from todo_lib.adapter.commands import Gateway
        from todo_lib.workflows.capture import CaptureWorkflow
        from tests.workflows.lifecycle.test_lifecycle import CommandRequest
        from todo_lib.presentation import OriginalStreams
        from io import StringIO
        saved = self.establish_pending()
        pending_at = saved.history.observations['X']
        before = self.bytes()
        created = item('actual-created', content='Created title', priority=3,
                       added_at='2026-10-22T11:59:59Z')
        changed = item('B', parent_id='A', content='Concurrent unrelated update')
        if invalid:
            changed['priority'] = 9
        add = CommandRequest(self, 'item_add', dict(project_id='cat',
            content='Created title', priority=3, description='', labels=[],
            auto_reminder=False, due=None), target='actual-created')
        done = CommandRequest(self, 'item_close', {'id': 'actual-created'}, token='created-token')
        original_check = done.check
        def check_published(request, timeout):
            # The next submission observes the actual saved identity, active
            # membership and new token through a new StateStore instance.
            reloaded = StateStore(self.root).load_consistent_state()
            self.assertEqual(reloaded.snapshot.items['actual-created'].title, 'Created title')
            self.assertFalse(reloaded.snapshot.items['actual-created'].completed)
            self.assertIn('actual-created', reloaded.current_snapshot.items)
            self.assertEqual(reloaded.sync_token, 'created-token')
            self.assertEqual(reloaded.snapshot.items['B'].title, 'Concurrent unrelated update')
            self.assertEqual(reloaded.history.observations['X'], pending_at)
            self.assertEqual((self.root / 'report-cursor').read_bytes(), before['report-cursor'])
            original_check(request, timeout)
        done.check = check_published
        final = dict(created, checked=True, completed_at='2026-10-22T12:00:00Z')
        add.resources = delta(sync_token='created-token', items=[created, changed])
        steps = [add.step()]
        if invalid:
            # Required outcome reconciliation cannot publish the invalid active
            # result, even though the UUID and temporary identity were accepted.
            steps += [self.sync('delta-token', delta(items=[created, changed]))]
        else:
            if archived_completion:
                # A full active replacement omits the completed owner. Freshness
                # and scoped lifecycle/comments remain necessary, not inferred.
                done.resources = open_tree(user_plan_limits={'current': {'activity_log': True,
                    'activity_log_limit': -1, 'reminders': True}})
                done.resources['items'] = [item('A', added_at=CREATED), changed, self.recurring()]
                steps += [done.step(), self.sync('full-token', delta(sync_token='completed-token')),
                    self.completed([final]),
                    (Expected('/comments', [('task_id', 'actual-created'), ('limit', '200')]),
                     {'results': [], 'next_cursor': None})]
            else:
                done.resources = delta(sync_token='completed-token', items=[final])
                steps += [done.step()]
        transport, http = self.boundary(steps)
        sync = Synchronizer(transport, self.store, clock=lambda: NOW)
        result = CaptureWorkflow(sync, gateway=Gateway(transport,
            clock=lambda: d.instant_datetime(NOW)), streams=OriginalStreams(StringIO(), StringIO(), StringIO())).execute(
                ['add', 'cat', 'Created title', '--done'])
        if invalid:
            self.assertEqual(result.status, 1)
            self.assertEqual([o.outcome for o in result.outcomes], ['accepted', 'unattempted'])
            self.assertEqual(self.bytes(), before)
        else:
            self.assertEqual(result.status, 0, result.document.stderr)
            after = self.store.load_consistent_state()
            self.assertTrue(after.snapshot.items['actual-created'].completed)
            self.assertEqual(after.sync_token, 'completed-token')
            self.assertNotIn('X', after.current_snapshot.items)
            self.assertEqual([(o.item_id, d.instant_text(o.completed_at))
                for o in after.history.snapshot.occurrences.values() if o.item_id == 'actual-created'],
                [('actual-created', '2026-10-22T12:00:00Z')])
            self.assertEqual(after.snapshot.items['B'].title, 'Concurrent unrelated update')
            self.assertEqual(after.history.observations['X'], pending_at)
            self.assertEqual(after.snapshot.comments['x-note'].body, 'Last established text')
            self.assertEqual(after.cursor, saved.cursor)
            self.assertEqual(after.history.coverage, saved.history.coverage)
            self.assertEqual(len(http.requests), 5 if archived_completion else 2)
        return result

    def test_accepted_parent_move_ignores_unrelated_reminder_with_one_dispatch(self):
        from io import StringIO
        from todo_lib.adapter.commands import Gateway
        from todo_lib.presentation import OriginalStreams
        from todo_lib.workflows.moves import MoveWorkflow
        from tests.workflows.lifecycle.test_lifecycle import CommandRequest
        from tests.support.reminders import absolute
        ignored = absolute('ignored-reminder', item_id='never-managed', type='location',
                           due={'private': 'unused'}, minute_offset={'private': 'unused'})
        op = CommandRequest(self, 'item_move', {'id': 'B', 'project_id': 'cat'},
            resources=delta(items=[item('B', parent_id=None, content='Normalized result')],
                            reminders=[ignored], sync_token='moved-token'))
        transport, http = self.boundary([op.step()])
        sync = Synchronizer(transport, self.store, clock=lambda: NOW)
        streams = OriginalStreams(StringIO(), StringIO(), StringIO())
        result = MoveWorkflow(sync, gateway=Gateway(transport, clock=lambda: d.instant_datetime(NOW)),
                              streams=streams).execute(['move', 'B', '--task', '', '--to', 'cat'])
        self.assertEqual(result.status, 0)
        self.assertEqual(result.document.stderr, '')
        self.assertEqual(len(op.commands), 1)
        self.assertEqual(len(http.requests), 1)
        saved = StateStore(self.root).load_consistent_state()
        self.assertEqual(saved.snapshot.items['B'].title, 'Normalized result')
        self.assertIsNone(saved.snapshot.items['B'].parent_id)
        self.assertEqual(saved.sync_token, 'moved-token')
        self.assertEqual(saved.current_snapshot.items['B'], saved.snapshot.items['B'])
        self.assertFalse(saved.current_reminder_ids)
        for data in self.bytes().values():
            self.assertNotIn(b'ignored-reminder', data)
            self.assertNotIn(b'never-managed', data)
        self.assertNotIn('ignored', result.document.stdout)

    def test_composed_incremental_create_published_before_complete_reuses_required_proof(self):
        self.compose()

    def test_combined_server_full_completion_retains_freshness_and_scoped_evidence(self):
        self.compose(archived_completion=True)

    def test_unrelated_invalid_active_change_fails_before_second_write(self):
        self.compose(invalid=True)

    def test_deferred_history_older_than_writes_reported_and_failure_boundaries(self):
        from io import StringIO
        from todo_lib.presentation import OriginalStreams
        from todo_lib.workflows.report import Reporter
        self.compose()
        before = self.bytes()
        event = dict(id=801, object_type='note', object_id='x-note', event_type='updated',
            event_date='2026-10-21T18:00:00Z', parent_item_id='X', parent_project_id='cat')
        recurring = dict(id=802, object_type='item', object_id='R', event_type='completed',
                         event_date='2026-10-21T18:00:01Z', parent_project_id='cat')
        self.assertLess(d.instant_key(d.instant_from_wire('2026-10-21T13:00:00Z')),
                        d.instant_key(d.instant_from_wire(event['event_date'])))
        self.assertLess(d.instant_key(d.instant_from_wire(event['event_date'])),
                        d.instant_key(self.store.load_consistent_state().synced_at))
        def steps(failed=False):
            return [self.sync(self.store.load_consistent_state().sync_token, delta()), self.completed([self.archived()]),
                    self.activities([event, recurring]),
                    self.own('X', 'Deferred changed text') if not failed else
                    (self.own('X', '')[0], Response(b'{invalid'))]
        transport, _ = self.boundary(steps(True))
        with self.assertRaises(SyncError):
            Reporter(transport, self.store, clock=lambda: NOW).run(['--final'])
        self.assertEqual(self.bytes(), before)
        for boundary in ('output', 'cursor'):
            transport, _ = self.boundary(steps())
            out = StringIO()
            reporter = Reporter(transport, self.store, clock=lambda: NOW,
                streams=OriginalStreams(StringIO(), out, StringIO()))
            protected = {}
            def fail(*args, **kwargs):
                protected['history'] = (self.root / 'history.json').read_bytes()
                raise OSError('controlled final ' + boundary + ' failure')
            target = ('todo_lib.workflows.report.deliver' if boundary == 'output' else
                      'todo_lib.local.store.StateStore.write_cursor')
            with patch(target, side_effect=fail):
                with self.assertRaises((SyncError, OSError)):
                    reporter.run(['--final'])
            self.assertEqual((self.root / 'report-cursor').read_bytes(), before['report-cursor'])
            self.assertEqual((self.root / 'history.json').read_bytes(), protected['history'])
            self.assertIn('X', self.store.load_history().snapshot.items)
        transport, _ = self.boundary(steps())
        out = StringIO()
        Reporter(transport, self.store, clock=lambda: NOW,
            streams=OriginalStreams(StringIO(), out, StringIO())).run()
        self.assertIn('Deferred changed text', out.getvalue())
        self.assertIn('Archived pending', out.getvalue())
        self.assertIn('Deferred recurring work', out.getvalue())


    def test_combined_active_note_update_delete_reuses_complete_current_notes(self):
        from io import StringIO
        from todo_lib.adapter.commands import Gateway
        from todo_lib.presentation import OriginalStreams
        from todo_lib.workflows.comments import CommentWorkflow, Change
        from tests.workflows.lifecycle.test_lifecycle import CommandRequest
        updated = note('own', 'B', content='Actual updated text', posted_at=COMMENT)
        blank = note('blank', 'B', posted_at=None)
        blank.pop('content')  # documented NoteSyncView default; retain identity
        edit = CommandRequest(self, 'note_update', {'id': 'own', 'content': 'Actual updated text'},
            resources=delta(sync_token='note-updated', notes=[updated, blank]))
        delete = CommandRequest(self, 'note_delete', {'id': 'own'}, token='note-updated',
            resources=delta(sync_token='note-deleted', notes=[{'id': 'own', 'is_deleted': True}]))
        check = delete.check
        def published(request, timeout):
            saved = StateStore(self.root).load_consistent_state()
            self.assertEqual(saved.snapshot.comments['own'].body, 'Actual updated text')
            self.assertEqual(saved.snapshot.comments['blank'].body, '')
            self.assertEqual(saved.sync_token, 'note-updated')
            check(request, timeout)
        delete.check = published
        transport, http = self.boundary([edit.step(), delete.step()])
        sync = Synchronizer(transport, self.store, clock=lambda: NOW)
        workflow = CommentWorkflow(sync, gateway=Gateway(transport),
            streams=OriginalStreams(StringIO(), StringIO(), StringIO()))
        with exclusive_lock('combined notes', self.root):
            current = sync.read_local()
            result = workflow._apply(current, current.snapshot.items['B'],
                (Change('edit', 'own', 'Actual updated text'), Change('delete', 'own')))
        self.assertEqual(result.status, 0, result.document.stderr)
        saved = StateStore(self.root).load_consistent_state()
        self.assertNotIn('own', saved.snapshot.comments)
        self.assertEqual(saved.snapshot.comments['blank'].body, '')
        self.assertEqual(saved.sync_token, 'note-deleted')
        self.assertEqual(len(http.requests), 2)

    def test_archived_comment_evidence_shared_without_losing_other_pending_owner(self):
        from io import StringIO
        from todo_lib.adapter.commands import Gateway
        from todo_lib.presentation import OriginalStreams
        from todo_lib.workflows.comments import CommentWorkflow, Change
        from tests.workflows.lifecycle.test_lifecycle import CommandRequest
        saved = self.establish_pending(second=True)
        before = self.bytes()
        op = CommandRequest(self, 'note_add', {'item_id': 'X', 'content': 'New own text'}, target='R',
            resources=delta(notes=[note('R', 'X', content='New own text', posted_at=COMMENT)]))
        # Complete, paginated owner scope includes unaffected own comments too.
        query = [('task_id', 'X'), ('limit', '200')]
        steps = [op.step(),
            (Expected('/comments', query), {'results': [dict(id='x-note', content='Last established text',
                posted_at=COMMENT, is_deleted=False)], 'next_cursor': 'own.page'}),
            (Expected('/comments', query + [('cursor', 'own.page')]),
                {'results': [dict(id='R', content='New own text', posted_at=COMMENT,
                                 is_deleted=False)], 'next_cursor': None}),
            self.completed([self.archived()])]
        transport, http = self.boundary(steps)
        sync = Synchronizer(transport, self.store, clock=lambda: NOW)
        workflow = CommentWorkflow(sync, gateway=Gateway(transport, clock=lambda: d.instant_datetime(NOW)),
            streams=OriginalStreams(StringIO(), StringIO(), StringIO()))
        # Exercise the archived-owner consumer directly; ordinary title selection
        # intentionally selects open owners. Public Done composition is covered
        # by AdapterLifecycleTests with the same real gateway/publication path.
        with exclusive_lock('archived comment', self.root):
            result = workflow._apply(sync.read_local(), saved.snapshot.items['X'],
                                     (Change('add', body='New own text'),))
        self.assertEqual(result.status, 0, result.document.stderr)
        after = self.store.load_consistent_state()
        self.assertEqual(after.snapshot.comments['R'].body, 'New own text')
        self.assertEqual(after.snapshot.comments['x-note'], saved.snapshot.comments['x-note'])
        self.assertEqual(after.snapshot.comments['y-note'], saved.snapshot.comments['y-note'])
        self.assertEqual(after.history.observations['Y'], saved.history.observations['Y'])
        # Resource namespaces do not make the new note ID an affected item ID.
        self.assertEqual(after.history.observations['R'], saved.history.observations['R'])
        self.assertEqual((self.root / 'report-cursor').read_bytes(), before['report-cursor'])
        self.assertEqual(len(http.requests), 4)

    def test_explicit_archived_note_removal_survives_deferred_history(self):
        from io import StringIO
        from todo_lib.adapter.commands import Gateway
        from todo_lib.presentation import OriginalStreams
        from todo_lib.workflows.capture import CaptureWorkflow
        from tests.workflows.lifecycle.test_lifecycle import CommandRequest
        self.establish_pending()
        saved = self.store.load_consistent_state()
        op = CommandRequest(self, 'item_update', {'id': 'B', 'content': 'Renamed'})
        transport, http = self.boundary([op.step(), self.sync('delta-token', delta(
            items=[item('B', parent_id='A', content='Renamed')],
            notes=[{'id': 'x-note', 'is_deleted': True}]))])
        workflow = CaptureWorkflow(Synchronizer(transport, self.store, clock=lambda: NOW),
            gateway=Gateway(transport, clock=lambda: d.instant_datetime(NOW)),
            streams=OriginalStreams(StringIO(), StringIO(), StringIO()))
        result = workflow.execute(['rename', 'B', '--to', 'Renamed'])
        self.assertEqual(result.status, 0, result.document.stderr)
        after = self.store.load_consistent_state()
        self.assertNotIn('x-note', after.snapshot.comments)
        self.assertNotIn('x-note', after.history.snapshot.comments)
        self.assertEqual(after.history.observations['X'], saved.history.observations['X'])
        self.assertEqual(len(http.requests), 2)
