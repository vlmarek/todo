"""Reusable synthetic capture fixtures; no executable test cases."""
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import tempfile
from uuid import UUID
from todo_lib import domain as d, presentation as p
from todo_lib.adapter.current import retrieve
from todo_lib.adapter.transport import Replay
from todo_lib.local import StateStore, prepare_candidates, empty_history, exclusive_lock
from todo_lib.syntax import parse
from todo_lib.workflows.sync import Synchronizer
from todo_lib.workflows.capture import CaptureWorkflow
from tests.support.current import full, delta, item, reminder, project, RESOURCES
from tests.support.fixture import Fixture


NOW = d.instant_from_wire('2026-10-22T12:00:00.123456789012350Z')
PRECISE = '2026-10-20T12:00:00.123456789012349Z'


def due(value, **kwargs):
    return dict(dict(date=value, timezone='UTC' if value.endswith('Z') else None, string='input', lang='en', is_recurring=False), **kwargs)


class Boundary:
    """Scripted responses never derive normalized state from outgoing requests."""

    def __init__(self, case):
        self.case, self.steps, self.calls = case, [], []

    def read(self, response, resources=RESOURCES):
        self.steps.append(('read', resources, deepcopy(response)))

    def completed(self, records=()):
        self.steps.append(('get', '/tasks/completed/by_completion_date', {'items': list(records)}))

    def activities(self, owner):
        self.steps.append(('get', ('/activities', owner), {'results': [], 'next_cursor': None}))

    def comments(self, owner):
        self.steps.append(('get', ('/comments', owner), {'results': [], 'next_cursor': None}))

    def command(self, kind, args, identity='new', status='ok'):
        self.steps.append(('command', (kind, args), (identity, status)))

    def request(self, method, path, **kwargs):
        if method == 'GET':
            kind, expected, response = self.steps.pop(0)
            expected_owner = None
            if isinstance(expected, tuple):
                expected, expected_owner = expected
            self.case.assertEqual((kind, path), ('get', expected))
            self.case.assertEqual(kwargs['replay'], Replay.READ)
            if path == '/comments':
                self.case.assertEqual(dict(kwargs['query'])['task_id'], expected_owner)
            elif path == '/activities':
                self.case.assertEqual(kwargs['query'], [
                    ('object_type', 'item'), ('object_id', expected_owner),
                    ('date_from', '2026-10-22T12:00:00Z'),
                    ('date_to', '2026-10-22T12:00:01Z'), ('limit', '200'),
                    ('object_event_types', '["item:completed", "item:uncompleted", "item:deleted", "note:added", "note:updated", "note:deleted"]')])
            else:
                self.case.assertEqual(dict(kwargs['query'])['project_id'], 'cat')
            self.case.assertEqual(dict(kwargs['query'])['limit'], '200')
            return deepcopy(response)
        self.case.assertEqual((method, path), ('POST', '/sync'))
        self.case.assertTrue(self.steps, 'unexpected HTTP request')
        kind, expected, response = self.steps.pop(0)
        form = kwargs['form']
        self.calls.append(deepcopy(form))
        if kind == 'read':
            self.case.assertEqual(kwargs['replay'], Replay.READ)
            self.case.assertEqual(set(form), {'sync_token', 'resource_types'})
            self.case.assertEqual(form['resource_types'], expected)
            self.case.assertIsInstance(form['sync_token'], str)
            if isinstance(response, Exception):
                raise response
            return response
        self.case.assertEqual(kwargs['replay'], Replay.IDEMPOTENT)
        commands = json.loads(form['commands'])
        self.case.assertEqual(len(commands), 1)
        command = commands[0]
        self.case.assertEqual((command['type'], command['args']), expected)
        self.case.assertEqual(str(UUID(command['uuid'])), command['uuid'])
        self.case.assertEqual(kwargs['command_uuids'], (command['uuid'],))
        identity, status = response
        result = {} if status is None else {'sync_status': {command['uuid']: status}}
        if 'temp_id' in command:
            UUID(command['temp_id'])
            self.case.assertNotEqual(command['uuid'], command['temp_id'])
            result['temp_id_mapping'] = {command['temp_id']: identity}
        return result


class CaptureSupport:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / '.todo'
        self.root.mkdir(mode=0o700)
        path = self.root / 'config'
        path.write_text('[main]\nproject=root\ndefault_sections=cat\nhidden_from_now=Later\n')
        path.chmod(0o600)
        self.store = StateStore(self.root)
        self.http = Boundary(self)
        self.wire_items = [item('parent', content='Parent', priority=3),
                           item('precise', content='Known sibling', added_at=PRECISE),
                           item('null', content='Unknown creation', added_at=None)]
        self.wire_reminders = []
        self.seed()
        self.sync = Synchronizer(self.http, self.store, clock=lambda: NOW)
        self.workflow = CaptureWorkflow(self.sync, streams=p.OriginalStreams(StringIO(), StringIO(), StringIO()))

    def state(self, items=None, reminders=None, **kwargs):
        return full(items=self.wire_items if items is None else items,
                    reminders=self.wire_reminders if reminders is None else reminders,
                    labels=getattr(self, 'wire_labels', [dict(id='waiting', name='waiting', is_deleted=False)]),
                    user={'id': 'u', 'tz_info': {'timezone': getattr(self, 'account_zone', 'UTC')}}, **kwargs)

    def seed(self):
        self.http.read(self.state())
        self.http.read(delta())
        current = retrieve(self.http, d.Binding('u', 'root', frozenset({'cat'})))
        with exclusive_lock('test', self.root):
            self.store.publish_snapshot(prepare_candidates(current.snapshot, empty_history(current.snapshot),
                account_display='Person', waiting_label_ids=current.waiting_label_ids, current_snapshot=current.snapshot, sync_token=current.sync_token, synced_at=NOW,
                initial_cursor=NOW if not (self.root / 'cursor').exists() and not (self.root / 'binding.json').exists() else None))

    def queue_refresh(self, state=None, *, synchronize=True):
        state = self.state() if state is None else state
        self.http.read(state)
        self.http.read(delta())
        if synchronize and any(i['due'] and i['due']['is_recurring'] for i in state['items']):
            self.http.completed()
            for owner in sorted(i['id'] for i in state['items']
                                if i['due'] and i['due']['is_recurring']):
                self.http.activities(owner)

    def refresh(self, state=None, *, synchronize=True):
        """Legitimate explicit refresh setup, completed before command execution."""
        self.queue_refresh(state, synchronize=synchronize)
        self.sync.refresh()

    def operation(self, kind, args, state, identity='new', status='ok'):
        self.http.command(kind, args, identity, status)
        self.queue_refresh(state, synchronize=False)  # gateway's authoritative reads
        if kind == 'project_add' and status == 'ok':
            self.queue_refresh(state)  # provisioning keeps full refresh policy

    def run_request(self, argv):
        result = self.workflow.execute(parse(argv))
        self.assertFalse(self.http.steps, 'unconsumed boundary expectations')
        return result


class CaptureFixture(CaptureSupport, Fixture):
    """Standalone fixture with cleanup owned by its calling test."""
