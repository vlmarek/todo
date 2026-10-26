import io
import json
import os
from pathlib import Path
import pty
import signal
import stat
import subprocess
import sys
import tempfile
import termios
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from todo_lib.presentation import Color, Document, OriginalStreams, OutputError, deliver
from todo_lib.presentation.delivery import PAGED_VIEWS


class TtyFile:
    """Controlled TTY eligibility with a real inherited file descriptor."""
    def __init__(self, file, tty=True):
        self.file, self.tty = file, tty
    def isatty(self):
        return self.tty
    def fileno(self):
        return self.file.fileno()
    def write(self, data):
        return self.file.write(data)
    def flush(self):
        return self.file.flush()


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        files = [tempfile.TemporaryFile(mode='w+', encoding='utf-8') for _ in range(3)]
        for file in files:
            self.addCleanup(file.close)
        self.streams = OriginalStreams(*(TtyFile(file) for file in files))
        self.script = self.root / 'pager.py'
        self.capture = self.root / 'capture.json'
        self.script.write_text('''import json, os, stat, sys
from pathlib import Path
mode, capture, *args = sys.argv[1:]
if mode == 'early':
    sys.exit(0)
if mode == 'sigint':
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    os.kill(os.getpid(), signal.SIGINT)
if mode == 'fail':
    sys.stdin.read(1)
    sys.exit(7)
Path(capture).write_text(json.dumps({'args': args, 'input': sys.stdin.read(), 'mode': stat.S_IMODE(os.fstat(0).st_mode), 'seekable': sys.stdin.seekable()}))
''')

    def settings(self, mode='read', *args):
        return SimpleNamespace(pager=(sys.executable, str(self.script), mode, str(self.capture), *args))

    def contents(self, stream):
        stream.flush()
        stream.file.seek(0)
        return stream.file.read()

    def test_exact_argv_complete_input_original_colors_and_private_file(self):
        document = Document('\x1b[1mP1\x1b[0m title\n\n  full Unicode λ', 'coverage')
        result = deliver(document, self.settings('read', 'a b', '$HOME', '|', '-FR'), self.streams, environ={'TERM': 'xterm'})
        self.assertEqual(result, 0)
        data = json.loads(self.capture.read_text())
        self.assertEqual(data, {'args': ['a b', '$HOME', '|', '-FR'], 'input': document.stdout + '\n', 'mode': 0o600, 'seekable': True})
        self.assertEqual(self.contents(self.streams.stdout), '')
        self.assertEqual(self.contents(self.streams.stderr), 'coverage\n')

    def test_short_and_empty_documents_are_paged(self):
        for text in ('', 'No actionable items.'):
            with self.subTest(text=text):
                deliver(Document(text), self.settings(), self.streams, environ={'TERM': 'xterm'})
                self.assertEqual(json.loads(self.capture.read_text())['input'], text + ('\n' if text else ''))

    def test_early_exit_zero_no_fallback_even_for_huge_document(self):
        deliver(Document('unread line\n' * 100000), self.settings('early'), self.streams, environ={'TERM': 'xterm'})
        self.assertEqual(self.contents(self.streams.stdout), '')
        self.assertEqual(self.contents(self.streams.stderr), '')

    def test_real_failure_and_launch_failure_full_fallback(self):
        for settings in (self.settings('fail'), SimpleNamespace(pager=('/no/such/todo-test-pager',))):
            with self.subTest(settings=settings):
                for stream in (self.streams.stdout, self.streams.stderr):
                    stream.file.seek(0)
                    stream.file.truncate()
                text = 'all original\n\n  lines λ'
                self.assertEqual(deliver(Document(text), settings, self.streams, environ={'TERM': 'xterm'}), 0)
                self.assertEqual(self.contents(self.streams.stdout), text + '\n')
                self.assertEqual(self.contents(self.streams.stderr), 'todo: warning: pager failed; writing complete output directly\n')

    def test_every_eligible_kind_pages_whole_document(self):
        for kind in PAGED_VIEWS:
            with self.subTest(kind=kind):
                deliver(Document(kind), self.settings(), self.streams, kind, environ={'TERM': 'xterm'})
                self.assertEqual(json.loads(self.capture.read_text())['input'], kind + '\n')

    def test_direct_exclusions_and_noninteractive(self):
        for kind in ('help', 'diagnostic', 'prompt', 'ambiguity', 'mutation-preview', 'receipt', 'report-final'):
            with self.subTest(kind=kind), patch('todo_lib.presentation.delivery.subprocess.Popen') as launch:
                deliver(Document('direct'), self.settings(), self.streams, kind, environ={'TERM': 'xterm'})
                launch.assert_not_called()
        for input_tty, output_tty, term, pager in ((False, True, 'xterm', True), (True, False, 'xterm', True),
                                                    (True, True, 'dumb', True), (True, True, 'xterm', False)):
            self.streams.stdin.tty, self.streams.stdout.tty = input_tty, output_tty
            settings = self.settings() if pager else SimpleNamespace(pager=())
            with patch('todo_lib.presentation.delivery.subprocess.Popen') as launch:
                deliver(Document('direct'), settings, self.streams, environ={'TERM': term})
                launch.assert_not_called()
        self.assertEqual(self.contents(self.streams.stdout), 'direct\n' * 11)

    def test_temp_closed_on_failure_and_interruption(self):
        real_temp = tempfile.TemporaryFile
        opened = []
        def create(*args, **kwargs):
            file = real_temp(*args, **kwargs)
            opened.append(file)
            return file
        with patch('todo_lib.presentation.delivery.tempfile.TemporaryFile', side_effect=create):
            deliver(Document('complete'), self.settings('fail'), self.streams, environ={'TERM': 'xterm'})
            self.assertTrue(opened[-1].closed)
            child = SimpleNamespace(wait=lambda: (_ for _ in ()).throw(KeyboardInterrupt()), poll=lambda: 0)
            with patch('todo_lib.presentation.delivery.subprocess.Popen', return_value=child):
                with self.assertRaises(KeyboardInterrupt):
                    deliver(Document('complete'), self.settings(), self.streams, environ={'TERM': 'xterm'})
            self.assertTrue(opened[-1].closed)
        self.assertEqual(self.contents(self.streams.stdout), 'complete\n')

    def test_real_sigint_child_reaped_terminal_restored_and_no_fallback(self):
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        before = termios.tcgetattr(slave)
        pidfile = self.root / 'pid'
        self.script.write_text('''import os, signal, sys, termios, time
from pathlib import Path
state = termios.tcgetattr(1)
state[3] &= ~termios.ECHO
termios.tcsetattr(1, termios.TCSANOW, state)
Path(sys.argv[1]).write_text(str(os.getpid()))
os.kill(os.getppid(), signal.SIGINT)
time.sleep(30)
''')
        harness = self.root / 'harness.py'
        harness.write_text('''import sys
from types import SimpleNamespace
from todo_lib.presentation import Document, deliver
try:
    deliver(Document('must not be dumped'), SimpleNamespace(pager=tuple(sys.argv[1:])), environ={'TERM': 'xterm'})
except KeyboardInterrupt:
    sys.exit(130)
''')
        env = dict(os.environ, PYTHONPATH=str(Path.cwd()), PYTHONDONTWRITEBYTECODE='1')
        parent = subprocess.Popen((sys.executable, '-B', str(harness), sys.executable, str(self.script), str(pidfile)),
                                  stdin=slave, stdout=slave, stderr=subprocess.PIPE, env=env)
        self.addCleanup(lambda: parent.kill() if parent.poll() is None else None)
        _, errors = parent.communicate(timeout=10)
        self.assertEqual(parent.returncode, 130, errors)
        self.assertEqual(errors, b'')
        self.assertEqual(termios.tcgetattr(slave), before)
        with self.assertRaises(ProcessLookupError):
            os.kill(int(pidfile.read_text()), 0)
        import select
        self.assertEqual(select.select([master], [], [], 0)[0], [])

    def test_direct_write_and_flush_errors_exposed_to_finalization(self):
        class Bad(io.StringIO):
            def flush(self):
                raise OSError('disk full')
        with self.assertRaises(OutputError):
            deliver(Document('full report'), self.settings(), OriginalStreams(io.StringIO(), Bad(), io.StringIO()), 'report-final')
        class Short(io.StringIO):
            def write(self, text):
                return 1
        with self.assertRaises(OutputError):
            deliver(Document('full report'), self.settings(), OriginalStreams(io.StringIO(), Short(), io.StringIO()), 'report-final')

    def test_original_stdout_color_policy(self):
        for mode, env, tty, enabled in [('auto', {}, True, True), ('auto', {}, False, False),
                                        ('auto', {'NO_COLOR': ''}, True, False),
                                        ('auto', {'TERM': 'dumb'}, True, False),
                                        ('always', {'NO_COLOR': '', 'TERM': 'dumb'}, False, True),
                                        ('never', {}, True, False)]:
            self.streams.stdout.tty = tty
            self.assertEqual(Color.for_stdout(self.streams.stdout, mode, environ=env).enabled, enabled)

    def test_child_sigint_never_falls_back(self):
        with self.assertRaises(KeyboardInterrupt):
            deliver(Document('no dump'), self.settings('sigint'), self.streams, environ={'TERM': 'xterm'})
        self.assertEqual(self.contents(self.streams.stdout), '')
        self.assertEqual(self.contents(self.streams.stderr), '')

    def test_input_preparation_failure_fallback_and_failed_fallback_propagates(self):
        with patch('todo_lib.presentation.delivery.tempfile.TemporaryFile', side_effect=OSError('full')):
            self.assertEqual(deliver(Document('original'), self.settings(), self.streams, environ={'TERM': 'xterm'}), 0)
        self.assertEqual(self.contents(self.streams.stdout), 'original\n')
        class BadTty(TtyFile):
            def write(self, text):
                raise OSError('closed output')
        streams = OriginalStreams(self.streams.stdin, BadTty(self.streams.stdout.file), self.streams.stderr)
        with self.assertRaises(OutputError):
            deliver(Document('original'), self.settings('fail'), streams, environ={'TERM': 'xterm'})
