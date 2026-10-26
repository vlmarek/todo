"""Optional direct-argv pager with a complete protected, seekable input file.

No producer pipe exists: exit zero is success even when no bytes were read.
Children inherit the original terminal output and process group, so /dev/tty
remains available for navigation. Terminal attributes are restored on every path.
"""
from dataclasses import dataclass
import os
import signal
import subprocess
import sys
import tempfile
import termios
from .render import Document


@dataclass(frozen=True)
class OriginalStreams:
    stdin: object
    stdout: object
    stderr: object

    @classmethod
    def current(cls):
        return cls(sys.stdin, sys.stdout, sys.stderr)


# Explicit allowlist keeps decisions, help, diagnostics and mutations direct.
PAGED_VIEWS = frozenset(('default', 'now', 'task', 'step', 'category', 'comments',
                         'comment', 'waiting', 'someday', 'search', 'report',
                         'report-preview', 'report-show-cursor'))


class OutputError(OSError):
    """Complete direct write or flush failed; finalization must not advance."""


def _write(stream, text):
    try:
        if text:
            data = text if text.endswith('\n') else text + '\n'
            written = stream.write(data)
            if written != len(data):
                raise OutputError('incomplete output write')
        stream.flush()
    except (OSError, ValueError, UnicodeError) as error:
        raise OutputError('could not write complete output') from error


def _terminal_state(stream):
    try:
        fd = stream.fileno()
        return fd, termios.tcgetattr(fd)
    except (AttributeError, OSError, ValueError, termios.error):
        return None


def _stop(child):
    if child is None or child.poll() is not None:
        return
    try:
        child.terminate()
    except ProcessLookupError:
        child.wait()
        return
    try:
        child.wait(timeout=1)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


def deliver(document, settings, original_streams=None, view_kind='now', *, environ=None):
    """Write/flush a rendered Document, returning 0 on complete delivery.

    OutputError propagates on direct failure. KeyboardInterrupt propagates after
    cleanup, for the CLI's existing exit-130 handler; it never starts fallback.
    settings.pager is the configuration API's already parsed argv tuple. Text and
    colors must already have been chosen against original_streams.stdout.
    """
    streams = original_streams or OriginalStreams.current()
    env = os.environ if environ is None else environ
    if isinstance(document, str):
        document = Document(document)
    _write(streams.stderr, document.stderr)
    argv = settings.pager
    eligible = (bool(argv) and view_kind in PAGED_VIEWS and
                streams.stdin.isatty() and streams.stdout.isatty() and env.get('TERM') != 'dumb')
    if not eligible:
        _write(streams.stdout, document.stdout)
        return 0
    states = [state for stream in (streams.stdin, streams.stdout)
              if (state := _terminal_state(stream)) is not None]
    child = None
    failed = False
    try:
        # TemporaryFile is created mode 0600 and immediately unlinked on Unix.
        # Complete the file before launch; no short/empty-output fit heuristics.
        with tempfile.TemporaryFile(mode='w+b') as source:
            # A child writes through stdout's file descriptor, bypassing write().
            # Apply any public output filter before bytes reach its input file.
            content = getattr(streams.stdout, 'sanitize', lambda text: text)(document.stdout)
            if content and not content.endswith('\n'):
                content += '\n'
            encoded = content.encode('utf-8')
            if source.write(encoded) != len(encoded):
                raise OSError('incomplete pager input write')
            source.flush()
            source.seek(0)
            streams.stdout.flush()
            child = subprocess.Popen(tuple(argv), stdin=source, stdout=streams.stdout,
                                     stderr=streams.stderr, shell=False)
            status = child.wait()
            if status == -signal.SIGINT:
                raise KeyboardInterrupt
            failed = status != 0
    except KeyboardInterrupt:
        _stop(child)
        raise
    except (OSError, ValueError, UnicodeError):
        _stop(child)
        failed = True
    finally:
        for state in states:
            try:
                termios.tcsetattr(state[0], termios.TCSANOW, state[1])
            except (OSError, termios.error):
                pass
    if failed:
        _write(streams.stderr, 'todo: warning: pager failed; writing complete output directly')
        _write(streams.stdout, document.stdout)
    return 0
