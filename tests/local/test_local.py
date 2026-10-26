"""Controlled local boundaries with synthetic credentials and temporary homes."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from contextlib import redirect_stdout, redirect_stderr
import io
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch
from zoneinfo import ZoneInfo

from todo_lib import domain as d
from todo_lib.local import *
from todo_lib.local.codec import loads, dumps

NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)
INI = b'[main]\nproject = Work\ndefault_sections = engineer, manager\nhidden_from_now =\n'


def model():
    return d.Snapshot(d.Binding('account', 'root', frozenset({'cat'})),
        d.Account('account', 'UTC'), d.Project('root', 'Work'),
        {'cat': d.Project('cat', 'engineer', 'root')},
        {'parent': d.Item('parent', 'cat', 'Parent', added_at=None),
         'child': d.Item('child', 'cat', 'Child', 'parent', added_at=None)},
        {'comment': d.Comment('comment', 'child', 'Own comment', None)})


class LocalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / '.todo'
        create_directory(self.root)
        self.store = StateStore(self.root)
        self.snapshot = model()
        self.history = History(self.snapshot, {'child': NOW}, (), False)

    def put(self, name, data, mode=0o600):
        path = self.root / name
        path.write_bytes(data)
        path.chmod(mode)
        return path

    def candidates(self, **kwargs):
        args = dict(account_display='Person', sync_token='synthetic-sync-cursor',
                    synced_at=NOW, initial_cursor=NOW - timedelta(days=1))
        args.update(kwargs)
        return prepare_candidates(self.snapshot, self.history, **args)

    def initialize(self):
        with exclusive_lock('init', self.root):
            self.store.publish_snapshot(self.candidates())

    def test_exact_model_public_round_trip_and_pruning(self):
        early = d.instant_from_wire('2026-01-02T00:00:00.123456001Z')
        late = d.instant_from_wire('2026-01-02T00:00:00.123456999Z')
        exact = d.instant_from_wire('2026-01-02T00:00:00.123456789Z')
        long = d.instant_from_wire('2026-01-02T00:00:00.123456789012345678901234567890123456789Z')
        boundary = d.instant_from_wire('2026-01-02T00:00:00.123456500Z')
        s = replace(self.snapshot, items={
            'parent': replace(self.snapshot.items['parent'], added_at=long),
            'child': replace(self.snapshot.items['child'], added_at=exact, completed=True, completed_at=exact),
            'a': d.Item('a', 'cat', 'Early', added_at=early),
            'z': d.Item('z', 'cat', 'Late', added_at=late),
            'null': d.Item('null', 'cat', 'Unknown')},
            comments={'comment': d.Comment('comment', 'parent', 'Context', early),
                      'unknown': d.Comment('unknown', 'child', 'Unknown', None)},
            occurrences={'occ': d.Occurrence('occ', 'child', exact)})
        h = History(s, {'child': late}, (Coverage(early, late),))
        context = replace(s, items={k: v for k, v in self.snapshot.items.items()},
                          comments={'comment': d.Comment('comment', 'parent', 'Context', early)},
                          occurrences={})
        variants = (
            History(context, {'child': late}),
            History(replace(context, occurrences={'o': d.Occurrence('o', 'child', late)})),
            History(replace(context, comments={**context.comments,
                'new': d.Comment('new', 'child', 'Later', late)})),
            History(replace(context, items={**context.items,
                'child': replace(context.items['child'], completed=True, completed_at=late)})),
        )
        for pending in variants:
            with self.subTest(pending=pending):
                retained = prune_history(pending, boundary, output_finalized=True, saved_cursor=boundary)
                self.assertEqual(set(retained.snapshot.items), {'parent', 'child'})
                self.assertIn('comment', retained.snapshot.comments)
        old = History(context, {'child': early})
        self.assertEqual(prune_history(old, boundary, output_finalized=True,
                                      saved_cursor=boundary).snapshot.items, {})

        with exclusive_lock('init', self.root):
            self.store.publish_snapshot(prepare_candidates(s, h, account_display='Person',
                sync_token='synthetic-token', synced_at=long, initial_cursor=boundary))
        state = self.store.load_consistent_state()
        for saved in (state.snapshot, state.history.snapshot):
            self.assertEqual(d.instant_text(saved.items['child'].added_at), '2026-01-02T00:00:00.123456789Z')
            self.assertEqual(d.instant_text(saved.items['parent'].added_at), d.instant_text(long))
            self.assertEqual([i.id for i in d.ordered_siblings(saved, 'cat')], ['z', 'parent', 'a', 'null'])
            self.assertEqual(d.instant_key(saved.occurrences['occ'].completed_at), d.instant_key(exact))
            self.assertEqual(d.instant_text(saved.items['child'].completed_at), '2026-01-02T00:00:00.123456789Z')
            self.assertEqual(d.instant_text(saved.comments['comment'].added_at), d.instant_text(early))
            self.assertIsNone(saved.comments['unknown'].added_at)
        self.assertEqual(d.instant_text(state.synced_at), d.instant_text(long))
        self.assertEqual(d.instant_text(state.cursor), '2026-01-02T00:00:00.123456500Z')
        self.assertEqual(d.instant_key(state.history.observations['child']), d.instant_key(late))
        self.assertEqual(d.instant_text(state.history.coverage[0].end), d.instant_text(late))
        with self.assertRaises(LocalError):
            prune_history(state.history, boundary, saved_cursor=boundary)
        with self.assertRaises(LocalError):
            prune_history(state.history, boundary, output_finalized=True, saved_cursor=early)
        pruned = prune_history(state.history, boundary, output_finalized=True, saved_cursor=boundary)
        self.assertEqual(set(pruned.snapshot.items), {'parent', 'child'})
        self.assertIn('comment', pruned.snapshot.comments)
        self.assertIn('occ', pruned.snapshot.occurrences)
        self.assertEqual(d.instant_text(pruned.coverage[0].start), d.instant_text(boundary))
        with exclusive_lock('report-final', self.root):
            self.store.write_cursor(exact)
            self.store.save_history(pruned)
        self.assertEqual(d.instant_text(self.store.load_cursor()), d.instant_text(exact))
        self.assertEqual(self.store.load_history(), pruned)
        incoming = History(replace(s, items={**s.items, 'child': replace(s.items['child'], added_at=None)},
                                   comments={**s.comments, 'comment': replace(s.comments['comment'], added_at=None)}),
                           {'child': None})
        merged = merge_history(h, incoming)
        self.assertIsNone(merged.snapshot.items['child'].added_at)
        self.assertIsNone(merged.snapshot.comments['comment'].added_at)
        self.assertIsNone(merged.observations['child'])
        with exclusive_lock('sync', self.root):
            self.store.save_history(merged)
        self.assertIsNone(self.store.load_history().snapshot.items['child'].added_at)

    def test_malformed_required_exact_times_preserve_stored_bytes(self):
        self.initialize()
        for name in ('cache.json', 'history.json'):
            original = (self.root / name).read_bytes()
            for bad in (None, 42, '2026-01-02T00:00:00', 'bad'):
                raw = loads(original)
                if name == 'cache.json':
                    raw['synced_at'] = bad
                else:
                    raw['coverage'] = [{'start': bad, 'end': '2026-01-02T00:00:00Z'}]
                content = dumps(raw)
                self.put(name, content)
                with self.subTest(name=name, bad=bad), self.assertRaises(LocalError):
                    self.store.load_consistent_state()
                self.assertEqual((self.root / name).read_bytes(), content)
            self.put(name, original)

    def test_config_states_schema_and_unknowns(self):
        self.assertEqual(inspect_config(self.root), ConfigState.MISSING)
        self.put('config', b'')
        self.assertEqual(inspect_config(self.root), ConfigState.EMPTY)
        self.put('config', b' ')
        self.assertEqual(inspect_config(self.root), ConfigState.POPULATED)
        with self.assertRaisesRegex(ConfigError, 'missing required'):
            load_config(self.root)
        write_config(self.root, INI + b'[unknown]\nsetting=anything\n[main-extension]\nx=y\n')
        config = load_config(self.root)
        self.assertEqual(config.project, 'Work')
        self.assertEqual(config.default_sections, ('engineer', 'manager'))
        self.assertEqual(config.hidden_from_now, ())
        self.assertTrue(config.warn_limited_history)
        self.assertEqual(config.pager, ())
        self.assertEqual(config.colors, SOLARIZED)
        config = parse_config(INI.replace(b'hidden_from_now =', b'hidden_from_now = Someday'))
        self.assertEqual(config.hidden_from_now, ('Someday',))
        self.assertNotIn('Someday', config.default_sections)
        with self.assertRaisesRegex(ConfigError, 'missing required'):
            parse_config(b'[DEFAULT]\nproject=X\ndefault_sections=A\nhidden_from_now=\n')

    def test_config_negative_values_and_pager(self):
        for value in (b'', b'a,', b',a', b'a,,b', b'a,a', b'a,A'):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                parse_config(INI.replace(b'engineer, manager', value))
        for value in (b'a,', b'a,A', b','):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                parse_config(INI.replace(b'hidden_from_now =', b'hidden_from_now = ' + value))
        for value in (b'1', b'yes', b'', b'perhaps'):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                parse_config(INI + b'[report]\nwarn_limited_history=' + value)
        self.assertFalse(parse_config(INI + b'[report]\nwarn_limited_history=False').warn_limited_history)
        for color in (b'red', b'#fff', b'#12345678', b'123456', b'#zzzzzz'):
            with self.subTest(color=color), self.assertRaises(ConfigError):
                parse_config(INI + b'[colors]\nred=' + color)
        self.assertEqual(parse_config(INI + b'[colors]\nred=#AbCdEf').colors['red'], '#AbCdEf')
        config = parse_config(INI + b'pager = viewer "two words" "$HOME" | other\ndefault_wait_due=invalid\n')
        self.assertEqual(config.pager, ('viewer', 'two words', '$HOME', '|', 'other'))
        for command in ('"', '"" argument', 'viewer\0'):
            with self.assertRaises(ConfigError):
                command_argv(command)

    def test_credential_precedence_repr_and_redaction(self):
        configured = 'synthetic-config-secret'
        environment = 'synthetic-env-secret'
        config = parse_config(INI + b'[todoist]\ntoken=' + configured.encode())
        for env, expected in (({}, configured), ({'TODOIST_TOKEN': ''}, configured),
                              ({'TODOIST_TOKEN': environment}, environment)):
            cred = config.resolve_credentials(env)
            self.assertEqual(cred.token(), expected)
            self.assertNotIn(expected, repr(cred))
            self.assertNotIn(expected, cred.redact('failure: ' + expected))
            self.assertNotIn('Bearer', cred.redact('Authorization: Bearer anything'))
        self.assertNotIn(configured, repr(config))
        with self.assertRaises(ConfigError):
            resolve_credentials(environ={})
        self.assertEqual(resolve_credentials(environ={}, wizard_token='synthetic-hidden').source, 'wizard')
        self.put('config', INI + b'[todoist]\ntoken=' + configured.encode())
        self.put('history.json', b'{}', 0o644)
        with patch('todo_lib.local.config.read_bytes', side_effect=AssertionError('secret accessed')):
            with self.assertRaisesRegex(LocalError, '0600'):
                load_config(self.root)

    def test_no_credential_leaks_to_output_repository_or_state(self):
        secret = 'synthetic-' + uuid.uuid4().hex
        capture = io.StringIO()
        with redirect_stdout(capture), redirect_stderr(capture):
            config = parse_config(INI + b'[todoist]\ntoken=' + secret.encode())
            cred = config.resolve_credentials({})
            print(repr(config), repr(cred))
            print(cred.redact({'Authorization': 'Bearer ' + secret}))
            try:
                parse_config(b'[todoist]\ntoken=' + secret.encode() + b'\n[broken')
            except ConfigError as error:
                print(str(error))
            self.initialize()
        self.assertNotIn(secret, capture.getvalue())
        for path in self.root.iterdir():
            self.assertNotIn(secret.encode(), path.read_bytes())
        repository = Path(__file__).resolve().parents[2]
        for tree in ('tests', 'todo_lib'):
            for path in (repository / tree).rglob('*.py'):
                self.assertNotIn(secret.encode(), path.read_bytes(), str(path))

    def test_creation_under_restrictive_umask(self):
        other = Path(self.temp.name) / 'other'
        old_umask = os.umask(0o777)
        try:
            create_directory(other)
            with exclusive_lock('init', other):
                write_config(other, INI)
        finally:
            os.umask(old_umask)
        self.assertEqual(stat.S_IMODE(other.stat().st_mode), 0o700)
        for path in other.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_sensitive_modes_and_symlinks(self):
        self.put('config', INI)
        for name in ('config', 'binding.json', 'report-cursor', 'cache.json', 'history.json', 'lock'):
            path = self.root / name
            old = path.read_bytes() if path.exists() else None
            if path.exists():
                path.unlink()
            target = Path(self.temp.name) / 'outside'
            target.write_bytes(INI)
            target.chmod(0o600)
            path.symlink_to(target)
            with self.subTest(name=name), self.assertRaisesRegex(LocalError, 'non-symlink'):
                load_config(self.root)
            path.unlink()
            if old is not None:
                self.put(name, old)
        self.root.chmod(0o755)
        with self.assertRaisesRegex(LocalError, '0700'):
            load_config(self.root)
        self.root.chmod(0o700)
        other = Path(self.temp.name) / 'linked'
        other.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(LocalError):
            load_config(other)

    def test_wizard_repair_is_explicit_and_narrow(self):
        self.put('config', b'', 0o644)
        self.root.chmod(0o755)
        self.assertEqual(len(wizard_mode_repairs(self.root)), 2)
        with self.assertRaisesRegex(LocalError, 'confirmation'):
            repair_wizard_modes(self.root)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o755)
        repair_wizard_modes(self.root, confirmed=True)
        self.assertEqual(inspect_config(self.root), ConfigState.EMPTY)
        self.put('config', b' ', 0o644)
        with self.assertRaises(LocalError):
            repair_wizard_modes(self.root, confirmed=True)
        self.put('config', b'', 0o644)
        self.put('binding.json', b'{}', 0o644)
        with self.assertRaises(LocalError):
            repair_wizard_modes(self.root, confirmed=True)
        self.assertEqual(stat.S_IMODE((self.root / 'config').stat().st_mode), 0o644)

    def test_round_trip_timezone_nulls_modes_and_cache_clear(self):
        self.initialize()
        state = StateStore(self.root).load_consistent_state()
        self.assertEqual(state.snapshot, self.snapshot)
        self.assertEqual(state.history, self.history)
        self.assertIsNone(state.snapshot.items['child'].added_at)
        self.assertIsNone(state.history.snapshot.comments['comment'].added_at)
        self.assertEqual(state.binding.last_synced_account_timezone, 'UTC')
        for name in ('cache.json', 'history.json'):
            data = loads((self.root / name).read_bytes())
            self.assertNotIn('timezone', data['snapshot']['account'])
        old = {name: (self.root / name).read_bytes() for name in ('history.json', 'report-cursor', 'binding.json')}
        with exclusive_lock('clear-cache', self.root):
            self.store.clear_cache()
        for name, data in old.items():
            self.assertEqual((self.root / name).read_bytes(), data)
        with self.assertRaisesRegex(LocalError, '--refresh'):
            self.store.load_consistent_state()
        self.assertEqual(self.store.load_consistent_state(require_cache=False).history, self.history)
        with exclusive_lock('refresh', self.root):
            self.store.publish_snapshot(self.candidates(initial_cursor=None))
        for path in self.root.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
        self.assertEqual(self.store.load_consistent_state().history, self.history)

    def test_atomic_replace_and_write_failures_preserve_old_bytes(self):
        path = self.put('config', INI)
        with patch('todo_lib.local.safety.os.replace', side_effect=OSError('synthetic')):
            with self.assertRaises(LocalError):
                write_config(self.root, INI + b'[unknown]\nx=y\n')
        self.assertEqual(path.read_bytes(), INI)
        self.assertEqual(list(self.root.glob('.todo-candidate-*')), [])
        real_fdopen = os.fdopen
        class BrokenWriter:
            def __init__(self, fd):
                self.stream = real_fdopen(fd, 'wb')
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.stream.close()
            def fileno(self):
                return self.stream.fileno()
            def write(self, content):
                self.stream.write(content[:5])
                raise OSError('injected partial write')
        with patch('todo_lib.local.safety.os.fdopen', side_effect=lambda fd, mode: BrokenWriter(fd)):
            with self.assertRaises(LocalError):
                write_config(self.root, INI)
        self.assertEqual(path.read_bytes(), INI)
        self.assertEqual(list(self.root.glob('.todo-candidate-*')), [])
        with self.assertRaises(ConfigError):
            write_config(self.root, b'invalid')
        self.assertEqual(path.read_bytes(), INI)

    def test_binding_last_failed_publication_and_restart(self):
        self.initialize()
        old_binding = (self.root / 'binding.json').read_bytes()
        old_cursor = (self.root / 'report-cursor').read_bytes()
        real_replace = os.replace
        destinations = []
        def fail_binding(src, dst):
            destinations.append(Path(dst).name)
            if Path(dst).name == 'binding.json':
                raise OSError('injected binding failure')
            real_replace(src, dst)
        with exclusive_lock('refresh', self.root):
            with patch('todo_lib.local.safety.os.replace', side_effect=fail_binding):
                with self.assertRaises(LocalError):
                    self.store.publish_snapshot(self.candidates(initial_cursor=None))
        self.assertEqual(destinations, ['cache.json', 'history.json', 'binding.json'])
        self.assertEqual((self.root / 'binding.json').read_bytes(), old_binding)
        self.assertEqual((self.root / 'report-cursor').read_bytes(), old_cursor)
        with self.assertRaisesRegex(LocalError, 'history'):
            StateStore(self.root).load_consistent_state()
        self.assertEqual(list(self.root.glob('.todo-candidate-*')), [])

    def test_reused_publication_rejected_before_replacement(self):
        self.initialize()
        original = self.store.load_consistent_state()
        before = {p.name: p.read_bytes() for p in self.root.iterdir() if p.name != 'lock'}
        reused = self.candidates(initial_cursor=None, publication=original.binding.publication)
        changed = replace(self.snapshot, items={**self.snapshot.items,
            'child': replace(self.snapshot.items['child'], title='Changed')})
        variants = {
            'unchanged': reused,
            'cache': prepare_candidates(changed, self.history, account_display='Person',
                sync_token='synthetic-sync-cursor', synced_at=NOW,
                publication=original.binding.publication),
            'history': prepare_candidates(self.snapshot, replace(self.history, snapshot=changed),
                account_display='Person', sync_token='synthetic-sync-cursor', synced_at=NOW,
                publication=original.binding.publication),
            'sync-token': self.candidates(initial_cursor=None,
                publication=original.binding.publication, sync_token='next-sync-cursor'),
            'binding': self.candidates(initial_cursor=None,
                publication=original.binding.publication, account_display='Renamed'),
        }
        real_replace = os.replace
        def fail_history(src, dst):
            if Path(dst).name == 'history.json':
                raise OSError('injected history failure')
            real_replace(src, dst)
        for name, candidate in variants.items():
            with self.subTest(name=name), exclusive_lock('refresh', self.root):
                with patch('todo_lib.local.safety.os.replace', side_effect=fail_history) as replacement:
                    with self.assertRaisesRegex(LocalError, 'fresh publication'):
                        self.store.publish_snapshot(candidate)
                replacement.assert_not_called()
                for path, content in before.items():
                    self.assertEqual((self.root / path).read_bytes(), content)
                self.assertEqual(StateStore(self.root).load_consistent_state(), original)
        # Cache deletion does not remove the authoritative publication identity.
        with exclusive_lock('refresh', self.root):
            self.store.clear_cache()
            with self.assertRaisesRegex(LocalError, 'fresh publication'):
                self.store.publish_snapshot(reused)
            self.store.publish_snapshot(self.candidates(initial_cursor=None))
        restored = StateStore(self.root).load_consistent_state()
        self.assertNotEqual(restored.binding.publication, original.binding.publication)
        self.assertEqual(restored.snapshot, original.snapshot)
        self.assertEqual(restored.history, original.history)
        self.assertEqual(restored.cursor, original.cursor)

    def test_first_replace_failure_preserves_publication_and_initial_order(self):
        destinations = []
        real_replace = os.replace
        def record(src, dst):
            destinations.append(Path(dst).name)
            real_replace(src, dst)
        with patch('todo_lib.local.safety.os.replace', side_effect=record):
            self.initialize()
        self.assertEqual(destinations, ['cache.json', 'history.json', 'report-cursor', 'binding.json'])
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        with exclusive_lock('refresh', self.root):
            with patch('todo_lib.local.safety.os.replace', side_effect=OSError('failed first replace')):
                with self.assertRaises(LocalError):
                    self.store.publish_snapshot(self.candidates(initial_cursor=None))
        for name, content in before.items():
            self.assertEqual((self.root / name).read_bytes(), content)
        self.assertEqual(self.store.load_consistent_state().snapshot, self.snapshot)

    def test_process_publication_rejects_intermediate_mixed_set(self):
        self.initialize()
        candidate = self.candidates(initial_cursor=None)
        # A child pauses after replacing cache, while retaining the writer lock.
        code = '''import sys
from pathlib import Path
from todo_lib.local import exclusive_lock, StateStore, Candidates
from todo_lib.local.safety import atomic_write
root = Path(sys.argv[1])
data = sys.stdin.buffer
parts = [bytes.fromhex(data.readline().decode().strip()) for _ in range(3)]
c = Candidates(*parts)
with exclusive_lock('refresh', root):
 atomic_write(root / 'cache.json', c.cache, lambda b: None)
 print('cache replaced', flush=True)
 data.readline()
 StateStore(root).publish_snapshot(c)
'''
        child = subprocess.Popen([sys.executable, '-B', '-c', code, str(self.root)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: child.poll() is None and child.kill())
        child.stdin.write(b''.join(v.hex().encode() + b'\n' for v in (candidate.binding, candidate.cache, candidate.history)))
        child.stdin.flush()
        self.assertEqual(child.stdout.readline(), b'cache replaced\n')
        with self.assertRaisesRegex(LocalError, 'mixed account/root/publication'):
            self.store.load_consistent_state()
        out, err = child.communicate(b'continue\n', timeout=5)
        self.assertEqual(child.returncode, 0, err)
        self.assertEqual(self.store.load_consistent_state().snapshot, self.snapshot)

    def test_due_round_trip_preserves_lossless_representation(self):
        due = d.resolve_remote_due({'date': '2026-01-02T12:00:00.123456789Z', 'is_recurring': False}, 'UTC')
        self.snapshot = replace(self.snapshot, items={**self.snapshot.items,
            'child': replace(self.snapshot.items['child'], attention=due)})
        self.history = History(self.snapshot, {'child': NOW})
        self.initialize()
        loaded = self.store.load_consistent_state()
        self.assertEqual(loaded.snapshot.items['child'].attention, due)
        self.assertEqual(loaded.history.snapshot.items['child'].attention.raw_due, due.raw_due)

    def test_required_history_identity_and_schema_are_not_reset(self):
        self.initialize()
        path = self.root / 'history.json'
        original = path.read_bytes()
        for bad in (b'{', dumps({**loads(original), 'association': dict(account_id='foreign', root_id='root', publication='other')})):
            path.write_bytes(bad)
            with self.assertRaises(LocalError):
                self.store.load_consistent_state()
            self.store.clear_cache()
            self.assertEqual(path.read_bytes(), bad)
            with self.assertRaises(LocalError):
                self.store.publish_snapshot(self.candidates(initial_cursor=None))
        path.unlink()
        with self.assertRaises(LocalError):
            self.store.load_consistent_state(require_cache=False)
        self.put('history.json', original)
        binding = loads((self.root / 'binding.json').read_bytes())
        self.put('binding.json', dumps({**binding, 'schema': 99}))
        with self.assertRaisesRegex(LocalError, 'unsupported binding schema'):
            self.store.load_consistent_state(require_cache=False)

    def test_cursor_set_repairs_content_but_never_prunes_or_unsafe_paths(self):
        self.initialize()
        history = (self.root / 'history.json').read_bytes()
        self.put('report-cursor', b'corrupt but readable')
        with self.assertRaises(LocalError):
            self.store.load_cursor()
        with exclusive_lock('set-cursor', self.root):
            self.store.write_cursor(NOW)
        self.assertEqual((self.root / 'report-cursor').read_bytes(), b'2026-01-02T00:00:00Z\n')
        self.assertEqual((self.root / 'history.json').read_bytes(), history)
        (self.root / 'report-cursor').unlink()
        self.store.write_cursor(NOW)
        self.put('report-cursor', b'unsafe', 0o644)
        with self.assertRaises(LocalError):
            self.store.write_cursor(NOW)
        self.assertEqual((self.root / 'report-cursor').read_bytes(), b'unsafe')

    def test_candidates_reject_before_any_publication(self):
        good = self.candidates()
        data = loads(good.cache)
        data['snapshot']['account']['timezone'] = 'Europe/London'
        bad = replace(good, cache=dumps(data))
        with self.assertRaises(LocalError):
            self.store.publish_snapshot(bad)
        self.assertEqual(list(self.root.iterdir()), [])
        data = loads(good.cache)
        data['association']['account_id'] = 5
        with self.assertRaises(LocalError):
            validate_candidates(replace(good, cache=dumps(data)))

    def test_interrupted_init_preserves_authority_on_rerun(self):
        candidate = self.candidates()
        real_replace = os.replace
        def fail_binding(src, dst):
            if Path(dst).name == 'binding.json':
                raise OSError('interrupted initial publication')
            real_replace(src, dst)
        with patch('todo_lib.local.safety.os.replace', side_effect=fail_binding):
            with self.assertRaises(LocalError):
                self.store.publish_snapshot(candidate)
        with self.assertRaises(LocalError):
            self.store.load_consistent_state()
        before = (self.root / 'history.json').read_bytes()
        with self.assertRaisesRegex(LocalError, 'cursor must be preserved'):
            self.store.publish_snapshot(self.candidates(initial_cursor=NOW))
        self.assertEqual((self.root / 'history.json').read_bytes(), before)
        # An explicit rerun can finish using the retained initial boundary.
        self.store.publish_snapshot(self.candidates())
        self.assertEqual(self.store.load_consistent_state().history, self.history)

    def test_history_save_reload_and_finalization_eligibility(self):
        self.history = replace(self.history, coverage=(Coverage(NOW - timedelta(days=1), NOW + timedelta(days=1)),))
        self.initialize()
        self.assertEqual(self.store.load_history(), self.history)
        with self.assertRaises(LocalError):
            prune_history(self.history, NOW, output_finalized=True, saved_cursor=NOW - timedelta(seconds=1))
        newer = replace(self.history, observations={'child': NOW + timedelta(days=1)})
        with exclusive_lock('refresh', self.root):
            self.store.save_history(newer)
        self.assertEqual(StateStore(self.root).load_history(), newer)
        original = (self.root / 'history.json').read_bytes()
        with patch('todo_lib.local.safety.os.replace', side_effect=OSError('cleanup failure')):
            with self.assertRaises(LocalError):
                self.store.save_history(self.history)
        self.assertEqual((self.root / 'history.json').read_bytes(), original)
        self.assertEqual(self.store.load_cursor(), NOW - timedelta(days=1))

    def test_fold_coverage_merge_reload_and_prune(self):
        wall = datetime(2026, 10, 25, 2, 30, tzinfo=ZoneInfo('Europe/Prague'), fold=1)
        exact = d.instant_from_wire('2026-10-25T01:30:00.000000000Z')
        end = d.instant_from_wire('2026-10-25T01:30:00.000000999Z')
        cursor = d.instant_from_wire('2026-10-25T01:30:00.000000500Z')
        old = History(self.snapshot, {'child': end}, (Coverage(wall, end),))
        incoming = History(self.snapshot, {'child': end}, (Coverage(exact, end),))
        distinct = replace(incoming, coverage=(Coverage(wall.replace(fold=0), end),))
        self.assertEqual(len(merge_history(old, distinct).coverage), 2)
        for index, (first, second) in enumerate(((old, incoming), (incoming, old))):
            with self.subTest(first=first.coverage):
                merged = merge_history(first, second)
                self.assertEqual(len(merged.coverage), 1)
                with exclusive_lock('init', self.root):
                    self.store.publish_snapshot(prepare_candidates(self.snapshot, merged,
                        account_display='Person', sync_token='synthetic-token',
                        synced_at=end, initial_cursor=cursor if index == 0 else None))
                restored = self.store.load_consistent_state().history
                again = merge_history(restored, old)
                self.assertEqual(len(again.coverage), 1)
                pruned = prune_history(again, cursor, output_finalized=True, saved_cursor=cursor)
                self.assertEqual(len(pruned.coverage), 1)
                self.assertEqual(d.instant_text(pruned.coverage[0].start),
                                 '2026-10-25T01:30:00.000000500Z')
                self.assertEqual(d.instant_text(pruned.coverage[0].end),
                                 '2026-10-25T01:30:00.000000999Z')
                self.assertEqual(set(pruned.snapshot.items), {'parent', 'child'})
                with exclusive_lock('refresh', self.root):
                    self.store.save_history(pruned)
                self.assertEqual(self.store.load_history(), pruned)

    def test_history_merge_prune_newer_shared_context_and_departures(self):
        boundary = NOW
        s = replace(self.snapshot, comments={}, occurrences={
            'old': d.Occurrence('old', 'parent', NOW - timedelta(hours=1)),
            'new': d.Occurrence('new', 'child', NOW + timedelta(hours=1))})
        h = History(s, {'parent': NOW - timedelta(hours=1), 'child': NOW + timedelta(hours=1)})
        incoming = History(replace(s, occurrences={}), {'child': NOW - timedelta(hours=2)})
        merged = merge_history(h, incoming)
        self.assertEqual(merged.observations['child'], NOW + timedelta(hours=1))
        self.assertEqual(set(merged.snapshot.occurrences), {'old', 'new'})
        with self.assertRaises(LocalError):
            prune_history(merged, boundary)
        pruned = prune_history(merged, boundary, output_finalized=True, saved_cursor=boundary)
        self.assertEqual(set(pruned.snapshot.items), {'parent', 'child'})
        self.assertEqual(set(pruned.snapshot.occurrences), {'new'})
        self.assertEqual(prune_history(pruned, boundary, output_finalized=True, saved_cursor=boundary), pruned)
        removed = merge_history(merged, incoming, removed_item_ids={'parent'})
        self.assertEqual(removed.snapshot.items, {})
        self.assertEqual(removed.snapshot.occurrences, {})
        self.assertFalse(empty_history(self.snapshot).complete)

    def test_process_lock_fail_fast_release_and_ordered_cursor_read(self):
        self.initialize()
        code = '''import sys
from todo_lib.local import exclusive_lock, StateStore
from todo_lib.domain import instant_text
with exclusive_lock('report-final', sys.argv[1]):
 print(instant_text(StateStore(sys.argv[1]).load_cursor()), flush=True)
 sys.stdin.readline()
'''
        child = subprocess.Popen([sys.executable, '-B', '-c', code, str(self.root)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: child.poll() is None and child.kill())
        self.assertIn('2026-01-01', child.stdout.readline())
        # Offline reads do not queue behind the writer.
        self.assertEqual(self.store.load_consistent_state().snapshot, self.snapshot)
        started = time.monotonic()
        with self.assertRaisesRegex(LockBusy, 'report-final'):
            with exclusive_lock('init', self.root):
                self.fail('acquired competing lock')
        self.assertLess(time.monotonic() - started, 1)
        out, err = child.communicate('\n', timeout=5)
        self.assertEqual(child.returncode, 0, err)
        with self.assertRaises(KeyboardInterrupt):
            with exclusive_lock('set-cursor', self.root):
                self.store.write_cursor(NOW)
                raise KeyboardInterrupt()
        child2 = subprocess.run([sys.executable, '-B', '-c', code, str(self.root)],
            input='\n', capture_output=True, text=True, timeout=5)
        self.assertEqual(child2.returncode, 0, child2.stderr)
        self.assertIn('2026-01-02', child2.stdout)


if __name__ == '__main__':
    unittest.main()
