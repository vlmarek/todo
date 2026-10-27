"""Public complete-set reminder syntax, without state access."""
import unittest
from todo_lib.syntax import parse, UsageError


class ReminderSyntaxTests(unittest.TestCase):
    def test_interleaved_scalar_forms_and_noun_adjacency(self):
        values = (('reminder-at', 'Friday 09:00'), ('reminder', '30m'),
                  ('reminder-at', 'keep'), ('reminder', 'keep'))
        for argv in (
            ['schedule', 'Meeting', '--reminder-at=Friday 09:00', '--reminder', '30m', '--reminder-at', 'keep', '--reminder=keep'],
            ['task', '--reminder-at', 'Friday 09:00', 'Meeting', '--reminder=30m', '--reminder-at=keep', '--reminder', 'keep'],
            ['step', '--reminder-at=Friday 09:00', 'Parent', 'Meeting', '--reminder=30m', '--reminder-at=keep', '--reminder', 'keep']):
            with self.subTest(argv=argv):
                request = parse(argv)
                self.assertEqual(request.command, 'schedule')
                self.assertEqual(request.selector, ('Meeting',))
                self.assertEqual(request.reminder_markers, values)
        self.assertEqual(request.parent, ('Parent',))

    def test_creation_groups_remain_separate(self):
        request = parse(['add', 'Work', '--title', 'One task', '--reminder-at', '2h',
                         '--step', 'One child', '--reminder=30m', '--at', 'tomorrow 10'])
        self.assertEqual([(g.kind, g.values) for g in request.groups],
                         [('title', ('One task',)), ('step', ('One child',))])
        self.assertEqual(request.reminder_markers, (('reminder-at', '2h'), ('reminder', '30m')))

    def test_reserved_clear_missing_and_inapplicable(self):
        for suffix in (['--reminder-at'], ['--reminder-at='], ['--reminder-at', 'clear'],
                       ['--reminder-at', 'Keep'], ['--reminder', 'KEEP'],
                       ['--reminder-at', 'keep', '--reminder-at', 'keep'],
                       ['--reminder', 'clear', '--reminder-at', 'keep']):
            with self.subTest(suffix=suffix), self.assertRaises(UsageError):
                parse(['schedule', 'Task', *suffix])
        with self.assertRaises(UsageError):
            parse(['unhide', 'Task', '--reminder-at', '2h'])
        with self.assertRaises(UsageError):
            parse(['add', 'Work', 'Bad\nTitle', '--reminder-at', '2h'])
        with self.assertRaises(UsageError):
            parse(['add', 'Work', 'Task', '--done', '--reminder-at', '2h'])
