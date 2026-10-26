from dataclasses import replace
import re
import unittest
from tests.presentation.test_render import snap, instant, day, NOW, waiting
from todo_lib.domain import Item, Project, parse_attention, validate
from todo_lib.presentation import *


class ReportTests(unittest.TestCase):
    def test_exact_complete_supplied_report(self):
        rows = [Item('r', 'w', 'Deploy staging'), Item('s', 'w', 'Run migration', 'r'),
                Item('h', 'w', 'Deploy production', attention=parse_attention('2026-08-17T00:00:00+02:00', NOW, 'Europe/Prague'),
                     description=waiting('waiting for approval'), labels=frozenset(('waiting',)))]
        result = render_report(snap(rows), instant('2026-08-07T14:30:42Z'), instant('2026-08-14T14:30:42Z'),
                               finished=[ReportEvent('r', instant('2026-08-14T08:00:00Z'))],
                               progress=[ReportEvent('s', instant('2026-08-14T07:45:00Z'), 'comment', 'Checks passed'),
                                         ReportEvent('r', instant('2026-08-14T07:30:00Z'), 'comment', 'Ready for review'),
                                         ReportEvent('s', instant('2026-08-14T07:00:00Z'))], hidden=[rows[2]])
        self.assertEqual(result.stdout, '''Report
From (exclusive): Fri 07 Aug 2026, 16:30:42
Until (inclusive): Fri 14 Aug 2026, 16:30:42
Timezone: Europe/Prague

Finished
  Work
    Fri 14 Aug 2026, 10:00:00 — Deploy staging

Progress
  Work
    Deploy staging
      Fri 14 Aug 2026, 09:00:00 — Completed step: Run migration
      Fri 14 Aug 2026, 09:30:00 — Comment: Ready for review
      Fri 14 Aug 2026, 09:45:00 — Comment on step: Run migration — Checks passed

Hidden
  Work
    Deploy production
      Until: Mon 17 Aug 2026, 00:00:00
      Reason: waiting for approval''')

    def test_supplied_events_not_filtered_and_exact_precision_ties(self):
        rows = [Item('r', 'w', 'Root'), Item('z', 'w', 'Earlier', 'r'), Item('a', 'w', 'Later', 'r')]
        early = instant('2026-08-14T07:00:00.123456001Z')
        late = instant('2026-08-14T07:00:00.123456009Z')
        events = [ReportEvent('a', late, event_id='a'), ReportEvent('z', early, event_id='z'),
                  ReportEvent('z', early, 'comment', 'event id tie first', event_id='a'),
                  ReportEvent('z', early, 'comment', 'null event id last')]
        text = render_report(snap(rows), NOW, NOW, progress=events).stdout
        self.assertEqual(text.split('Progress\n')[1].split('\n\nHidden')[0], '''  Work
    Root
      Fri 14 Aug 2026, 09:00:00 — Comment on step: Earlier — event id tie first
      Fri 14 Aug 2026, 09:00:00 — Completed step: Earlier
      Fri 14 Aug 2026, 09:00:00 — Comment on step: Earlier — null event id last
      Fri 14 Aug 2026, 09:00:00 — Completed step: Later''')
        self.assertIn('Finished\n  None.', text)
        self.assertIn('Hidden\n  None.', text)

    def test_deep_event_context_and_hidden_recursive_once(self):
        rows = [Item('r', 'w', 'Root'), Item('s', 'w', 'Prepare', 'r'),
                Item('g', 'w', 'Figures', 's', attention=day('2026-10-25'), labels=frozenset(('waiting',))),
                Item('h', 'w', 'Check sources', 'g', attention=day('2026-10-26'), labels=frozenset(('waiting',)), description=waiting('Reason: original\nSince: 2026-07-13'))]
        text = render_report(snap(rows), NOW, NOW, progress=[ReportEvent('g', NOW, 'comment', 'first\n\nlast')], hidden=[rows[3], rows[2]]).stdout
        self.assertIn('Comment on step: Figures — Root > Prepare — first\n        \n        last', text)
        self.assertEqual(text.split('\n\nHidden\n')[1], '''  Work
    Root  [context]
      Prepare  [context]
        Figures
          Until: 2026-10-25
          Check sources
            Until: 2026-10-26
            Reason: Reason: original
              Since: 2026-07-13''')

    def test_finished_root_input_enforced(self):
        rows = [Item('r', 'w', 'Root'), Item('s', 'w', 'Step', 'r')]
        with self.assertRaises(ValueError):
            render_report(snap(rows), NOW, NOW, finished=[ReportEvent('s', NOW)])


class ReceiptTests(unittest.TestCase):
    def test_scalar_hiding_reason_multiline_changes_only(self):
        row = Item('r', 'w', 'Deploy staging')
        state = snap([row])
        self.assertEqual(render_mutation(state, row, changes=[('Priority', 'P2', 'P1'), ('Hiding', False, True), ('Reason', None, 'first\n\nlast'), ('Title', 'same', 'same')]).stdout, '''Updated task: Deploy staging
  Priority: P2 -> P1
  Hiding: off -> on
  Reason: none -> first
\x20\x20\x20\x20
    last''')
        self.assertEqual(render_mutation(state, row, changes=[('Hiding', False, True), ('Reason', None, None)]).stdout,
                         'Updated task: Deploy staging\n  Hiding: off -> on')

    def test_move_parent_paths_and_resulting_type(self):
        rows = [Item('r', 'w', 'Launch'), Item('s', 'w', 'Prepare', 'r'), Item('g', 'w', 'Figures', 's'), Item('x', 'w', 'Sources')]
        before = snap(rows)
        after_rows = [*rows[:3], replace(rows[3], category_id='s', parent_id=None)]
        after = snap(after_rows)
        self.assertEqual(render_move(before, rows[3], after, after_rows[3]).stdout, 'Moved task: Sources\n  Category: Work -> Someday')
        new = replace(rows[3], parent_id='g')
        self.assertEqual(render_move(before, rows[3], snap([*rows[:3], new]), new).stdout,
                         'Moved step: Sources — Launch > Prepare > Figures\n  Parent: none -> Launch > Prepare > Figures')
        self.assertEqual(render_move(snap([*rows[:3], new]), new, before, rows[3]).stdout,
                         'Moved task: Sources\n  Parent: Launch > Prepare > Figures -> none')

    def test_creation_due_actual_and_comments_bodies(self):
        rows = [Item('r', 'w', 'Root'), Item('s', 'w', 'Prepare', 'r'), Item('g', 'w', 'Figures', 's')]
        state = snap(rows)
        self.assertEqual(render_mutation(state, rows[2], 'Created', attention=day('2026-10-25')).stdout,
                         'Created step: Figures — Root > Prepare\n  Due: 2026-10-25')
        self.assertEqual(render_created_category(Project('x', 'Release')).stdout, 'Created category: Release')
        self.assertEqual(render_comment_bodies(state, rows[2], ['Filed test\n\nSecond line', 'Resubmitted RTI']).stdout, '''Comments for: Figures — Root > Prepare
-> Filed test
\x20\x20
  Second line
-> Resubmitted RTI''')
        self.assertEqual(render_comment_bodies(state, rows[2], ['Done: Finished'], owner_identified=True).stdout, '-> Done: Finished')
        self.assertEqual(render_comment_bodies(state, rows[2], []).stdout, '')

    def test_move_distinct_parents_with_identical_display_paths(self):
        rows = [Item('p1', 'w', 'A > B'), Item('a', 'w', 'A'),
                Item('p2', 'w', 'B', 'a'), Item('x', 'w', 'Sources', 'p1')]
        before = validate(snap(rows))
        moved = replace(rows[3], parent_id='p2')
        after = validate(snap([*rows[:3], moved]))
        receipt = render_move(before, rows[3], after, moved)
        self.assertEqual(receipt.stdout,
                         'Moved step: Sources — A > B\n  Parent: A > B -> A > B')
        self.assertEqual(render_move(after, moved, before, rows[3]).stdout,
                         'Moved step: Sources\n  Parent: A > B -> A > B')
        self.assertEqual(render_receipts([
            receipt, render_comment_bodies(after, moved, ['Checked'], owner_identified=True)
        ]).stdout, 'Moved step: Sources — A > B\n  Parent: A > B -> A > B\n-> Checked')

    def test_move_identity_controls_category_and_unchanged_context(self):
        row = Item('x', 'w', 'Sources', 'p')
        parent = Item('p', 'w', 'Before')
        before = validate(snap([parent, row]))
        renamed = replace(before, items={'p': replace(parent, title='After'), 'x': row},
                          categories={**before.categories, 'w': Project('w', 'Renamed', 'root')})
        self.assertEqual(render_move(before, row, validate(renamed), row), Document())

        # Names can change between authoritative snapshots while each remains unique.
        moved = replace(row, parent_id=None, category_id='s')
        after = snap([parent, moved])
        after = validate(replace(after, categories={
            'w': Project('w', 'Renamed', 'root'), 's': Project('s', 'Work', 'root')}))
        self.assertEqual(render_move(before, row, after, moved).stdout,
                         'Moved task: Sources\n  Parent: Before -> none\n  Category: Work -> Work')

    def test_reopened_ancestors_operation_order(self):
        rows = [Item('r', 'w', 'Root'), Item('s', 'w', 'Prepare', 'r'), Item('g', 'w', 'Figures', 's')]
        state = snap(rows)
        self.assertEqual(render_mutation(state, rows[2], 'Reopened', also_reopened=[rows[0], rows[1]]).stdout, '''Reopened step: Figures — Root > Prepare
Also reopened:
  task: Root — Work
  step: Prepare — Root — Work''')

    def test_editor_success_noop_and_partial_streams(self):
        owner = Item('r', 'w', 'toupper')
        state = snap([owner])
        self.assertEqual(render_comment_edit(state, owner, added=2, edited=1, deleted=1).stdout,
                         'Comments updated: toupper · 2 added, 1 edited, 1 deleted')
        self.assertEqual(render_comment_edit(state, owner), Document())
        result = render_comment_edit(state, owner, outcomes=[
            CommentOutcome('Accepted', 'edited', timestamp=instant('2026-07-13T15:28:00Z')),
            CommentOutcome('Accepted', 'added', body='Checked the SPARC result.'),
            CommentOutcome('Unknown', 'add', body='Sent the follow-up.\nFull body', reason='connection lost'),
            CommentOutcome('Not attempted', 'delete', timestamp=instant('2026-06-17T07:57:00Z'))])
        self.assertEqual(result.stdout, '''  Accepted: edited comment from 2026-07-13 17:28
  Accepted: added “Checked the SPARC result.”''')
        self.assertEqual(result.stderr, '''Comments for: toupper — partial failure
  Unknown: add “Sent the follow-up.
    Full body” — connection lost
  Not attempted: delete comment from 2026-06-17 09:57''')


class CompositionTests(unittest.TestCase):
    def test_receipt_composition_and_field_edge_normalization(self):
        row = Item('r', 'w', 'Root')
        state = snap([row])
        change = render_mutation(state, row, changes=[('Reason', '\nold\n\n', '\nnew\n')])
        bodies = render_comment_bodies(state, row, ['Done: body'], owner_identified=True)
        self.assertEqual(render_receipts([change, bodies]).stdout, 'Updated task: Root\n  Reason: old -> new\n-> Done: body')
        self.assertEqual(render_receipts([]), Document())

    def test_report_event_object_and_source_ties(self):
        rows = [Item('r', 'w', 'Root'), Item('a', 'w', 'A', 'r'), Item('z', 'w', 'Z', 'r')]
        events = [ReportEvent('z', NOW, 'comment', 'Z', event_id='same'),
                  ReportEvent('a', instant('2026-10-19T06:00:00.000000000Z'), 'comment', 'A second', event_id='same', source_order=2),
                  ReportEvent('a', NOW, 'comment', 'A first', event_id='same', source_order=1),
                  ReportEvent('a', NOW, 'comment', 'A same source stable', event_id='same', source_order=1)]
        text = render_report(snap(rows), NOW, NOW, progress=events).stdout
        self.assertLess(text.index('A first'), text.index('A same source stable'))
        self.assertLess(text.index('A same source stable'), text.index('A second'))
        self.assertLess(text.index('A second'), text.index('Comment on step: Z'))


class ScalarViewTests(unittest.TestCase):
    def test_empty_scalar_update_and_unchanged_move_are_noops(self):
        row = Item('r', 'w', 'Root')
        state = snap([row])
        self.assertEqual(render_mutation(state, row, changes=[('Priority', 'P2', 'P2')]), Document())
        self.assertEqual(render_move(state, row, state, row), Document())

    def test_report_cursor_nullable_and_exact_absolute_template(self):
        self.assertEqual(render_report_cursor(None, 'Europe/Prague').stdout, 'Report cursor: none\nTimezone: Europe/Prague')
        self.assertEqual(render_report_cursor(instant('2026-08-14T14:30:42.999999999Z'), 'Europe/Prague').stdout,
                         'Report cursor: Fri 14 Aug 2026, 16:30:42\nTimezone: Europe/Prague')
