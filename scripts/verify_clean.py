"""Single broad gate plus distinct copied probes. No dependency installation."""
from pathlib import Path
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def environment(home, install, outside):
    # Allowlist, never forward credential, Python startup, pager or editor settings.
    return dict(HOME=str(home), PATH=str(install) + ':/usr/local/bin:/usr/bin:/bin',
                TMPDIR=str(outside), LANG='C.UTF-8', TERM='xterm',
                PYTHONDONTWRITEBYTECODE='1', TODOIST_TOKEN='synthetic-delivery-token')


def status(root):
    return subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=all'], cwd=root)


def artifacts(root):
    forbidden = {'__pycache__', '.todo', '.pytest_cache', '.coverage', '.env'}
    bad = [p.relative_to(root) for p in root.rglob('*') if '.git' not in p.parts and
           (p.name in forbidden or p.suffix in ('.pyc', '.pyo') or p.name.startswith('.todo-candidate-'))]
    if bad:
        raise RuntimeError('forbidden generated/credential paths: ' + ', '.join(map(str, bad)))


def run(root=ROOT):
    root = Path(root).resolve()
    entry = status(root)
    print('verify-clean: Git status entry (full porcelain, including untracked):', flush=True)
    print(entry.decode() or '(clean)', end='' if entry else '\n', flush=True)
    subprocess.run(['git', 'status', '--untracked-files=all'], cwd=root, check=True)
    artifacts(root)
    with tempfile.TemporaryDirectory(prefix='todo-verify-') as temp:
        base = Path(temp)
        home, install, outside = (base / n for n in ('home', 'bin', 'outside'))
        for path in (home, install, outside):
            path.mkdir(mode=0o700)
        env = environment(home, install, outside)
        try:
            # The only complete suite invocation in this gate.
            subprocess.run([str(root / 'scripts/check')], cwd=root, env=env, check=True)
            shutil.copy2(root / 'todo', install / 'todo')
            shutil.copytree(root / 'todo_lib', install / 'todo_lib')
            runtime = [root / 'todo', *(root / 'todo_lib').rglob('*')]
            for source in runtime:
                if source.is_file():
                    assert source.read_bytes() == (install / source.relative_to(root)).read_bytes()
            # Test-only programs are copied separately; runtime has no tests tree.
            for name in ('copy_probe.py', 'less_probe.py'):
                shutil.copy2(root / 'tests/delivery/final' / name, outside / name)
            subprocess.run(['todo', 'help'], cwd=outside, env=env, check=True, stdout=subprocess.PIPE)
            subprocess.run(['python3.11', '-I', '-B', str(outside / 'copy_probe.py'), str(install)],
                           cwd=outside, env=env, check=True, timeout=60)
            subprocess.run(['python3.11', '-I', '-B', str(outside / 'less_probe.py'), str(install)],
                           cwd=outside, env=env, check=True, timeout=30)
            for source in runtime:
                if source.is_file():
                    assert source.read_bytes() == (install / source.relative_to(root)).read_bytes()
            for area in (root, install, outside):
                artifacts(area)
        finally:
            end = status(root)
            print('verify-clean: Git status end (full porcelain, including untracked):', flush=True)
            print(end.decode() or '(clean)', end='' if end else '\n', flush=True)
            subprocess.run(['git', 'status', '--untracked-files=all'], cwd=root, check=True)
            artifacts(root)
            if end != entry:
                raise RuntimeError('Git status changed during verification')
    print('verify-clean: one complete suite + unchanged copied runtime + real less passed', flush=True)


if __name__ == '__main__':
    if (platform.system(), platform.machine(), sys.implementation.name, sys.version_info[:2]) != (
            'Linux', 'x86_64', 'cpython', (3, 11)) or not Path('/.dockerenv').exists():
        raise SystemExit('setup blocker: pinned Docker Linux/amd64 CPython 3.11 environment required')
    if not shutil.which('less'):
        raise SystemExit('setup blocker: GNU less required')
    ZoneInfo('Europe/Prague')
    run()
