"""Contract-authored goldens, not renderer snapshots."""
from dataclasses import replace
from datetime import datetime, timezone, date, timedelta
import io
import re
import unittest
from todo_lib.domain import (Account, Binding, Project, Snapshot, Item, Comment,
                             Reminder, Attention, instant_from_wire, ordered_siblings,
                             parse_attention)
from todo_lib.presentation import *

UTC = timezone.utc
NOW = datetime(2026, 10, 19, 6, tzinfo=UTC)


def instant(text):
    return instant_from_wire(text)


def day(text, **kwargs):
    return Attention('date', date_value=date.fromisoformat(text), **kwargs)


def snap(items=(), comments=(), reminders=(), zone='Europe/Prague'):
    return Snapshot(Binding('a', 'root', frozenset(('w', 's'))), Account('a', zone),
                    Project('root', 'Todo'), {'w': Project('w', 'Work', 'root'), 's': Project('s', 'Someday', 'root')},
                    {i.id: i for i in items}, {c.id: c for c in comments}, {r.id: r for r in reminders})


def waiting(body):
    return '[todo waiting]\n' + body + '\n[/todo waiting]'


class NowTests(unittest.TestCase):
    def test_exact_independent_queue_all_sections_and_counts(self):
        root = Item('root', 'w', 'Prepare for audit', priority=4)
        rows = [root,
                Item('s', 'w', 'Collect audit evidence', 'root', priority=1, attention=parse_attention('2026-10-21T13:00:00Z', NOW, 'Europe/Prague')),
                Item('late', 'w', 'Review budget', attention=day('2026-11-11', recurring=True, rule='every 2nd monday')),
                Item('over', 'w', 'Pay invoice', priority=4, attention=day('2026-10-16')),
                Item('today', 'w', 'Submit client proposal', priority=1, attention=parse_attention('2026-10-19T08:00:00Z', NOW, 'Europe/Prague'))]
        reminders = [Reminder('r1', 'today', 60), Reminder('r0', 'today', 0)]
        expected = '''NOW · Mon 19 Oct 2026 · 08:00 Europe/Prague
5 actions · 1 overdue · 1 today

OVERDUE (1)
  P4 Pay invoice  due:3d overdue

TODAY (1)
  P1 Submit client proposal  due:2h left reminders:at due, 1h before

NEXT 7 DAYS (1)
  P1 Collect audit evidence  due:2d 7h left — Prepare for audit

NO DATE (1)
  P4 Prepare for audit

LATER (1)
  P2 Review budget  due:in 23d ↻ every 2nd monday'''
        self.assertEqual(render_now(snap(rows, reminders=reminders), NOW).stdout, expected)

    def test_deep_paths_and_waiting_multiline_counts(self):
        rows = [Item('r', 'w', 'Launch'), Item('s', 'w', 'Prepare slides', 'r'),
                Item('g', 'w', 'Collect figures', 's'),
                Item('h', 'w', 'Check sources', 'g', description=waiting('Reason: first\n\nlast\nSince: 2026-07-13'), labels=frozenset(('waiting',)), attention=day('2026-10-23'))]
        result = render_now(snap(rows), NOW, all_items=True).stdout
        self.assertIn('4 actions · 0 overdue · 0 today', result)
        self.assertIn('  P2 Check sources  due:in 4d (first\n    \n    last) — Launch > Prepare slides > Collect figures', result)
        self.assertIn('  P2 Collect figures — Launch > Prepare slides', result)
        self.assertNotIn('Since:', result)

    def test_visibility_filters_and_empty_category(self):
        rows = [Item('r', 'w', 'Parent', attention=day('2026-10-23'), labels=frozenset(('waiting',))),
                Item('s', 'w', 'Child', 'r'), Item('x', 's', 'Hidden'),
                Item('c', 'w', 'Done', completed=True, completed_at=NOW)]
        state = snap(rows)
        self.assertEqual(render_now(state, NOW, hidden_names=('Someday',)).stdout, 'No actionable items.')
        self.assertIn('3 actions', render_now(state, NOW, all_items=True).stdout)
        self.assertEqual(render_now(state, NOW, category_id='s', hidden_names=('Someday',)).stdout, 'No actionable items.')
        # Existing cached state is classified anew at its hide-until day.
        self.assertIn('3 actions', render_now(state, NOW + timedelta(days=4)).stdout)

    def test_all_boundaries_and_priority_date_title_id_order(self):
        rows = [Item('z', 'w', 'same', attention=day('2026-10-26')),
                Item('a', 'w', 'same', attention=day('2026-10-26')),
                Item('n', 'w', 'later', attention=day('2026-10-27')),
                Item('p', 'w', 'past', attention=day('2026-10-18')),
                Item('t', 'w', 'today', attention=day('2026-10-19')),
                Item('q', 'w', 'priority', priority=1, attention=day('2026-10-26'))]
        text = render_now(snap(rows), NOW).stdout
        self.assertIn('NEXT 7 DAYS (3)\n  P1 priority', text)
        self.assertIn('LATER (1)\n  P2 later  due:in 8d', text)
        self.assertIn('OVERDUE (1)\n  P2 past  due:1d overdue', text)
        self.assertIn('TODAY (1)\n  P2 today  due:today', text)

    def test_color_bytes_equivalent_and_slots(self):
        rows = [Item('r', 'w', 'Parent', priority=1), Item('s', 'w', 'Child', 'r', priority=1, attention=day('2026-10-18'))]
        state = snap(rows)
        colored = render_now(state, NOW, color=Color(True)).stdout
        self.assertEqual(re.sub(r'\x1b\[[0-9;]*m', '', colored), render_now(state, NOW).stdout)
        self.assertIn('\x1b[1mP1\x1b[0m', colored)
        self.assertIn('\x1b[38;2;220;50;47mdue:1d overdue\x1b[0m', colored)


class TimingTests(unittest.TestCase):
    def test_before_at_after_subminute_and_full_precision(self):
        for wire, expected in [('2026-10-19T06:00:00.000000001Z', '<1m left'),
                               ('2026-10-19T06:00:00Z', 'now'),
                               ('2026-10-19T05:59:59.999999999Z', '<1m overdue')]:
            value = parse_attention(wire, NOW, 'Europe/Prague')
            self.assertEqual(timing(value, (), NOW, 'Europe/Prague')[0], expected)
            text = render_now(snap([Item('x', 'w', 'X', attention=value)]), NOW).stdout
            self.assertIn('OVERDUE (1)' if 'overdue' in expected else 'TODAY (1)', text)

    def test_truncation_units(self):
        for delta, expected in [(59, '<1m'), (60, '1m'), (1201, '20m'), (10800, '3h'),
                                (12059, '3h 20m'), (86400, '1d'), (172800, '2d'), (198059, '2d 7h')]:
            value = parse_attention((NOW + timedelta(seconds=delta)).isoformat(), NOW, 'Europe/Prague')
            self.assertEqual(timing(value, (), NOW, 'Europe/Prague')[0], expected + ' left')

    def test_all_reminders_rule_and_fallback(self):
        value = parse_attention('2026-10-19T09:00:00Z', NOW, 'Europe/Prague')
        value = replace(value, recurring=True, rule='kazde utery 15:00')
        self.assertEqual(timing(value, [10080, 1440, 90, 60, 0], NOW, 'Europe/Prague')[0],
                         '3h left ↻ kazde utery 15:00 reminders:at due, 1h before, 90m before, 1d before, 1w before')
        self.assertEqual(timing(replace(value, rule=None), [], NOW, 'Europe/Prague')[0], '3h left ↻ recurring')

    def test_dst_elapsed_and_calendar_membership(self):
        now = datetime(2026, 10, 24, 10, tzinfo=UTC)  # noon before fall-back
        due = parse_attention('2026-10-25T12:00:00+01:00', now, 'Europe/Prague')
        self.assertEqual(timing(due, [], now, 'Europe/Prague')[0], '1d 1h left')
        self.assertEqual(timing(day('2026-10-25'), [], now, 'Europe/Prague')[0], 'in 1d')
        midnight = datetime(2026, 10, 24, 22, tzinfo=UTC)
        self.assertEqual(timing(day('2026-10-25'), [], midnight, 'Europe/Prague')[0], 'today')

    def test_one_account_zone_absolute_compact_none(self):
        value = instant('2026-08-14T14:30:42.999999999Z')
        self.assertEqual(absolute(value, 'Europe/Prague'), 'Fri 14 Aug 2026, 16:30:42')
        self.assertEqual(compact(value, 'Europe/Prague'), '2026-08-14 16:30')
        self.assertEqual(absolute(None, 'Europe/Prague'), 'none')
        self.assertEqual(compact(None, 'Europe/Prague'), 'none')


class DetailTests(unittest.TestCase):
    def test_exact_recursive_comments_and_owner_separation(self):
        rows = [Item('r', 'w', 'Launch', priority=4, description='\n  first\n\nlast\n'),
                Item('s', 'w', 'Collect figures', 'r', added_at=instant('2026-10-24T08:00:00Z')),
                Item('g', 'w', 'Check sources', 's', added_at=instant('2026-10-24T08:15:00Z'), completed=True, completed_at=NOW)]
        comments = [Comment('r', 'r', '\nowner\n\nsecond\n', NOW),
                    Comment('s', 's', 'Use the current figures', instant('2026-10-24T08:30:00Z')),
                    Comment('g', 'g', 'Verified', instant('2026-10-24T08:45:00Z'))]
        expected = '''P4  Work  Launch
Due: none

Waiting: none

Description
    first
\x20\x20
  last

Steps
- [ ] P2 Collect figures
  Comments
  - 2026-10-24 10:30  Use the current figures
  - [x] P2 Check sources — completed 2026-10-19 08:00
    Comments
    - 2026-10-24 10:45  Verified

Comments
- 2026-10-19 08:00  owner
\x20\x20
  second'''
        result = render_detail(snap(rows, comments), 'r', NOW)
        self.assertEqual(result.stdout, expected)
        self.assertEqual(result.stderr, 'todo: completed steps use retained history; coverage may be incomplete')

    def test_submicrosecond_newest_siblings_oldest_comments_and_ties_nulls(self):
        early = instant('2026-08-14T10:00:00.123456001Z')
        late = instant('2026-08-14T10:00:00.123456009Z')
        rows = [Item('r', 'w', 'Root'), Item('a', 'w', 'Earlier', 'r', added_at=early),
                Item('z', 'w', 'Later', 'r', added_at=late),
                Item('b', 'w', 'Tie B', 'r', added_at=early), Item('u', 'w', 'Unknown', 'r')]
        comments = [Comment('z', 'r', 'Earlier comment', early), Comment('a', 'r', 'Later comment', late),
                    Comment('zz', 'r', 'Tie comment', early), Comment('u', 'r', 'Undated')]
        state = snap(rows, comments)
        self.assertEqual([i.id for i in ordered_siblings(state, 'w', 'r')], ['z', 'a', 'b', 'u'])
        self.assertEqual(render_detail(state, 'r', NOW).stdout, '''P2  Work  Root
Due: none

Waiting: none

Steps
- [ ] P2 Later
- [ ] P2 Earlier
- [ ] P2 Tie B
- [ ] P2 Unknown

Comments
- 2026-08-14 12:00  Earlier comment
- 2026-08-14 12:00  Tie comment
- 2026-08-14 12:00  Later comment
- none  Undated''')
        self.assertEqual(render_comments(state, 'r').stdout, '''Comments for: Root
- 2026-08-14 12:00  Earlier comment
- 2026-08-14 12:00  Tie comment
- 2026-08-14 12:00  Later comment
- none  Undated''')

    def test_mixed_datetime_equal_instant_stable_id_and_unknown_ties(self):
        rows = [Item('r', 'w', 'Root'), Item('z', 'w', 'Z', 'r', added_at=NOW),
                Item('a', 'w', 'A', 'r', added_at=instant('2026-10-19T06:00:00.000000000Z')),
                Item('u2', 'w', 'Unknown 2', 'r'), Item('u1', 'w', 'Unknown 1', 'r')]
        self.assertEqual([i.id for i in ordered_siblings(snap(rows), 'w', 'r')], ['a', 'z', 'u1', 'u2'])
        state = snap(rows, [Comment('z', 'r', 'Z', NOW), Comment('a', 'r', 'A', instant('2026-10-19T06:00:00Z'))])
        self.assertEqual(render_comments(state, 'r').stdout, 'Comments for: Root\n- 2026-10-19 08:00  A\n- 2026-10-19 08:00  Z')

    def test_detail_due_actual_and_leaf_deep_header(self):
        rows = [Item('r', 'w', 'Launch'), Item('s', 'w', 'Prepare', 'r'),
                Item('g', 'w', 'Figures', 's', attention=parse_attention('2026-10-19T08:31:32Z', NOW, 'Europe/Prague'))]
        self.assertEqual(render_detail(snap(rows), 'g', NOW).stdout, '''P2  Work  Figures — Launch > Prepare
Due: 2026-10-19 10:31:32 Europe/Prague · 2h 31m left

Waiting: none

Steps: none

Comments: none''')
        self.assertEqual(render_comments(snap(rows), 'g').stdout, 'Comments for: Figures — Launch > Prepare\nComments: none')

    def test_inherited_policies_root_to_parent_and_reasonless(self):
        rows = [Item('r', 'w', 'Launch', labels=frozenset(('waiting',)), attention=day('2026-10-23')),
                Item('s', 'w', 'Prepare', 'r', labels=frozenset(('waiting',)), attention=day('2026-10-24'), description=waiting('Reason: approval\ncontinued\nSince: 2026-07-13')),
                Item('g', 'w', 'Figures', 's')]
        state = snap(rows)
        self.assertIn('Waiting\n- Inherited from Launch\n- Inherited from Launch > Prepare: approval\n  continued (98d)', render_detail(state, 'g', NOW).stdout)
        self.assertIn('Waiting: enabled', render_detail(state, 'r', NOW).stdout)
        state = snap([rows[0], replace(rows[1], labels=frozenset(), description=''), rows[2]])
        self.assertIn('Waiting: inherited from Launch', render_detail(state, 'g', NOW).stdout)

    def test_own_waiting_since_and_description_omits_metadata(self):
        now = NOW + timedelta(days=1)
        row = Item('r', 'w', 'toupper', description='ordinary\n\n' + waiting('Reason: Should I take it back?\nSince: 2026-07-13'), labels=frozenset(('waiting',)), attention=day('2026-10-19'))
        self.assertEqual(render_detail(snap([row]), row, now).stdout, '''P2  Work  toupper
Due: 2026-10-19 · 1d overdue

Waiting
- Should I take it back? (99d)

Description
  ordinary

Steps: none

Comments: none''')


class WaitingTests(unittest.TestCase):
    def test_since_interpretation_edge_cases(self):
        cases = [('Reason: approval\nSince: 2026-10-19', ('approval', 0)),
                 ('Reason: approval\nSince: 2026-10-20', ('approval\nSince: 2026-10-20', None)),
                 ('approval\nSince: 2026-02-30', ('approval\nSince: 2026-02-30', None)),
                 ('approval\nSince: 2026-10-18\nSince: 2026-10-18', ('approval\nSince: 2026-10-18\nSince: 2026-10-18', None)),
                 ('approval\nSince: 2026-10-18\nlast', ('approval\nSince: 2026-10-18\nlast', None)),
                 ('Reason: Since: 2026-10-18', ('Reason: Since: 2026-10-18', None)),
                 ('Reason: Reason: approval', ('Reason: approval', None)), ('ordinary', ('ordinary', None))]
        for body, expected in cases:
            with self.subTest(body=body):
                row = Item('r', 'w', 'R', attention=day('2026-10-23'), labels=frozenset({'waiting'}), description=waiting(body))
                self.assertEqual(waiting_reason(row, NOW, 'Europe/Prague'), expected)

    def test_exact_waiting_recursive_context_reasonless_and_multiline(self):
        rows = [Item('d', 'w', 'Deploy', priority=1, attention=day('2026-10-23'), labels=frozenset(('waiting',)), description=waiting('Reason: client approval\nSince: 2026-07-13')),
                Item('p', 'w', 'Plan', 'd', attention=day('2026-10-24'), labels=frozenset(('waiting',))),
                Item('r', 'w', 'Release notes', priority=3),
                Item('g', 'w', 'Get review', 'r', priority=4, attention=day('2026-10-25'), labels=frozenset(('waiting',)), description=waiting('reviewer\navailable Sunday'))]
        self.assertEqual(render_waiting(snap(rows), NOW).stdout, '''Work
  P1 Deploy  until:2026-10-23 (client approval)
    P2 Plan  until:2026-10-24
  P3 Release notes  [context]
    P4 Get review  until:2026-10-25 (reviewer
      available Sunday)''')
        self.assertEqual(render_waiting(snap(rows), NOW + timedelta(days=7)).stdout, 'No waiting items.')
        self.assertEqual(render_waiting(snap(rows), NOW, hidden_names=('Work',)).stdout, 'No waiting items.')


class OtherViewTests(unittest.TestCase):
    def test_someday_search_hierarchy_own_priority_and_context_only(self):
        rows = [Item('r', 's', 'Launch', priority=1), Item('s', 's', 'Prepare', 'r', priority=4),
                Item('g', 's', 'Figures', 's'), Item('x', 's', 'Unmatched', 'r')]
        state = snap(rows)
        self.assertEqual(render_search(state, [rows[2]], NOW).stdout, '''Someday
  [ ] P1 Launch
    [ ] P4 Prepare
      [ ] P2 Figures''')
        self.assertEqual(render_search(state, [rows[0]], NOW).stdout, 'Someday\n  [ ] P1 Launch')
        self.assertIn('    [ ] P2 Unmatched\n    [ ] P4 Prepare', render_someday(state, NOW, hidden_names=('Someday',)).stdout)
        self.assertEqual(render_someday(state, NOW).stdout, 'No someday items.')
        empty = render_search(state, [], NOW, all_items=True)
        self.assertEqual(empty.stdout, 'No matches in open or retained completed items.')
        self.assertEqual(empty.stderr, 'todo: completed search uses retained history; earliest retained completion: none; coverage may be incomplete')
        self.assertEqual(render_search(state, [], NOW).stdout, 'No matches.')

    def test_mixed_ambiguity_exact_and_noninteractive(self):
        rows = [Item('r', 'w', 'Weekly review'), Item('s', 'w', 'Prepare', 'r'),
                Item('g', 'w', 'Write report', 's', attention=day('2026-10-21')),
                Item('t', 'w', 'Report', attention=day('2026-10-19')),
                Item('c', 'w', 'Old report', completed=True, completed_at=instant('2026-08-14T08:00:00Z'))]
        state = snap(rows)
        candidates = [Project('cat', 'Release'), rows[3], rows[2], rows[4]]
        expected = '''Multiple items match "report":
  1. category: Release
  2. task: Report  due:2026-10-19 · today — Work
  3. step: Write report  due:2026-10-21 · in 2d — Weekly review > Prepare — Work
  4. task: Old report  completed 2026-08-14 10:00 — Work'''
        self.assertEqual(render_ambiguity(state, 'report', candidates, NOW).stdout, expected + '\nSelect 1-4, or q to cancel:')
        result = render_ambiguity(state, 'report', candidates, NOW, interactive=False)
        self.assertEqual(result.stdout, expected)
        self.assertEqual(result.stderr, 'todo: multiple items match; interactive selection is unavailable')
        self.assertEqual(invalid_selection(4).stdout, 'Enter a number from 1-4, or q.')

    def test_fragments_and_edge_normalization(self):
        self.assertEqual(edge('\n  \nfirst\n\n last\n\n'), 'first\n\n last')
        self.assertEqual(history_warning(7).stderr, 'todo: warning: Your Todoist account keeps 7 days of report history; set [report] warn_limited_history=false to hide this warning.')
        self.assertEqual(pagination_progress('report activity', 20).stderr, 'todo: loading report activity: 20 pages')
        self.assertEqual(render_categories(snap()).stdout, 'Someday\nWork')


class AdditionalContractTests(unittest.TestCase):
    def test_timing_consumers_color_equivalence_and_whole_due_value(self):
        value = replace(parse_attention('2026-10-19T05:59:59.999999999Z', NOW, 'Europe/Prague'), recurring=True, rule='every day')
        rows = [Item('r', 'w', 'Root'), Item('s', 'w', 'Child', 'r', priority=1, attention=value)]
        state = snap(rows, reminders=[Reminder('r1', 's', 0), Reminder('r2', 's', 90)])
        for renderer in (lambda color: render_detail(state, 's', NOW, color=color),
                         lambda color: render_ambiguity(state, 'Child', [rows[1]], NOW, color=color)):
            plain, colored = renderer(Color()).stdout, renderer(Color(True)).stdout
            self.assertEqual(re.sub(r'\x1b\[[0-9;]*m', '', colored), plain)
            self.assertIn('<1m overdue ↻ every day reminders:at due, 90m before', plain)
            self.assertIn('\x1b[38;2;88;110;117m — Root\x1b[0m', colored)
        self.assertIn('Due: \x1b[38;2;220;50;47m2026-10-19 07:59:59 Europe/Prague · <1m overdue ↻ every day reminders:at due, 90m before\x1b[0m', render_detail(state, 's', NOW, color=Color(True)).stdout)

    def test_now_id_tie_visible_only_in_context_and_date_then_title(self):
        rows = [Item('r1', 'w', 'Parent Z'), Item('r2', 'w', 'Parent A'),
                Item('a', 'w', 'Same', 'r1', priority=1, attention=day('2026-10-19')),
                Item('z', 'w', 'Same', 'r2', priority=1, attention=day('2026-10-19')),
                Item('n', 'w', 'Z early', priority=1, attention=parse_attention('2026-10-19T07:00:00Z', NOW, 'Europe/Prague')),
                Item('m', 'w', 'A late', priority=1, attention=parse_attention('2026-10-19T08:00:00Z', NOW, 'Europe/Prague'))]
        text = render_now(snap(rows), NOW).stdout
        self.assertLess(text.index('Same  due:today — Parent Z'), text.index('Same  due:today — Parent A'))
        self.assertLess(text.index('Z early'), text.index('A late'))

    def test_unknown_comment_ties_and_exact_nested_owner_comments(self):
        rows = [Item('r', 'w', 'Root'), Item('s', 'w', 'Child', 'r')]
        comments = [Comment('z', 's', 'earlier', instant('2026-08-14T10:00:00.123456001Z')),
                    Comment('a', 's', 'later', instant('2026-08-14T10:00:00.123456009Z')),
                    Comment('u2', 's', 'unknown 2'), Comment('u1', 's', 'unknown 1')]
        self.assertEqual(render_detail(snap(rows, comments), 'r', NOW).stdout, '''P2  Work  Root
Due: none

Waiting: none

Steps
- [ ] P2 Child
  Comments
  - 2026-08-14 12:00  earlier
  - 2026-08-14 12:00  later
  - none  unknown 1
  - none  unknown 2

Comments: none''')

    def test_literal_list_hiding_and_full_width_unicode_paths(self):
        root = Item('r', 'w', 'É > 漢' * 30)
        child = Item('s', 'w', '子', 'r', description=waiting('Reason: first\n\nlast\nSince: 2026-07-13'),
                     attention=parse_attention('2026-10-23T10:00:00Z', NOW, 'Europe/Prague'), labels=frozenset(('waiting',)))
        state = snap([root, child])
        self.assertEqual(render_search(state, [child], NOW).stdout, 'Work\n  [ ] P2 ' + root.title + '\n    [ ] P2 子 — due:2026-10-23 12:00:00 Europe/Prague · 4d 4h left\n      Hidden until: Fri 23 Oct 2026, 12:00:00\n      Reason: Reason: first\n        \n        last\n        Since: 2026-07-13')
        self.assertIn(' — ' + root.title, render_now(state, NOW, all_items=True).stdout)
