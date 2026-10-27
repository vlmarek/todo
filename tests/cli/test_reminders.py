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

    def test_help_is_consistent_and_teaches_limits(self):
        for command in ('schedule', 'task', 'step', 'add'):
            text = render_help(command)
            for fragment in ('--reminder-at', 'Todoist', 'exact time', 'complete set',
                             '--reminder keep', '--reminder-at keep', 'noninteractive', 'new ID'):
                with self.subTest(command=command, fragment=fragment):
                    self.assertIn(fragment, text)
