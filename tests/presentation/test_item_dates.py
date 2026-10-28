"""Revision-14 row fragments, using the existing calendar and timing model."""
from dataclasses import replace
import re
import unittest
from io import StringIO
from todo_lib import presentation as p, domain as d
from todo_lib.workflows.reads import choose, AmbiguityError
from tests.presentation.test_render import snap, day, instant, NOW


class ItemDateTests(unittest.TestCase):
    def setUp(self):
        self.root = d.Item('r', 'w', 'Parent', attention=day('2026-10-20'))
        self.child = d.Item('s', 'w', 'Child', 'r', attention=day('2026-10-21'))
        self.undated = d.Item('u', 'w', 'Undated', 's')
        self.done = d.Item('d', 'w', 'Done', 'r', added_at=instant('2026-01-01T00:00:00Z'),
            attention=day('2026-10-25'), completed=True, completed_at=instant('2026-10-18T17:30:00Z'))
        self.state = snap([self.root, self.child, self.undated, self.done])

    def test_recursive_own_dates_completion_and_missing_time_fallback(self):
        text = p.render_detail(self.state, self.root, NOW).stdout
        self.assertIn('- [ ] P2 Child — due:2026-10-21 · in 2d\n', text)
        self.assertIn('  - [ ] P2 Undated\n', text)
        self.assertIn('- [x] P2 Done — completed 2026-10-18 19:30\n', text)
        self.assertNotIn('2026-01-01', text)
        # Deliberately bypass validation only at the pure renderer boundary.
        missing = replace(self.done, completed_at=None)
        state = replace(self.state, items={**self.state.items, 'd': missing})
        self.assertIn('- [x] P2 Done\n', p.render_detail(state, self.root, NOW).stdout)
        self.assertIn('step: Done — Parent — Work', p.render_ambiguity(state, 'Done', [missing], NOW).stdout)
        self.assertIn('    [x] P2 Done', p.render_search(state, [missing, self.undated], NOW).stdout.splitlines())
        with self.assertRaises(d.DomainError):
            d.validate(state)

    def test_shared_lists_context_color_and_date_only_no_midnight(self):
        search = p.render_search(self.state, [self.undated, self.done], NOW, all_items=True)
        someday = p.render_someday(self.state, NOW, items=self.state.items.values())
        self.assertEqual(search.stdout, someday.stdout)
        self.assertIn('  [ ] P2 Parent — due:2026-10-20 · in 1d', search.stdout)
        self.assertIn('      [ ] P2 Undated', search.stdout)
        self.assertIn('    [x] P2 Done — completed 2026-10-18 19:30', search.stdout)
        self.assertNotIn('00:00', search.stdout)
        for render in (lambda color: p.render_search(self.state, [self.undated, self.done], NOW, color=color),
                       lambda color: p.render_someday(self.state, NOW, items=self.state.items.values(), color=color),
                       lambda color: p.render_detail(self.state, self.root, NOW, color=color)):
            plain, colored = render(p.Color()).stdout, render(p.Color(True)).stdout
            self.assertEqual(re.sub(r'\x1b\[[0-9;]*m', '', colored), plain)
            self.assertIn('\x1b[38;2;38;139;210mdue:2026-10-21 · in 2d\x1b[0m', colored)
            self.assertIn('completed 2026-10-18 19:30', colored)

    def test_timed_recurring_active_and_selected_occurrence_authority(self):
        active = replace(self.child, attention=d.parse_attention('2026-10-19T08:00:00Z', NOW, 'Europe/Prague'))
        active = replace(active, attention=replace(active.attention, recurring=True, rule='cada día'))
        state = replace(self.state, items={**self.state.items, 's': active})
        text = p.render_ambiguity(state, 'Child', [active], NOW).stdout
        self.assertIn('due:2026-10-19 10:00:00 Europe/Prague · 2h left ↻ cada día — Parent — Work', text)
        occurrence = d.LifecycleCandidate('s', self.done.completed_at, 'occurrence')
        streams = p.OriginalStreams(StringIO(), StringIO(), StringIO())
        with self.assertRaises(AmbiguityError) as caught:
            choose(state, 'Child', [occurrence, self.root], NOW, streams=streams)
        text = caught.exception.document.stdout
        self.assertIn('step: Child  completed 2026-10-18 19:30 — Parent — Work', text)
        self.assertEqual(text.count('completed '), 1)
        self.assertNotIn('cada día', text)
        class Terminal(StringIO):
            def isatty(self):
                return True
        selected = choose(state, 'Child', [occurrence, self.root], NOW,
            streams=p.OriginalStreams(Terminal('1\n'), Terminal(), StringIO()))
        self.assertIs(selected, occurrence)

    def test_undated_absolute_reminder_only_candidate_and_no_list_summary(self):
        reminder = d.Reminder('absolute', 'u', type='absolute', due=d.parse_attention('2026-10-20T08:00:00Z', NOW, 'Europe/Prague'))
        state = replace(self.state, reminders={'absolute': reminder})
        text = p.render_ambiguity(state, 'Undated', [self.undated], NOW).stdout
        self.assertIn('step: Undated  reminders:at 2026-10-20 10:00:00 Europe/Prague — Parent > Child — Work', text)
        self.assertNotIn('due:none', text)
        self.assertNotIn('reminders:', p.render_search(state, [self.undated], NOW).stdout)
        text = p.render_ambiguity(self.state, 'Undated', [self.undated], NOW).stdout
        self.assertIn('step: Undated — Parent > Child — Work', text)
