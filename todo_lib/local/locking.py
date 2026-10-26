"""Fail-fast POSIX coordination; offline reads never acquire this lock."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
from .safety import LocalError, check_paths, regular


class LockBusy(LocalError):
    pass


@contextmanager
def exclusive_lock(operation, root=None):
    """Acquire before freshness-sensitive reads. Released even on SIGINT/error.

    Lock file remains in place: unlinking it would allow independent lock inodes.
    Operation is a non-secret command identifier, never arbitrary argv or input.
    """
    root = Path.home() / '.todo' if root is None else Path(root)
    if not isinstance(operation, str) or re.fullmatch(r'[a-z][a-z0-9 -]{0,63}', operation) is None:
        raise LocalError('invalid lock operation identifier')
    check_paths(root)
    path = root / 'lock'
    flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        fd = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        fd = os.open(path, flags)
    else:
        os.fchmod(fd, 0o600)
    try:
        regular(path)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # The owner publishes an identifier while holding this inode. Do not
            # display arbitrary pre-existing bytes from a runtime coordination file.
            raw = os.pread(fd, 128, 0).decode('ascii', errors='ignore')
            match = re.fullmatch(r'([0-9]+) ([a-z][a-z0-9 -]{0,63})\n', raw)
            detail = f' ({match[2]}, pid {match[1]})' if match else ''
            raise LockBusy('local state is busy' + detail) from None
        os.ftruncate(fd, 0)
        os.write(fd, f'{os.getpid()} {operation}\n'.encode('ascii'))
        try:
            yield
        finally:
            os.ftruncate(fd, 0)
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
