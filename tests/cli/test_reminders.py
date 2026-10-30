"""Real public CLI routing and streams with isolated state and synthetic transport."""
import unittest
from tests.cli.test_cli import invoke
from tests.workflows.capture import test_capture as f
from tests.workflows.capture.test_coexistence import Terminal
from tests.support.reminders import absolute, FIXED
from todo_lib.syntax.help import render_help


class PublicReminders(unittest.TestCase):
    setUp = f.CaptureTests.setUp
    state = f.CaptureTests.state
    seed = f.CaptureTests.seed
    refresh = f.CaptureTests.refresh
    queue_refresh = f.CaptureTests.queue_refresh
    operation = f.CaptureTests.operation

    def test_noninteractive_preview_refuses_before_task_write(self):
        self.wire_reminders = [absolute('old', FIXED, item_id='parent')]
        self.seed()
        self.refresh()
        status, out, err, _ = invoke(self, ['task', '--reminder-at=every Monday at 9am', 'Parent',
                                          '--at', 'tomorrow 10'], self.http)
        self.assertEqual(status, 1)
        self.assertIn('Reminder replacement for: Parent', out)
        self.assertIn('expression (Todoist): every Monday at 9am', out)
        self.assertNotIn('[y/N]', out)
        self.assertIn('terminals', err)
        self.assertTrue(all('commands' not in c for c in self.http.calls))
        self.assertFalse(self.http.steps)

    def test_public_addition_undated_noun_alias_reconciles_actual(self):
        self.refresh()
        returned = [absolute('a', FIXED, item_id='parent')]
        self.operation('reminder_add', {'item_id': 'parent', 'type': 'absolute',
            'due': {'string': 'every day at 9am', 'lang': 'en'}}, self.state(reminders=returned), 'a')
        status, out, err, _ = invoke(self, ['task', '--reminder-at', 'every day at 9am', 'Parent'], self.http)
        self.assertEqual(status, 0, err)
        self.assertIn('Reminders: none -> at ', out)
        self.assertIn('↻ cada día a las 9', out)
        self.assertNotIn('every day at 9am', out)
        self.assertFalse(self.http.steps)

    def test_public_blank_replacement_cancels(self):
        self.wire_reminders = [absolute('old', FIXED, item_id='parent')]
        self.seed()
        self.refresh()
        status, out, err, _ = invoke(self, ['schedule', 'Parent', '--reminder-at', '2h'], self.http,
                                     input=Terminal('\n'), output=Terminal())
        self.assertEqual(status, 1)
        self.assertIn('[y/N]:', out)
        self.assertIn('cancelled', err)
        self.assertTrue(all('commands' not in c for c in self.http.calls))

    def test_managed_failure_context_is_escaped_redacted_and_only_on_stderr(self):
        from tests.adapter.current.test_current import delta
        before = {name: (self.root / name).read_bytes() for name in
                  ('cache.json', 'history.json', 'binding.json', 'report-cursor')}
        rows = [dict(i, content='Task secret\nsecond\tline') if i['id'] == 'parent' else i
                for i in self.wire_items]
        raw = self.state(items=rows, reminders=[absolute('managed-id', item_id='parent',
            due={'date': {'secret': 'do not dump arbitrary nested payload'}}),
            absolute('private-id', item_id='unrelated-owner', type='location', due={'private': 'unused'})])
        self.http.read(raw)
        self.http.read(delta())
        status, out, err, _ = invoke(self, ['--refresh', 'now'], self.http)
        self.assertEqual(status, 1)
        self.assertEqual(out, '')
        for value in ('due.date must be', 'reminder managed-id', 'title Task [REDACTED]\\nsecond\\tline',
                      'category cat', 'type absolute', 'date=<malformed object>'):
            self.assertIn(value, err)
        for value in ('secret', 'do not dump', 'private-id', 'unrelated-owner', 'Read-only recovery:'):
            self.assertNotIn(value, err)
        self.assertEqual({name: (self.root / name).read_bytes() for name in before}, before)
        self.assertFalse(self.http.steps)

    def test_early_unrelated_reminder_failures_do_not_disclose_payloads(self):
        from tests.adapter.current.test_current import item, project, delta
        from copy import deepcopy
        before = {name: (self.root / name).read_bytes() for name in
                  ('cache.json', 'history.json', 'binding.json', 'report-cursor')}
        outside = absolute('outside-reminder', item_id='outside-owner',
            type='PRIVATE TYPE', due={'date': 'PRIVATE UNUSED SCHEDULE'})
        cases = [([dict(outside, id='')], 'ID', 1),
                 ([dict(outside, item_id=None)], 'ID', 2),
                 ([dict(outside, item_id='absent', is_deleted=None)], 'is_deleted', 2),
                 ([outside, dict(outside, item_id='another-owner')], 'contradictory', 1)]
        for reminders, reason, reads in cases:
            with self.subTest(reason=reason, reminders=reminders):
                raw = self.state(items=self.wire_items + [item('outside-owner',
                    project_id='outside-project', content='CONFIDENTIAL OUTSIDE TITLE')],
                    reminders=deepcopy(reminders), projects=[project('root', None, name='root'),
                        project(), project('outside-project', None, name='PRIVATE OUTSIDE PROJECT')])
                self.http.read(raw)
                if reads == 2:
                    self.http.read(delta())
                calls = len(self.http.calls)
                status, out, err, _ = invoke(self, ['--refresh', 'now'], self.http)
                self.assertEqual(status, 1)
                self.assertEqual(out, '')
                self.assertIn(reason, err)
                self.assertIn('reminder', err)
                for value in ('CONFIDENTIAL', 'PRIVATE', 'Read-only recovery:'):
                    self.assertNotIn(value, err)
                self.assertEqual(len(self.http.calls) - calls, reads)
                self.assertFalse(self.http.steps)
                self.assertEqual({name: (self.root / name).read_bytes() for name in before}, before)

    def test_departed_category_cannot_authorize_fresh_failure_context(self):
        from tests.adapter.current.test_current import item, project, delta
        before = {name: (self.root / name).read_bytes() for name in
                  ('cache.json', 'history.json', 'binding.json', 'report-cursor')}
        # Synthetic PersonalProjectSyncView parent/lifecycle updates and
        # NotificationSyncView identity fields, from the retained API-v1 schema.
        # A bound ID alone cannot authorize new payloads after scope departure.
        for incremental in (False, True):
            for change in ({'parent_id': 'elsewhere'}, {'parent_id': None},
                           {'is_deleted': True}, {'is_archived': True},
                           {'is_shared': True}, {'workspace_id': 'workspace'}):
                for owner in ('never-known', 'parent'):
                    with self.subTest(incremental=incremental, change=change, owner=owner):
                        rows = [item(owner, content='CONFIDENTIAL NEW OUTSIDE TITLE')]
                        projects = [project(name='PRIVATE MOVED PROJECT', **change)]
                        reminders = [absolute('', item_id=owner, type='absolute',
                            due={'date': '2026-11-01T09:00:00Z'})]
                        raw = (delta(items=rows, projects=projects, reminders=reminders)
                               if incremental else self.state(items=rows,
                                   projects=[project('root', None), *projects], reminders=reminders))
                        self.http.read(raw)
                        calls = len(self.http.calls)
                        status, out, err, _ = invoke(self, ['--refresh', 'now'], self.http)
                        self.assertEqual(status, 1)
                        self.assertEqual(out, '')
                        self.assertIn('reminders.id must be a nonempty string ID', err)
                        self.assertIn('reminder', err)
                        for value in ('CONFIDENTIAL', 'PRIVATE', 'Read-only recovery:'):
                            self.assertNotIn(value, err)
                        if owner == 'parent':
                            self.assertIn('cached title Parent', err)
                            self.assertIn('cached category cat', err)
                            self.assertIn('type absolute', err)
                            self.assertIn('2026-11-01T09:00:00Z', err)
                        else:
                            self.assertNotIn('2026-11-01', err)
                            self.assertNotIn('type absolute', err)
                        self.assertEqual(len(self.http.calls) - calls, 1)
                        self.assertFalse(self.http.steps)
                        self.assertEqual({name: (self.root / name).read_bytes()
                                          for name in before}, before)

    def test_help_is_consistent_and_teaches_limits(self):
        for command in ('schedule', 'task', 'step', 'add'):
            text = render_help(command)
            for fragment in ('--reminder-at', 'Todoist', 'exact time', 'complete set',
                             '--reminder keep', '--reminder-at keep', 'noninteractive', 'new ID'):
                with self.subTest(command=command, fragment=fragment):
                    self.assertIn(fragment, text)
