import unittest
from todo_lib import domain as d
from todo_lib.adapter.current import retrieve
from tests.support.reminders import observed, boundary, response, absolute, MINIMAL, FLOATING
from tests.adapter.current.test_current import delta


class ReminderMappingTests(unittest.TestCase):
    def test_minimal_omitted_null_unused_and_timezone_reresolution(self):
        raw = response()
        raw['reminders'][1]['minute_offset'] = None
        first = observed(self, raw)
        zone = 'America/New_York'
        second = retrieve(boundary(self, [('delta-token', delta(user={'id': 'u', 'tz_info': {'timezone': zone}}))]),
                          first.binding, prior=first.snapshot, sync_token=first.sync_token)
        self.assertEqual(second.snapshot.reminders['abs'].due.instant, first.snapshot.reminders['abs'].due.instant)
        self.assertNotEqual(second.snapshot.reminders['floating'].due.instant, first.snapshot.reminders['floating'].due.instant)
        self.assertEqual(second.snapshot.reminders['floating'].due.raw_due, FLOATING)
        self.assertEqual(second.snapshot.reminders['rel'].raw_due, {'unused': 'never interpreted'})
        self.assertIsNone(second.snapshot.items['undated'].attention)

    def test_consumed_invalid_and_type_aware_duplicates(self):
        for changes in ({'due': None}, {'due': {'date': '2026-10-30'}}, {'type': 'location'},
                        {'is_urgent': None}, {'notify_uid': ''}, {'due': {**MINIMAL, 'lang': 2}}):
            raw = response()
            raw['reminders'] = [absolute(**changes)]
            with self.subTest(changes=changes), self.assertRaises(d.DomainError):
                observed(self, raw)
        raw = response()
        raw['reminders'] += [absolute(minute_offset='unused')]
        observed(self, raw)
        raw['reminders'][-1]['due']['date'] = '2025-02-12T10:00:00'
        from tests.adapter.current.test_current import BINDING
        with self.assertRaisesRegex(d.DomainError, 'contradictory'):
            retrieve(boundary(self, [('*', raw)]), BINDING)
        raw = response()
        raw['reminders'] = [absolute(item_id='private', type='location', due=None)]
        raw['items'].append({'id': 'private', 'project_id': 'elsewhere'})
        self.assertFalse(observed(self, raw).snapshot.reminders)

    def test_absolute_duplicate_optional_defaults_preserve_actual_raw_due(self):
        # NotificationSyncView's open due object allows the minimal shape;
        # shared remote-time semantics default timezone to null and recurrence false.
        minimal = {'date': '2026-10-30T09:00:00', 'lang': 'en'}
        encodings = [minimal, {**minimal, 'timezone': None},
                     {**minimal, 'is_recurring': False},
                     {**minimal, 'timezone': None, 'is_recurring': False}]
        for left, right in ((a, b) for a in encodings for b in encodings):
            raw = response()
            raw['reminders'] = [absolute(schedule=left), absolute(schedule=right)]
            mapped = observed(self, raw).snapshot.reminders['abs']
            self.assertEqual(mapped.due.raw_due, right)
            self.assertEqual(mapped.due.kind, 'floating')
            self.assertFalse(mapped.due.recurring)

    def test_absolute_duplicate_defaults_keep_consumed_conflicts_strict(self):
        from tests.adapter.current.test_current import BINDING
        minimal = {'date': '2026-10-30T09:00:00', 'lang': 'en'}
        for changes in ({'timezone': 'Europe/Madrid'}, {'is_recurring': True},
                        {'is_recurring': None}, {'is_recurring': 0},
                        {'lang': None}, {'string': None}, {'date': '2026-10-30T09:00:01'}):
            raw = response()
            raw['reminders'] = [absolute(schedule=minimal),
                                absolute(schedule={**minimal, **changes})]
            with self.subTest(changes=changes), self.assertRaises(d.DomainError):
                retrieve(boundary(self, [('*', raw)]), BINDING)
