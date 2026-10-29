"""Exact preview and authoritative receipt fragments using pinned wire fixtures."""
import unittest
from dataclasses import replace
from todo_lib import domain as d, presentation as p
from todo_lib.workflows.capture import reminder_values
from tests.support.reminders import observed


class ReminderReceiptTests(unittest.TestCase):
    def test_exact_preview_unknown_safe_expression_and_keep_hint(self):
        snapshot = observed(self).snapshot
        owner = replace(snapshot.items['timed'], title='Team meeting\nline')
        relative = replace(snapshot.reminders['rel'], minutes=30)
        absolute = snapshot.reminders['abs']
        addition = d.Reminder('requested', owner.id, type='absolute',
                             due=replace(d.parse_attention('every Monday at 9am',
                                 d.instant_datetime(d.instant_from_wire('2026-10-22T12:00:00Z')), snapshot.account.timezone), expression='every Monday at 9am\nnext'))
        text = p.render_reminder_replacement(snapshot, owner, [relative, absolute], [addition]).stdout
        self.assertEqual(text, 'Reminder replacement for: Team meeting\\nline\nRemove:\n'
            '  - 30m before\n  - at 2025-02-12 09:00:00 Europe/Prague\nAdd:\n'
            '  - expression (Todoist): every Monday at 9am\\nnext\n'
            'To keep existing reminders, include:\n  --reminder 30m\n  --reminder-at keep')

    def test_complete_scalar_set_relative_zero_and_absolute(self):
        snapshot = observed(self).snapshot
        reminder = replace(snapshot.reminders['abs'], item_id='timed')
        snapshot = replace(snapshot, reminders={'rel': snapshot.reminders['rel'], 'abs': reminder})
        values = reminder_values(snapshot, 'timed')
        self.assertEqual(values, '0m, at 2025-02-12 09:00:00 Europe/Prague (2025-02-12 09:00:00 Europe/Madrid)')
        doc = p.render_mutation(snapshot, snapshot.items['timed'], changes=[('Reminders', None, values)])
        self.assertIn('  Reminders: none -> 0m, at 2025-02-12 09:00:00 Europe/Prague', doc.stdout)

    def test_empty_add_and_no_duplicate_absolute_hint(self):
        snapshot = observed(self).snapshot
        doc = p.render_reminder_replacement(snapshot, snapshot.items['undated'],
            [snapshot.reminders['floating'], snapshot.reminders['fixed']], [])
        self.assertIn('Add:\n  None.\n', doc.stdout)
        self.assertEqual(doc.stdout.count('--reminder-at keep'), 1)
        self.assertIn('↻ cada día a las 9', doc.stdout)
