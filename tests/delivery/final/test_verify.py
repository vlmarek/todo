"""Harness regressions use disposable mini-suites, never relaunch real suites."""
from contextlib import redirect_stdout
from io import StringIO
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('verify_clean', ROOT / 'scripts/verify_clean.py')
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        for folder in ('scripts', 'todo_lib', 'tests/delivery/final'):
            (self.root / folder).mkdir(parents=True)
        (self.root / 'todo').write_text('#!/usr/bin/env python3\nprint("mini help")\n')
        (self.root / 'todo').chmod(0o755)
        (self.root / 'todo_lib/__init__.py').write_text('# synthetic runtime\n')
        self.check = self.root / 'scripts/check'
        self.check.write_text('#!/usr/bin/env python3\nimport unittest\nsuite=unittest.TestSuite([unittest.FunctionTestCase(lambda: None)])\nresult=unittest.TextTestRunner().run(suite)\nraise SystemExit(not result.wasSuccessful())\n')
        self.check.chmod(0o755)
        for name in ('copy_probe.py', 'less_probe.py'):
            (self.root / 'tests/delivery/final' / name).write_text('pass\n')

    def test_single_mini_suite_unchanged_status_and_isolated_environment(self):
        run = subprocess.run
        calls = []
        def record(argv, **kw):
            calls.append(argv)
            kw.setdefault('stdout', subprocess.DEVNULL)
            kw.setdefault('stderr', subprocess.DEVNULL)
            return run(argv, **kw)
        with patch.dict(os.environ, {'TODOIST_TOKEN': 'must-not-inherit', 'PYTHONPATH': '/source',
                                     'LESS': '+G', 'EDITOR': 'bad'}), patch.object(verify.subprocess, 'run', record), redirect_stdout(StringIO()):
            before = verify.status(self.root)
            verify.run(self.root)
            self.assertEqual(before, verify.status(self.root))
        self.assertEqual(sum(str(self.check) == str(c[0]) for c in calls), 1)
        env = verify.environment('home', 'bin', 'outside')
        self.assertEqual(env['TODOIST_TOKEN'], 'synthetic-delivery-token')
        self.assertFalse({'PYTHONPATH', 'LESS', 'EDITOR'} & env.keys())
        verify.artifacts(self.root)

    def test_failure_stops_probes_and_propagates(self):
        self.check.write_text('#!/bin/sh\nexit 7\n')
        probe = self.root / 'tests/delivery/final/copy_probe.py'
        probe.write_text('raise AssertionError("must not run")\n')
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            verify.run(self.root)
        self.assertEqual(caught.exception.returncode, 7)
        self.check.write_text('#!/bin/sh\nexit 0\n')
        with self.assertRaises(subprocess.CalledProcessError):
            verify.run(self.root)
        probe.write_text('pass\n')
        (self.root / 'tests/delivery/final/less_probe.py').write_text('raise SystemExit(9)\n')
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            verify.run(self.root)
        self.assertEqual(caught.exception.returncode, 9)

    def test_artifacts_and_status_change_rejected(self):
        for relative in ('__pycache__/x.pyc', '.todo/config', '.env'):
            path = self.root / relative
            path.parent.mkdir(exist_ok=True)
            path.touch()
            with self.assertRaises(RuntimeError): verify.artifacts(self.root)
            if path.parent == self.root: path.unlink()
            else: shutil.rmtree(path.parent)
        self.check.write_text('#!/bin/sh\nprintf changed > changed\n')
        with self.assertRaisesRegex(RuntimeError, 'Git status changed'):
            verify.run(self.root)
