"""Reusable synthetic lifecycle fixtures; no executable test cases."""
from dataclasses import replace
import io
import json
from pathlib import Path
from types import SimpleNamespace
from todo_lib import domain as d, presentation as p
from todo_lib.adapter.commands import Gateway, Result, Outcome
from todo_lib.adapter.current import retrieve
from todo_lib.local import empty_history, prepare_candidates, exclusive_lock
from todo_lib.workflows.lifecycle import LifecycleWorkflow
from tests.support.current import delta, due, BINDING
from tests.support import sync as fixtures


stamp = d.instant_from_wire
CURSOR = stamp('2026-10-22T12:00:00.123456781Z')
AT = stamp('2026-10-22T12:00:00.123456782Z')
END = stamp('2026-10-22T12:00:00.123456783Z')
LATER = stamp('2026-10-22T12:00:00.123456784Z')


class TTY(io.StringIO):
    def isatty(self):
        return True


def streams(answer='yes\n', tty=True):
    stream = TTY if tty else io.StringIO
    return p.OriginalStreams(stream(answer), stream(), io.StringIO())


def recurring(identity='R', parent=None, labels=()):
    return d.Item(identity, 'cat', identity, parent_id=parent,
        labels=frozenset(labels), attention=d.resolve_remote_due(
            due('2026-10-25', timezone=None, string='every day', is_recurring=True), 'UTC'))


class FakeSync:
    def __init__(self, snapshot, after=()):
        self.store = SimpleNamespace(root=Path('/unused'))
        self.transport = SimpleNamespace(request=self.unexpected_request)
        self.snapshot = snapshot
        self.after = iter(after)
        self.calls = []

    def unexpected_request(self, *args, **kwargs):
        raise AssertionError('ordinary selection made a remote request')

    def value(self):
        return SimpleNamespace(snapshot=self.snapshot, now=END,
            state=SimpleNamespace(cursor=CURSOR, sync_token='token',
                current_snapshot=None, current_reminder_ids=None, waiting_label_ids=None))

    def read_local(self):
        self.calls.append(('local', {}))
        return self.value()

    def refresh_locked(self, **kwargs):
        self.calls.append(('refresh', kwargs))
        return self.value()

    def reconcile_accepted_locked(self, result=None):
        self.calls.append(('accepted', {}))
        value = next(self.after, self.snapshot)
        if isinstance(value, Exception):
            raise value
        self.snapshot = value
        return self.value()


class FakeGateway:
    def __init__(self, outcomes=()):
        self.outcomes = iter(outcomes)
        self.calls = []

    def execute(self, op, **kwargs):
        self.calls.append((op, kwargs))
        value = next(self.outcomes, Outcome.ACCEPTED)
        if isinstance(value, Result):
            return replace(value, operation=op)
        return Result(value, op, actual=(d.Comment('created', op.args['item_id'], op.args['content'])
                                        if op.type == 'note_add' and value == Outcome.ACCEPTED else None))


class CommandRequest:
    """Dynamic UUID only; semantic request and response state are independent."""

    def __init__(self, case, kind, args, status='ok', target=None, *, token='delta-token', resources=None):
        from tests.support.http import Response
        self.case, self.kind, self.args = case, kind, args
        self.status, self.target = status, target
        self.token, self.resources = token, resources
        self.response = Response()
        self.commands = []

    def check(self, request, timeout):
        from urllib.parse import parse_qs
        from uuid import UUID
        from tests.support.http import ExpectedRequest
        wire = parse_qs(request.data.decode())
        if self.token is None:
            self.case.assertEqual(set(wire), {'commands'})
        else:
            self.case.assertEqual(set(wire), {'commands', 'sync_token', 'resource_types'})
            self.case.assertEqual(wire['sync_token'], [self.token])
            self.case.assertEqual(wire['resource_types'], [fixtures.RESOURCES])
        commands = json.loads(wire['commands'][0])
        self.case.assertEqual(len(commands), 1)
        op = commands[0]
        self.case.assertEqual(op['type'], self.kind)
        self.case.assertEqual(op['args'], self.args)
        self.case.assertEqual(str(UUID(op['uuid'])), op['uuid'])
        self.case.assertEqual(set(op), {'type', 'uuid', 'args'} | ({'temp_id'} if self.kind.endswith('_add') else set()))
        ExpectedRequest('POST', '/sync', 'secret', form={k: v[0] for k, v in wire.items()}).check(request, timeout)
        self.commands.append(op)
        response = {} if self.status is None else {'sync_status': {op['uuid']: self.status}}
        if self.target:
            self.case.assertEqual(str(UUID(op['temp_id'])), op['temp_id'])
            response['temp_id_mapping'] = {op['temp_id']: self.target}
        if self.resources is not None:
            response.update(self.resources)
        self.response.write(json.dumps(response).encode())
        self.response.seek(0)

    def step(self):
        return self, self.response


class LifecycleSupport:
    def setUp(self):
        self.fixture = fixtures.SyncFixture(self)
        self.store = self.fixture.store
        self.out = streams()

    def seed(self, raw, cursor=fixtures.CURSOR):
        transport, _ = self.fixture.boundary([self.fixture.sync('*', raw),
                                             self.fixture.sync('full-token', delta())])
        observed = retrieve(transport, BINDING)
        with exclusive_lock('setup', self.store.root):
            self.store.publish_snapshot(prepare_candidates(observed.snapshot,
                empty_history(observed.snapshot), account_display='Person',
                waiting_label_ids=observed.waiting_label_ids, current_snapshot=observed.snapshot, sync_token=observed.sync_token, synced_at=fixtures.INITIAL))
            self.store.write_cursor(cursor)

    def establish(self, steps, *, now=fixtures.NOW, recent=False):
        """Explicit fixture refresh, finished before the command boundary exists."""
        sync, http = self.fixture.workflow(steps, now=now)
        current = sync.refresh()
        if recent:
            from tests.support.history import retain_completed
            from todo_lib.local import load_config
            with exclusive_lock('retained fixture evidence', self.store.root):
                retain_completed(sync, current, load_config(self.store.root).hidden_from_now)
        http.assert_done()

    def workflow(self, steps, *, now=fixtures.NOW, setup=(), recent=False):
        if setup:
            self.establish(setup, now=now, recent=recent)
        sync, http = self.fixture.workflow(steps, now=now)
        return LifecycleWorkflow(sync, gateway=Gateway(sync.transport, clock=lambda: now), streams=self.out), http

    def comments(self, owner, records):
        from tests.support.history import Expected
        return Expected('/comments', [('task_id', owner), ('limit', '200')]), {'results': records, 'next_cursor': None}

    def activity(self, identity='B', records=()):
        from tests.support.history import Expected
        query = [('object_type', 'item'), ('object_id', identity),
            ('date_from', '2026-10-20T00:00:00Z'), ('date_to', '2026-10-22T12:00:01Z'),
            ('limit', '200'),
            ('object_event_types', '["item:completed", "item:uncompleted", "note:added", "note:updated", "note:deleted"]')]
        return Expected('/activities', query), {'results': list(records), 'next_cursor': None}
