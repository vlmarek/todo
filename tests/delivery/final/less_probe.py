"""Bounded real GNU less through copied public CLI/config and original PTY color."""
import errno
import fcntl
import os
from pathlib import Path
import pty
import select
import signal
import struct
import sys
import termios
import time


def probe(argv, navigate):
    pid, fd = pty.fork()
    if pid == 0:
        os.execvp('todo', ['todo', *argv])
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', 8, 100, 0, 0))
    output = bytearray()
    deadline = time.monotonic() + 8
    sent_g = sent_q = exited = False
    try:
        while time.monotonic() < deadline:
            if select.select([fd], [], [], 0.05)[0]:
                try:
                    chunk = os.read(fd, 65536)
                except OSError as error:
                    if error.errno != errno.EIO: raise
                    chunk = b''
                output.extend(chunk)
            child, status = os.waitpid(pid, os.WNOHANG)
            if child:
                exited = True
                assert os.waitstatus_to_exitcode(status) == 0, bytes(output)
                assert not navigate or sent_q, 'long view exited before navigation'
                assert b'pager failed' not in output, bytes(output)
                return bytes(output)
            if navigate and not sent_g and b'Alpha' in output:
                assert b'Newer pending work' not in output, 'long view unexpectedly fit'
                os.write(fd, b'G'); sent_g = True
            if sent_g and not sent_q and b'Newer pending work' in output:
                os.write(fd, b'q'); sent_q = True
        raise AssertionError('bounded real-less PTY timed out: ' + repr(bytes(output)))
    finally:
        if not exited:
            os.killpg(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        os.close(fd)


if __name__ == '__main__':
    config = Path.home() / '.todo/config'
    config.write_text(config.read_text().replace('hidden_from_now=\n', 'hidden_from_now=\npager=less -FR\n'))
    # The cache retains inspection context even after pending history cleanup.
    short = probe(['category'], False)
    assert b'cat' in short
    long = probe(['--color=always', 'step', 'D'], True)
    assert b'\x1b[38;2;' in long, repr(long)
    print('real less -FR: short fit exits 0; long G reaches final work, q exits 0, truecolor retained (8x100 PTY)')
