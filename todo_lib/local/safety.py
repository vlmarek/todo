"""POSIX path checks and ordinary-process atomic replacement (no fsync promise)."""
import os
from pathlib import Path
import stat
import tempfile


class LocalError(ValueError):
    """Safe-to-display local problem; never includes file contents."""


SENSITIVE = ('config', 'binding.json', 'report-cursor', 'cache.json', 'history.json', 'lock')


def directory(path, *, missing=False):
    path = Path(path)
    try:
        info = path.lstat()
    except FileNotFoundError:
        if missing:
            return None
        raise LocalError(f'{path}: missing directory; run todo init') from None
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise LocalError(f'{path}: requires an owned real directory, not a symlink')
    if stat.S_IMODE(info.st_mode) != 0o700:
        raise LocalError(f'{path}: repair directory mode to 0700')
    return info


def regular(path, *, missing=False):
    path = Path(path)
    try:
        info = path.lstat()
    except FileNotFoundError:
        if missing:
            return None
        raise LocalError(f'{path}: missing required file') from None
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise LocalError(f'{path}: requires an owned regular non-symlink file')
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise LocalError(f'{path}: repair file mode to 0600')
    return info


def check_paths(root, *, missing_directory=False):
    """Inspect every relevant path before credential or coordinated state access."""
    root = Path(root)
    if directory(root, missing=missing_directory) is None:
        return
    for name in SENSITIVE:
        regular(root / name, missing=True)


def read_bytes(path):
    path = Path(path)
    directory(path.parent)
    regular(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
                raise LocalError(f'{path}: unsafe file')
            return stream.read()
    except OSError:
        raise LocalError(f'{path}: unreadable file; repair local access') from None


def atomic_write(path, content, validator):
    """Validate complete bytes, write a 0600 sibling, replace, clean on failure.

    Each call is atomic individually. Callers coordinate multiple files with the
    process lock and a binding-last publication; this is not a transaction.
    """
    path = Path(path)
    directory(path.parent)
    regular(path, missing=True)
    validator(content)
    candidate = None
    try:
        fd, candidate = tempfile.mkstemp(prefix='.todo-candidate-', dir=path.parent)
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(content)
            stream.flush()
        regular(path, missing=True)
        os.replace(candidate, path)
    except OSError:
        raise LocalError(f'{path}: atomic replacement failed') from None
    finally:
        if candidate is not None:
            try:
                os.unlink(candidate)
            except FileNotFoundError:
                pass


def wizard_mode_repairs(root):
    """Inspect only; return (path, current_mode, required_mode) for T11 prompts.

    This exception applies only with missing or zero-byte config, owned real
    directory/files. No content or credentials are read and nothing is changed.
    """
    root = Path(root)
    try:
        info = root.lstat()
    except FileNotFoundError:
        return ()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise LocalError(f'{root}: requires an owned real directory')
    config = root / 'config'
    try:
        ci = config.lstat()
    except FileNotFoundError:
        ci = None
    if ci is not None and (not stat.S_ISREG(ci.st_mode) or ci.st_uid != os.getuid() or ci.st_size != 0):
        raise LocalError(f'{config}: wizard repair requires an owned real empty config')
    for name in SENSITIVE:
        if name != 'config':
            regular(root / name, missing=True)
    repairs = []
    for path, entry, mode in ((root, info, 0o700), (config, ci, 0o600)):
        if entry is not None and stat.S_IMODE(entry.st_mode) != mode:
            repairs.append((path, stat.S_IMODE(entry.st_mode), mode))
    return tuple(repairs)


def repair_wizard_modes(root, *, confirmed=False):
    """T11 calls only after explicit confirmation of wizard_mode_repairs()."""
    repairs = wizard_mode_repairs(root)
    if not confirmed:
        raise LocalError('wizard mode repair requires explicit confirmation')
    for path, _, mode in repairs:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            os.fchmod(fd, mode)
        finally:
            os.close(fd)
    check_paths(root, missing_directory=True)


def create_directory(root):
    """Wizard caller must establish terminal eligibility before creation."""
    root = Path(root)
    directory(root, missing=True)
    try:
        root.mkdir(mode=0o700)
    except FileExistsError:
        pass
    else:
        # An unusually restrictive umask must not leave our new directory
        # unusable. Existing directories are never silently repaired here.
        os.chmod(root, 0o700, follow_symlinks=False)
    directory(root)
