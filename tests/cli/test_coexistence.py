"""Representative amendment composition through the public CLI and real stores.

Raw comments follow pinned api-v1.openapi.json NoteSyncView/default content;
reminders follow NotificationSyncView and Sync Reminders. Responses are synthetic,
independently supplied outcomes, never generated from the outgoing commands.
"""
from copy import deepcopy
import unittest
from unittest.mock import patch

from tests.cli.test_cli import invoke
from tests.workflows.capture import test_capture as f
from tests.workflows.capture.test_coexistence import Terminal
from tests.workflows.capture import test_reminders as reminders
from tests.workflows.report import test_report as reports
from tests.adapter.current.test_current import full, delta, item
from tests.support.reminders import absolute, FIXED
from todo_lib.workflows.comments import CommentWorkflow
from todo_lib.syntax.help import render_help


class PublicText(unittest.TestCase):
    setUp = reports.Reports.setUp
    put = reports.Reports.put
    sync = reports.Reports.sync
    boundary = reports.Reports.boundary
    requests = reports.Reports.requests

    def test_help_teaches_imported_text_and_collision_distinctions(self):
        self.assertIn('Imported duplicates', render_help('rename'))
        for fragment in ('[no text]', 'unchanged editor', 'by ID', 'emptying nonblank', 'metadata is ignored'):
            self.assertIn(fragment, render_help('comment'))

    def test_refresh_reload_editor_current_text_report_and_incomplete_cursor(self):
        blank = dict(id='own', item_id='B', posted_at=reports.CREATED, is_deleted=False)
        text = dict(id='text', item_id='B', posted_at=reports.CREATED,
                    is_deleted=False, content='Current text')
        notes = [blank, text, dict(text, file_attachment={'file_type': 'website',
                  'file_url': 'https://example.invalid/preview'})]
        wire, _ = self.boundary([self.sync('delta-token', full(
            items=[item('A'), item('B', parent_id='A')], notes=notes,
            user_plan_limits=reports.limits())), self.sync('full-token', delta())])
        status, out, err, _ = invoke(self, ['task', 'A', '--refresh'], wire)
        self.assertEqual(status, 0, err)
        self.assertIn('[no text]', out)
        self.assertEqual(out.count('Current text'), 1)
        original = self.store.load_consistent_state().snapshot.comments
        self.assertEqual(original['own'].body, '')
        wire, _ = self.boundary([])
        def unchanged(buffer):
            self.assertIn('[id: own posted:', buffer)
            self.assertNotIn('[no text]', buffer)
            return buffer.replace('\n', '\r\n')
        with patch.object(CommentWorkflow, '_edit', side_effect=unchanged):
            status, _, err, _ = invoke(self, ['comment', '--edit', 'B'], wire)
        self.assertEqual(status, 0, err)
        self.assertEqual(self.store.load_consistent_state().snapshot.comments, original)
        before = (self.root / 'report-cursor').read_bytes()
        events = [reports.event(1, reports.LAST), reports.event(2, reports.LAST, obj='text')]
        scoped = [{k: v for k, v in n.items() if k != 'item_id'} for n in notes]
        steps = self.requests(events=events, current_notes=notes, comments=scoped)
        wire, _ = self.boundary(steps)
        status, out, err, _ = invoke(self, ['report'], wire)
        self.assertEqual(status, 0, err)
        self.assertEqual(out.count('[no text]'), 1)
        self.assertEqual(out.count('Current text'), 1)
        self.assertNotIn('annotation', out)
        self.assertEqual((self.root / 'report-cursor').read_bytes(), before)
        steps = self.requests(events=events, current_notes=notes, comments=scoped)
        steps[-1][1].pop('next_cursor')
        wire, _ = self.boundary(steps)
        status, out, err, _ = invoke(self, ['report', '--final'], wire)
        self.assertEqual(status, 1)
        self.assertEqual(out, '')
        self.assertIn('next_cursor', err)
        self.assertEqual((self.root / 'report-cursor').read_bytes(), before)


class PublicSets(unittest.TestCase):
    setUp = f.CaptureTests.setUp
    state = f.CaptureTests.state
    seed = f.CaptureTests.seed
    refresh = f.CaptureTests.refresh
    queue_refresh = f.CaptureTests.queue_refresh
    operation = f.CaptureTests.operation
    mixed = reminders.ReminderWorkflowTests.mixed

    def call(self, argv, **kwargs):
        result = invoke(self, argv, self.http, **kwargs)
        self.assertFalse(self.http.steps)
        return result[:3]

    def test_imported_duplicates_inactive_text_selection_mutation_and_collision(self):
        self.wire_items[1].update(content='Imported', labels=['waiting'],
                                  description='[todo waiting]')
        self.wire_items[2]['content'] = 'Imported'
        self.seed()
        status, out, err = self.call(['task', 'Imported'])
        self.assertEqual(status, 1)
        self.assertIn('Imported', out)
        self.refresh()
        changed = deepcopy(self.wire_items)
        changed[0]['content'] = 'Unique'
        self.operation('item_update', {'id': 'parent', 'content': 'Unique'},
                       self.state(items=changed), 'parent')
        status, _, err = self.call(['rename', 'Parent', '--to', 'Unique'])
        self.assertEqual(status, 0, err)
        snapshot = self.store.load_consistent_state().snapshot
        self.assertEqual(snapshot.items['precise'].description, '[todo waiting]')
        self.assertEqual(snapshot.items['precise'].title, snapshot.items['null'].title)
        self.wire_items = changed
        self.refresh()
        count = len(self.http.calls)
        status, _, err = self.call(['rename', 'Unique', '--to', 'Imported'])
        self.assertEqual(status, 1)
        self.assertIn('sibling', err)
        self.assertTrue(all('commands' not in c for c in self.http.calls[count:]))

    def test_mixed_keep_zero_reload_cancel_escaped_preview_receipt_and_clear(self):
        self.mixed()
        self.wire_items[0]['content'] = 'Parent\nline\ttab'
        self.seed()
        original = self.store.load_consistent_state().snapshot.reminders
        self.refresh()
        returned = self.wire_reminders + [f.reminder('zero', 'parent', minute_offset=0)]
        self.operation('reminder_add', {'item_id': 'parent', 'type': 'relative', 'minute_offset': 0},
                       self.state(reminders=returned), 'zero')
        status, out, err = self.call(['schedule', 'Parent', '--reminder-at', 'keep',
                                      '--reminder', '30m', '--reminder', '0m'])
        self.assertEqual(status, 0, err)
        self.assertIn(r'Parent\nline\ttab', out)
        self.assertNotIn('Parent\nline\ttab', out)
        saved = self.store.load_consistent_state().snapshot
        self.assertEqual({k: saved.reminders[k] for k in original}, original)
        status, out, err = self.call(['task', 'Parent'])
        self.assertEqual(status, 0, err)
        self.assertIn('0m', out)
        self.wire_reminders = returned
        for streams in ({}, {'input': Terminal('\n'), 'output': Terminal()}):
            self.refresh()
            count = len(self.http.calls)
            status, out, err = self.call(['schedule', 'Parent', '--at', 'tomorrow 10',
                '--reminder-at', 'every Monday at 9am'], **streams)
            self.assertEqual(status, 1)
            self.assertIn(r'Reminder replacement for: Parent\nline\ttab', out)
            self.assertIn('expression (Todoist): every Monday at 9am', out)
            self.assertIn('--reminder-at keep', out)
            self.assertEqual('[y/N]:' in out, bool(streams))
            self.assertTrue(all('commands' not in c for c in self.http.calls[count:]))
            self.assertEqual(self.store.load_consistent_state().snapshot.reminders, saved.reminders)
        self.refresh()
        returned = [returned[2], returned[0], returned[1]]
        for index, reminder in enumerate(returned):
            self.operation('reminder_delete', {'id': reminder['id']},
                           self.state(reminders=returned[index + 1:]), reminder['id'])
        status, out, err = self.call(['schedule', 'Parent', '--reminder', 'clear'])
        self.assertEqual(status, 0, err)
        self.assertNotIn('[y/N]', out)
        self.assertFalse(self.store.load_consistent_state().snapshot.reminders)

    def test_new_absolute_undated_normalized_recurrence_then_unrelated_change(self):
        self.refresh()
        returned = [absolute('new', FIXED, item_id='parent')]
        self.operation('reminder_add', {'item_id': 'parent', 'type': 'absolute',
            'due': {'string': 'every day at nine', 'lang': 'en'}},
            self.state(reminders=returned), 'new')
        status, out, err = self.call(['schedule', 'Parent', '--reminder-at', 'every day at nine'])
        self.assertEqual(status, 0, err)
        self.assertIn('cada día a las 9', out)
        self.assertNotIn('every day at nine', out)
        saved = self.store.load_consistent_state().snapshot
        self.assertIsNone(saved.items['parent'].attention)
        self.wire_reminders = returned
        self.refresh()
        changed = deepcopy(self.wire_items)
        changed[0]['content'] = 'Renamed'
        self.operation('item_update', {'id': 'parent', 'content': 'Renamed'},
                       self.state(items=changed), 'parent')
        status, _, err = self.call(['rename', 'Parent', '--to', 'Renamed'])
        self.assertEqual(status, 0, err)
        self.assertEqual(self.store.load_consistent_state().snapshot.reminders, saved.reminders)
