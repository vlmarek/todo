"""Public parse -> workflow -> UUID gateway -> independent after-state.

Synthetic wire fixtures cite docs/design/external/todoist/upstream/api-v1.openapi.json,
Sync Reminders and NotificationSyncView; no expected state is derived from requests.
"""
import unittest
from copy import deepcopy
from io import StringIO
from dataclasses import replace
from todo_lib import domain as d, presentation as p
from todo_lib.syntax import parse
from todo_lib.workflows.scheduling import propose
from tests.workflows.capture import test_capture as f
from tests.workflows.capture.test_coexistence import Terminal
from tests.support.reminders import absolute, FLOATING, FIXED


class ReminderWorkflowTests(unittest.TestCase):
    setUp = f.CaptureTests.setUp
    state = f.CaptureTests.state
    seed = f.CaptureTests.seed
    refresh = f.CaptureTests.refresh
    queue_refresh = f.CaptureTests.queue_refresh
    operation = f.CaptureTests.operation
    run_request = f.CaptureTests.run_request

    def mixed(self):
        self.wire_items[0]['due'] = f.due('2026-10-30T10:00:00Z')
        self.wire_reminders = [f.reminder('relative', 'parent', minute_offset=30),
                               absolute('absolute', FLOATING, item_id='parent')]
        self.seed()

    def terminal(self, answer='y\n'):
        self.workflow.streams = p.OriginalStreams(Terminal(answer), Terminal(), StringIO())

    def test_cancel_blank_eof_noninteractive_no_task_or_reminder_write(self):
        self.mixed()
        for answer in ('n\n', '\n', '', None):
            with self.subTest(answer=answer):
                if answer is None:
                    self.workflow.streams = p.OriginalStreams(StringIO('y\n'), StringIO(), StringIO())
                else:
                    self.terminal(answer)
                self.refresh()
                result = self.run_request(['schedule', 'Parent', '--at', 'tomorrow 12',
                    '--reminder-at', 'every Monday at 9am'])
                self.assertEqual(result.status, 1)
                self.assertFalse(result.outcomes)
                text = self.workflow.streams.stdout.getvalue()
                self.assertIn('expression (Todoist): every Monday at 9am', text)
                self.assertIn('--reminder 30m', text)
                self.assertIn('--reminder-at keep', text)
                self.assertEqual('[y/N]:' in text, answer is not None)
                self.assertTrue(all('commands' not in c for c in self.http.calls))

    def test_unknown_equivalent_normalization_can_have_new_identity(self):
        self.wire_reminders = [absolute('old', FIXED, item_id='parent')]
        self.seed()
        self.terminal()
        self.refresh()
        self.operation('reminder_delete', {'id': 'old'}, self.state(reminders=[]), 'old')
        returned = [absolute('new', FIXED, item_id='parent')]
        self.operation('reminder_add', {'item_id': 'parent', 'type': 'absolute',
            'due': {'string': 'every day at nine', 'lang': 'en'}}, self.state(reminders=returned))
        result = self.run_request(['task', '--reminder-at=every day at nine', 'Parent'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertEqual(set(result.snapshot.reminders), {'new'})
        self.assertIn('↻ cada día a las 9', result.document.stdout)
        self.assertNotIn('every day at nine', result.document.stdout)
        self.assertIn('expression (Todoist): every day at nine', self.workflow.streams.stdout.getvalue())

    def test_keep_and_relative_match_preserve_metadata_without_prompt(self):
        self.mixed()
        original = self.store.load_consistent_state().snapshot.reminders
        self.refresh()
        returned = self.wire_reminders + [f.reminder('zero', 'parent', minute_offset=0)]
        self.operation('reminder_add', {'item_id': 'parent', 'type': 'relative', 'minute_offset': 0},
                       self.state(reminders=returned), 'zero')
        result = self.run_request(['schedule', 'Parent', '--reminder-at', 'keep',
                                  '--reminder', '30m', '--reminder', '0m'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertEqual([o.operation for o in result.outcomes], ['create_reminder'])
        self.assertEqual({k: result.snapshot.reminders[k] for k in original}, original)
        self.assertEqual(self.workflow.streams.stdout.getvalue(), '')
        self.assertIn('Reminders: 30m, at ', result.document.stdout)

    def test_known_noop_duplicate_date_only_and_relative_eligibility_before_writes(self):
        self.mixed()
        for args, message in (
            (['--reminder', '30m', '--reminder-at', 'keep'], 'no-op'),
            (['--reminder', 'keep', '--reminder', '30m'], 'duplicate'),
            (['--reminder-at', 'tomorrow'], 'exact time'),
            (['--at', 'tomorrow'], 'relative reminders'),
            (['--reminder-at', '2026-11-02T10:00:00Z', '--reminder-at', '2026-11-02T11:00:00+01:00'], 'duplicate')):
            self.refresh()
            with self.subTest(args=args), self.assertRaisesRegex(d.DomainError, message):
                self.run_request(['schedule', 'Parent', *args])
        self.assertTrue(all('commands' not in c for c in self.http.calls))

    def test_known_fixed_match_retains_id_and_dst_refuses(self):
        raw = {'date': '2026-11-02T10:00:00Z', 'timezone': 'UTC', 'lang': 'en', 'is_recurring': False}
        self.wire_reminders = [absolute('same', raw, item_id='parent')]
        self.seed()
        snapshot = self.store.load_consistent_state().snapshot
        proposal = propose(parse(['schedule', 'Parent', '--reminder-at', '2026-11-02T10:00:00Z']),
                           snapshot, snapshot.items['parent'], d.instant_datetime(f.NOW))
        self.assertEqual([r.id for r in proposal.retained], ['same'])
        self.assertFalse(proposal.removals or proposal.additions)
        snapshot = replace(snapshot, account=replace(snapshot.account, timezone='Europe/Prague'))
        with self.assertRaises(d.DomainError):
            propose(parse(['schedule', 'Parent', '--reminder-at', 'Sunday 02:30']),
                    snapshot, snapshot.items['parent'], d.instant_datetime(f.NOW))

    def test_omitted_recurrence_flag_requires_consent_but_keep_preserves_metadata(self):
        # NotificationSyncView.due is open: omission is valid, not proof of false.
        # Source: docs/design/external/todoist/upstream/api-v1.openapi.json,
        # components.schemas.NotificationSyncView.properties.due.
        for rule in (None, 'every day at 10'):
            with self.subTest(rule=rule):
                self.wire_items[0]['due'] = None
                raw = {'date': '2026-11-02T10:00:00Z', 'timezone': 'UTC', 'lang': 'en'}
                if rule is not None:
                    raw['string'] = rule
                self.wire_reminders = [absolute('old', raw, item_id='parent')]
                self.seed()
                original = self.store.load_consistent_state().snapshot.reminders['old']
                self.terminal('\n')
                self.refresh()
                result = self.run_request(['schedule', 'Parent', '--reminder-at', raw['date']])
                self.assertEqual(result.status, 1)
                self.assertFalse(result.outcomes)
                self.assertIn('Remove:\n  - at 2026-11-02 10:00:00 UTC',
                              self.workflow.streams.stdout.getvalue())
                self.assertIn('--reminder-at keep', self.workflow.streams.stdout.getvalue())
                self.assertEqual(self.store.load_consistent_state().snapshot.reminders['old'], original)

                # Explicit keep still works across a task write and publication.
                self.terminal()
                self.refresh()
                state = self.state()
                state['items'][0]['due'] = f.due('2026-10-23')
                self.operation('item_update', {'id': 'parent', 'due': {'date': '2026-10-23', 'lang': 'en'}},
                               state, 'parent')
                result = self.run_request(['schedule', 'Parent', '--at', 'tomorrow', '--reminder-at', 'keep'])
                self.assertEqual(result.status, 0, result.document.stderr)
                self.assertEqual(result.snapshot.reminders['old'], original)
                self.assertEqual(self.workflow.streams.stdout.getvalue(), '')

                # A subsequent one-off replacement removes the uncertain old ID.
                self.wire_items = state['items']
                self.terminal()
                self.refresh()
                self.operation('reminder_delete', {'id': 'old'}, self.state(reminders=[]), 'old')
                returned = [absolute('new', f.due(raw['date']), item_id='parent')]
                self.operation('reminder_add', {'item_id': 'parent', 'type': 'absolute',
                    'due': {'date': raw['date'], 'lang': 'en'}}, self.state(reminders=returned))
                result = self.run_request(['schedule', 'Parent', '--reminder-at', raw['date']])
                self.assertEqual(result.status, 0, result.document.stderr)
                self.assertEqual(set(result.snapshot.reminders), {'new'})
                self.assertIn('Replace reminders and remove', self.workflow.streams.stdout.getvalue())

    def test_same_instant_distinct_rules_are_not_duplicates_and_empty_keep_noop(self):
        self.wire_reminders = [absolute('a', FIXED, item_id='parent'),
                               absolute('b', {**FIXED, 'string': 'cada lunes'}, item_id='parent')]
        self.seed()
        snapshot = self.store.load_consistent_state().snapshot
        proposal = propose(parse(['schedule', 'Parent', '--reminder-at', 'keep', '--reminder', 'keep']),
                           snapshot, snapshot.items['parent'], d.instant_datetime(f.NOW))
        self.assertEqual([r.id for r in proposal.retained], ['a', 'b'])
        self.refresh()
        with self.assertRaisesRegex(d.DomainError, 'no-op'):
            self.run_request(['schedule', 'Parent', '--reminder-at', 'keep'])

    def test_keep_absolute_replace_relative_before_date_only_task_write(self):
        self.mixed()
        self.terminal()
        self.refresh()
        state = self.state(reminders=self.wire_reminders[1:])
        self.operation('reminder_delete', {'id': 'relative'}, state, 'relative')
        changed = deepcopy(state)
        changed['items'][0]['due'] = f.due('2026-10-23')
        self.operation('item_update', {'id': 'parent', 'due': {'date': '2026-10-23', 'lang': 'en'}}, changed, 'parent')
        result = self.run_request(['schedule', 'Parent', '--at', 'tomorrow', '--reminder-at', 'keep'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertEqual(set(result.snapshot.reminders), {'absolute'})
        self.assertIn('Add:\n  None.', self.workflow.streams.stdout.getvalue())
        self.assertNotIn('--reminder-at keep', self.workflow.streams.stdout.getvalue())

    def test_direct_clear_both_types_and_all_scheduling_clear(self):
        for all_scheduling in (False, True):
            self.mixed()
            self.refresh()
            state = self.state(reminders=self.wire_reminders[1:])
            self.operation('reminder_delete', {'id': 'relative'}, state, 'relative')
            state = self.state(reminders=[])
            self.operation('reminder_delete', {'id': 'absolute'}, state, 'absolute')
            if all_scheduling:
                state['items'][0]['due'] = None
                self.operation('item_update', {'id': 'parent', 'due': None}, state, 'parent')
            result = self.run_request(['schedule', 'Parent', *(['clear'] if all_scheduling else ['--reminder', 'clear'])])
            self.assertEqual(result.status, 0, result.document.stderr)
            self.assertFalse(result.snapshot.reminders)
            self.assertEqual(result.snapshot.items['parent'].attention is None, all_scheduling)
            self.assertEqual(self.workflow.streams.stdout.getvalue(), '')

    def test_creation_absolute_undated_actual_set_and_inline_exclusion(self):
        self.refresh()
        state = self.state(items=self.wire_items + [f.item('new', content='New task', priority=3)])
        self.operation('item_add', {'project_id': 'cat', 'content': 'New task', 'priority': 3,
            'description': '', 'labels': [], 'auto_reminder': False, 'due': None}, state)
        returned = [absolute('a', {'date': '2026-10-22T14:00:02Z', 'timezone': 'UTC',
                                 'lang': 'en', 'is_recurring': False}, item_id='new')]
        state['reminders'] = returned
        self.operation('reminder_add', {'item_id': 'new', 'type': 'absolute',
            'due': {'date': '2026-10-22T14:00:00.123456Z', 'lang': 'en'}}, state, 'a')
        state = deepcopy(state)
        state['items'].append(f.item('child', content='Child step', parent_id='new', priority=3))
        self.operation('item_add', {'project_id': 'cat', 'content': 'Child step', 'priority': 3,
            'description': '', 'labels': [], 'auto_reminder': False, 'parent_id': 'new'}, state, 'child')
        result = self.run_request(['add', 'cat', 'New task', '--step', 'Child step', '--reminder-at', '2h'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertIsNone(result.snapshot.items['new'].attention)
        self.assertIsNone(result.snapshot.items['child'].attention)
        self.assertIn('  Reminders: at 2026-10-22 14:00:02 UTC', result.document.stdout)

    def test_accepted_date_only_is_partial_and_stops_next_operation(self):
        self.refresh()
        invalid = [absolute('invalid', {'date': '2026-10-23', 'lang': 'en'}, item_id='parent')]
        self.operation('reminder_add', {'item_id': 'parent', 'type': 'absolute',
            'due': {'string': 'some provider expression', 'lang': 'en'}}, self.state(reminders=invalid), 'invalid')
        # No complete Current exists to share after the rejected resource mapping.
        self.queue_refresh(self.state(reminders=invalid), synchronize=False)
        # Reconciliation also refuses the invalid current state; no rollback follows.
        result = self.run_request(['schedule', 'Parent', '--reminder-at', 'some provider expression',
                                  '--reminder-at', 'another expression'])
        self.assertEqual(result.status, 1)
        self.assertEqual([o.outcome for o in result.outcomes], ['accepted', 'unattempted'])
        self.assertNotIn('Reminders:', result.document.stdout)
        self.assertNotIn('some provider expression', result.document.stdout)

    def test_exact_two_second_tolerance_and_strict_semantics(self):
        for returned, extra, accepted in (
            ('2026-11-02T09:59:58Z', {}, True),
            ('2026-11-02T10:00:02Z', {}, True),
            ('2026-11-02T10:00:02.000001Z', {}, False),
            ('2026-11-02T10:00:03Z', {}, False),
            ('2026-11-02T10:00:00Z', {'is_recurring': True, 'string': 'every day'}, False),
            ('2026-11-02T10:00:00Z', {'timezone': 'Europe/Prague'}, False),
        ):
            with self.subTest(returned=returned, extra=extra):
                self.refresh()
                after = [absolute('new', f.due(returned, **extra), item_id='parent')]
                self.operation('reminder_add', {'item_id': 'parent', 'type': 'absolute',
                    'due': {'date': '2026-11-02T10:00:00Z', 'lang': 'en'}}, self.state(reminders=after))
                result = self.run_request(['schedule', 'Parent', '--reminder-at', '2026-11-02T10:00:00Z'])
                self.assertEqual(result.status, 0 if accepted else 1, result.document.stderr)
                self.assertEqual(result.outcomes[0].outcome, 'accepted')
                self.assertEqual(result.snapshot.reminders['new'].due.raw_due['date'], returned)
                if accepted:
                    self.assertIn('Reminders: none -> at ', result.document.stdout)
                else:
                    self.assertNotIn('Reminders:', result.document.stdout)
                    self.assertIn("requested {'date': '2026-11-02T10:00:00Z'", result.document.stderr)
                    self.assertIn("actual {'date': '" + returned + "'", result.document.stderr)
                    self.assertIn("'timezone': '" + extra.get('timezone', 'UTC') + "'", result.document.stderr)
                    self.assertIn('account timezone UTC', result.document.stderr)

    def test_later_rejection_preserves_accepted_removal_and_retained_id(self):
        self.mixed()
        self.terminal()
        self.refresh()
        state = self.state(reminders=self.wire_reminders[1:])
        self.operation('reminder_delete', {'id': 'relative'}, state, 'relative')
        self.operation('reminder_add', {'item_id': 'parent', 'type': 'absolute',
            'due': {'string': 'first unknown', 'lang': 'en'}}, state, 'failed', status={'error_code': 1, 'error': 'rejected'})
        result = self.run_request(['schedule', 'Parent', '--reminder-at', 'keep',
                                  '--reminder-at', 'first unknown', '--reminder-at', 'second unknown'])
        self.assertEqual(result.status, 1)
        self.assertEqual([o.outcome for o in result.outcomes], ['accepted', 'rejected', 'unattempted'])
        self.assertEqual(set(result.snapshot.reminders), {'absolute'})
        self.assertIn('Reminders: 30m, at ', result.document.stdout)
        self.assertIn('Not attempted', result.document.stderr)

    def test_mixed_addition_order_and_distinct_provider_recurrences(self):
        self.wire_items[0]['due'] = f.due('2026-10-30T10:00:00Z')
        self.seed()
        self.refresh()
        first = absolute('a', {**FIXED, 'string': 'every Monday'}, item_id='parent')
        second = absolute('b', {**FIXED, 'string': 'every day'}, item_id='parent')
        relative = f.reminder('relative', 'parent', minute_offset=0)
        self.operation('reminder_add', {'item_id': 'parent', 'type': 'absolute',
            'due': {'string': 'every Monday at 9am', 'lang': 'en'}}, self.state(reminders=[first]), 'a')
        self.operation('reminder_add', {'item_id': 'parent', 'type': 'relative', 'minute_offset': 0},
            self.state(reminders=[first, relative]), 'relative')
        self.operation('reminder_add', {'item_id': 'parent', 'type': 'absolute',
            'due': {'string': 'every day at 9am', 'lang': 'en'}}, self.state(reminders=[first, relative, second]), 'b')
        result = self.run_request(['schedule', 'Parent', '--reminder-at', 'every Monday at 9am',
                                  '--reminder=0m', '--reminder-at=every day at 9am'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertEqual([o.target_id for o in result.outcomes], ['a', 'relative', 'b'])
        self.assertEqual(set(result.snapshot.reminders), {'a', 'b', 'relative'})
        self.assertEqual(self.workflow.streams.stdout.getvalue(), '')
        self.assertIn('0m, at ', result.document.stdout)

    def test_unknown_proof_stops_reminder_additions_without_accepted_receipt(self):
        self.refresh()
        self.operation('reminder_add', {'item_id': 'parent', 'type': 'absolute',
            'due': {'string': 'first unknown', 'lang': 'en'}}, self.state(), 'unknown', status=None)
        result = self.run_request(['schedule', 'Parent', '--reminder-at', 'first unknown',
                                  '--reminder-at', 'second unknown'])
        self.assertEqual(result.status, 1)
        self.assertEqual([o.outcome for o in result.outcomes], ['unknown', 'unattempted'])
        self.assertEqual(result.document.stdout, '')
        self.assertIn('do not replay', result.document.stderr)

    def test_fixed_input_does_not_retain_floating_same_instant(self):
        self.wire_reminders = [absolute('floating', {'date': '2026-11-02T10:00:00',
            'timezone': None, 'lang': 'en', 'is_recurring': False}, item_id='parent')]
        self.seed()
        snapshot = self.store.load_consistent_state().snapshot
        proposal = propose(parse(['schedule', 'Parent', '--reminder-at', '2026-11-02T10:00:00Z']),
                           snapshot, snapshot.items['parent'], d.instant_datetime(f.NOW))
        self.assertFalse(proposal.retained)
        self.assertEqual([r.id for r in proposal.removals], ['floating'])
        self.assertEqual(len(proposal.additions), 1)
