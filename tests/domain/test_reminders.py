from dataclasses import replace
import unittest
from todo_lib import domain as d
from tests.support.reminders import observed, MINIMAL, FLOATING


class ReminderTests(unittest.TestCase):
    def test_legacy_constructor_and_independent_absolute(self):
        s = observed(self).snapshot
        self.assertEqual(d.Reminder('old', 'timed', 0).type, 'relative')
        self.assertIsNone(s.items['undated'].attention)
        self.assertEqual(d.urgency(s.items['undated'], d.instant_datetime(d.instant_from_wire('2026-10-30T12:00:00Z')), s.account.timezone), d.Urgency.NO_DATE)
        self.assertEqual(s.reminders['abs'].due.kind, 'fixed')
        self.assertEqual(s.reminders['abs'].due.instant.hour, 8)
        self.assertEqual(s.reminders['floating'].due.kind, 'floating')
        d.validate(s)
        d.validate(replace(s, items={**s.items, 'undated': replace(s.items['undated'], attention=d.resolve_remote_due({'date': '2026-10-30'}, s.account.timezone))}))
        for changes in ({'minutes': False}, {'minutes': -1}, {'item_id': 'unknown'},
                        {'item_id': None}, {'item_id': {'private': 'never dump'}}):
            with self.subTest(changes=changes), self.assertRaises(d.DomainError):
                d.validate(replace(s, reminders={'rel': replace(s.reminders['rel'], **changes)}))
        with self.assertRaises(d.DomainError):
            d.validate(replace(s, items={**s.items, 'timed': replace(s.items['timed'], attention=None)}))

    def test_reminder_specific_due_keeps_task_validation(self):
        a = d.resolve_reminder_due({**MINIMAL, 'is_recurring': True}, 'UTC')
        self.assertTrue(a.recurring)
        self.assertIsNone(a.rule)
        with self.assertRaises(d.DomainError):
            d.resolve_remote_due(MINIMAL, 'UTC')
        for raw in ({'date': '2026-10-30'}, {**FLOATING, 'is_recurring': None},
                    {**MINIMAL, 'lang': None}, {**MINIMAL, 'timezone': 'bad'}):
            with self.subTest(raw=raw), self.assertRaises(d.DomainError):
                d.resolve_reminder_due(raw, 'UTC')

    def test_duplicate_offsets_identify_both_reminders_and_owner(self):
        s = observed(self).snapshot
        first = s.reminders['rel']
        s = replace(s, reminders={'rel': first, 'other': replace(first, id='other')})
        with self.assertRaises(d.DomainError) as caught:
            d.validate(s)
        message = str(caught.exception)
        for value in ('duplicate reminder offsets', 'reminder rel', 'reminder other',
                      'title timed', 'category cat', 'type relative', 'offset 0'):
            self.assertIn(value, message)

    def test_managed_capability_eligibility_and_identity_failures_have_context(self):
        s = observed(self).snapshot
        cases = [replace(s, account=replace(s.account, capabilities=d.Capabilities())),
                 replace(s, items={**s.items, 'timed': replace(s.items['timed'], attention=None)}),
                 replace(s, reminders={'rel': replace(s.reminders['rel'], id='wrong')})]
        for candidate, reason in zip(cases, ('capability', 'exact attention', 'key/ID mismatch')):
            with self.subTest(reason=reason), self.assertRaises(d.DomainError) as caught:
                d.validate(candidate)
            message = str(caught.exception)
            for value in (reason, 'owner timed', 'title timed', 'category cat', 'type relative', 'offset 0'):
                self.assertIn(value, message)
