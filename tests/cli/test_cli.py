"""Public composition with dependency fixtures, actual workflows and adapters.

No CLI server flags or alternate runtime implementations. Existing focused suites
supply the detailed grammar, calendar/DST, reconciliation and finalization cases.
"""
from contextlib import ExitStack
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from todo_lib import cli, domain as d
from todo_lib.local import StateStore, exclusive_lock
from todo_lib.workflows.sync import Synchronizer
from todo_lib.workflows.report import Reporter
from todo_lib.syntax.help import SYNOPSES, ALIASES
from tests.workflows.capture import test_capture as capture
from tests.workflows.sync import test_sync as sync_fixture
from tests.workflows.report import test_report as report
from tests.adapter.current.test_current import item, note, full, delta

ROOT = Path(__file__).resolve().parents[2]


def invoke(case, argv, transport=None, now=capture.NOW, output=None, error=None, input=None, environ=None):
    out = output if output is not None else StringIO()
    err = error if error is not None else StringIO()
    with ExitStack() as stack:
        stack.enter_context(patch.object(sys, 'stdin', input if input is not None else StringIO()))
        stack.enter_context(patch.object(sys, 'stdout', out))
        stack.enter_context(patch.object(sys, 'stderr', err))
        stack.enter_context(patch.dict(os.environ, {'TODOIST_TOKEN': 'secret', 'TERM': 'dumb', **(environ or {})}))
        stack.enter_context(patch.object(cli, 'StateStore', return_value=case.store))
        factory = stack.enter_context(patch.object(cli, 'Transport', return_value=transport))
        stack.enter_context(patch.object(cli, 'Synchronizer', side_effect=lambda wire, store:
            Synchronizer(wire, store, clock=lambda: now)))
        stack.enter_context(patch.object(cli, 'Reporter', side_effect=lambda wire, store, **kw:
            Reporter(wire, store, clock=lambda: now, **kw)))
        status = cli.main(argv)
    return status, out.getvalue(), err.getvalue(), factory


class RoutingTests(unittest.TestCase):
    def test_priority_help_teaches_independent_step_priority(self):
        help_text = cli.render_help('priority')
        self.assertIn('task or step', help_text)
        self.assertIn('immediate parent', help_text)
        self.assertIn('once', help_text)
        self.assertIn('independent', help_text)

    def test_help_all_commands_and_aliases_without_state(self):
        with patch.object(cli, 'StateStore', side_effect=AssertionError('state touched')):
            for command in [None, *SYNOPSES, *ALIASES]:
                with self.subTest(command=command):
                    a, b = StringIO(), StringIO()
                    with patch.object(sys, 'stdout', a):
                        self.assertEqual(cli.main(['help', command] if command else ['help']), 0)
                    with patch.object(sys, 'stdout', b):
                        self.assertEqual(cli.main([command, '--help'] if command else ['--help']), 0)
                    self.assertEqual(a.getvalue(), b.getvalue())
                    self.assertIn('todo', a.getvalue())

    def test_syntax_status_and_environment_secret_redaction(self):
        with patch.dict(os.environ, {'TODOIST_TOKEN': 'sensitive'}), patch.object(cli, 'StateStore', side_effect=AssertionError('state touched')):
            for argv in (['--color', 'sensitive'], ['task', '--due'], ['now', '--refresh', '--refresh'], ['reopen', 'A', '--comment', 'x'], ['report', '--since', 'bad-boundary']):
                out, err = StringIO(), StringIO()
                with patch.object(sys, 'stdout', out), patch.object(sys, 'stderr', err):
                    self.assertEqual(cli.main(argv), 2)
                self.assertEqual(out.getvalue(), '')
                self.assertIn('Usage:', err.getvalue())
                self.assertIn('Example:', err.getvalue())
                self.assertNotIn('sensitive', err.getvalue())

    def test_unexpected_failure_is_opaque_and_sigint_is_130(self):
        for error, status in ((RuntimeError('private provider response'), 1), (KeyboardInterrupt(), 130)):
            err = StringIO()
            with patch.object(cli, 'StateStore', side_effect=error), patch.object(sys, 'stderr', err):
                self.assertEqual(cli.main(['now']), status)
            self.assertNotIn('private', err.getvalue())
            self.assertNotIn('Traceback', err.getvalue())

    def test_interrupt_during_failure_diagnostic_is_handled(self):
        class InterruptedError(StringIO):
            def write(self, text):
                raise KeyboardInterrupt()
        with patch.object(cli, 'StateStore', side_effect=cli.LocalError('failed read')), patch.object(sys, 'stderr', InterruptedError()):
            self.assertEqual(cli.main(['now']), 130)

    def test_copied_launcher_on_path_and_real_sigint(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            shutil.copy2(ROOT / 'todo', target / 'todo')
            shutil.copytree(ROOT / 'todo_lib', target / 'todo_lib', ignore=shutil.ignore_patterns('__pycache__'))
            env = {**os.environ, 'PATH': temp + os.pathsep + os.environ['PATH'],
                   'HOME': temp, 'PYTHONPATH': '', 'PYTHONDONTWRITEBYTECODE': '1'}
            result = subprocess.run(['todo', 'help', 'move'], cwd='/', env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('promotion', result.stdout)
            self.assertEqual((target / 'todo').read_bytes().splitlines()[0], b'#!/usr/bin/env python3')
            # Install a signal at the public boundary, without a production flag.
            code = 'import signal; from unittest.mock import patch; from todo_lib.cli import main\nwith patch("todo_lib.cli.StateStore", side_effect=lambda: signal.raise_signal(signal.SIGINT)):\n raise SystemExit(main(["now"]))'
            result = subprocess.run(['python3.11', '-B', '-c', code], cwd=temp, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 130, result.stderr)
            self.assertNotIn('Traceback', result.stderr)
            self.assertFalse(list(target.rglob('__pycache__')))


class PublicCapture(unittest.TestCase):
    setUp = capture.CaptureTests.setUp
    state = capture.CaptureTests.state
    seed = capture.CaptureTests.seed
    refresh = capture.CaptureTests.refresh
    operation = capture.CaptureTests.operation

    def call(self, argv, **kw):
        result = invoke(self, argv, self.http, **kw)
        self.assertFalse(self.http.steps, 'missing adapter calls')
        return result[:3]

    def test_default_implicit_queries_ambiguity_and_local_errors(self):
        first = self.call([])
        self.assertEqual(first, self.call(['now']))
        status, out, err = self.call(['Parent'])
        self.assertEqual(status, 0, err)
        self.assertIn('Parent', out)
        self.assertEqual(self.call(['no-such-title'])[0], 1)
        self.wire_items.append(item('dup', content='Parent extra'))
        self.seed()
        status, out, err = self.call(['Parent'])
        self.assertEqual(status, 1)
        self.assertIn('Parent extra', out + err)
        self.assertNotIn('Select 1', out + err)
        (self.root / 'cache.json').write_text('{broken')
        status, out, err = self.call(['nothing'])
        self.assertEqual(status, 1)
        self.assertNotIn('no matching', err.lower())
        self.assertEqual(out, '')

    def test_pager_redacts_complete_document_and_failure_fallback(self):
        class FileTerminal:
            def __init__(self, file):
                self.file = file
            def isatty(self):
                return True
            def getvalue(self):
                self.file.flush()
                self.file.seek(0)
                return self.file.read()
            def __getattr__(self, name):
                return getattr(self.file, name)
        class InputTerminal(StringIO):
            def isatty(self):
                return True
        self.wire_items[0]['content'] = 'Parent secret'
        self.wire_items[0]['due'] = capture.due('2026-10-22T12:00:00Z')
        self.seed()
        config = self.root / 'config'
        original = config.read_text()
        # Actual children inherit file descriptors. StringIO would accidentally
        # test only the fallback path, where stream.write already redacts.
        for pager in ('/bin/cat', '/bin/false', ''):
            with self.subTest(pager=pager):
                config.write_text(original.replace('[main]\n', '[main]\npager=' + pager + '\n'))
                with tempfile.TemporaryFile(mode='w+') as out, tempfile.TemporaryFile(mode='w+') as err:
                    status, text, diagnostic, factory = invoke(self, ['--color=always', 'now'],
                        output=FileTerminal(out), error=FileTerminal(err), input=InputTerminal(),
                        environ={'TERM': 'xterm'})
                self.assertEqual(status, 0, diagnostic)
                factory.assert_not_called()
                self.assertIn('Parent [REDACTED]', text)
                self.assertNotIn('secret', text + diagnostic)
                self.assertIn('\x1b[', text)
                self.assertEqual('pager failed' in diagnostic, pager == '/bin/false')

    def test_mutation_ambiguity_preserves_color_policy_without_mutation(self):
        self.wire_items.append(item('dup', content='Parent extra'))
        for row in self.wire_items:
            row['due'] = capture.due('2026-10-22T12:00:00Z')
        config = self.root / 'config'
        config.write_text(config.read_text() + '[colors]\nred=#010203\n')
        self.seed()
        # Shared selectors: scalar source, creation parent, nested parent,
        # move source, move destination and lifecycle target/parent.
        commands = (['rename', 'Parent', '--to', 'Changed'],
                    ['add', 'step', 'Parent', 'New step'],
                    ['step', '--rename', 'Changed', 'Parent', 'Child'],
                    ['move', 'Parent', 'cat'],
                    ['move', 'Known sibling', '--task', 'Parent'],
                    ['done', 'Parent'], ['step', '--done', 'Parent', 'Child'])
        import re
        for argv in commands:
            plain = None
            for mode in ('never', 'always'):
                self.refresh()
                status, out, err = self.call(['--color=' + mode, *argv])
                self.assertEqual(status, 1, (argv, err))
                self.assertIn('Parent extra', out, (argv, err))
                self.assertNotIn('Select 1', out)
                if mode == 'never':
                    plain = out
                    self.assertNotIn('\x1b[', out)
                else:
                    self.assertIn('\x1b[38;2;1;2;3m', out)
                    self.assertEqual(re.sub(r'\x1b\[[0-9;]*m', '', out), plain)
        class Terminal(StringIO):
            def isatty(self):
                return True
        # Auto color uses original stdout, with NO_COLOR/TERM exclusions.
        for env, enabled in (({'TERM': 'xterm'}, True),
                             ({'TERM': 'xterm', 'NO_COLOR': '1'}, False),
                             ({'TERM': 'dumb'}, False)):
            self.refresh()
            with patch.dict(os.environ):
                os.environ.pop('NO_COLOR', None)
                status, out, err = self.call(commands[0], output=Terminal(), environ=env)
            self.assertEqual(status, 1, err)
            self.assertEqual('\x1b[' in out, enabled)
        self.assertEqual(self.store.load_consistent_state().snapshot.items['parent'].title, 'Parent')

    def test_full_implicit_query_preserves_phrase_boundaries(self):
        self.wire_items += [item('phrase', content='Alpha beta gamma'),
                            item('terms', content='Alpha gamma beta')]
        self.seed()
        status, out, err = self.call(['Alpha beta', 'gamma'])
        self.assertEqual(status, 0, err)
        self.assertIn('Alpha beta gamma', out)
        self.assertNotIn('Alpha gamma beta', out)
        self.assertEqual(self.call(['Alpha', 'beta', 'gamma'])[0], 1)
        status, out, err = self.call(['schedle', 'some phrase', 'tail'])
        self.assertEqual(status, 1)
        self.assertIn('"schedle" "some phrase" "tail"', err)

    def test_unknown_creation_is_not_silent_and_never_replays(self):
        self.refresh()
        after = self.state(items=self.wire_items + [item('new', content='Unknown task', priority=3)])
        self.operation('item_add', dict(project_id='cat', content='Unknown task', description='', priority=3,
                       labels=[], auto_reminder=False, due=None), after, status=None)
        status, out, err = self.call(['add', 'cat', '--title', 'Unknown task', 'Later task'])
        self.assertEqual(status, 1)
        self.assertEqual(out, '')
        self.assertIn('Unknown:', err)
        self.assertIn('Unknown task', err)
        self.assertIn('Not attempted:', err)
        self.assertIn('do not replay', err)
        self.assertNotIn('new', self.store.load_consistent_state().snapshot.items)

    def test_capture_refine_nested_step_alias_schedule_and_search(self):
        self.refresh()
        after = self.state(items=self.wire_items + [item('new', content='Captured', priority=3)])
        self.operation('item_add', dict(project_id='cat', content='Captured', description='', priority=3,
                       labels=[], auto_reminder=False, due=None), after)
        status, out, err = self.call(['add', 'task', 'cat', 'Captured'])
        self.assertEqual(status, 0, err)
        self.assertIn('Captured', out)
        self.wire_items = after['items']
        self.refresh()
        after = self.state(items=[dict(i, content='Refined') if i['id'] == 'new' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'new', 'content': 'Refined'}, after)
        self.assertEqual(self.call(['rename', 'Captured', '--to', 'Refined'])[0], 0)
        self.wire_items = after['items'] + [item('child', content='Nested', parent_id='parent', priority=3),
            item('leaf', content='Leaf', parent_id='child'), item('other', content='Other'),
            item('other-leaf', content='Leaf', parent_id='other')]
        self.seed()
        self.refresh()
        after = self.state(items=[dict(i, due=capture.due('2026-10-23')) if i['id'] == 'leaf' else i for i in self.wire_items])
        self.operation('item_update', {'id': 'leaf', 'due': {'date': '2026-10-23', 'lang': 'en'}}, after, 'leaf')
        status, out, err = self.call(['step', '--due', 'tomorrow', 'Nested', 'Leaf'])
        self.assertEqual(status, 0, err)
        loaded = self.store.load_consistent_state().snapshot
        self.assertIsNone(loaded.items['other-leaf'].attention)
        self.assertIsNotNone(loaded.items['leaf'].attention)
        self.assertEqual(self.call(['search', 'Refined'])[0], 0)
        for command in ('waiting', 'someday', 'category'):
            self.assertEqual(self.call([command])[0], 0)

    def test_accepted_mutation_late_binding_interrupt_stops_batch(self):
        self.refresh()
        after = self.state(items=self.wire_items + [item('new', content='Accepted', priority=3)])
        self.operation('item_add', dict(project_id='cat', content='Accepted', description='', priority=3,
                       labels=[], auto_reminder=False, due=None), after)
        replace = os.replace
        cursor = (self.root / 'report-cursor').read_bytes()
        def interrupt_binding(source, destination):
            if Path(destination).name == 'binding.json' and any('commands' in call for call in self.http.calls):
                raise KeyboardInterrupt()
            return replace(source, destination)
        with patch('todo_lib.local.safety.os.replace', side_effect=interrupt_binding):
            status, out, err = self.call(['add', 'cat', '--title', 'Accepted', 'Later task'])
        self.assertEqual(status, 130, err)
        self.assertIn('Accepted:', err)
        self.assertIn('Not attempted:', err)
        self.assertIn('partially published', err)
        self.assertIn('unusable', err)
        self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)
        self.assertFalse(list(self.root.glob('.*.tmp')))
        for name in ('cache.json', 'history.json', 'binding.json'):
            json.loads((self.root / name).read_text())
        self.assertEqual(json.loads((self.root / 'cache.json').read_text())['snapshot']['items']['precise']['added_at'], capture.PRECISE)
        with exclusive_lock('released', self.root):
            pass
        self.assertEqual(self.call(['now'])[0], 1)
        result = subprocess.run([str(ROOT / 'todo'), 'now'], env={**os.environ, 'HOME': str(self.root.parent),
            'PYTHONDONTWRITEBYTECODE': '1'}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('restore consistent state', result.stderr)
        self.assertEqual(result.stdout, '')


class PublicReports(unittest.TestCase):
    setUp = sync_fixture.SyncTests.setUp
    put = sync_fixture.SyncTests.put
    sync = sync_fixture.SyncTests.sync
    boundary = sync_fixture.SyncTests.boundary
    requests = report.Reports.requests

    def test_detail_order_and_final_exact_cursor_reload_with_actual_http(self):
        self.store.write_cursor(d.instant_from_wire(report.START))
        notes = [note('early', 'B', content='Earlier own text', posted_at=report.FIRST),
                 note('late', 'B', content='Later own text', posted_at=report.LAST)]
        rows = [item('A'), item('B', parent_id='A')]
        transport, _ = self.boundary([self.sync('delta-token', full(items=rows, notes=notes)),
                                     self.sync('full-token', delta())])
        status, out, err, _ = invoke(self, ['--refresh', 'step', 'B'], transport, now=sync_fixture.NOW)
        self.assertEqual(status, 0, err)
        self.assertLess(out.index('Earlier own text'), out.index('Later own text'))
        state = StateStore(self.root).load_consistent_state()
        self.assertEqual(d.instant_text(state.snapshot.comments['late'].added_at), report.LAST)
        self.assertEqual(d.instant_text(state.snapshot.comments['early'].added_at), report.FIRST)
        # Human timestamps keep their existing minute template despite exact data.
        self.assertNotIn('123456', out)
        self.assertEqual(d.instant_text(state.cursor), report.START)
        steps = self.requests(events=[report.event(1, report.LAST, obj='late')],
            cursor=d.instant_from_wire(report.START), current_items=rows, current_notes=notes,
            comments=[dict(id='early', content='Earlier own text', posted_at=report.FIRST, is_deleted=False, file_attachment=None),
                      dict(id='late', content='Later own text', posted_at=report.LAST, is_deleted=False, file_attachment=None)])
        # Prior public refresh advanced current state to the report command time.
        transport, _ = self.boundary(steps)
        status, out, err, _ = invoke(self, ['report', '--final'], transport, now=sync_fixture.NOW)
        self.assertEqual(status, 0, err)
        self.assertIn('Later own text', out)
        self.assertNotIn('Earlier own text', out)
        self.assertEqual(d.instant_text(StateStore(self.root).load_cursor()), report.END)
        status, out, err, factory = invoke(self, ['report', '--show-cursor'])
        self.assertEqual(status, 0, err)
        factory.assert_not_called()
        self.assertIn('Thu 22 Oct 2026, 14:00:00', out)

    def test_refresh_late_binding_failure_no_normal_output_and_new_process_refusal(self):
        cursor = (self.root / 'report-cursor').read_bytes()
        transport, _ = self.boundary([self.sync('delta-token', full(items=[item('A'), item('B', parent_id='A')],
            notes=[note('own', 'B', content='Preserved observation', posted_at=sync_fixture.COMMENT)])),
            self.sync('full-token', delta())])
        replace = os.replace
        def fail_binding(source, destination):
            if Path(destination).name == 'binding.json':
                raise OSError('controlled binding replacement failure')
            return replace(source, destination)
        with patch('todo_lib.local.safety.os.replace', side_effect=fail_binding):
            status, out, err, _ = invoke(self, ['now', '--refresh'], transport, now=sync_fixture.NOW)
        self.assertEqual(status, 1)
        self.assertEqual(out, '')
        self.assertIn('publication', err)
        self.assertIn('partially published', err)
        self.assertIn('unusable', err)
        self.assertNotIn('previous cache was not replaced', err)
        self.assertIn('Preserved observation', (self.root / 'history.json').read_text())
        self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)
        for name in ('cache.json', 'history.json', 'binding.json'):
            json.loads((self.root / name).read_text())
        result = subprocess.run([str(ROOT / 'todo'), 'now'],
            env={**os.environ, 'HOME': str(self.root.parent), 'TODOIST_TOKEN': '',
                 'PYTHONDONTWRITEBYTECODE': '1'}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertIn('restore consistent state', result.stderr)
        # Offline mixed-set refusal has no credential or transport dependency.
        status, out, err, factory = invoke(self, ['now'])
        self.assertEqual(status, 1)
        self.assertEqual(out, '')
        factory.assert_not_called()
        self.assertIn('restore consistent state', err)

    def test_relative_report_and_cursor_boundaries_use_command_calendar(self):
        # Relative command-time projection is permitted; full-second resolved
        # boundaries are asserted without a strict submicrosecond clock demand.
        status, out, err, factory = invoke(self, ['report', '--set-cursor', '1 day ago', '--yes'], now=sync_fixture.NOW)
        self.assertEqual(status, 0, err)
        factory.assert_not_called()
        self.assertEqual(d.instant_text(self.store.load_cursor()), '2026-10-21T12:00:00.123456Z')
        self.assertIn('Previous report cursor:', out)
        self.assertIn('Proposed report cursor:', out)
        status, out, err, _ = invoke(self, ['report', '--since', 'bad-boundary'])
        self.assertEqual(status, 2)
        self.assertIn('Boundaries:', err)


    def test_public_final_output_failure_keeps_cursor_and_history(self):
        before = (self.root / 'report-cursor').read_bytes()
        transport, _ = self.boundary(self.requests(comments=[]))
        class BrokenOutput(StringIO):
            def write(self, text):
                raise BrokenPipeError('pipe closed')
        status, out, err, _ = invoke(self, ['report', '--final'], transport, now=sync_fixture.NOW, output=BrokenOutput())
        self.assertEqual(status, 1)
        self.assertIn('could not write complete output', err)
        self.assertEqual((self.root / 'report-cursor').read_bytes(), before)
        self.assertTrue(self.store.load_history().snapshot.items)
