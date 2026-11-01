"""Reusable synthetic comments fixtures; no executable test cases."""
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import shlex
import sys
import tempfile
from uuid import UUID
from todo_lib import domain as d
from todo_lib import presentation as p
from todo_lib.adapter.current import retrieve
from todo_lib.adapter.transport import Replay
from todo_lib.local import LockBusy, StateStore, empty_history, exclusive_lock, prepare_candidates
from todo_lib.workflows import Synchronizer
from todo_lib.workflows.comments import CommentWorkflow, CommentError, encode_buffer
from tests.support.current import BINDING, RESOURCES, full, delta, item, note
from tests.support.fixture import Fixture


OLD = '2026-10-21T12:00:00.123456789012348Z'
NEW = '2026-10-21T12:00:00.123456789012349Z'
NOW = d.instant_from_wire('2026-10-22T12:00:00.123456789012350Z')
CURSOR = d.instant_from_wire('2026-10-20T00:00:00Z')


class Terminal(StringIO):
    def isatty(self):
        return True


class Boundary:
    def __init__(self, case):
        self.case, self.steps, self.commands = case, [], []
        self.lock_root = None

    def request(self, method, path, **kwargs):
        if self.lock_root:
            with self.case.assertRaises(LockBusy), exclusive_lock('probe', self.lock_root):
                pass
        self.case.assertTrue(self.steps, 'unexpected request')
        expected_method, expected_path, expected, reply = self.steps.pop(0)
        self.case.assertEqual((method, path), (expected_method, expected_path))
        if callable(expected):
            command = expected(kwargs)
            return reply(command)
        self.case.assertEqual(kwargs['replay'], Replay.READ)
        for key, value in expected.items():
            self.case.assertEqual(kwargs[key], value)
        if isinstance(reply, BaseException):
            raise reply
        return deepcopy(reply)

    def sync(self, token, reply):
        self.steps.append(('POST', '/sync', {'form': {'sync_token': token, 'resource_types': RESOURCES}}, reply))

    def command(self, kind, args, status='ok', identity='new-comment'):
        def check(kwargs):
            self.case.assertEqual(kwargs['replay'], Replay.IDEMPOTENT)
            self.case.assertEqual(kwargs['operation'], kind)
            self.case.assertEqual(set(kwargs['form']), {'commands', 'sync_token', 'resource_types'})
            self.case.assertEqual(kwargs['form']['resource_types'], RESOURCES)
            self.case.assertEqual(kwargs['form']['sync_token'], 'delta-token')
            commands = json.loads(kwargs['form']['commands'])
            self.case.assertEqual(len(commands), 1)
            command = commands[0]
            self.case.assertEqual(command['type'], kind)
            self.case.assertEqual(command['args'], args)
            self.case.assertEqual(str(UUID(command['uuid'])), command['uuid'])
            self.case.assertEqual(kwargs['command_uuids'], (command['uuid'],))
            if kind == 'note_add':
                self.case.assertEqual(set(command), {'type', 'args', 'uuid', 'temp_id'})
                self.case.assertEqual(str(UUID(command['temp_id'])), command['temp_id'])
                self.case.assertNotEqual(command['temp_id'], command['uuid'])
            else:
                self.case.assertEqual(set(command), {'type', 'args', 'uuid'})
            self.commands.append(command)
            return command
        def reply(command):
            if status == 'interrupt':
                raise KeyboardInterrupt
            result = {} if status is None else {'sync_status': {command['uuid']: status}}
            if kind == 'note_add':
                result['temp_id_mapping'] = {command['temp_id']: identity}
            return result
        self.steps.append(('POST', '/sync', check, reply))

    def comments(self, notes, *, pages=False, malformed=False):
        rows = [{k: v for k, v in n.items() if k != 'item_id'}
                for n in notes if n['item_id'] == 'C']
        if malformed:
            rows[0].pop('posted_at')
        query = [('task_id', 'C'), ('limit', '200')]
        if pages:
            self.steps.append(('GET', '/comments', {'query': query},
                               {'results': rows[:1], 'next_cursor': 'page.two', 'unknown': 42}))
            query = [*query, ('cursor', 'page.two')]
            rows = rows[1:]
        self.steps.append(('GET', '/comments', {'query': query}, {'results': rows, 'next_cursor': None}))

    def done(self):
        self.case.assertFalse(self.steps, 'missing requests')


def tree(notes):
    return full(user={'id': 'u', 'tz_info': {'timezone': 'UTC'}},
                items=[item('A', content='Root'), item('B', content='Branch', parent_id='A'),
                       item('C', content='Leaf', parent_id='B')], notes=notes)


class CommentSupport:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / '.todo'
        self.root.mkdir(mode=0o700)
        config = self.root / 'config'
        config.write_text('[main]\nproject=root\ndefault_sections=cat\nhidden_from_now=\n')
        config.chmod(0o600)
        self.store = StateStore(self.root)
        self.wire = Boundary(self)
        self.addCleanup(self.wire.done)
        self.notes = [note('a-newer', 'C', content='newer', posted_at=NEW),
                      note('z-older', 'C', content='older', posted_at=OLD),
                      note('unknown', 'C', content='unknown', posted_at=None),
                      note('parent-note', 'A', content='parent only', posted_at=OLD)]
        self.wire.sync('*', tree(self.notes))
        self.wire.sync('full-token', delta())
        observed = retrieve(self.wire, BINDING)
        with exclusive_lock('init', self.root):
            self.store.publish_snapshot(prepare_candidates(observed.snapshot,
                empty_history(observed.snapshot), account_display='Person', waiting_label_ids=observed.waiting_label_ids, current_snapshot=observed.snapshot, sync_token=observed.sync_token,
                synced_at=NOW, initial_cursor=CURSOR))
        self.wire.lock_root = self.root
        self.streams = p.OriginalStreams(StringIO(), StringIO(), StringIO())
        self.sync = Synchronizer(self.wire, self.store, clock=lambda: NOW)
        self.editor_code = ''
        self.environ = {}
        self.workflow = CommentWorkflow(self.sync, streams=self.streams, environ=self.environ)

    def queue_refresh(self, notes=None):
        self.wire.sync('delta-token', tree(self.notes if notes is None else notes))
        self.wire.sync('full-token', delta())

    def refresh(self, notes=None):
        """Publish through explicit refresh before starting the selected command."""
        self.queue_refresh(notes)
        self.sync.refresh()

    def owner_comments(self):
        return tuple(c for c in self.store.load_consistent_state().snapshot.comments.values() if c.item_id == 'C')

    def editor(self, code='', exit_code=0):
        # Spaces in executable path and metacharacters in a literal argument
        # distinguish shlex/direct argv from a shell launch.
        path = Path(self.temp.name) / 'controlled editor.py'
        path.write_text('import sys, os, stat, fcntl\nfrom pathlib import Path\n'
            'assert sys.argv[1] == "literal ; $(no-shell)"\n'
            'path = Path(sys.argv[-1])\n'
            'assert stat.S_IMODE(path.stat().st_mode) == 0o600\n'
            'fd = os.open(path.parent / "lock", os.O_RDWR)\n'
            'try:\n fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n'
            'except BlockingIOError:\n pass\n'
            'else:\n raise AssertionError("editor lock not held")\n'
            'os.close(fd)\ntext = path.read_text()\n' + code + f'\nsys.exit({exit_code})\n')
        self.environ['VISUAL'] = ' '.join(map(shlex.quote, (sys.executable, str(path), 'literal ; $(no-shell)')))
        self.environ['EDITOR'] = '/does-not-exist'

    def save(self, text):
        self.editor(f'path.write_text({text!r})')

    def cleaned(self):
        self.assertEqual(list(self.root.glob('comment-*.txt')), [])
        self.assertEqual(list(self.root.glob('.todo-candidate-*')), [])
        with exclusive_lock('test', self.root):
            pass

    def edit(self):
        return self.workflow.execute(['comment', '--edit', 'Leaf'])

    def operation(self, kind, args, notes, *, status='ok', identity='new-comment'):
        self.wire.command(kind, args, status, identity)
        if status == 'interrupt':
            return
        self.queue_refresh(notes)


class CommentFixture(CommentSupport, Fixture):
    """Standalone fixture with cleanup owned by its calling test."""
