"""Public workflows, real codec/gateway/adapters/store and controlled editors.

Synthetic provider shapes use the pinned API-v1 Sync note_add/update/delete and
NoteSyncView contracts, inspected 2026-10-26. The strict boundary rejects wrong
arguments/resource requests and exercises documented absent task_id in REST
comments, null posted_at, unknown fields and pagination. Shared publisher boundary
coverage lives in T08; here one accepted-editor failure proves consumer behavior.
"""
from copy import deepcopy
from io import StringIO
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import termios
import unittest
from unittest.mock import patch
from uuid import UUID
from urllib.parse import parse_qs

from todo_lib import domain as d
from todo_lib import presentation as p
from todo_lib.adapter.current import retrieve
from todo_lib.adapter.transport import Replay, Transport
from todo_lib.local import (LocalError, LockBusy, StateStore, empty_history,
                            exclusive_lock, prepare_candidates)
from todo_lib.local.codec import loads
from todo_lib.syntax import parse, CommandRequest, TextGroup, InputError
from todo_lib.workflows import Synchronizer, SyncError
from todo_lib.workflows.comments import CommentWorkflow, CommentError, encode_buffer
from tests.adapter.current.test_current import BINDING, RESOURCES, full, delta, item, note
from tests.workflows.comments.test_codec import OLD, NEW
from tests.support.http import ControlledHTTP, ExpectedRequest, Response

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
            self.case.assertEqual(set(kwargs['form']), {'commands'})
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


class WorkflowTests(unittest.TestCase):
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

    def operation(self, kind, args, notes, *, status='ok', identity='new-comment',
                  actual=None, pages=False, malformed=False):
        self.wire.command(kind, args, status, identity)
        if status == 'interrupt':
            return
        self.queue_refresh(notes)
        self.wire.comments(notes if actual is None else actual, pages=pages, malformed=malformed)
        if status == 'ok':
            self.queue_refresh(notes)

    def test_unchanged_and_removed_starter_exact_timestamps_and_own_identity(self):
        for removed in (False, True):
            with self.subTest(removed=removed):
                before = self.store.load_consistent_state().snapshot.comments
                self.refresh()
                self.editor('assert text.index("z-older") < text.index("a-newer")\n'
                            'assert "parent-note" not in text\n' +
                            ('path.write_text(text.removesuffix("[new]\\n"))' if removed else ''))
                result = self.edit()
                self.assertEqual(result.status, 0)
                self.assertEqual(result.document, p.document())
                self.assertEqual(self.wire.commands, [])
                after = self.store.load_consistent_state().snapshot.comments
                self.assertEqual(after, before)
                self.assertEqual(d.instant_text(after['z-older'].added_at), OLD)
                self.assertEqual(d.instant_text(after['a-newer'].added_at), NEW)
                self.assertIsNone(after['unknown'].added_at)
                self.cleaned()

    def test_fill_starter_and_additional_saved_order_count_receipt(self):
        self.refresh()
        self.editor('path.write_text(text + "  first  \\n[new]\\nsecond\\n[new]\\n")')
        self.refresh()
        notes = [*self.notes, note('one', 'C', content='  first  ', posted_at=NEW)]
        self.operation('note_add', {'item_id': 'C', 'content': '  first  '}, notes, identity='one', pages=True)
        notes = [*notes, note('two', 'C', content='second', posted_at=None)]
        self.operation('note_add', {'item_id': 'C', 'content': 'second'}, notes, identity='two')
        result = self.edit()
        self.assertEqual(result.status, 0)
        self.assertEqual(result.document.stdout, 'Comments updated: Leaf — Root > Branch · 2 added, 0 edited, 0 deleted')
        self.assertEqual(result.document.stderr, '')
        self.assertEqual(self.store.load_consistent_state().snapshot.comments['one'].body, '  first  ')
        self.assertEqual(d.instant_text(self.store.load_consistent_state().snapshot.comments['a-newer'].added_at), NEW)
        self.cleaned()

    def test_interior_header_removal_is_edit_then_delete(self):
        self.refresh()
        text = encode_buffer(self.owner_comments()).replace('[id: a-newer posted: 2026-10-21 12:00]\n', '')
        self.save(text)
        self.refresh()
        edited = [dict(n, content='older\n\nnewer') if n['id'] == 'z-older' else n for n in self.notes]
        self.operation('note_update', {'id': 'z-older', 'content': 'older\n\nnewer'}, edited)
        deleted = [n for n in edited if n['id'] != 'a-newer']
        self.operation('note_delete', {'id': 'a-newer'}, deleted)
        result = self.edit()
        self.assertEqual(result.status, 0)
        self.assertIn('0 added, 1 edited, 1 deleted', result.document.stdout)
        self.assertEqual(self.streams.stdout.getvalue(), '')  # no inferred-intent prompt
        self.assertEqual(self.store.load_consistent_state().snapshot.comments['parent-note'].item_id, 'A')
        self.cleaned()

    def test_concurrent_add_preserved_known_edit_overwritten_then_deletion(self):
        self.refresh()
        saved = encode_buffer(self.owner_comments()).replace('\nolder\n', '\nmy edit\n')
        saved = saved.replace('[id: unknown posted: none]\nunknown\n\n', '') + 'addition\n'
        self.save(saved)
        concurrent = [dict(n, content='external edit') if n['id'] == 'z-older' else n for n in self.notes]
        concurrent.append(note('external', 'C', content='external addition', posted_at=NEW))
        edited = [dict(n, content='my edit') if n['id'] == 'z-older' else n for n in concurrent]
        self.operation('note_update', {'id': 'z-older', 'content': 'my edit'}, edited)
        added = [*edited, note('new-comment', 'C', content='addition', posted_at=NEW)]
        self.operation('note_add', {'item_id': 'C', 'content': 'addition'}, added)
        deleted = [n for n in added if n['id'] != 'unknown']
        self.operation('note_delete', {'id': 'unknown'}, deleted)
        result = self.edit()
        self.assertEqual(result.status, 0)
        comments = self.store.load_consistent_state().snapshot.comments
        self.assertEqual(comments['z-older'].body, 'my edit')
        self.assertEqual(comments['external'].body, 'external addition')
        self.assertNotIn('unknown', comments)
        self.assertEqual(result.document.stdout, 'Comments updated: Leaf — Root > Branch · 1 added, 1 edited, 1 deleted')
        self.cleaned()

    def test_concurrently_deleted_target_fails_in_order_after_accepted_edit(self):
        self.refresh()
        saved = encode_buffer(self.owner_comments()).replace('\nolder\n', '\nchanged\n')
        saved = saved.replace('[id: unknown posted: none]\nunknown\n\n', '')
        self.save(saved)
        concurrent = [n for n in self.notes if n['id'] != 'unknown']
        edited = [dict(n, content='changed') if n['id'] == 'z-older' else n for n in concurrent]
        self.operation('note_update', {'id': 'z-older', 'content': 'changed'}, edited)
        self.operation('note_delete', {'id':'unknown'}, edited,
                       status={'error_code':22, 'error':'comment was concurrently deleted'})
        result = self.edit()
        self.assertEqual(result.status, 1)
        self.assertEqual([o.status for o in result.outcomes], ['Accepted', 'Failed'])
        self.assertIn('Accepted: edited comment from 2026-10-21 12:00', result.document.stdout)
        self.assertIn('Failed: delete comment at position 3 — comment was concurrently deleted', result.document.stderr)
        self.assertEqual(len(self.wire.commands), 2)
        self.cleaned()

    def test_editor_mid_add_rejection_stops_before_later_adds_and_deletions(self):
        self.refresh()
        self.save('[new]\none\n[new]\ntwo\n[new]\nthree\n')
        self.refresh()
        added = [*self.notes, note('one', 'C', content='one', posted_at=NEW)]
        self.operation('note_add', {'item_id': 'C', 'content': 'one'}, added, identity='one')
        self.operation('note_add', {'item_id': 'C', 'content': 'two'}, added,
                       status={'error_code': 22, 'error': 'denied'})
        result = self.edit()
        self.assertEqual(result.status, 1)
        self.assertEqual([o.status for o in result.outcomes],
                         ['Accepted', 'Failed', 'Not attempted', 'Not attempted', 'Not attempted', 'Not attempted'])
        self.assertEqual(result.document.stdout, '  Accepted: added “one”')
        self.assertIn('Failed: add “two” — denied', result.document.stderr)
        self.assertIn('Not attempted: add “three”', result.document.stderr)
        self.assertNotIn('Comments updated:', result.document.stdout)
        self.assertEqual(len(self.wire.commands), 2)
        self.assertEqual(len(self.owner_comments()), 4)
        self.cleaned()

    def test_delete_all_empty_and_only_starter_require_confirmation(self):
        for saved in ('', '[new]\n \n'):
            for answer in (None, 'n\n', 'yes\n'):
                with self.subTest(saved=saved, answer=answer):
                    self.refresh()
                    self.save(saved)
                    streams = self.streams if answer is None else p.OriginalStreams(Terminal(answer), Terminal(), StringIO())
                    self.workflow.streams = streams
                    if answer == 'yes\n':
                        self.refresh()
                        remaining = list(self.notes)
                        for identity in ('z-older', 'a-newer', 'unknown'):
                            remaining = [n for n in remaining if n['id'] != identity]
                            self.operation('note_delete', {'id': identity}, remaining)
                        result = self.edit()
                        self.assertEqual(result.status, 0)
                        self.assertIn('0 added, 0 edited, 3 deleted', result.document.stdout)
                    else:
                        with self.assertRaises(InputError):
                            self.edit()
                    self.cleaned()

    def test_no_originals_unused_starter_is_successful_noop(self):
        self.refresh([])
        self.editor('assert text == "[new]\\n"')
        result = self.edit()
        self.assertEqual(result.status, 0)
        self.assertEqual(result.document, p.document())
        self.assertEqual(self.wire.commands, [])
        self.cleaned()

    def test_invalid_late_block_validates_before_any_mutation(self):
        self.refresh()
        self.save('[new]\nvalid\n[id: alien posted: now]\ninvalid\n')
        with self.assertRaises(CommentError):
            self.edit()
        self.assertEqual(self.wire.commands, [])
        self.cleaned()

    def test_launch_nonzero_and_sigint_cleanup_without_mutation(self):
        for failure in ('launch', 'nonzero', 'sigint', 'bad-quoting'):
            with self.subTest(failure=failure):
                self.refresh()
                if failure == 'launch':
                    self.environ['VISUAL'] = '/no/such/editor'
                elif failure == 'bad-quoting':
                    self.environ['VISUAL'] = "'unterminated"
                elif failure == 'nonzero':
                    self.editor('path.write_text("[new]\\nnot accepted")', exit_code=9)
                else:
                    self.editor('signal = __import__("signal")\nsignal.signal(2, signal.SIG_DFL)\nos.kill(os.getpid(), 2)')
                if failure == 'sigint':
                    self.assertEqual(self.edit().status, 130)
                else:
                    with self.assertRaises(LocalError):
                        self.edit()
                self.assertEqual(self.wire.commands, [])
                self.cleaned()

    def test_terminal_restored_after_editor_sigint(self):
        master, slave = os.openpty()
        self.addCleanup(os.close, master)
        stream = os.fdopen(slave, 'r')
        self.addCleanup(stream.close)
        self.workflow.streams = p.OriginalStreams(stream, StringIO(), StringIO())
        saved = termios.tcgetattr(slave)
        self.refresh()
        self.editor('import termios, signal\n'
                    f'terminal = os.open({os.ttyname(slave)!r}, os.O_RDWR)\n'
                    'mode = termios.tcgetattr(terminal)\nmode[3] &= ~termios.ECHO\n'
                    'termios.tcsetattr(terminal, termios.TCSANOW, mode)\n'
                    'signal.signal(2, signal.SIG_DFL)\nos.kill(os.getpid(), 2)')
        self.assertEqual(self.edit().status, 130)
        self.assertEqual(termios.tcgetattr(slave), saved)
        self.cleaned()

    def test_unsafe_editor_replacement_is_rejected_before_read_or_mutation(self):
        target = Path(self.temp.name) / 'untouched.txt'
        target.write_text('[new]\nprivate external text')
        target.chmod(0o600)
        for code in ('path.chmod(0o644)', f'path.unlink()\npath.symlink_to({str(target)!r})'):
            with self.subTest(code=code):
                self.refresh()
                self.editor(code)
                with self.assertRaises(LocalError):
                    self.edit()
                self.assertEqual(self.wire.commands, [])
                self.assertEqual(target.read_text(), '[new]\nprivate external text')
                self.cleaned()

    def test_editor_then_vi_fallback(self):
        self.refresh()
        self.editor()
        self.environ['EDITOR'] = self.environ.pop('VISUAL')
        self.assertEqual(self.edit().status, 0)
        self.environ.clear()
        self.refresh()
        with patch('todo_lib.workflows.comments.subprocess.run',
                   return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertEqual(self.edit().status, 0)
        self.assertEqual(run.call_args.args[0][0], 'vi')
        self.assertFalse(run.call_args.kwargs.get('shell', False))
        self.cleaned()

    def test_ordinary_aliases_groups_actual_body_and_stable_deep_owner(self):
        aliases = [ ['comment', 'Leaf', 'shorthand', 'words'],
                    ['add', 'comment', 'Leaf', 'shorthand', 'words'],
                    ['comments', 'Leaf', '--comment', 'shorthand', 'words'] ]
        for argv in aliases:
            with self.subTest(argv=argv):
                self.refresh()
                notes = [*self.notes, note('new-comment', 'C', content='shorthand words', posted_at=None)]
                self.operation('note_add', {'item_id': 'C', 'content': 'shorthand words'}, notes)
                result = self.workflow.execute(argv)
                self.assertEqual(result.status, 0)
                self.assertEqual(result.document.stdout, 'Comments for: Leaf — Root > Branch\n-> shorthand words')
                self.assertEqual(result.document.stderr, '')
        self.cleaned()

    def test_creation_mid_failure_preserves_accepted_actual_body_and_unattempted(self):
        self.refresh()
        notes = [*self.notes, note('one', 'C', content='first body', posted_at=NEW)]
        self.operation('note_add', {'item_id': 'C', 'content': 'first body'}, notes, identity='one')
        self.operation('note_add', {'item_id': 'C', 'content': 'second body'}, notes, status=None)
        result = self.workflow.execute(['add', 'comment', 'Le', 'af', '--comment', 'first body',
                                        'second body', '--comment', 'third', 'body'])
        self.assertEqual(result.status, 1)
        self.assertEqual(result.document.stdout, '-> first body')
        self.assertIn('Unknown: add “second body”', result.document.stderr)
        self.assertIn('Not attempted: add “third body”', result.document.stderr)
        self.assertEqual((result.document.stdout + result.document.stderr).count('Leaf — Root > Branch'), 1)
        self.assertEqual([o.status for o in result.outcomes], ['Accepted', 'Unknown', 'Not attempted'])
        self.assertIn('Read-only recovery: todo --refresh now', result.document.stderr)
        self.assertEqual(self.store.load_consistent_state().snapshot.comments['one'].body, 'first body')
        self.cleaned()

    def test_creation_revalidates_all_bodies_before_sync(self):
        request = CommandRequest('comment', selector=('Leaf',), groups=(
            TextGroup('comment', (), ('valid', 'bad\x00')),))
        with self.assertRaises(d.DomainError):
            self.workflow.execute(request)
        self.assertEqual(self.wire.commands, [])
        self.cleaned()

    def test_actual_accepted_body_mismatch_stops_later_creation(self):
        self.refresh()
        notes = [*self.notes, note('new-comment', 'C', content='accepted actual', posted_at=None)]
        self.operation('note_add', {'item_id': 'C', 'content': 'requested body'}, notes)
        result = self.workflow.execute(['comment', 'Leaf', '--comment', 'requested body', 'later body'])
        self.assertEqual(result.status, 1)
        self.assertEqual(result.document.stdout, '-> accepted actual')
        self.assertIn('differs from requested owner/text', result.document.stderr)
        self.assertIn('Not attempted: add “later body”', result.document.stderr)
        self.assertNotIn('-> requested body', result.document.stdout)

    def test_accepted_creation_missing_actual_body_is_reported_without_invented_arrow(self):
        self.refresh()
        self.operation('note_add', {'item_id': 'C', 'content': 'requested body'}, self.notes)
        result = self.workflow.execute(['comment', 'Leaf', '--comment', 'requested body', 'later body'])
        self.assertEqual(result.status, 1)
        self.assertEqual([o.status for o in result.outcomes], ['Accepted', 'Not attempted'])
        self.assertEqual(result.document.stdout, '')
        self.assertIn('Accepted: added comment at position 1', result.document.stderr)
        self.assertNotIn('Accepted: added “requested body”', result.document.stderr)
        self.assertIn('actual accepted body unavailable', result.document.stderr)
        self.assertIn('Not attempted: add “later body”', result.document.stderr)
        self.assertNotIn('->', result.document.stdout)

    def test_accepted_editor_interruption_during_reconciliation_stops_later_work(self):
        self.refresh()
        self.editor('path.write_text(text + "accepted body\\n[new]\\nlater body")')
        self.refresh()
        notes = [*self.notes, note('new-comment', 'C', content='accepted body', posted_at=NEW)]
        self.operation('note_add', {'item_id': 'C', 'content': 'accepted body'}, notes)
        real_publish = self.store.publish_snapshot
        def interrupt(candidates):
            if self.wire.commands:
                raise KeyboardInterrupt
            return real_publish(candidates)
        with patch.object(self.store, 'publish_snapshot', side_effect=interrupt):
            result = self.edit()
        self.assertEqual(result.status, 130)
        self.assertEqual([o.status for o in result.outcomes], ['Accepted', 'Not attempted'])
        self.assertIn('Accepted: added “accepted body”', result.document.stdout)
        self.assertIn('Previous protected files were preserved', result.document.stderr)
        self.assertIn('Remote operation outcome: accepted; do not replay', result.document.stderr)
        self.assertNotIn('Comments updated:', result.document.stdout)
        self.cleaned()

    def test_editor_partial_receipt_uses_authoritative_body(self):
        self.refresh()
        self.editor('path.write_text(text + "requested body\\n[new]\\nlater body")')
        self.refresh()
        notes = [*self.notes, note('new-comment', 'C', content='accepted actual', posted_at=None)]
        self.operation('note_add', {'item_id': 'C', 'content': 'requested body'}, notes)
        result = self.edit()
        self.assertEqual(result.status, 1)
        self.assertEqual(result.document.stdout, '  Accepted: added “accepted actual”')
        self.assertEqual(result.outcomes[0].body, 'accepted actual')
        self.assertIn('differs from requested owner/text', result.document.stderr)
        self.assertIn('Not attempted: add “later body”', result.document.stderr)
        self.assertEqual(self.store.load_consistent_state().snapshot.comments['new-comment'].body,
                         'accepted actual')
        self.cleaned()

    def test_editor_partial_receipt_marks_unavailable_actual_body(self):
        self.refresh()
        self.editor('path.write_text(text + "requested body\\n[new]\\nlater body")')
        self.refresh()
        self.operation('note_add', {'item_id': 'C', 'content': 'requested body'}, self.notes)
        result = self.edit()
        self.assertEqual(result.status, 1)
        self.assertEqual(result.document.stdout,
                         '  Accepted: added comment at position 1 — actual accepted body unavailable')
        self.assertNotIn('requested body', result.document.stdout)
        self.assertIn('Not attempted: add “later body”', result.document.stderr)
        self.cleaned()

    def acknowledged_read_interrupt(self, *, editing, scoped=False, rejected=False):
        before = {path.name: path.read_bytes() for path in self.root.iterdir() if path.name != 'lock'}
        self.refresh()
        if editing:
            self.editor('path.write_text(text + "requested body\\n[new]\\nlater body")')
            self.refresh()
        status = {'error_code': 22, 'error': 'Comment content too long'} if rejected else 'ok'
        self.wire.command('note_add', {'item_id': 'C', 'content': 'requested body'}, status)
        if scoped:
            self.queue_refresh([*self.notes, note('new-comment', 'C', content='requested body', posted_at=NEW)])
            self.wire.steps.append(('GET', '/comments',
                {'query': [('task_id', 'C'), ('limit', '200')]}, KeyboardInterrupt()))
        else:
            self.wire.sync('delta-token', KeyboardInterrupt())
        result = self.edit() if editing else self.workflow.execute(
            ['comment', 'Leaf', '--comment', 'requested body', 'later body'])
        self.assertEqual(result.status, 130)
        expected = 'Failed' if rejected else 'Accepted'
        self.assertEqual([o.status for o in result.outcomes], [expected, 'Not attempted'])
        self.assertEqual(result.operations[0].target_id, 'new-comment')
        self.assertNotIn('Unknown:', result.document.stderr)
        if rejected:
            self.assertIn('Failed: add “requested body” — Comment content too long; interrupted',
                          result.document.stderr)
            self.assertEqual(result.document.stdout, '')
        else:
            stream = result.document.stdout if editing else result.document.stderr
            self.assertIn('Accepted: added comment at position 1', stream)
            self.assertIn('actual accepted body unavailable', stream)
            self.assertIn('Remote operation outcome: accepted; do not replay', result.document.stderr)
            self.assertNotIn('“requested body”', result.document.stdout)
        self.assertIn('Not attempted: add “later body”', result.document.stderr)
        self.assertEqual(len(self.wire.commands), 1)
        # Initial synchronization may republish associations, but interruption
        # cannot publish the partially retrieved mutation state.
        self.assertEqual(len(self.owner_comments()), 3)
        self.assertEqual((self.root / 'report-cursor').read_bytes(), before['report-cursor'])
        self.cleaned()
        # A subsequent explicit read-only refresh recovers without replay.
        self.queue_refresh()
        self.sync.refresh()
        self.assertEqual(len(self.wire.commands), 1)

    def test_creation_acknowledged_before_current_read_sigint(self):
        self.acknowledged_read_interrupt(editing=False)

    def test_editor_acknowledged_before_scoped_read_sigint(self):
        self.acknowledged_read_interrupt(editing=True, scoped=True)

    def test_editor_acknowledged_before_current_read_sigint(self):
        self.acknowledged_read_interrupt(editing=True)

    def test_rejection_acknowledged_before_current_read_sigint(self):
        self.acknowledged_read_interrupt(editing=False, rejected=True)

    def http_failure_reconciliation(self, *, editing, http_status=403, structured=False, addition=False,
                                    error_message="Comment content too long", interrupted=True, attributable=True, deletion=False):
        self.refresh()
        kind = 'note_delete' if deletion else 'note_update' if editing and not addition else 'note_add'
        args = {'id': 'z-older', 'content': 'requested body'} if kind == 'note_update' else {
            'item_id': 'C', 'content': 'requested body'}
        if deletion:
            args = {'id': 'z-older'}
            self.editor('path.write_text(text[text.index("[id: unknown"):])')
            self.refresh()
        elif editing and addition:
            self.editor('path.write_text(text + "requested body\\n[new]\\nlater body")')
            self.refresh()
        elif editing:
            self.editor('path.write_text(text.replace("\\nolder\\n", "\\nrequested body\\n")'
                        ' + "later body")')
            self.refresh()
        case = self
        sent_commands = []
        response = Response() if structured else Response(json.dumps({'error': 'denied secret\nAuthorization: Bearer private-header',
                                                      'error_code': 20}).encode(), http_status)

        class MutationRequest:
            def check(self, request, timeout):
                form = parse_qs(request.data.decode('ascii'))
                case.assertEqual(set(form), {'commands'})
                commands = json.loads(form['commands'][0])
                case.assertEqual(len(commands), 1)
                command = commands[0]
                case.assertEqual(command['type'], kind)
                case.assertEqual(command['args'], args)
                sent_commands.append(command)
                case.assertEqual(str(UUID(command['uuid'])), command['uuid'])
                case.assertEqual(set(command), {'type', 'args', 'uuid', 'temp_id'}
                                 if kind == 'note_add' else {'type', 'args', 'uuid'})
                if kind == 'note_add':
                    case.assertEqual(str(UUID(command['temp_id'])), command['temp_id'])
                if structured:
                    response.seek(0)
                    response.truncate()
                    response.write(json.dumps({'sync_status': {
                        'unrelated-uuid': {'error_code': 20, 'error': 'unrelated diagnostic'},
                        **({command['uuid']: {'error_code': 22, 'error': error_message}}
                           if attributable else {})}}).encode())
                    response.seek(0)
                ExpectedRequest('POST', '/sync', 'secret',
                                form={'commands': form['commands'][0]}).check(request, timeout)

        class InterruptedRead(ExpectedRequest):
            def check(self, request, timeout):
                super().check(request, timeout)
                raise KeyboardInterrupt

        read = InterruptedRead if interrupted else ExpectedRequest
        steps = [
            (MutationRequest(), response),
            (read('POST', '/sync', 'secret',
                  form={'sync_token': 'delta-token', 'resource_types': RESOURCES}),
             None if interrupted else Response(json.dumps(delta()).encode())),
        ]
        if not interrupted:
            rows = [{k: v for k, v in n.items() if k != 'item_id'}
                    for n in self.notes if n['item_id'] == 'C']
            steps.append((ExpectedRequest('GET', '/comments', 'secret',
                query={'task_id': 'C', 'limit': '200'}),
                Response(json.dumps({'results': rows, 'next_cursor': None}).encode())))
        http = ControlledHTTP(steps)
        transport = Transport('secret', opener=http)
        self.workflow.gateway.transport = transport
        before = {path.name: path.read_bytes() for path in self.root.iterdir() if path.name != 'lock'}
        result = self.edit() if editing else self.workflow.execute(
            ['comment', 'Leaf', '--comment', 'requested body', 'later body'])
        self.assertEqual(result.status, 130 if interrupted else 1)
        state = 'Failed' if http_status == 403 and attributable else 'Unknown'
        self.assertEqual([o.status for o in result.outcomes], [state, 'Not attempted'])
        self.assertEqual(result.operations[0].outcome.value, 'rejected' if state == 'Failed' else 'unknown')
        self.assertEqual(result.document.stdout, '')
        action = {'note_add': 'add', 'note_update': 'edit', 'note_delete': 'delete'}[kind]
        self.assertIn(state + ': ' + action, result.document.stderr)
        self.assertEqual(result.operations[0].operation.uuid, sent_commands[0]['uuid'])
        self.assertEqual(result.operations[0].operation.args, args)
        self.assertIn(('command', sent_commands[0]['uuid'],
                       result.operations[0].outcome.value), result.operations[0].evidence)
        if kind == 'note_add':
            self.assertIn('add “requested body”', result.document.stderr)
        else:
            self.assertIn(action + ' comment from 2026-10-21 12:00', result.document.stderr)
        if structured:
            if attributable:
                safe_reason = ('Comment content too long: [REDACTED]\nAuthorization: [REDACTED]'
                               if 'Authorization:' in error_message else 'Comment content too long')
                self.assertIn(safe_reason.replace('\n', '\n    '), result.document.stderr)
                self.assertIn(safe_reason, result.operations[0].issues)
            else:
                self.assertNotIn('Comment content too long', result.document.stderr)
            if interrupted:
                self.assertIn('interrupted', result.document.stderr)
            else:
                self.assertNotIn('interrupted', result.document.stderr)
            self.assertNotIn('unrelated diagnostic', result.document.stderr)
            self.assertNotIn('secret', result.document.stderr)
            self.assertNotIn('Bearer private-header', result.document.stderr)
            self.assertEqual(result.operations[0].target_id, None if kind == 'note_add' else 'z-older')
        else:
            diagnostic = (kind + ': HTTP 403 rejection' if state == 'Failed' else
                          kind + ': HTTP 507; reconcile before replay')
            self.assertIn(diagnostic, result.document.stderr)
            self.assertIn(diagnostic, result.operations[0].issues)
            if state == 'Failed':
                self.assertNotIn('Unknown:', result.document.stderr)
            self.assertNotIn('secret', result.document.stderr)
            self.assertNotIn('private-header', result.document.stderr)
            self.assertNotIn('secret', repr(result.operations[0]))
        if deletion:
            self.assertIn('Not attempted: delete comment from 2026-10-21 12:00', result.document.stderr)
        else:
            self.assertIn('Not attempted: add “later body”', result.document.stderr)
        if not interrupted:
            self.assertIsNotNone(result.operations[0].after)
            self.assertEqual(result.operations[0].target_id, None if kind == 'note_add' else 'z-older')
            self.assertEqual(result.operations[0].actual, None if kind == 'note_add' else
                             next(c for c in self.owner_comments() if c.id == 'z-older'))
        self.assertIs(self.workflow.gateway.transport, transport)
        self.assertEqual(len(http.requests), 2 if interrupted else 3)
        http.assert_done()
        self.assertEqual(len(self.owner_comments()), 3)
        self.assertEqual((self.root / 'report-cursor').read_bytes(), before['report-cursor'])
        self.cleaned()
        # Recovery is read-only and does not replay the rejected/unknown command.
        self.queue_refresh()
        self.sync.refresh()
        self.assertEqual(len(http.requests), 2 if interrupted else 3)

    def test_structured_rejection_reason_before_read_sigint(self):
        for editing, addition in ((False, False), (True, True), (True, False)):
            with self.subTest(editing=editing, addition=addition):
                self.http_failure_reconciliation(editing=editing, addition=addition, structured=True)

    def test_structured_rejection_reason_redacts_credentials_before_read_sigint(self):
        self.http_failure_reconciliation(editing=True, addition=True, structured=True,
            error_message='Comment content too long: secret\nAuthorization: Bearer private-header')

    def test_structured_rejection_reason_after_successful_reconciliation(self):
        for editing, addition in ((False, False), (True, True), (True, False)):
            with self.subTest(editing=editing, addition=addition):
                self.http_failure_reconciliation(editing=editing, addition=addition, structured=True,
                    interrupted=False,
                    error_message='Comment content too long: secret\nAuthorization: Bearer private-header')

    def test_unrelated_rejection_after_successful_reconciliation_remains_unknown(self):
        self.http_failure_reconciliation(editing=False, structured=True,
                                         interrupted=False, attributable=False)

    def test_http_failure_reason_after_successful_reconciliation(self):
        for editing, addition, deletion in ((False, False, False), (True, True, False),
                                            (True, False, False), (True, False, True)):
            for http_status in (403, 507):
                with self.subTest(editing=editing, addition=addition, deletion=deletion,
                                  http_status=http_status):
                    self.http_failure_reconciliation(editing=editing, addition=addition,
                        deletion=deletion, http_status=http_status, interrupted=False)

    def test_editor_deletion_rejection_channels(self):
        for structured, interrupted in ((True, False), (True, True), (False, True)):
            with self.subTest(structured=structured, interrupted=interrupted):
                self.http_failure_reconciliation(editing=True, deletion=True, structured=structured,
                    interrupted=interrupted,
                    error_message='Comment content too long: secret\nAuthorization: Bearer private-header')

    def test_creation_http_rejection_before_read_sigint(self):
        self.http_failure_reconciliation(editing=False)

    def test_editor_http_rejection_before_read_sigint(self):
        self.http_failure_reconciliation(editing=True)

    def test_creation_unresolved_http_failure_before_read_sigint(self):
        self.http_failure_reconciliation(editing=False, http_status=507)

    def test_existing_comment_acknowledgment_survives_read_sigint(self):
        for kind in ('edit', 'delete'):
            with self.subTest(kind=kind):
                self.refresh()
                if kind == 'edit':
                    self.editor('path.write_text(text.replace("\\nolder\\n", "\\nchanged body\\n"))')
                    args = {'id': 'z-older', 'content': 'changed body'}
                else:
                    self.editor('start = text.index("[id: z-older")\n'
                                'end = text.index("[id: a-newer")\n'
                                'path.write_text(text[:start] + text[end:])')
                    args = {'id': 'z-older'}
                self.refresh()
                self.wire.command('note_update' if kind == 'edit' else 'note_delete', args)
                self.wire.sync('delta-token', KeyboardInterrupt())
                result = self.edit()
                self.assertEqual(result.status, 130)
                self.assertEqual(result.outcomes[0].status, 'Accepted')
                self.assertEqual(result.operations[0].target_id, 'z-older')
                self.assertIn('Accepted: ' + ('edited' if kind == 'edit' else 'deleted'),
                              result.document.stdout)
                self.assertNotIn('interrupted', result.document.stdout)
                self.cleaned()

    def test_no_text_delegates_cache_first_with_no_lock_or_http(self):
        result = self.workflow.execute(['comments', 'Leaf'])
        self.assertEqual(result.status, 0)
        self.assertIn('older', result.document.stdout)
        self.assertNotIn('parent only', result.document.stdout)
        self.assertEqual(self.wire.commands, [])

    def test_inflight_sigint_unknown_and_later_operations_unattempted(self):
        self.refresh()
        self.editor('path.write_text(text + "first body\\n[new]\\nlater body")')
        self.refresh()
        self.operation('note_add', {'item_id': 'C', 'content': 'first body'}, self.notes, status='interrupt')
        result = self.edit()
        self.assertEqual(result.status, 130)
        self.assertEqual([o.status for o in result.outcomes], ['Unknown', 'Not attempted'])
        self.assertIn('Unknown: add “first body”', result.document.stderr)
        self.cleaned()

    def test_accepted_editor_partial_publication_keeps_outcomes_and_refuses_mixed_state(self):
        self.refresh()
        self.editor('path.write_text(text + "accepted body\\n[new]\\nlater body")')
        self.refresh()
        notes = [*self.notes, note('new-comment', 'C', content='accepted body', posted_at=NEW)]
        self.operation('note_add', {'item_id': 'C', 'content': 'accepted body'}, notes)
        before_cursor = (self.root / 'report-cursor').read_bytes()
        real_replace = os.replace
        def fail_binding(source, destination):
            if self.wire.commands and Path(destination).name == 'binding.json':
                raise OSError('controlled binding publication failure')
            return real_replace(source, destination)
        with patch('todo_lib.local.safety.os.replace', side_effect=fail_binding):
            result = self.edit()
        self.assertEqual(result.status, 1)
        self.assertEqual([o.status for o in result.outcomes], ['Accepted', 'Not attempted'])
        self.assertIn('Accepted: added “accepted body”', result.document.stdout)
        self.assertIn('local publication failed', result.document.stderr)
        self.assertEqual(result.document.stdout, '  Accepted: added “accepted body”')
        self.assertNotIn('local publication failed', result.document.stdout)
        self.assertNotIn('Read-only recovery', result.document.stdout)
        self.assertIn('saved snapshot may be unusable', result.document.stderr)
        self.assertNotIn('previous cache was not replaced', result.document.stderr)
        self.assertNotIn('Comments updated:', result.document.stdout)
        self.assertEqual(len(self.wire.commands), 1)
        self.assertEqual((self.root / 'report-cursor').read_bytes(), before_cursor)
        # Individually complete candidates retain exact known times and history.
        cache = loads((self.root / 'cache.json').read_bytes())
        history = loads((self.root / 'history.json').read_bytes())
        self.assertIn(NEW, json.dumps(cache))
        self.assertIn(OLD, json.dumps(history))
        with self.assertRaises(LocalError):
            Synchronizer(None, self.store, clock=lambda: NOW).read_local()
        self.cleaned()


if __name__ == '__main__':
    unittest.main()
