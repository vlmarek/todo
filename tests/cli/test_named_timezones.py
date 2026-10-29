"""Public request/response conformance, not live abbreviation or delivery proof.

Strict UUID/argument/read fixtures reuse CaptureTests.Boundary. Provider shapes:
retained docs/design/external/todoist/upstream/api-v1.openapi.json, Due dates,
Sync Tasks Add/Update and Reminders Add/NotificationSyncView.
"""
import json
import unittest
from todo_lib.adapter.transport import Transport
from tests.support.http import ControlledHTTP, ExpectedRequest, Response
from tests.workflows.lifecycle.test_lifecycle import CommandRequest
from tests.cli.test_cli import invoke
from tests.workflows.capture import test_capture as f
from tests.support.reminders import absolute
from tests.presentation.test_named_timezones import NY, TOKYO


class PublicNamedTimezones(unittest.TestCase):
    setUp = f.CaptureTests.setUp
    state = f.CaptureTests.state
    seed = f.CaptureTests.seed
    queue_refresh = f.CaptureTests.queue_refresh
    operation = f.CaptureTests.operation

    def call(self, argv):
        status, out, err, _ = invoke(self, argv, self.http)
        self.assertFalse(self.http.steps, (status, out, err, len(self.http.steps)))
        return status, out, err

    def test_mixed_schedule_receipts_reload_detail_retained_and_default(self):
        self.account_zone = 'Europe/Prague'
        self.seed()
        rows = [dict(i, due=f.due('2026-11-12T14:00:00Z', timezone='America/New_York'))
                if i['id'] == 'parent' else i for i in self.wire_items]
        self.operation('item_update', {'id': 'parent', 'due': {'date': '2026-11-12T14:00:00Z',
            'lang': 'en', 'timezone': 'America/New_York'}}, self.state(items=rows), 'parent')
        reminders = [absolute('tokyo', f.due('2026-11-11T23:30:00Z', timezone='Asia/Tokyo'), item_id='parent')]
        self.operation('reminder_add', {'item_id': 'parent', 'type': 'absolute', 'due': {
            'date': '2026-11-11T23:30:00Z', 'lang': 'en', 'timezone': 'Asia/Tokyo'}},
            self.state(items=rows, reminders=reminders), 'tokyo')
        start = len(self.http.calls)
        status, out, err = self.call(['task', '--due=2026-11-12 09:00 America/New_York', 'Parent',
                                      '--reminder-at', '2026-11-12 08:30 Asia/Tokyo'])
        self.assertEqual(status, 0, err)
        self.assertIn('commands', self.http.calls[start])
        self.assertIn('Due: none -> ' + NY, out)
        self.assertIn('Reminders: none -> at ' + TOKYO, out)
        saved = self.store.load_consistent_state().snapshot
        self.assertEqual(saved.items['parent'].attention.zone, 'America/New_York')
        status, out, err = self.call(['task', 'Parent'])
        self.assertEqual(status, 0, err)
        self.assertIn('Due: ' + NY + ' · ', out)
        self.assertIn('reminders:at ' + TOKYO, out)
        reminders.append(absolute('default', f.due('2026-11-12T07:00:00Z', timezone='Europe/Prague'), item_id='parent'))
        self.operation('reminder_add', {'item_id': 'parent', 'type': 'absolute', 'due': {
            'date': '2026-11-12T07:00:00Z', 'lang': 'en'}}, self.state(items=rows, reminders=reminders), 'default')
        status, out, err = self.call(['schedule', 'Parent', '--reminder-at', 'keep',
                                     '--reminder-at', '2026-11-12T08:00:00+01:00'])
        self.assertEqual(status, 0, err)
        self.assertIn('Reminders: at ' + TOKYO + ' -> at ' + TOKYO +
                      ', at 2026-11-12 08:00:00 Europe/Prague', out)
        # Omitted zone resolves in the binding account, retains the independent reminder.
        rows[0] = dict(rows[0], due=f.due('2026-11-13T08:00:00Z', timezone='Europe/Prague'))
        self.operation('item_update', {'id': 'parent', 'due': {'date': '2026-11-13T08:00:00Z', 'lang': 'en'}},
                       self.state(items=rows, reminders=reminders), 'parent')
        status, out, err = self.call(['schedule', 'Parent', '--at', '2026-11-13T09:00:00+01:00'])
        self.assertEqual(status, 0, err)
        self.assertIn(NY + ' -> 2026-11-13 09:00:00 Europe/Prague\n', out)
        self.assertIn('Reminders retained: at ' + TOKYO, out)

    def test_reminder_only_creation_uses_normalized_abbreviation_zone(self):
        self.account_zone = 'Europe/Prague'
        self.seed()
        rows = self.wire_items + [f.item('new', content='Created', priority=3)]
        self.operation('item_add', {'content': 'Created', 'project_id': 'cat', 'priority': 3, 'description': '', 'labels': [], 'auto_reminder': False, 'due': None},
                       self.state(items=rows), 'new')
        returned = absolute('new-reminder', f.due('2026-11-11T23:30:00Z', timezone='Asia/Tokyo'), item_id='new')
        self.operation('reminder_add', {'item_id': 'new', 'type': 'absolute', 'due': {
            'string': 'Friday 08:30 CET', 'lang': 'en'}}, self.state(items=rows, reminders=[returned]), 'new-reminder')
        status, out, err = self.call(['add', 'cat', 'Created', '--reminder-at=Friday 08:30 CET'])
        self.assertEqual(status, 0, err)
        self.assertIn('Created task: Created\n  Reminders: at ' + TOKYO, out)
        self.assertNotIn('Due:', out)
        self.assertNotIn('CET', out)

    def test_date_only_attention_then_unsuitable_reminder_preserves_partial_work(self):
        rows = [dict(i, due=f.due('2026-11-02', timezone=None, string='every Monday', is_recurring=True))
                if i['id'] == 'parent' else i for i in self.wire_items]
        self.operation('item_update', {'id': 'parent', 'due': {'string': 'every Monday',
            'lang': 'en', 'timezone': 'America/New_York'}}, self.state(items=rows), 'parent')
        returned = absolute('unsuitable', f.due('2026-11-02', timezone=None), item_id='parent')
        self.http.command('reminder_add', {'item_id': 'parent', 'type': 'absolute', 'due': {
            'string': 'next Monday', 'lang': 'en', 'timezone': 'Asia/Tokyo'}}, 'unsuitable')
        invalid = self.state(items=rows, reminders=[returned])
        # Both reads encounter the invalid reminder before history hydration.
        self.queue_refresh(invalid, synchronize=False)
        self.queue_refresh(invalid, synchronize=False)
        status, out, err = self.call(['schedule', 'Parent', '--at', 'every Monday America/New_York',
            '--reminder-at', 'next Monday Asia/Tokyo', '--reminder-at', 'Friday 9 CET'])
        self.assertEqual(status, 1)
        self.assertIn('Due: none -> 2026-11-02', out)
        self.assertIn('Accepted: create reminder Parent', err)
        self.assertIn('Not attempted', err)
        saved = self.store.load_consistent_state().snapshot
        self.assertEqual(saved.items['parent'].attention.kind, 'date')
        self.assertEqual(saved.items['parent'].attention.zone, None)

    def test_public_http_named_request_reconciles_and_reloads_cross_date(self):
        self.account_zone = 'Europe/Prague'
        self.seed()
        rows = [dict(i, due=f.due('2026-11-12T14:00:00Z', timezone='America/New_York'))
                if i['id'] == 'parent' else i for i in self.wire_items]
        reminder = absolute('cross', f.due('2026-11-11T15:30:00Z', timezone='Asia/Tokyo'), item_id='parent')
        due_command = CommandRequest(self, 'item_update', {'id': 'parent', 'due': {
            'date': '2026-11-12T14:00:00Z', 'timezone': 'America/New_York', 'lang': 'en'}})
        reminder_command = CommandRequest(self, 'reminder_add', {'item_id': 'parent', 'type': 'absolute',
            'due': {'date': '2026-11-11T15:30:00Z', 'timezone': 'Asia/Tokyo', 'lang': 'en'}}, target='cross')
        steps = []
        for command, state in [(due_command, self.state(items=rows)),
                               (reminder_command, self.state(items=rows, reminders=[reminder]))]:
            steps.append(command.step())
            for _ in range(1):  # Gateway current is reused for publication.
                for token, response in [('delta-token', state), ('full-token', f.delta())]:
                    steps.append((ExpectedRequest('POST', '/sync', 'secret', form={
                        'sync_token': token, 'resource_types': f.RESOURCES}),
                        Response(json.dumps(response).encode())))
        http = ControlledHTTP(steps)
        self.addCleanup(http.assert_done)
        status, out, err, _ = invoke(self, ['schedule', 'Parent', '--at', '2026-11-12 09:00 America/New_York',
            '--reminder-at', '2026-11-12 00:30 Asia/Tokyo'], Transport('secret', opener=http, sleep=lambda _: None))
        self.assertEqual(status, 0, err)
        self.assertIn('Due: none -> ' + NY, out)
        cross = '2026-11-11 16:30:00 Europe/Prague (2026-11-12 00:30:00 Asia/Tokyo)'
        self.assertIn('Reminders: none -> at ' + cross, out)
        http.assert_done()
        self.assertEqual(len(due_command.commands), 1)
        self.assertEqual(len(reminder_command.commands), 1)
        status, detail, err, factory = invoke(self, ['task', 'Parent'])
        self.assertEqual(status, 0, err)
        factory.assert_not_called()
        self.assertIn('Due: ' + NY + ' · ', detail)
        self.assertIn('reminders:at ' + cross, detail)
