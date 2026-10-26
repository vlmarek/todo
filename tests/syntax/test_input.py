import io
import unittest
from unittest.mock import patch
from todo_lib.syntax import prompt, select, InputError, Cancelled, Interrupted


class Stream(io.StringIO):
    def __init__(self, text='', tty=True, events=None):
        super().__init__(text)
        self.tty, self.events = tty, events if events is not None else []

    def isatty(self):
        return self.tty

    def fileno(self):
        return 99

    def write(self, text):
        self.events.append(('write', text))
        return super().write(text)

    def flush(self):
        self.events.append(('flush',))

    def readline(self):
        self.events.append(('read',))
        return super().readline()


class InputTests(unittest.TestCase):
    def test_flush_before_every_read_and_validation(self):
        events = []
        source, dest = Stream('bad\n42\n', events=events), Stream(events=events)
        errors = Stream(tty=False)
        self.assertEqual(prompt('Number: ', stdin=source, stdout=dest, stderr=errors, validate=int), 42)
        self.assertEqual(dest.getvalue(), 'Number: Number: ')
        self.assertIn('bad', errors.getvalue())
        self.assertEqual(errors.events[-1], ('flush',))
        reads = [i for i, e in enumerate(events) if e == ('read',)]
        self.assertEqual(len(reads), 2)
        self.assertTrue(all(events[i - 1] == ('flush',) for i in reads))

    def test_both_ttys_required(self):
        for a, b in ((False, True), (True, False), (False, False)):
            events = []
            source, dest = Stream('secret\n', a, events), Stream(tty=b, events=events)
            with self.subTest(stdin=a, stdout=b), self.assertRaises(InputError):
                prompt('Question: ', stdin=source, stdout=dest)
            self.assertEqual(events, [])

    def test_eof_cancel_default_and_interrupt(self):
        for text in ('', 'q\n'):
            with self.subTest(text=text), self.assertRaises(Cancelled):
                prompt('Q: ', stdin=Stream(text), stdout=Stream())
        self.assertEqual(prompt('Q: ', stdin=Stream('\n'), stdout=Stream(), default='Work'), 'Work')
        with self.assertRaises(Interrupted) as caught:
            prompt('Q: ', stdin=Stream(), stdout=Stream(), reader=lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))
        self.assertEqual(caught.exception.status, 130)
        with self.assertRaises(Cancelled):
            prompt('Q: ', stdin=Stream(), stdout=Stream(), reader=lambda _: (_ for _ in ()).throw(EOFError()))

    def test_hidden_input_restores_on_all_exit_paths(self):
        import termios
        saved = [0, 0, 0, termios.ECHO | termios.ECHONL | termios.ICANON, 0, 0, []]
        for outcome in ('secret\n', '', KeyboardInterrupt(), EOFError(), OSError('read failed')):
            changes = []
            def read(_):
                self.assertFalse(changes[0][3] & (termios.ECHO | termios.ECHONL))
                if isinstance(outcome, BaseException): raise outcome
                return outcome
            dest = Stream()
            with self.subTest(outcome=type(outcome)), patch('termios.tcgetattr', return_value=saved), patch('termios.tcsetattr', side_effect=lambda fd, when, attrs: changes.append(attrs)):
                if outcome == 'secret\n':
                    self.assertEqual(prompt('Token: ', stdin=Stream(), stdout=dest, hidden=True, reader=read), 'secret')
                else:
                    with self.assertRaises((Cancelled, Interrupted, OSError)):
                        prompt('Token: ', stdin=Stream(), stdout=dest, hidden=True, reader=read)
                self.assertEqual(changes[-1], saved)
                self.assertNotIn('secret', dest.getvalue())

    def test_real_terminal_echo_restoration(self):
        import os
        import termios
        master, slave = os.openpty()
        try:
            with os.fdopen(slave, 'r') as source:
                saved = termios.tcgetattr(source.fileno())
                self.assertTrue(saved[3] & termios.ECHO)
                def interrupt(stream):
                    attrs = termios.tcgetattr(stream.fileno())
                    self.assertFalse(attrs[3] & (termios.ECHO | termios.ECHONL))
                    raise KeyboardInterrupt()
                with self.assertRaises(Interrupted):
                    prompt('Token: ', stdin=source, stdout=Stream(), hidden=True, reader=interrupt)
                self.assertEqual(termios.tcgetattr(source.fileno()), saved)
        finally:
            os.close(master)

    def test_hidden_failure_never_falls_back(self):
        with patch('termios.tcgetattr', side_effect=OSError('no terminal')), self.assertRaises(InputError):
            prompt('Token: ', stdin=Stream('secret\n'), stdout=Stream(), hidden=True,
                   reader=lambda _: self.fail('must not read echoed token'))
        with self.assertRaises(InputError):
            prompt('Token: ', stdin=Stream(), stdout=Stream(), hidden=True,
                   hidden_reader=lambda _: (_ for _ in ()).throw(OSError('cannot hide')))

    def test_hidden_validation_redacts_answer(self):
        dest, errors = Stream(), Stream(tty=False)
        def validate(value):
            if value == 'secret': raise ValueError('invalid secret')
            return value
        self.assertEqual(prompt('Token: ', stdin=Stream('secret\nok\n'), stdout=dest,
                                stderr=errors,
                                hidden=True, hidden_reader=lambda s: s.readline(), validate=validate), 'ok')
        self.assertEqual(dest.getvalue(), 'Token: \nToken: \n')
        self.assertEqual(errors.getvalue(), 'Invalid input.\n')
        self.assertNotIn('secret', dest.getvalue() + errors.getvalue())

    def test_default_stderr_and_retry_then_cancel(self):
        dest, errors = Stream(), Stream(tty=False)
        with patch('sys.stderr', errors), self.assertRaises(Cancelled):
            prompt('Number: ', stdin=Stream('bad\nq\n'), stdout=dest, validate=int)
        self.assertEqual(dest.getvalue(), 'Number: Number: ')
        self.assertIn('bad', errors.getvalue())
        self.assertEqual(errors.events[-1], ('flush',))

    def test_explicit_choices_stable_identity_retry_cancel_noninteractive(self):
        first, second = object(), object()
        candidates = [(2, first), (7, second)]
        render = lambda n, obj: f'{n}. Candidate {n}'
        dest, errors = Stream(), Stream(tty=False)
        self.assertIs(select(candidates, render=render, stdin=Stream('1\n7\n'), stdout=dest, stderr=errors), second)
        expected = '2. Candidate 2\n7. Candidate 7\n'
        self.assertEqual(dest.getvalue(), expected + 'Selection: Selection: ')
        self.assertEqual(errors.getvalue(), 'Choose a displayed number, q, or blank to cancel.\n')
        for text in ('\n', 'q\n', ''):
            with self.subTest(text=text), self.assertRaises(Cancelled):
                select(candidates, render=render, stdin=Stream(text), stdout=Stream())
        dest = Stream(tty=False)
        with self.assertRaises(InputError):
            select(candidates, render=render, stdin=Stream(), stdout=dest)
        self.assertEqual(dest.getvalue(), expected)


if __name__ == '__main__':
    unittest.main()
