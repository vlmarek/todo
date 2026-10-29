"""Named-zone requests at the real UUID/current/publication boundary.

Independent response fixtures follow the retained api-v1.openapi.json Due dates
and Sync task/reminder commands. The strict boundary rejects wrong request fields;
responses are supplied independently, never calculated from outgoing commands.
"""
import unittest
from io import StringIO
from todo_lib import domain as d, presentation as p
from todo_lib.syntax import parse
from tests.workflows.capture import test_capture as f
from tests.workflows.capture.test_coexistence import Terminal
from tests.support.reminders import absolute


class NamedTimezoneWorkflowTests(unittest.TestCase):
    setUp = f.CaptureTests.setUp
    state = f.CaptureTests.state
    seed = f.CaptureTests.seed
    queue_refresh = f.CaptureTests.queue_refresh
    operation = f.CaptureTests.operation
    run_request = f.CaptureTests.run_request

    def test_independent_zones_omission_and_saved_roundtrip(self):
        self.account_zone = 'Europe/Prague'
        self.seed()
        attention = f.due('2026-11-12T14:00:00Z', timezone='America/New_York')
        state = self.state(items=[dict(i, due=attention) if i['id'] == 'parent' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'parent', 'due': {
            'date': '2026-11-12T14:00:00Z', 'lang': 'en', 'timezone': 'America/New_York'}}, state, 'parent')
        reminders = [absolute('tokyo', f.due('2026-11-11T23:30:00Z', timezone='Asia/Tokyo'), item_id='parent')]
        state = dict(state, reminders=reminders)
        self.operation('reminder_add', {'item_id': 'parent', 'type': 'absolute', 'due': {
            'date': '2026-11-11T23:30:00Z', 'lang': 'en', 'timezone': 'Asia/Tokyo'}}, state, 'tokyo')
        reminders = reminders + [absolute('default', f.due('2026-11-12T07:00:00Z', timezone='Europe/Prague'), item_id='parent')]
        state = dict(state, reminders=reminders)
        self.operation('reminder_add', {'item_id': 'parent', 'type': 'absolute', 'due': {
            'date': '2026-11-12T07:00:00Z', 'lang': 'en'}}, state, 'default')
        start = len(self.http.calls)
        result = self.run_request(['task', '--due=2026-11-12 09:00 America/New_York', 'Parent',
            '--reminder-at', '2026-11-12 08:30 Asia/Tokyo', '--reminder-at=2026-11-12T08:00:00+01:00'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertIn('commands', self.http.calls[start])  # cached, command first
        saved = self.store.load_consistent_state().snapshot
        self.assertEqual(saved.items['parent'].attention.zone, 'America/New_York')
        self.assertEqual({k: r.due.zone for k, r in saved.reminders.items()}, {'tokyo': 'Asia/Tokyo', 'default': 'Europe/Prague'})
        # A complete exact match retains IDs and performs no request or prompt.
        with self.assertRaisesRegex(d.DomainError, 'no-op'):
            self.run_request(['schedule', 'Parent', '--reminder-at', '2026-11-12 08:30 Asia/Tokyo',
                              '--reminder-at', '2026-11-12T08:00:00+01:00'])

    def test_invalid_scalars_make_zero_writes_on_creation_and_scheduling(self):
        for scalar in ['tomorrow Unknown/Location', '2026-11-01 01:30 America/New_York',
                       '2027-03-14 02:30 America/New_York']:
            for argv in [['schedule', 'Parent', '--at', scalar],
                         ['add', 'cat', 'New task', '--at', scalar],
                         ['task', '--reminder-at', scalar, 'Parent']]:
                with self.subTest(argv=argv), self.assertRaises(d.DomainError):
                    self.run_request(argv)
        with self.assertRaisesRegex(d.DomainError, 'exact time'):
            self.run_request(['schedule', 'Parent', '--at', 'tomorrow America/New_York',
                              '--reminder-at', 'tomorrow Asia/Tokyo'])
        self.assertTrue(all('commands' not in c for c in self.http.calls))

    def test_named_recurrence_request_survives_dst_offsets(self):
        for date in ['2026-10-26T13:00:00Z', '2026-11-02T14:00:00Z']:
            with self.subTest(date=date):
                state = self.state(items=[dict(i, due=f.due(date, timezone='America/New_York',
                    string='every Monday at 09:00', is_recurring=True)) if i['id'] == 'parent' else i for i in self.wire_items])
                self.operation('item_update', {'id': 'parent', 'due': {'string': 'every Monday at 09:00',
                    'lang': 'en', 'timezone': 'America/New_York'}}, state, 'parent')
                result = self.run_request(['schedule', 'Parent', '--at', 'every Monday at 09:00 America/New_York'])
                self.assertEqual(result.status, 0, result.document.stderr)
                attention = self.store.load_consistent_state().snapshot.items['parent'].attention
                self.assertEqual((attention.zone, attention.rule, attention.recurring), ('America/New_York', 'every Monday at 09:00', True))
                self.assertEqual(attention.instant.astimezone(d.account_timezone(attention.zone)).hour, 9)

    def test_occurrence_move_retains_rule_language_zone_and_reminders(self):
        raw = f.due('2026-10-26T13:00:00Z', timezone='America/New_York', string='cada lunes a las 9', lang='es', is_recurring=True)
        self.wire_items[0]['due'] = raw
        self.wire_reminders = [absolute('independent', f.due('2026-11-12T00:00:00Z', timezone='Asia/Tokyo'), item_id='parent')]
        self.seed()
        before = self.store.load_consistent_state().snapshot.reminders
        moved = {**raw, 'date': '2026-11-12T08:00:00Z'}
        state = self.state(items=[dict(i, due=moved) if i['id'] == 'parent' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'parent', 'due': moved}, state, 'parent')
        result = self.run_request(['schedule', 'Parent', '--at', '2026-11-12 09:00 Europe/Prague'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertEqual(result.snapshot.reminders, before)
        self.assertEqual(result.snapshot.items['parent'].attention.raw_due, moved)

    def test_short_code_forwarding_has_no_predicted_zone(self):
        # Synthetic actual normalization makes no claim about live CET behavior.
        state = self.state(items=[dict(i, due=f.due('2026-11-12T16:00:00Z', timezone='Asia/Tokyo'))
                                 if i['id'] == 'parent' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'parent', 'due': {'string': 'Friday 09:00 CET', 'lang': 'en'}}, state, 'parent')
        result = self.run_request(['task', '--schedule', 'Friday 09:00 CET', 'Parent'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertEqual(result.snapshot.items['parent'].attention.zone, 'Asia/Tokyo')

    def test_iso_date_short_codes_delegate_and_preserve_actual_normalization(self):
        # Synthetic responses exercise both valid kinds, without promising any
        # particular provider interpretation of these abbreviations.
        items = [dict(i, due=f.due('2026-11-12', timezone=None))
                 if i['id'] == 'parent' else i for i in self.wire_items]
        state = self.state(items=items)
        self.operation('item_update', {'id': 'parent', 'due': {
            'string': '2026-11-12 CET', 'lang': 'en'}}, state, 'parent')
        result = self.run_request(['schedule', 'Parent', '--at=2026-11-12 CET'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertEqual((result.snapshot.items['parent'].attention.kind,
                          result.snapshot.items['parent'].attention.zone), ('date', None))

        actual = absolute('normalized', f.due('2026-11-12T16:00:00Z', timezone='Asia/Tokyo'), item_id='parent')
        state = self.state(items=items, reminders=[actual])
        self.operation('reminder_add', {'item_id': 'parent', 'type': 'absolute', 'due': {
            'string': '2026-11-12 EST', 'lang': 'en'}}, state, 'normalized')
        result = self.run_request(['task', '--reminder-at', '2026-11-12 EST', 'Parent'])
        self.assertEqual(result.status, 0, result.document.stderr)
        saved = self.store.load_consistent_state().snapshot
        self.assertEqual(saved.reminders['normalized'].due.zone, 'Asia/Tokyo')
        # A later exact request matches the saved authoritative schedule by ID.
        calls = len(self.http.calls)
        with self.assertRaisesRegex(d.DomainError, 'no-op'):
            self.run_request(['schedule', 'Parent', '--reminder-at', '2026-11-13 01:00 Asia/Tokyo'])
        self.assertEqual(len(self.http.calls), calls)
        self.assertFalse(self.http.steps)

    def test_named_reminder_wrong_authoritative_zone_is_partial(self):
        actual = absolute('wrong', f.due('2026-11-02T14:00:00Z', timezone='Europe/Prague',
                          string='every Monday at 9', is_recurring=True), item_id='parent')
        state = self.state(reminders=[actual])
        self.operation('reminder_add', {'item_id': 'parent', 'type': 'absolute', 'due': {
            'string': 'every Monday at 9', 'lang': 'en', 'timezone': 'America/New_York'}}, state, 'wrong')
        result = self.run_request(['schedule', 'Parent', '--reminder-at', 'every Monday at 9 America/New_York'])
        self.assertEqual(result.status, 1)
        self.assertEqual(result.outcomes[0].outcome, 'accepted')
        self.assertTrue(result.outcomes[0].issues)
        self.assertEqual(self.store.load_consistent_state().snapshot.reminders['wrong'].due.zone, 'Europe/Prague')

    def test_delegated_named_attention_can_normalize_date_only(self):
        state = self.state(items=[dict(i, due=f.due('2026-11-02', string='every Monday', is_recurring=True))
                                 if i['id'] == 'parent' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'parent', 'due': {'string': 'every Monday', 'lang': 'en', 'timezone': 'America/New_York'}}, state, 'parent')
        result = self.run_request(['schedule', 'Parent', '--at', 'every Monday America/New_York'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertEqual((result.snapshot.items['parent'].attention.kind, result.snapshot.items['parent'].attention.zone), ('date', None))

    def test_cancelled_removal_shows_original_named_expression(self):
        self.wire_reminders = [absolute('old', item_id='parent')]
        self.seed()
        self.workflow.streams = p.OriginalStreams(Terminal('n\n'), Terminal(), StringIO())
        result = self.run_request(['schedule', 'Parent', '--at', '2026-11-12 09:00 America/New_York',
            '--reminder-at', 'every Monday at 9 Europe/London'])
        self.assertEqual(result.status, 1)
        self.assertFalse(result.outcomes)
        self.assertIn('expression (Todoist): every Monday at 9 Europe/London', self.workflow.streams.stdout.getvalue())
        self.assertTrue(all('commands' not in c for c in self.http.calls))

    def test_delegated_attention_wrong_zone_is_accepted_partial(self):
        state = self.state(items=[dict(i, due=f.due('2026-11-02T14:00:00Z', timezone='Europe/Prague'))
                                 if i['id'] == 'parent' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'parent', 'due': {'string': 'next Monday at 9',
            'lang': 'en', 'timezone': 'America/New_York'}}, state, 'parent')
        result = self.run_request(['schedule', 'Parent', '--at', 'next Monday at 9 America/New_York'])
        self.assertEqual(result.status, 1)
        self.assertTrue(result.outcomes[0].issues)
        self.assertEqual(self.store.load_consistent_state().snapshot.items['parent'].attention.zone, 'Europe/Prague')

    def test_whole_scalar_aliases_keep_selector_and_creation_boundaries(self):
        scalar = '2026-11-12 09:00 America/New_York'
        cases = [(['schedule', 'Parent', '--at=' + scalar], 'at'),
                 (['hide', 'Parent', '--at', scalar], 'at'),
                 (['task', '--due', scalar, 'Parent'], 'at'),
                 (['step', '--schedule=' + scalar, 'Parent', 'Child'], 'at'),
                 (['add', 'cat', 'New title', '--reminder-at=' + scalar], 'reminder-at')]
        for argv, key in cases:
            with self.subTest(argv=argv):
                request = parse(argv)
                value = dict(request.options)[key]
                self.assertEqual(value, (scalar,) if key == 'reminder-at' else scalar)

    def test_absolute_named_recurrence_at_adapter_across_dst(self):
        from tests.adapter.commands import test_commands as a
        for date in ['2026-10-26T13:00:00Z', '2026-11-02T14:00:00Z']:
            returned = f.due(date, timezone='America/New_York', string='every Monday at 9', is_recurring=True)
            gateway, _ = a.CommandsTests.gateway(self, 'reminder_add', {'item_id': 'task', 'type': 'absolute',
                'due': {'string': 'every Monday at 9', 'timezone': 'America/New_York', 'lang': 'en'}},
                read=[f.delta(reminders=[absolute('new', returned, item_id='task')])])
            result = gateway.create_reminder('task', due=d.parse_attention('every Monday at 9 America/New_York',
                d.instant_datetime(f.NOW), 'UTC'), before=a.before())
            self.assertFalse(result.issues)
            self.assertEqual((result.actual.due.zone, result.actual.due.rule), ('America/New_York', 'every Monday at 9'))
