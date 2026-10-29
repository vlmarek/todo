"""Revision 15 per-scalar interpretation; no local recurrence/abbreviation engine."""
import unittest
from dataclasses import replace
from datetime import datetime, timezone, date
from todo_lib import domain as d
from todo_lib.adapter.commands import due_arguments
from todo_lib.local.codec import snapshot_data, snapshot_from, dumps, loads
from tests.support.reminders import observed

NOW = datetime(2026, 10, 29, 0, 30, tzinfo=timezone.utc)


class NamedTimezoneTests(unittest.TestCase):
    def parse(self, text, now=NOW):
        return d.parse_attention(text, now, 'Europe/Prague')

    def test_each_calendar_uses_own_zone(self):
        self.assertEqual(self.parse('tomorrow America/New_York').date_value, date(2026, 10, 29))
        self.assertEqual(self.parse('tomorrow Europe/Prague').date_value, date(2026, 10, 30))
        self.assertEqual(self.parse('tomorrow').date_value, date(2026, 10, 30))
        self.assertIsNone(self.parse('tomorrow America/New_York').zone)
        self.assertEqual(due_arguments(self.parse('2026-11-12 09:00 America/New_York')),
            {'date': '2026-11-12T14:00:00Z', 'timezone': 'America/New_York', 'lang': 'en'})
        for text, expected in [('1month America/New_York', '2026-02-28T14:00:00Z'),
                               ('1bd America/New_York', '2026-02-02T14:00:00Z')]:
            value = self.parse(text, datetime(2026, 1, 31, 14, tzinfo=timezone.utc))
            self.assertEqual(due_arguments(value)['date'], expected)
        start = datetime(2027, 3, 13, 17, tzinfo=timezone.utc)
        self.assertEqual(due_arguments(self.parse('1d America/New_York', start))['date'], '2027-03-14T16:00:00Z')
        self.assertEqual(due_arguments(self.parse('24h America/New_York', start))['date'], '2027-03-14T17:00:00Z')

    def test_offsets_and_precision_remain_authoritative(self):
        value = self.parse('2026-11-12T09:00:00.123456789012345+02:00 America/New_York')
        self.assertEqual(due_arguments(value)['date'], '2026-11-12T07:00:00.123456789012345Z')
        self.assertEqual(value.zone, 'America/New_York')
        local = self.parse('2026-11-12 09:00:00.123456789012345 America/New_York')
        self.assertEqual(due_arguments(local)['date'], '2026-11-12T14:00:00.123456789012345Z')
        with self.assertRaises(d.DomainError):
            self.parse('2026-11-12 09:00')

    def test_invalid_location_and_dst_are_local_errors(self):
        for text in ['tomorrow Nowhere/Unknown', '2026-11-01 01:30 America/New_York',
                     '2027-03-14 02:30 America/New_York']:
            with self.subTest(text=text), self.assertRaises(d.DomainError):
                self.parse(text)

    def test_delegation_preserves_wording_and_original_preview(self):
        text = 'every Monday at 09:00 America/New_York'
        value = self.parse(text)
        self.assertEqual(value.expression, text)
        self.assertEqual(due_arguments(value), {'string': 'every Monday at 09:00', 'lang': 'en', 'timezone': 'America/New_York'})
        for code in ['CET', 'CEST', 'CST', 'EST']:
            for base in ['every Monday at 09:00', '2026-11-12 09:00', '2026-11-12']:
                wording = base + ' ' + code
                with self.subTest(wording=wording):
                    value = self.parse(wording)
                    self.assertEqual((value.kind, value.expression, value.zone), ('unresolved', wording, None))
                    self.assertEqual(due_arguments(value), {'string': wording, 'lang': 'en'})

    def test_recurrence_dst_and_occurrence_move(self):
        # Due dates tag: UTC occurrence plus named zone is the recurring schedule,
        # not a stored first-firing offset. These two occurrences are independent.
        raw = dict(date='2026-10-26T13:00:00Z', timezone='America/New_York',
                   string='cada lunes a las 9', lang='es', is_recurring=True)
        previous = d.resolve_remote_due(raw, 'Europe/Prague')
        next_value = d.resolve_remote_due({**raw, 'date': '2026-11-02T14:00:00Z'}, 'Europe/Prague')
        for value in [previous, next_value]:
            self.assertEqual(value.instant.astimezone(d.account_timezone(value.zone)).hour, 9)
            self.assertEqual(due_arguments(value)['timezone'], 'America/New_York')
        moved = d.retain_recurrence(self.parse('2026-11-12 09:00 Europe/Prague'), previous, 'Europe/Prague')
        self.assertEqual(due_arguments(moved, previous), {**raw, 'date': '2026-11-12T08:00:00Z'})
        self.assertFalse(d.same_attention(moved, replace(moved, zone='Europe/Prague'), 'Europe/Prague'))
        self.assertFalse(d.same_attention(moved, replace(moved, rule='every day'), 'Europe/Prague'))
        self.assertTrue(d.same_attention(moved, replace(moved), 'Europe/Prague'))
        from todo_lib.workflows.scheduling import equivalent
        reminder = d.Reminder('one', 'task', type='absolute', due=moved)
        self.assertFalse(equivalent(reminder, replace(reminder, id='two',
            due=replace(moved, zone='Europe/Prague')), 'Europe/Prague'))
        self.assertTrue(equivalent(reminder, replace(reminder, id='two'), 'Europe/Prague'))
        full_day = d.retain_recurrence(self.parse('tomorrow Europe/Prague'), previous)
        self.assertIsNone(full_day.zone)
        self.assertIsNone(due_arguments(full_day, previous).get('timezone'))
        new = self.parse('every Friday at 10 Asia/Tokyo')
        self.assertEqual(due_arguments(new, previous), {'string': 'every Friday at 10', 'timezone': 'Asia/Tokyo', 'lang': 'en'})

    def test_floating_move_keeps_instant_then_floating_rule(self):
        old = d.resolve_remote_due(dict(date='2026-10-26T09:00:00', timezone=None,
            string='chaque lundi', lang='fr', is_recurring=True), 'Europe/Prague')
        moved = d.retain_recurrence(self.parse('2026-11-12 09:00 America/New_York'), old, 'Europe/Prague')
        self.assertEqual((moved.kind, moved.zone, moved.language), ('floating', None, 'fr'))
        self.assertEqual(due_arguments(moved, old)['date'], '2026-11-12T15:00:00')
        self.assertEqual(moved.instant.isoformat(), '2026-11-12T14:00:00+00:00')

    def test_unpredicted_named_metadata_and_date_normalization(self):
        wanted = self.parse('every Monday at 9 America/New_York')
        raw = dict(date='2026-11-02T14:00:00Z', timezone='America/New_York', string='every Monday at 9', lang='en', is_recurring=True)
        for zone, matches in [('America/New_York', True), ('Europe/Prague', False), (None, False)]:
            actual = d.resolve_remote_due({**raw, 'timezone': zone}, 'Europe/Prague')
            self.assertEqual(d.reconciles_attention(wanted, actual, 'Europe/Prague'), matches)
        full_day = d.resolve_remote_due({**raw, 'date': '2026-11-02', 'timezone': None}, 'Europe/Prague')
        self.assertTrue(d.reconciles_attention(wanted, full_day, 'Europe/Prague'))

    def test_authoritative_codec_roundtrip(self):
        current = observed(self)
        old = current.snapshot.reminders['fixed']
        raw = {**old.due.raw_due, 'timezone': 'America/New_York'}
        value = replace(old, due=d.resolve_reminder_due(raw, 'UTC'))
        snapshot = replace(current.snapshot, reminders={**current.snapshot.reminders, old.id: value})
        restored = snapshot_from(loads(dumps(snapshot_data(snapshot))), snapshot.account.timezone)
        self.assertEqual(restored.reminders[old.id], value)
