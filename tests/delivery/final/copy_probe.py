"""Standalone offline copy acceptance, never imports source/tests.

Synthetic fixtures: retained api-v1.openapi.json Sync read/command tables,
ItemSyncView, NoteSyncView; completed/by_completion_date terminal omission;
activities and scoped comments results/next_cursor. Inspected 2026-10-26.
PersonalProjectSyncView/WorkspaceProjectSyncView require is_shared; retained Sync
prose says shared instead. This literal follows the typed schemas.
Not a live provider emulator. Each phase starts a new interpreter.
"""
from contextlib import ExitStack
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import runpy
import shutil
import socket
import subprocess
import sys
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

CREATED = '2026-10-20T12:00:00.123456789012345Z'
EARLY = '2026-10-21T12:00:00.123456789012348Z'
LATE = '2026-10-21T12:00:00.123456789012349Z'
INITIAL = '2026-10-20T13:00:00Z'
CURSOR = '2026-10-20T00:00:00Z'
DONE = '2026-10-21T13:00:00.123456789012349Z'
END = '2026-10-22T12:00:00.123456789012350Z'
NEWER = '2026-10-22T12:00:00.123456789012351Z'
FINAL = '2026-10-22T12:00:01.123456789012352Z'
TOKEN = 'synthetic-delivery-token'
RESOURCES = '["user","user_plan_limits","projects","items","labels","notes","reminders"]'


def item(identity, parent=None, **changes):
    return dict(id=identity, project_id='cat', parent_id=parent, content=identity,
        priority=4, checked=False, labels=[], due=None, added_at=CREATED,
        completed_at=None, is_deleted=False, **changes)


def a():
    row = item('A'); row.update(content='Alpha', added_at=None)
    return row


def notes(future=False):
    rows = [dict(id=k, item_id='B', content=text, posted_at=at,
        is_deleted=False, file_attachment=None) for k, text, at in
        [('early', 'Earlier own text', EARLY), ('late', 'Later own text', LATE)]]
    if future:
        rows.append(dict(id='future', item_id='D', content='Newer pending work', posted_at=NEWER,
                         is_deleted=False, file_attachment=None))
    return rows


def full(rows, comments=()):
    return dict(full_sync=True, sync_token='full-token',
        user={'id': 'u', 'tz_info': {'timezone': 'Europe/Prague'}},
        user_plan_limits={'current': {'activity_log': True, 'activity_log_limit': -1, 'reminders': False}},
        projects=[dict(id=i, name=i, parent_id=p, is_shared=False, is_archived=False, is_deleted=False)
                  for i, p in [('root', None), ('cat', 'root')]],
        labels=[dict(id='waiting', name='waiting', is_deleted=False)],
        items=rows, notes=list(comments), reminders=[])


def delta(**changes):
    return dict(full_sync=False, sync_token='delta-token', **changes)


def sync(token, response):
    return ('POST', '/sync', {'sync_token': [token], 'resource_types': [RESOURCES]}, response)


def rest(path, query, response):
    return ('GET', path, {k: [v] for k, v in query.items()}, response)


def own(owner, future=False):
    return rest('/comments', dict(task_id=owner, limit='200'),
        dict(results=[{k: v for k, v in n.items() if k != 'item_id'}
                      for n in notes(future) if n['item_id'] == owner], next_cursor=None))


def completed(lower=CURSOR, upper='2026-10-22T12:00:01Z'):
    row = item('B', 'A'); row.update(checked=True, completed_at=DONE)
    return rest('/tasks/completed/by_completion_date', dict(project_id='cat', since=lower,
        until=upper, limit='200'), {'items': [row]})


class Boundary:
    def __init__(self, steps):
        self.steps = list(steps)
        self.errors = []

    def __call__(self, request, *, timeout):
        try:
            assert self.steps, 'extra HTTP'
            method, path, values, response = self.steps.pop(0)
            url = urlsplit(request.full_url)
            assert url.scheme == 'https' and url.netloc == 'api.todoist.com'
            assert url.path == '/api/v1' + path and not url.fragment
            assert request.get_method() == method and timeout == 30
            assert request.get_header('Authorization') == 'Bearer ' + TOKEN
            if method == 'POST':
                assert not url.query and request.get_header('Content-type') == 'application/x-www-form-urlencoded'
                actual = parse_qs(request.data.decode(), keep_blank_values=True)
            else:
                assert request.data is None
                actual = parse_qs(url.query, keep_blank_values=True)
            if callable(response):
                result = response(actual)
            else:
                assert actual == values, (path, actual, values)
                result = response
            reply = BytesIO(json.dumps(result).encode())
            reply.status, reply.headers = 200, {}
            return reply
        except BaseException as error:
            self.errors.append(str(error)); raise

    def done(self):
        assert not self.errors, self.errors
        assert not self.steps, ('missing HTTP', [(s[0], s[1]) for s in self.steps])


def phase(install, name):
    sys.path.insert(0, str(install))
    from todo_lib import cli, domain as d
    from todo_lib.adapter.transport import Transport
    from todo_lib.local import StateStore
    from todo_lib.workflows.init import Initializer
    from todo_lib.workflows.sync import Synchronizer
    from todo_lib.workflows.report import Reporter
    assert Path(cli.__file__).is_relative_to(install)
    assert not any(k == 'tests' or k.startswith('tests.') for k in sys.modules)
    assert Path(shutil.which('todo')).resolve() == install / 'todo'
    store = StateStore()

    def call(argv, steps=(), now=END, failure=None, expected_status=0):
        if name in ('tolerance', 'tolerance-read'):
            now = FINAL
        boundary = Boundary(steps)
        wire = Transport(TOKEN, opener=boundary, sleep=lambda _: None)
        output, error = StringIO(), StringIO()
        with ExitStack() as stack:
            stack.enter_context(patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')))
            stack.enter_context(patch.object(cli, 'Transport', return_value=wire))
            stack.enter_context(patch.object(cli, 'Initializer', side_effect=lambda **kw: Initializer(**kw, clock=lambda: d.instant_from_wire(now))))
            stack.enter_context(patch.object(cli, 'Synchronizer', side_effect=lambda t, s: Synchronizer(t, s, clock=lambda: d.instant_from_wire(now))))
            stack.enter_context(patch.object(cli, 'Reporter', side_effect=lambda t, s, **kw: Reporter(t, s, clock=lambda: d.instant_from_wire(now), **kw)))
            stack.enter_context(patch.object(sys, 'stdout', output))
            stack.enter_context(patch.object(sys, 'stderr', error))
            stack.enter_context(patch.object(sys, 'stdin', StringIO()))
            stack.enter_context(patch.object(sys, 'argv', ['todo', *argv]))
            if failure:
                stack.enter_context(patch('todo_lib.local.store.StateStore.write_cursor', side_effect=OSError('controlled cursor failure')))
            try:
                runpy.run_path(shutil.which('todo'), run_name='__main__')
            except SystemExit as result:
                status = result.code
            else:
                raise AssertionError('launcher did not exit')
        assert status == (1 if failure else expected_status), (argv, status, error.getvalue(), boundary.errors)
        boundary.done()
        return output.getvalue()

    def report_steps(last=False):
        lower = '2026-10-22T12:00:00Z' if last else CURSOR
        upper = '2026-10-22T12:00:02Z' if last else '2026-10-22T12:00:01Z'
        return [sync('*', full([a(), item('D', 'A')], notes(True)[2:])), sync('full-token', delta()),
            completed(lower, upper), rest('/activities', dict(date_from=lower, date_to=upper,
                limit='200', object_event_types='unused'), {})]

    # Pinned activities parameter and "Multiple event types" example: one JSON value.
    def reports(last=False):
        steps = report_steps(last)
        method, path, query, _ = steps[-1]
        query['object_event_types'] = ['["item:completed", "item:uncompleted", "note:added", "note:updated", "note:deleted"]']
        steps[-1] = (method, path, query, {'results': [], 'next_cursor': None})
        return steps + ([own('B', True)] if last else [own('B', True), own('B', True)]) + [own('A', True), own('D', True)]

    if name in ('tolerance', 'tolerance-read'):
        # Source: pinned api-v1.openapi.json NoteSyncView.content default and
        # NotificationSyncView.due / Due dates / Sync Add a reminder. Synthetic
        # dates, Spanish wording and ownership; no live recurrence assertion.
        from todo_lib.workflows.comments import CommentWorkflow
        row = item('E')
        row['content'] = 'Amendment\nline\ttab'
        blank = dict(id='blank', item_id='E', posted_at=EARLY, is_deleted=False)
        text = dict(id='text', item_id='E', posted_at=LATE, is_deleted=False,
                    content='Retained text')
        comments = [blank, text, dict(text, file_attachment={
            'file_type': 'file', 'file_url': 'https://example.invalid/synthetic'})]
        schedule = dict(date='2026-10-30T08:00:00Z', timezone='Europe/Madrid',
                        string='cada día a las 9', lang='es', is_recurring=True)
        reminder = dict(id='absolute', item_id='E', type='absolute', due=schedule,
                        notify_uid='u', is_urgent=False, is_deleted=False)
        def accepted(kind, args, created=False):
            def response(form):
                assert set(form) == {'commands'}
                commands = json.loads(form['commands'][0]); assert len(commands) == 1
                op = commands[0]
                assert set(op) == ({'type', 'uuid', 'args', 'temp_id'} if created else
                                   {'type', 'uuid', 'args'})
                UUID(op['uuid'])
                assert (op['type'], op['args']) == (kind, args)
                reply = {'sync_status': {op['uuid']: 'ok'}}
                if created:
                    UUID(op['temp_id']); assert op['temp_id'] != op['uuid']
                    reply['temp_id_mapping'] = {op['temp_id']: 'absolute'}
                return reply
            return ('POST', '/sync', None, response)
        def reconciled(**changes):
            # Gateway reads actual outcome; Synchronizer independently publishes.
            return [sync('delta-token', delta(**changes)), sync('delta-token', delta(**changes))]
        if name == 'tolerance':
            state = full([a(), item('D', 'A'), row], notes(True)[2:] + comments)
            state['user_plan_limits']['current']['reminders'] = True
            out = call(['task', 'Amendment', '--refresh'],
                       [sync('delta-token', state), sync('full-token', delta())])
            assert '[no text]' in out and out.count('Retained text') == 1
            original = store.load_consistent_state().snapshot.comments
            def unchanged(buffer):
                assert '[id: blank posted:' in buffer and '[no text]' not in buffer
                return buffer.replace('\n', '\r\n')
            with patch.object(CommentWorkflow, '_edit', side_effect=unchanged):
                call(['comment', '--edit', 'Amendment'], [sync('delta-token', delta())])
            assert store.load_consistent_state().snapshot.comments == original
            out = call(['schedule', 'Amendment', '--reminder-at', 'every day at nine'],
                [sync('delta-token', delta()), accepted('reminder_add', {
                    'item_id': 'E', 'type': 'absolute',
                    'due': {'string': 'every day at nine', 'lang': 'en'}}, True),
                 *reconciled(reminders=[reminder])])
            assert 'cada día a las 9' in out and 'every day at nine' not in out
            assert r'Amendment\nline\ttab' in out
            assert store.load_consistent_state().snapshot.items['E'].attention is None
        else:
            # A new interpreter consumes only published files, with no HTTP read.
            saved = store.load_consistent_state().snapshot
            assert saved.reminders['absolute'].due.language == 'es'
            out = call(['task', 'Amendment'])
            assert '[no text]' in out and 'cada día a las 9' in out
            out = call(['schedule', 'Amendment', '--reminder-at', 'every Monday at 9am'],
                       [sync('delta-token', delta())], expected_status=1)
            assert r'Reminder replacement for: Amendment\nline\ttab' in out
            assert 'expression (Todoist): every Monday at 9am' in out
            assert '--reminder-at keep' in out and '[y/N]' not in out
            assert store.load_consistent_state().snapshot.reminders == saved.reminders
            row['due'] = dict(date='2026-10-23', lang='en', string='tomorrow', is_recurring=False)
            out = call(['schedule', 'Amendment', '--at', 'tomorrow', '--reminder-at', 'keep'],
                [sync('delta-token', delta()), accepted('item_update', {
                    'id': 'E', 'due': {'date': '2026-10-23', 'lang': 'en'}}),
                 *reconciled(items=[row])])
            assert 'Reminder replacement' not in out
            assert store.load_consistent_state().snapshot.reminders == saved.reminders
            out = call(['schedule', 'Amendment', '--reminder', 'clear'],
                [sync('delta-token', delta()), accepted('reminder_delete', {'id': 'absolute'}),
                 *reconciled(reminders=[{'id': 'absolute', 'is_deleted': True}])])
            assert '[y/N]' not in out
            state = store.load_consistent_state().snapshot
            assert not state.reminders and state.items['E'].attention is not None
    elif name == 'init':
        store.root.mkdir(mode=0o700)
        config = store.root / 'config'
        config.write_text('[main]\nproject=root\ndefault_sections=cat\nhidden_from_now=\n')
        config.chmod(0o600)
        rows = [item('A'), item('B', 'A')]
        steps = [sync('*', full(rows, notes())), sync('full-token', delta())] * 2
        assert 'Initialized' in call(['init'], steps, INITIAL)
        call(['report', '--set-cursor', CURSOR, '--yes'])
    elif name == 'mutation':
        def accepted(form):
            assert set(form) == {'commands'}
            commands = json.loads(form['commands'][0]); assert len(commands) == 1
            op = commands[0]
            assert set(op) == {'type', 'uuid', 'args'}
            UUID(op['uuid'])
            assert op['type'] == 'item_update' and op['args'] == {'id': 'A', 'content': 'Alpha'}
            return {'sync_status': {op['uuid']: 'ok'}}
        changed = item('A'); changed['content'] = 'Alpha'
        steps = [sync('delta-token', delta()), ('POST', '/sync', None, accepted),
                 sync('delta-token', delta(items=[changed])), sync('delta-token', delta(items=[changed]))]
        assert 'Alpha' in call(['rename', 'A', '--to', 'Alpha'], steps, INITIAL)
    elif name == 'repeat':
        rows = [a(), item('B', 'A')]
        # Actual preflight null supersedes old value even when final reads omit it.
        steps = [sync('*', full(rows, notes())), sync('full-token', delta()),
                 sync('*', full([])), sync('full-token', delta())]
        call(['init'], steps, INITIAL)
        state = store.load_consistent_state()
        assert not state.snapshot.items
        assert state.history.snapshot.items['A'].added_at is None
        assert state.history.snapshot.items['A'].title == 'Alpha'
        assert d.instant_text(state.cursor) == CURSOR
        assert state.history.snapshot.comments['late'].body == 'Later own text'
    elif name in ('external', 'rebuild'):
        rows = [a(), item('D', 'A')]
        steps = [sync('*' if name == 'rebuild' else 'delta-token', full(rows, notes(True)[2:])),
                 sync('full-token', delta()), completed(), own('B')]
        args = ['task', 'Alpha', '--refresh']
        if name == 'rebuild': args += ['--clear-cache']
        out = call(args, steps)
        assert out.index('Earlier own text') < out.index('Later own text')
        state = store.load_consistent_state()
        assert not state.snapshot.items['A'].completed and state.snapshot.items['B'].completed
        assert state.snapshot.items['A'].added_at is None
        assert d.instant_text(state.snapshot.items['B'].added_at) == CREATED
        assert d.instant_text(state.snapshot.comments['late'].added_at) == LATE
        assert d.instant_text(next(iter(state.snapshot.occurrences.values())).completed_at) == DONE
    elif name == 'read':
        out = call(['Alpha'])
        assert out.index('Earlier own text') < out.index('Later own text')
        assert 'B' in call(['search', '--all', 'Later own text'])
        assert 'Alpha' in call(['now'])
    elif name in ('preview', 'failure', 'final', 'cleanup'):
        before = (store.root / 'report-cursor').read_bytes()
        final = name != 'preview'
        out = call(['report'] + (['--final'] if final else []), reports(name == 'cleanup'),
                   FINAL if name == 'cleanup' else END, failure=name == 'failure')
        if name != 'cleanup': assert 'B' in out and 'Alpha' in out
        state = store.load_consistent_state()
        if name in ('preview', 'failure'):
            assert (store.root / 'report-cursor').read_bytes() == before
            assert 'B' in state.history.snapshot.items and 'late' in state.history.snapshot.comments
        elif name == 'final':
            assert d.instant_text(state.cursor) == END
            assert set(state.history.snapshot.items) == {'A', 'D'}
            assert 'future' in state.history.snapshot.comments
        else:
            assert d.instant_text(state.cursor) == FINAL
            assert not state.history.snapshot.items
    else:
        raise AssertionError(name)
    for module in list(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename and 'todo_lib' in str(filename):
            assert Path(filename).resolve().is_relative_to(install)
    print('copied: ' + name + ' passed (separate process, zero network)')


if __name__ == '__main__':
    install = Path(sys.argv[1]).resolve()
    if len(sys.argv) == 3:
        phase(install, sys.argv[2])
    else:
        for name in ('init', 'mutation', 'repeat', 'external', 'read', 'rebuild', 'read',
                     'preview', 'failure', 'final', 'cleanup', 'tolerance', 'tolerance-read'):
            subprocess.run([sys.executable, '-I', '-B', __file__, str(install), name],
                           check=True, timeout=10)
