"""Reusable mixed-reminder capture setup."""
from io import StringIO
from todo_lib import presentation as p
from tests.support import capture as f
from tests.support.reminders import absolute, FLOATING
from tests.support.terminal import Terminal


class ReminderCaptureSupport:
    def mixed(self):
        self.wire_items[0]['due'] = f.due('2026-10-30T10:00:00Z')
        self.wire_reminders = [f.reminder('relative', 'parent', minute_offset=30),
                               absolute('absolute', FLOATING, item_id='parent')]
        self.seed()

    def terminal(self, answer='y\n'):
        self.workflow.streams = p.OriginalStreams(Terminal(answer), Terminal(), StringIO())

