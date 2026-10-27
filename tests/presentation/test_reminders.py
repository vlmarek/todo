import unittest
from todo_lib import domain as d
from todo_lib.presentation.formatting import reminders_text, time_block, Color
from todo_lib.presentation import render
from tests.support.reminders import observed


class ReminderRenderingTests(unittest.TestCase):
    def test_shared_order_original_rule_and_reminder_only_blue(self):
        s = observed(self).snapshot
        text = reminders_text(list(s.reminders.values()), s.account.timezone)
        self.assertTrue(text.startswith('at due, at 2025-02-12 09:00:00 Europe/Prague'))
        self.assertIn(' ↻ cada día a las 9', text)
        reminders = [s.reminders['abs']]
        now = d.instant_from_wire('2026-10-30T12:00:00Z')
        block = time_block(None, reminders, now, s.account.timezone, detail=True)
        self.assertEqual(block, 'none reminders:at 2025-02-12 09:00:00 Europe/Prague')
        doc = render.render_now(s, d.instant_datetime(now))
        self.assertIn('undated  reminders:', doc.stdout)
        self.assertNotIn('undated  due:', doc.stdout)

    def test_reminder_only_color_and_ties(self):
        from dataclasses import replace
        s = observed(self).snapshot
        r = s.reminders['abs']
        from tests.support.reminders import MINIMAL
        a = replace(r, id='a', due=d.resolve_reminder_due({**MINIMAL, 'is_recurring': True, 'string': 'rule A'}, s.account.timezone))
        b = replace(r, id='b', due=d.resolve_reminder_due({**MINIMAL, 'is_recurring': True, 'string': 'rule B'}, s.account.timezone))
        self.assertEqual(reminders_text([b, a], s.account.timezone),
            'at 2025-02-12 09:00:00 Europe/Prague ↻ rule A, at 2025-02-12 09:00:00 Europe/Prague ↻ rule B')
        text = time_block(None, [r], d.instant_from_wire('2026-10-30T12:00:00Z'),
                          s.account.timezone, Color(True), detail=True)
        self.assertEqual(text, Color(True).paint('none reminders:at 2025-02-12 09:00:00 Europe/Prague', 'blue'))
