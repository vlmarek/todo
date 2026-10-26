"""Checker self-tests execute only synthetic mini-suites, never this repository."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

CHECK = Path(__file__).resolve().parents[2] / 'scripts' / 'check'
PACKAGES = ('adapter', 'domain', 'local', 'presentation', 'syntax', 'workflows', 'cli', 'delivery',
    'adapter.commands', 'adapter.current', 'adapter.history', 'adapter.transport',
    'workflows.capture', 'workflows.comments', 'workflows.init', 'workflows.lifecycle',
    'workflows.moves', 'workflows.reads', 'workflows.report', 'workflows.sync')


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'scripts').mkdir()
        shutil.copy2(CHECK, self.root / 'scripts/check')
        (self.root / 'todo_lib').mkdir()
        (self.root / 'todo_lib/__init__.py').touch()
        (self.root / 'todo_lib/cli.py').write_text('def main(): return 0\n')
        (self.root / 'todo').write_text('#!/usr/bin/env python3\nfrom todo_lib.cli import main\n')
        (self.root / 'todo').chmod(0o755)
        (self.root / 'tests').mkdir()
        (self.root / 'tests/__init__.py').touch()
        for package in PACKAGES:
            folder = self.root / 'tests' / package.replace('.', '/')
            folder.mkdir()
            (folder / '__init__.py').touch()
            (folder / 'test_mini.py').write_text('import unittest\nclass Mini(unittest.TestCase):\n def test_ok(self): pass\n')

    def run_check(self):
        result = subprocess.run([str(self.root / 'scripts/check')], cwd='/',
                                capture_output=True, text=True, env={**os.environ, 'PYTHONPATH': ''})
        self.assertFalse(list(self.root.rglob('__pycache__')))
        return result

    def test_complete_discovery_runs_each_once(self):
        path = self.root / 'tests/cli/test_mini.py'
        path.write_text(path.read_text() + 'from tests.domain.test_mini import Mini as ImportedFixture\n')
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('discovered 20 offline tests', result.stdout)
        self.assertIn('Ran 20 tests', result.stderr)

    def test_failure_skip_missing_and_broken_import_propagate(self):
        path = self.root / 'tests/cli/test_mini.py'
        original = path.read_text()
        for body in ('import unittest\nclass Mini(unittest.TestCase):\n def test_bad(self): self.fail("failure")\n',
                     'import unittest\nclass Mini(unittest.TestCase):\n @unittest.skip("required")\n def test_bad(self): pass\n',
                     'raise ImportError("broken import")\n', ''):
            with self.subTest(body=body):
                path.write_text(body)
                result = self.run_check()
                self.assertNotEqual(result.returncode, 0)
        path.write_text(original)
        (self.root / 'tests/local/__init__.py').unlink()
        result = self.run_check()
        self.assertIn('missing required test package', result.stderr)

    def test_launcher_and_syntax_requirements(self):
        launcher = self.root / 'todo'
        launcher.chmod(0o644)
        self.assertNotEqual(self.run_check().returncode, 0)
        launcher.chmod(0o755)
        launcher.write_text('')
        self.assertNotEqual(self.run_check().returncode, 0)
        launcher.write_text('#!/usr/bin/env python\n')
        self.assertNotEqual(self.run_check().returncode, 0)
        launcher.write_text('#!/usr/bin/env python3\n')
        (self.root / 'todo_lib/cli.py').write_text('invalid python!\n')
        self.assertNotEqual(self.run_check().returncode, 0)
