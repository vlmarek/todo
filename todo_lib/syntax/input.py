"""The sole interactive read path for workflow consumers.

No --yes policy is embedded here: callers decide whether a question is needed.
Streams and read/hidden-reader callbacks are injectable for offline verification.
"""
import sys
from contextlib import contextmanager


class InputError(RuntimeError):
    status = 1


class Cancelled(InputError):
    pass


class Interrupted(InputError):
    status = 130


@contextmanager
def _no_echo(stream):
    # Never fall back to an echoed credential read (including getpass fallback).
    import termios
    try:
        fd = stream.fileno()
        saved = termios.tcgetattr(fd)
        hidden = saved[:]
        hidden[3] &= ~(termios.ECHO | termios.ECHONL)
        termios.tcsetattr(fd, termios.TCSAFLUSH, hidden)
    except (OSError, ValueError, AttributeError, termios.error) as exc:
        raise InputError('cannot hide input') from exc
    try:
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSAFLUSH, saved)


def interactive(stdin=None, stdout=None):
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    return bool(stdin.isatty() and stdout.isatty())


def prompt(message, *, stdin=None, stdout=None, stderr=None, hidden=False, default=None,
           validate=None, cancel=('q',), reader=None, hidden_reader=None):
    """Flush a question then read one line, retrying ValueError validation.

    Both streams must be TTYs even with injected readers. reader receives stdin;
    hidden_reader receives stdin and must guarantee suppression and restoration
    of echo. Without hidden_reader a termios guard encloses the supplied reader.
    EOF and cancel raise Cancelled (status 1); SIGINT raises Interrupted (130).
    Blank uses a supplied default; otherwise it is an ordinary value for validate.
    No token/answer content is included in hidden validation diagnostics.
    Questions use stdout; validation and retry diagnostics use stderr.
    """
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    if not interactive(stdin, stdout):
        raise InputError('interactive input requires both stdin and stdout terminals')
    read = reader or (lambda stream: stream.readline())
    try:
        while True:
            stdout.write(message)
            stdout.flush()
            if hidden:
                if hidden_reader is not None:
                    try:
                        line = hidden_reader(stdin)
                    except (OSError, ValueError) as exc:
                        raise InputError('cannot hide input') from exc
                else:
                    with _no_echo(stdin):
                        line = read(stdin)
                stdout.write('\n')
                stdout.flush()
            else:
                line = read(stdin)
            if line is None or line == '':
                raise Cancelled('input cancelled')
            answer = line.rstrip('\r\n')
            if answer in cancel:
                raise Cancelled('input cancelled')
            if answer == '' and default is not None:
                return default
            if validate is None:
                return answer
            try:
                return validate(answer)
            except ValueError as exc:
                stderr.write(('Invalid input.' if hidden else str(exc)) + '\n')
                stderr.flush()
    except EOFError as exc:
        raise Cancelled('input cancelled') from exc
    except KeyboardInterrupt as exc:
        raise Interrupted('input interrupted') from exc


def select(candidates, *, render, stdin=None, stdout=None, **kwargs):
    """Print explicit (number, stable object) choices and return chosen object.

    render(number, object) returns its complete workflow-owned display line.
    Noninteractive ambiguity prints the same candidates then fails without a
    question or detail. Numbers need not be contiguous but must be unique > 0.
    """
    candidates = tuple(candidates)
    choices = dict(candidates)
    if not choices or len(choices) != len(candidates) or any(type(n) is not int or n < 1 for n in choices):
        raise ValueError('candidates require unique positive numbers')
    stdout = sys.stdout if stdout is None else stdout
    for number, obj in candidates:
        stdout.write(render(number, obj) + '\n')
    stdout.flush()
    def choose(value):
        if value == '': raise Cancelled('selection cancelled')
        if not value.isascii() or not value.isdecimal() or int(value) not in choices:
            raise ValueError('Choose a displayed number, q, or blank to cancel.')
        return choices[int(value)]
    return prompt('Selection: ', stdin=stdin, stdout=stdout, validate=choose, **kwargs)
