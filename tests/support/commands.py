"""Reusable synthetic commands fixtures; no executable test cases."""
from datetime import datetime, timezone
import json
from uuid import UUID
from todo_lib.adapter.commands import Gateway
from todo_lib.adapter.current import Current
from todo_lib.adapter.history import HistoryError, Retrieval
from todo_lib.adapter.transport import OutcomeUnknown, Replay
from todo_lib.domain import (
    Account,
    Binding,
    Capabilities,
    Item,
    Project,
    Snapshot,
    instant_from_wire as stamp,
    instant_key,
    validate,
)
from tests.support.current import item, delta, RESOURCES


AT = '2026-10-20T12:00:00.123456789Z'
NEXT = '2026-10-20T12:00:00.123456790Z'
START = stamp('2026-10-20T12:00:00.123456780Z')
END = stamp('2026-10-20T12:00:00.123456799Z')
NOW = datetime(2026, 10, 20, 12, 1, tzinfo=timezone.utc)


def due(date='2026-10-21T10:00:00.123456789Z', **kw):
    return dict(date=date, timezone=None, string='tomorrow at 10', lang='en', is_recurring=False, **kw)


def before(*items, comments=(), occurrences=()):
    binding = Binding('u', 'root', frozenset({'cat', 'other'}))
    snapshot = Snapshot(binding, Account('u', 'UTC', Capabilities(True, True, -1)),
        Project('root', 'Root'), {'cat': Project('cat', 'Category', 'root'),
        'other': Project('other', 'Other', 'root')},
        {i.id: i for i in items or (Item('task', 'cat', 'Original', added_at=stamp(AT)),)},
        {c.id: c for c in comments}, {}, {o.id: o for o in occurrences})
    return Current(validate(snapshot), 'prior-token', current_snapshot=snapshot)


class Wire:
    """Checks one command, then consumes independently supplied read responses."""

    def __init__(self, case, kind, args, read, status='ok', mapping='new', lost=False, token='prior-token'):
        self.case, self.kind, self.args = case, kind, args
        self.read = list(read)
        self.status, self.mapping, self.lost = status, mapping, lost
        self.commands, self.reads = [], []
        self.command = None
        self.token = token

    def request(self, method, path, **kw):
        self.case.assertEqual((method, path), ('POST', '/sync'))
        form = kw['form']
        if 'commands' in form:
            self.case.assertEqual(kw['replay'], Replay.IDEMPOTENT)
            if self.kind in ('project_add', 'label_add'):
                self.case.assertEqual(set(form), {'commands'})
            else:
                self.case.assertEqual(set(form), {'commands', 'sync_token', 'resource_types'})
                self.case.assertEqual(form['sync_token'], self.token)
                self.case.assertEqual(form['resource_types'], RESOURCES)
            commands = json.loads(form['commands'])
            self.case.assertEqual(len(commands), 1)
            command = commands[0]
            self.case.assertEqual(command['type'], self.kind)
            self.case.assertEqual(command['args'], self.args)
            self.case.assertEqual(str(UUID(command['uuid'])), command['uuid'])
            self.case.assertEqual(kw['command_uuids'], (command['uuid'],))
            if self.kind.endswith('_add'):
                self.case.assertEqual(str(UUID(command['temp_id'])), command['temp_id'])
                self.case.assertNotEqual(command['uuid'], command['temp_id'])
            else:
                self.case.assertNotIn('temp_id', command)
            self.commands.append(command)
            self.case.assertEqual(len(self.commands), 1, 'no replay or compensation')
            self.command = command
            if self.lost:
                raise OutcomeUnknown('lost response', outcome='unknown')
            return self.receipt()
        self.case.assertEqual(kw['replay'], Replay.READ)
        self.case.assertEqual(set(form), {'sync_token', 'resource_types'})
        self.reads.append(form)
        self.case.assertTrue(self.read, 'unexpected extra read')
        result = self.read.pop(0)
        return result(self) if callable(result) else result

    def receipt(self):
        result = {}
        if self.status is not None:
            result['sync_status'] = {self.command['uuid']: self.status}
        if 'temp_id' in self.command and self.mapping is not None:
            result['temp_id_mapping'] = {self.command['temp_id']: self.mapping}
        return result

    def done(self):
        self.case.assertFalse(self.read, 'missing reconciliation reads')
        self.case.assertEqual(len(self.commands), 1)


class History:
    def __init__(self, records=(), comments=(), activities=(), failure=False):
        self.records, self.notes, self.events = records, comments, activities
        self.calls, self.failure = [], failure

    def completed(self, start, end, scope):
        self.calls.append(('completed', instant_key(start), instant_key(end), scope))
        if self.failure:
            raise HistoryError('incomplete bounded history')
        return Retrieval(tuple(self.records), (), start, end,
                         '/tasks/completed/by_completion_date', tuple(scope.items()))

    def comments(self, owner):
        self.calls.append(('comments', owner))
        return Retrieval(tuple(self.notes), (), endpoint='/comments', owner_id=owner)

    def activities(self, start, end, scope):
        self.calls.append(('activities', scope))
        return Retrieval(tuple(self.events), (), start, end, '/activities', tuple(scope.items()))


class CommandSupport:
    def gateway(self, kind, args, read=None, history=None, **kw):
        wire = Wire(self, kind, args, [delta()] if read is None else read, **kw)
        self.addCleanup(wire.done)
        return Gateway(wire, history=history, clock=lambda: NOW), wire
