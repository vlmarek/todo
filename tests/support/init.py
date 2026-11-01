"""Reusable synthetic init fixtures; no executable test cases."""
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import tempfile
from urllib.parse import parse_qs
from uuid import UUID
from todo_lib import domain as d
from todo_lib.adapter.transport import Transport
from todo_lib.local import StateStore
from todo_lib.workflows.init import Initializer
from tests.support.current import full, delta, project, item, note, RESOURCES
from tests.support.http import ExpectedRequest, Response


CREATED = '2026-10-20T12:00:00.123456789012345Z'
POSTED = '2026-10-21T12:00:00.123456789012349Z'
NOW = d.instant_from_wire('2026-10-22T12:00:00.123456789012350Z')
LATER = d.instant_from_wire('2026-10-23T12:00:00.123456789012351Z')
LABEL = dict(id='waiting-id', name='waiting', is_deleted=False)
CONFIG = b'[main]\nproject=root\ndefault_sections=cat\nhidden_from_now=\n[todoist]\ntoken=secret\n'


class Terminal(StringIO):
    def isatty(self):
        return True


class Boundary:
    """Exact read forms and one authorized project/label creation at a time."""

    def __init__(self, rounds=(), *, remote=None, expected=(), rejected=None):
        self.rounds = list(rounds)
        self.remote = full(labels=[LABEL]) if remote is None else deepcopy(remote)
        self.expected = list(expected)
        self.rejected = rejected
        self.requests, self.mutations = [], []
        self.fresh = False
        self.provision_fresh = False

    def __call__(self, request, *, timeout):
        self.requests.append(request)
        form = {k: v[0] for k, v in parse_qs(request.data.decode(), keep_blank_values=True).items()}
        if 'commands' in form:
            if set(form) != {'commands'}:
                raise AssertionError('unexpected command fields')
            commands = json.loads(form['commands'])
            if len(commands) != 1:
                raise AssertionError('one operation required')
            op = commands[0]
            if set(op) != {'type', 'uuid', 'temp_id', 'args'}:
                raise AssertionError('incorrect command structure')
            UUID(op['uuid']); UUID(op['temp_id'])
            if not self.expected or (op['type'], op['args']) != self.expected.pop(0):
                raise AssertionError('unexpected provisioning request')
            self.mutations.append(op)
            identity = 'created-' + str(len(self.mutations))
            if op['type'] == 'project_add':
                value = project(identity, op['args']['parent_id'], name=op['args']['name'])
                collection = 'projects'
            elif op['type'] == 'label_add':
                value = dict(id=identity, name=op['args']['name'], is_deleted=False)
                collection = 'labels'
            else:
                raise AssertionError('unauthorized mutation')
            if self.rejected == len(self.mutations):
                result = {'sync_status': {op['uuid']: {'error_code': 20, 'error': 'controlled rejection'}}}
            else:
                self.remote[collection].append(value)
                result = {'sync_status': {op['uuid']: 'ok'}, 'temp_id_mapping': {op['temp_id']: identity}}
        else:
            resources = form.get('resource_types')
            if resources == RESOURCES:
                if form.get('sync_token') != ('full-token' if self.fresh else '*'):
                    raise AssertionError('incorrect current token')
                if self.fresh:
                    result = getattr(self, 'freshness', delta())
                else:
                    value = self.rounds.pop(0) if self.rounds else deepcopy(self.remote)
                    result, self.freshness = value if isinstance(value, tuple) else (value, delta())
                self.fresh = not self.fresh
            elif resources == '["projects","labels"]':
                if form.get('sync_token') != ('provision-token' if self.provision_fresh else '*'):
                    raise AssertionError('incorrect provision token')
                result = (dict(full_sync=False, sync_token='provision-delta') if self.provision_fresh else
                          dict(full_sync=True, sync_token='provision-token',
                               projects=self.remote['projects'], labels=self.remote['labels']))
                self.provision_fresh = not self.provision_fresh
            else:
                raise AssertionError('unexpected resources or activity prerequisite')
            if set(form) != {'sync_token', 'resource_types'}:
                raise AssertionError('incorrect read fields')
        ExpectedRequest('POST', '/sync', 'secret', form=form).check(request, timeout)
        if isinstance(result, Response):
            return result
        return Response(json.dumps(result).encode())

    def assert_done(self):
        if self.rounds or self.expected:
            raise AssertionError('missing expected reads or creations')


class InitSupport:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / '.todo'
        self.store = StateStore(self.root)

    def put(self, name, data, mode=0o600):
        self.root.mkdir(mode=0o700, exist_ok=True)
        path = self.root / name
        path.write_bytes(data)
        path.chmod(mode)

    def bytes(self):
        return {p.name: p.read_bytes() for p in self.root.iterdir() if p.name != 'lock'} if self.root.exists() else {}

    def run_init(self, boundary=None, *, answers='', hidden=None, env=None, now=NOW,
                 stdin=None, stdout=None, clock=None, **kwargs):
        boundary = Boundary() if boundary is None else boundary
        out = Terminal() if stdout is None else stdout
        err = Terminal()
        workflow = Initializer(store=self.store,
            transport_factory=lambda token: Transport(token, opener=boundary, sleep=lambda _: None),
            clock=clock or (lambda: now), environ={} if env is None else env,
            stdin=Terminal(answers) if stdin is None else stdin, stdout=out, stderr=err,
            hidden_reader=hidden, **kwargs)
        result = workflow.run()
        boundary.assert_done()
        return result, out.getvalue(), err.getvalue()

    def initialize_existing(self, payload=None):
        self.put('config', CONFIG)
        payload = full(labels=[LABEL], items=[item(added_at=CREATED)], notes=[note(posted_at=POSTED)]) if payload is None else payload
        result, _, _ = self.run_init(Boundary([payload, payload]))
        return result

    def assert_protected(self):
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        for p in self.root.iterdir():
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            self.assertFalse(p.name.startswith('.todo-candidate-'))
