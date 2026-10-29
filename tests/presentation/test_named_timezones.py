"""Scoped revision-15 output over independently resolved schedules."""
import re
import unittest
from dataclasses import replace
from todo_lib import domain as d, presentation as p
from todo_lib.presentation.formatting import reminders_text, time_block
from tests.support.reminders import observed

NOW = d.instant_datetime(d.instant_from_wire('2026-11-12T13:00:00Z'))
NY = '2026-11-12 15:00:00 Europe/Prague (2026-11-12 09:00:00 America/New_York)'
TOKYO = '2026-11-12 00:30:00 Europe/Prague (2026-11-12 08:30:00 Asia/Tokyo)'


class NamedTimezoneOutput(unittest.TestCase):
    def setUp(self):
        self.snapshot = observed(self).snapshot
        self.due = d.resolve_remote_due(dict(date='2026-11-12T14:00:00Z', timezone='America/New_York',
            string='every Thursday at 9', lang='en', is_recurring=True), 'Europe/Prague')
        self.reminder = d.Reminder('tokyo', 'timed', type='absolute', due=d.resolve_reminder_due(
            dict(date='2026-11-11T23:30:00Z', timezone='Asia/Tokyo', string='every day at 8:30',
                 lang='en', is_recurring=True), 'Europe/Prague'))

    def test_detail_placement_independent_zones_color_and_descendants(self):
        owner = replace(self.snapshot.items['timed'], attention=self.due, title='Safe\nTitle')
        child = replace(owner, id='child', parent_id=owner.id, title='Child')
        snapshot = replace(self.snapshot, items={owner.id: owner, child.id: child},
                           reminders={'tokyo': self.reminder})
        plain = p.render_detail(snapshot, owner, NOW)
        self.assertIn('Due: ' + NY + ' · 1h left ↻ every Thursday at 9 reminders:at ' + TOKYO +
                      ' ↻ every day at 8:30', plain.stdout)
        self.assertIn(r'Safe\nTitle', plain.stdout)
        steps = plain.stdout.split('Steps\n')[1]
        self.assertNotIn('America/New_York', steps)
        self.assertIn('due:2026-11-12 15:00:00 Europe/Prague ·', steps)
        colored = p.render_detail(snapshot, owner, NOW, color=p.Color(True))
        self.assertEqual(re.sub(r'\x1b\[[0-9;]*m', '', colored.stdout), plain.stdout)
        self.assertEqual(colored.stderr, plain.stderr)
        self.assertNotIn('America/New_York', p.render_search(snapshot, [owner], NOW).stdout)
        self.assertNotIn('Asia/Tokyo', p.render_now(snapshot, NOW, items=[owner]).stdout)
        for doc in (p.render_someday(snapshot, NOW, items=[owner]),
                    p.render_ambiguity(snapshot, 'Safe', [owner], NOW),
                    p.render_waiting(snapshot, NOW, items=[owner])):
            self.assertNotIn('America/New_York', doc.stdout)
            self.assertNotIn('Asia/Tokyo', doc.stdout)

    def test_cross_date_defaults_same_zone_floating_and_date_only(self):
        cross = d.parse_attention('2026-11-12 00:30 Asia/Tokyo', d.instant_datetime(NOW), 'Europe/Prague')
        self.assertEqual(p.actual_due(cross, 'Europe/Prague', schedule_zone=True),
            '2026-11-11 16:30:00 Europe/Prague (2026-11-12 00:30:00 Asia/Tokyo)')
        for raw, expected in [
            (dict(date='2026-11-12T14:00:00Z', timezone='Europe/Prague'), '2026-11-12 15:00:00 Europe/Prague'),
            (dict(date='2026-11-12T14:00:00Z', timezone=None), '2026-11-12 15:00:00 Europe/Prague'),
            (dict(date='2026-11-12T14:00:00', timezone=None), '2026-11-12 14:00:00 Europe/Prague'),
            (dict(date='2026-11-12', timezone=None), '2026-11-12')]:
            with self.subTest(raw=raw):
                due = d.resolve_remote_due(dict(raw, string='value', lang='en', is_recurring=False), 'Europe/Prague')
                self.assertEqual(p.actual_due(due, 'Europe/Prague', schedule_zone=True), expected)
        self.assertEqual(p.actual_due(self.due, 'Europe/Prague'), '2026-11-12 15:00:00 Europe/Prague')
        self.assertNotIn('Asia/Tokyo', reminders_text([self.reminder], 'Europe/Prague'))
        self.assertNotIn('Asia/Tokyo', time_block(self.due, [self.reminder], NOW, 'Europe/Prague'))

    def test_creation_and_removal_preview_have_distinct_scope(self):
        owner = self.snapshot.items['timed']
        self.assertIn('  Due: ' + NY, p.render_mutation(self.snapshot, owner, 'Created', attention=self.due).stdout)
        unresolved = replace(self.reminder, due=d.parse_attention('every Monday at 9 Asia/Tokyo',
                              d.instant_datetime(NOW), 'Europe/Prague'))
        preview = p.render_reminder_replacement(self.snapshot, owner, [self.reminder], [unresolved]).stdout
        self.assertIn('expression (Todoist): every Monday at 9 Asia/Tokyo', preview)
        self.assertNotIn('(' + '2026', preview)
