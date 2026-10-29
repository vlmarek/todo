import unittest
from dataclasses import replace
from todo_lib import domain as d
from todo_lib.adapter.commands import Operation, Outcome, due_arguments
from tests.adapter.commands import test_commands as base
from tests.adapter.current.test_current import delta
from tests.support.reminders import absolute, MINIMAL, FIXED


class ReminderGatewayTests(unittest.TestCase):
    gateway = base.CommandsTests.gateway

    def test_absolute_serialization_independent_and_parser_result(self):
        for schedule in (MINIMAL, FIXED, {'string': 'every Monday at 9', 'lang': 'en'}):
            raw = MINIMAL if 'date' not in schedule else schedule
            g, wire = self.gateway('reminder_add', {'item_id': 'task', 'type': 'absolute', 'due': schedule},
                read=[delta(reminders=[absolute('new', raw, item_id='task')])])
            result = g.create_reminder('task', due=schedule, before=base.before())
            self.assertEqual(result.outcome, Outcome.ACCEPTED)
            self.assertFalse(result.issues)
            self.assertEqual(result.actual.id, 'new')
            self.assertIsNone(result.after.snapshot.items['task'].attention)
            self.assertNotEqual(wire.command['uuid'], wire.command['temp_id'])
        recurrence = d.resolve_reminder_due(FIXED, 'UTC')
        self.assertEqual(due_arguments(recurrence)['lang'], 'es')
        self.assertEqual(due_arguments(d.Attention('unresolved', expression='every Monday at 9')), {'string': 'every Monday at 9', 'lang': 'en'})

    def test_supplied_parser_metadata_and_type_are_validated(self):
        for schedule in ({'string': 'Friday', 'lang': None},
                         {'string': 'Friday', 'timezone': 2},
                         {'string': 'Friday', 'is_recurring': None}):
            with self.subTest(schedule=schedule), self.assertRaises(d.DomainError):
                Operation('reminder_add', {'item_id': 'task', 'type': 'absolute', 'due': schedule})
        with self.assertRaises(d.DomainError):
            Operation('reminder_add', {'item_id': 'task', 'type': None})
        minimal_recurring = d.resolve_reminder_due({**MINIMAL, 'is_recurring': True}, 'UTC')
        self.assertEqual(due_arguments(minimal_recurring), {**MINIMAL, 'is_recurring': True})

    def test_relative_zero_and_update_only_requested_fields(self):
        g, wire = self.gateway('reminder_add', {'item_id': 'task', 'type': 'relative', 'minute_offset': 0},
            read=[delta(reminders=[{'id': 'new', 'item_id': 'task', 'type': 'relative', 'minute_offset': 0, 'is_deleted': False}])])
        task = d.Item('task', 'cat', 'Task', attention=d.resolve_remote_due(base.due(), 'UTC'))
        self.assertFalse(g.create_reminder('task', 0, before=base.before(task)).issues)
        op = Operation('reminder_update', {'id': 'retained', 'due': MINIMAL})
        self.assertEqual(set(op.command()['args']), {'id', 'due'})
        with self.assertRaises(d.DomainError):
            Operation('reminder_add', {'item_id': 'task', 'type': 'absolute', 'due': {'date': '2026-10-30'}})

    def test_known_tolerance_strict_kind_day_zone_rule(self):
        expected = d.resolve_reminder_due(FIXED, 'UTC')
        for raw, accepted in (({**FIXED, 'date': '2026-10-30T08:00:02.123456789012345Z'}, True),
                              ({**FIXED, 'date': '2026-10-30T07:59:58.123456789012345Z'}, True),
                              ({**FIXED, 'date': '2026-10-30T08:00:02.123456789012346Z'}, False),
                              ({**FIXED, 'timezone': 'Europe/Prague'}, False),
                              ({**FIXED, 'string': 'otra regla'}, False),
                              ({**FIXED, 'is_recurring': False}, False),
                              ({**FIXED, 'lang': 'en'}, False),
                              ({**FIXED, 'date': '2026-10-30T08:00:00.123456789012345', 'timezone': None}, False)):
            with self.subTest(raw=raw):
                g, _ = self.gateway('reminder_add', {'item_id': 'task', 'type': 'absolute', 'due': FIXED},
                    read=[delta(reminders=[absolute('new', raw, item_id='task')])])
                result = g.create_reminder('task', due=expected, before=base.before())
                self.assertEqual(not result.issues, accepted)
                self.assertEqual(result.actual.due.raw_due, raw)

    def test_tolerance_cannot_cross_account_day(self):
        schedule = {'date': '2026-10-30T23:59:59Z', 'timezone': None}
        returned = {'date': '2026-10-31T00:00:00Z', 'timezone': None}
        g, _ = self.gateway('reminder_add', {'item_id': 'task', 'type': 'absolute', 'due': {**schedule, 'lang': 'en'}},
            read=[delta(reminders=[absolute('new', returned, item_id='task')])])
        result = g.create_reminder('task', due=d.resolve_reminder_due(schedule, 'UTC'), before=base.before())
        self.assertTrue(result.partial)
        self.assertEqual(result.actual.due.raw_due, returned)

    def test_date_only_invalid_actual_is_accepted_partial_and_matching_is_not_proof(self):
        for raw in ({'date': '2026-10-30'}, {'date': None}):
            g, _ = self.gateway('reminder_add', {'item_id': 'task', 'type': 'absolute', 'due': {'string': 'Friday', 'lang': 'en'}},
                read=[delta(reminders=[absolute('new', raw, item_id='task')])])
            result = g.create_reminder('task', due={'string': 'Friday'}, before=base.before())
            self.assertTrue(result.partial)
            self.assertIsNone(result.after)
        g, _ = self.gateway('reminder_add', {'item_id': 'task', 'type': 'absolute', 'due': MINIMAL},
            read=[delta(reminders=[absolute('new', item_id='task')])], status=None)
        result = g.create_reminder('task', due=MINIMAL, before=base.before())
        self.assertEqual(result.outcome, Outcome.UNKNOWN)


    def test_updates_validate_requested_fields_with_authoritative_untouched_context(self):
        initial = base.before()
        retained = d.Reminder('r', 'task', type='absolute',
            due=d.resolve_reminder_due(FIXED, 'UTC'), notify_uid='recipient', is_urgent=True)
        initial = replace(initial, snapshot=replace(initial.snapshot, reminders={'r': retained}))
        cases = [({'due': MINIMAL}, absolute('r', MINIMAL, item_id='task', notify_uid='other')),
                 ({'due': MINIMAL}, absolute('r', MINIMAL, item_id='task', is_urgent=False)),
                 ({'notify_uid': 'other'}, absolute('r', {**FIXED, 'date': '2026-11-01T08:00:00Z'},
                                                   item_id='task', notify_uid='other')),
                 ({'notify_uid': 'other'}, absolute('r', FIXED, item_id='task', notify_uid='other'))]
        for args, returned in cases:
            with self.subTest(args=args, returned=returned):
                g, _ = self.gateway('reminder_update', {'id': 'r', **args}, read=[delta(reminders=[returned])])
                result = g.execute(Operation('reminder_update', {'id': 'r', **args}), before=initial)
                self.assertEqual(result.outcome, Outcome.ACCEPTED)
                self.assertFalse(result.issues)
                self.assertEqual(result.actual.notify_uid, returned['notify_uid'])
                self.assertEqual(result.after.snapshot.reminders['r'], result.actual)

    def test_direct_reminder_operations_accept_valid_changed_owner_context(self):
        for changed in ({'due': base.due()}, {'content': 'Unexpected'}, {'priority': 4},
                        {'checked': True, 'completed_at': base.AT}):
            g, _ = self.gateway('reminder_add', {'item_id': 'task', 'type': 'absolute', 'due': MINIMAL},
                read=[delta(items=[base.item(**changed)], reminders=[absolute('new', item_id='task')])])
            result = g.create_reminder('task', due=MINIMAL, before=base.before())
            self.assertFalse(result.partial)
            self.assertFalse(result.issues)
        initial = base.before()
        retained = d.Reminder('r', 'task', type='absolute', due=d.resolve_reminder_due(FIXED, 'UTC'))
        initial = replace(initial, snapshot=replace(initial.snapshot, reminders={'r': retained}))
        for kind, args, raw in (
                ('reminder_update', {'id': 'r', 'notify_uid': 'new'},
                 absolute('r', FIXED, item_id='task', notify_uid='new')),
                ('reminder_delete', {'id': 'r'}, {'id': 'r', 'is_deleted': True})):
            g, _ = self.gateway(kind, args, read=[delta(items=[base.item(content='Unexpected')], reminders=[raw])])
            result = g.execute(Operation(kind, args), before=initial)
            self.assertFalse(result.partial)
            self.assertFalse(result.issues)
        floating = base.due('2026-10-30T09:00:00')
        initial = base.before(replace(base.before().snapshot.items['task'], attention=d.resolve_remote_due(floating, 'UTC')))
        g, _ = self.gateway('reminder_add', {'item_id': 'task', 'type': 'absolute', 'due': MINIMAL},
            read=[delta(user={'id': 'u', 'tz_info': {'timezone': 'America/New_York'}},
                        reminders=[absolute('new', item_id='task')])])
        self.assertFalse(g.create_reminder('task', due=MINIMAL, before=initial).issues)

    def test_fixed_omitted_request_timezone_defaults_but_explicit_zone_stays_strict(self):
        raw = {'date': '2026-10-30T09:00:00Z'}
        for attention in (raw, d.resolve_reminder_due(raw, 'UTC')):
            for zone, good in (('UTC', True), ('Europe/Madrid', False)):
                g, _ = self.gateway('reminder_add', {'item_id': 'task', 'type': 'absolute', 'due': {**raw, 'lang': 'en'}},
                    read=[delta(reminders=[absolute('new', {**raw, 'timezone': zone}, item_id='task')])])
                result = g.create_reminder('task', due=attention, before=base.before())
                self.assertEqual(not result.issues, good)


    def test_metadata_update_uses_authoritative_schedule_in_returned_zone(self):
        from tests.support.reminders import FLOATING
        initial = base.before()
        retained = d.Reminder('r', 'task', type='absolute', due=d.resolve_reminder_due(FLOATING, 'UTC'))
        initial = replace(initial, snapshot=replace(initial.snapshot, reminders={'r': retained}))
        for raw, good in ((FLOATING, True),
                          ({**FLOATING, 'date': '2026-10-30T09:00:01.123456789012345'}, False),
                          ({**FLOATING, 'date': '2026-10-31T09:00:00'}, False)):
            g, _ = self.gateway('reminder_update', {'id': 'r', 'notify_uid': 'new'},
                read=[delta(user={'id': 'u', 'tz_info': {'timezone': 'America/New_York'}},
                    reminders=[absolute('r', raw, item_id='task', notify_uid='new')])])
            result = g.execute(Operation('reminder_update', {'id': 'r', 'notify_uid': 'new'}), before=initial)
            self.assertFalse(result.issues)
            self.assertEqual(result.actual.due.raw_due, raw)
            self.assertTrue(result.actual.is_urgent)  # unknown metadata may become known
        task = replace(initial.snapshot.items['task'], attention=d.resolve_remote_due(base.due(), 'UTC'))
        initial = base.before(task)
        initial = replace(initial, snapshot=replace(initial.snapshot, reminders={'r': d.Reminder('r', 'task', 0)}))
        for offset in (0, 10):
            g, _ = self.gateway('reminder_update', {'id': 'r', 'is_urgent': False},
                read=[delta(reminders=[{'id': 'r', 'item_id': 'task', 'type': 'relative',
                    'minute_offset': offset, 'is_urgent': False, 'is_deleted': False}])])
            result = g.execute(Operation('reminder_update', {'id': 'r', 'is_urgent': False}), before=initial)
            self.assertFalse(result.issues)

    def test_requested_metadata_mismatch_remains_partial(self):
        initial = base.before()
        reminder = d.Reminder('r', 'task', type='absolute', due=d.resolve_reminder_due(FIXED, 'UTC'))
        initial = replace(initial, snapshot=replace(initial.snapshot, reminders={'r': reminder}))
        for args, returned in (({'notify_uid': 'requested'}, {'notify_uid': 'different'}),
                               ({'is_urgent': False}, {'is_urgent': True})):
            with self.subTest(args=args):
                g, _ = self.gateway('reminder_update', {'id':'r', **args},
                    read=[delta(reminders=[absolute('r', FIXED, item_id='task', **returned)])])
                result = g.execute(Operation('reminder_update', {'id':'r', **args}), before=initial)
                self.assertTrue(result.partial)

    def test_raw_item_parser_request_still_checks_explicit_named_zone(self):
        from tests.adapter.current.test_current import item
        g, _ = self.gateway('item_update', {'id': 'task', 'due': {
            'string': 'next Monday at 9', 'timezone': 'America/New_York', 'lang': 'en'}},
            read=[delta(items=[item('task', due={**base.due('2026-11-02T14:00:00Z'), 'timezone': 'Europe/Prague'})])])
        result = g.execute(Operation('item_update', {'id': 'task', 'due': {
            'string': 'next Monday at 9', 'timezone': 'America/New_York'}}), before=base.before())
        self.assertTrue(result.accepted)
        self.assertTrue(result.partial)
        self.assertIn('named timezone', '; '.join(result.issues))
