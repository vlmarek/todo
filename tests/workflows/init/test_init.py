"""Isolated terminal + actual Transport/current adapter/public StateStore probes.

Provider-shaped fixtures extend tests.adapter.current. Offline evidence:
docs/design/external/todoist/upstream/api-v1.openapi.json, Sync tag read resources,
full-sync freshness, project_add/label_add command UUID/temp_id receipts and task
comments; ItemSyncView checked/nullable added_at and NoteSyncView posted_at.
The small boundary below rejects unexpected resources, endpoints and mutations;
it is synthetic traffic, not an exhaustive provider emulator.
"""
from copy import deepcopy
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs
from uuid import UUID

from todo_lib import domain as d
from todo_lib.adapter.transport import Transport
from todo_lib.local import (StateStore, LocalError, load_config, exclusive_lock,
                            empty_history, Coverage)
from todo_lib.local.codec import loads
from todo_lib.workflows.init import Initializer, InitError
from tests.adapter.current.test_current import full, delta, project, item, note, due, RESOURCES
from tests.support.http import ExpectedRequest, Response


CREATED = '2026-10-20T12:00:00.123456789012345Z'
POSTED = '2026-10-21T12:00:00.123456789012349Z'
NOW = d.instant_from_wire('2026-10-22T12:00:00.123456789012350Z')
LATER = d.instant_from_wire('2026-10-23T12:00:00.123456789012351Z')
LABEL = dict(id='waiting-id', name='waiting', is_deleted=False)
CONFIG = b'[main]\nproject=root\ndefault_sections=cat\nhidden_from_now=\n[todoist]\ntoken=secret\n'


class Terminal(StringIO):
    def isatty(self):
        return True


class Boundary:
    """Exact read forms and one authorized project/label creation at a time."""
    def __init__(self, rounds=(), *, remote=None, expected=(), rejected=None):
        self.rounds = list(rounds)
        self.remote = full(labels=[LABEL]) if remote is None else deepcopy(remote)
        self.expected = list(expected)
        self.rejected = rejected
        self.requests, self.mutations = [], []
        self.fresh = False
        self.provision_fresh = False

    def __call__(self, request, *, timeout):
        self.requests.append(request)
        form = {k: v[0] for k, v in parse_qs(request.data.decode(), keep_blank_values=True).items()}
        if 'commands' in form:
            if set(form) != {'commands'}:
                raise AssertionError('unexpected command fields')
            commands = json.loads(form['commands'])
            if len(commands) != 1:
                raise AssertionError('one operation required')
            op = commands[0]
            if set(op) != {'type', 'uuid', 'temp_id', 'args'}:
                raise AssertionError('incorrect command structure')
            UUID(op['uuid']); UUID(op['temp_id'])
            if not self.expected or (op['type'], op['args']) != self.expected.pop(0):
                raise AssertionError('unexpected provisioning request')
            self.mutations.append(op)
            identity = 'created-' + str(len(self.mutations))
            if op['type'] == 'project_add':
                value = project(identity, op['args']['parent_id'], name=op['args']['name'])
                collection = 'projects'
            elif op['type'] == 'label_add':
                value = dict(id=identity, name=op['args']['name'], is_deleted=False)
                collection = 'labels'
            else:
                raise AssertionError('unauthorized mutation')
            if self.rejected == len(self.mutations):
                result = {'sync_status': {op['uuid']: {'error_code': 20, 'error': 'controlled rejection'}}}
            else:
                self.remote[collection].append(value)
                result = {'sync_status': {op['uuid']: 'ok'}, 'temp_id_mapping': {op['temp_id']: identity}}
        else:
            resources = form.get('resource_types')
            if resources == RESOURCES:
                if form.get('sync_token') != ('full-token' if self.fresh else '*'):
                    raise AssertionError('incorrect current token')
                if self.fresh:
                    result = getattr(self, 'freshness', delta())
                else:
                    value = self.rounds.pop(0) if self.rounds else deepcopy(self.remote)
                    result, self.freshness = value if isinstance(value, tuple) else (value, delta())
                self.fresh = not self.fresh
            elif resources == '["projects","labels"]':
                if form.get('sync_token') != ('provision-token' if self.provision_fresh else '*'):
                    raise AssertionError('incorrect provision token')
                result = (dict(full_sync=False, sync_token='provision-delta') if self.provision_fresh else
                          dict(full_sync=True, sync_token='provision-token',
                               projects=self.remote['projects'], labels=self.remote['labels']))
                self.provision_fresh = not self.provision_fresh
            else:
                raise AssertionError('unexpected resources or activity prerequisite')
            if set(form) != {'sync_token', 'resource_types'}:
                raise AssertionError('incorrect read fields')
        ExpectedRequest('POST', '/sync', 'secret', form=form).check(request, timeout)
        if isinstance(result, Response):
            return result
        return Response(json.dumps(result).encode())

    def assert_done(self):
        if self.rounds or self.expected:
            raise AssertionError('missing expected reads or creations')


class InitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / '.todo'
        self.store = StateStore(self.root)

    def put(self, name, data, mode=0o600):
        self.root.mkdir(mode=0o700, exist_ok=True)
        path = self.root / name
        path.write_bytes(data)
        path.chmod(mode)

    def bytes(self):
        return {p.name: p.read_bytes() for p in self.root.iterdir() if p.name != 'lock'} if self.root.exists() else {}

    def run_init(self, boundary=None, *, answers='', hidden=None, env=None, now=NOW,
                 stdin=None, stdout=None, clock=None, **kwargs):
        boundary = Boundary() if boundary is None else boundary
        out = Terminal() if stdout is None else stdout
        err = Terminal()
        workflow = Initializer(store=self.store,
            transport_factory=lambda token: Transport(token, opener=boundary, sleep=lambda _: None),
            clock=clock or (lambda: now), environ={} if env is None else env,
            stdin=Terminal(answers) if stdin is None else stdin, stdout=out, stderr=err,
            hidden_reader=hidden, **kwargs)
        result = workflow.run()
        boundary.assert_done()
        return result, out.getvalue(), err.getvalue()

    def initialize_existing(self, payload=None):
        self.put('config', CONFIG)
        payload = full(labels=[LABEL], items=[item(added_at=CREATED)], notes=[note(posted_at=POSTED)]) if payload is None else payload
        result, _, _ = self.run_init(Boundary([payload, payload]))
        return result

    def assert_protected(self):
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        for p in self.root.iterdir():
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            self.assertFalse(p.name.startswith('.todo-candidate-'))

    def test_new_home_wizard_exact_fallbacks_env_not_persisted(self):
        empty = full(projects=[], items=[], labels=[])
        expected = [('project_add', {'name': 'Work', 'parent_id': None})]
        expected += [('project_add', {'name': name, 'parent_id': 'created-1'})
                     for name in ('engineer', 'manager', 'someday')]
        expected += [('label_add', {'name': 'waiting'})]
        b = Boundary(remote=empty, expected=expected)
        result, out, _ = self.run_init(b, answers='\n\n\nyes\n', env={'TODOIST_TOKEN': 'secret'},
            hidden=lambda _: self.fail('environment token must skip hidden prompt'))
        self.assertTrue(result.config_saved)
        self.assertEqual(load_config(self.root).project, 'Work')
        self.assertEqual(load_config(self.root).default_sections, ('engineer', 'manager', 'someday'))
        self.assertEqual(load_config(self.root).hidden_from_now, ('someday',))
        self.assertNotIn(b'secret', (self.root / 'config').read_bytes())
        self.assertIn('todo now', out)
        self.assertEqual(len(b.mutations), 5)
        self.assertEqual(d.instant_text(self.store.load_cursor()), d.instant_text(NOW))
        self.assert_protected()

    def test_existing_root_categories_hidden_warning_and_pasted_token(self):
        payload = full(projects=[project('root', None, name='Oracle'), project(name='Engineering')], labels=[LABEL])
        result, out, _ = self.run_init(Boundary([payload, payload]),
            answers='1\n\n\nyes\n', hidden=lambda _: 'secret\n')
        self.assertTrue(result.config_saved)
        self.assertEqual(load_config(self.root).default_sections, ('Engineering',))
        self.assertEqual(load_config(self.root).resolve_credentials({}).token(), 'secret')
        self.assertIn('has no effect', out)
        self.assertIn('existing', out)
        self.assertNotIn('secret', out)
        self.assertEqual(result.state.binding.root_id, 'root')

    def test_wizard_excludes_shared_inbox_and_workspace_choices(self):
        payload = full(projects=[project('shared', None, is_shared=True, shared=False),
            project('inbox', None, inbox_project=True),
            project('workspace', None, workspace_id='ws'),
            project('root', None), project()], labels=[LABEL])
        boundary = Boundary(remote=payload)
        result, out, _ = self.run_init(boundary, answers='1\n\n-\nyes\n',
                                      env={'TODOIST_TOKEN': 'secret'})
        self.assertEqual(result.state.binding.root_id, 'root')
        self.assertIn('1. root (personal top-level project, choice 1)', out)
        for name in ('shared', 'inbox', 'workspace'):
            self.assertNotIn('. ' + name + ' (personal', out)
        self.assertFalse(boundary.mutations)

    def test_empty_existing_root_offers_fallback_categories(self):
        payload = full(projects=[project('root', None)], items=[], labels=[LABEL])
        expected = [('project_add', {'name': name, 'parent_id': 'root'})
                    for name in ('engineer', 'manager', 'someday')]
        b = Boundary(remote=payload, expected=expected)
        result, _, _ = self.run_init(b, answers='1\n\n-\nyes\n', env={'TODOIST_TOKEN': 'secret'})
        self.assertEqual(len(result.state.snapshot.categories), 3)
        self.assertEqual(load_config(self.root).hidden_from_now, ())

    def test_hidden_warning_uses_effective_names_after_category_reuse(self):
        for sections, hidden, warns in (
            ('cat', 'cat', True),
            ('cat', 'CAT', False),
            ('cat, new', 'new', False),
        ):
            with self.subTest(sections=sections, hidden=hidden):
                self.root = Path(self.temp.name) / hidden
                self.store = StateStore(self.root)
                payload = full(projects=[project('root', None), project(name='CAT')],
                               labels=[LABEL])
                expected = ([('project_add', {'name': 'new', 'parent_id': 'root'})]
                            if hidden == 'new' else [])
                b = Boundary(remote=payload, expected=expected)
                result, out, _ = self.run_init(b,
                    answers=f'1\n{sections}\n{hidden}\nyes\n',
                    env={'TODOIST_TOKEN': 'secret'})
                self.assertTrue(result.config_saved)
                self.assertEqual('has no effect' in out, warns)
                if warns:
                    self.assertLess(out.index('has no effect'),
                                    out.index('Save configuration and continue'))
                self.assertIn('Category: CAT (existing)', out)
                self.assertNotIn('Category: cat (proposed new)', out)
                self.assertEqual(len(b.mutations), len(expected))
                config = load_config(self.root)
                self.assertEqual(config.default_sections,
                                 ('cat', 'new') if hidden == 'new' else ('cat',))
                self.assertEqual(config.hidden_from_now, (hidden,))
                state = self.store.load_consistent_state()
                self.assertEqual(state.snapshot.categories['cat'].name, 'CAT')
                self.assertEqual(state.binding.root_id, 'root')
                # Saved choices must still reuse the same category on normal init.
                repeat = Boundary(remote=b.remote)
                self.run_init(repeat, env={'TODOIST_TOKEN': 'secret'})
                self.assertFalse(repeat.mutations)
                self.assertEqual(self.store.load_consistent_state().snapshot.categories['cat'].name, 'CAT')

    def test_terminal_eligibility_before_directory_or_repair(self):
        for which in ('stdin', 'stdout'):
            with self.subTest(which=which):
                b = Boundary()
                with self.assertRaises(InitError) as caught:
                    self.run_init(b, **{which: StringIO()})
                self.assertIn('terminal', str(caught.exception))
                self.assertFalse(self.root.exists())
                self.assertFalse(b.requests)
        self.put('config', b'', mode=0o644)
        before = self.bytes()
        with self.assertRaises(InitError):
            self.run_init(stdin=StringIO())
        self.assertEqual(self.bytes(), before)
        self.assertEqual((self.root / 'config').stat().st_mode & 0o777, 0o644)

    def test_empty_0644_config_repair_accept_and_decline(self):
        self.put('config', b'', mode=0o644)
        b = Boundary()
        with self.assertRaises(InitError):
            self.run_init(b, answers='no\n', hidden=lambda _: self.fail('credential read before repair'))
        self.assertFalse(b.requests)
        self.assertEqual((self.root / 'config').stat().st_mode & 0o777, 0o644)
        result, out, _ = self.run_init(Boundary(), answers='yes\n1\n\n-\nyes\n', env={'TODOIST_TOKEN': 'secret'})
        self.assertTrue(result.config_saved)
        self.assertIn('0644', out)
        self.assert_protected()

    def test_directory_repair_and_unsafe_types_before_credentials(self):
        self.root.mkdir(mode=0o755)
        b = Boundary()
        with self.assertRaises(InitError):
            self.run_init(b, answers='no\n', hidden=lambda _: self.fail('credentials accessed'))
        self.assertFalse(b.requests)
        with self.assertRaises(InitError) as caught:
            self.run_init(b, answers='yes\n', hidden=lambda _: (_ for _ in ()).throw(OSError()))
        self.assertIn('repaired mode', str(caught.exception))
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        for kind in ('symlink', 'directory', 'foreign'):
            with self.subTest(kind=kind):
                path = self.root / 'config'
                if kind == 'symlink':
                    path.symlink_to(Path(self.temp.name) / 'outside')
                elif kind == 'directory':
                    path.mkdir()
                else:
                    self.put('config', b'')
                try:
                    original_lstat = Path.lstat
                    def foreign_lstat(target, *args, **kwargs):
                        result = original_lstat(target, *args, **kwargs)
                        if kind == 'foreign' and target == path:
                            fields = list(result)
                            fields[4] = os.getuid() + 1
                            return os.stat_result(fields)
                        return result
                    with patch.object(Path, 'lstat', foreign_lstat):
                        with self.assertRaises(InitError):
                            self.run_init(b, hidden=lambda _: self.fail('credentials accessed'))
                finally:
                    if path.is_dir(): path.rmdir()
                    else: path.unlink()
        self.assertFalse(b.requests)

    def test_populated_config_never_rewritten_or_repaired(self):
        for content, mode in ((CONFIG, 0o644), (b' \n', 0o600), (b'bad', 0o600)):
            with self.subTest(content=content, mode=mode):
                self.put('config', content, mode)
                b = Boundary()
                with self.assertRaises(InitError):
                    self.run_init(b, hidden=lambda _: self.fail('wizard entered'))
                self.assertFalse(b.requests)
                self.assertEqual((self.root / 'config').read_bytes(), content)
                self.assertEqual((self.root / 'config').stat().st_mode & 0o777, mode)

    def test_all_populated_names_validate_before_http(self):
        for bound in (False, True):
            if bound:
                self.initialize_existing()
            for control in (b'\x01', b'\xc2\x80'):
                for old, new in (
                    (b'project=root', b'project=bad' + control + b'name'),
                    (b'default_sections=cat', b'default_sections=cat,valid-new,bad' + control + b'name'),
                    (b'hidden_from_now=', b'hidden_from_now=cat,bad' + control + b'name'),
                ):
                    with self.subTest(bound=bound, control=control, setting=old):
                        self.put('config', CONFIG.replace(old, new))
                        before = self.bytes()
                        b = Boundary()
                        with self.assertRaises(InitError) as caught:
                            self.run_init(b, hidden=lambda _: self.fail('wizard entered'))
                        self.assertEqual(caught.exception.phase, 'local validation')
                        self.assertFalse(b.requests)
                        self.assertFalse(b.mutations)
                        self.assertEqual(self.bytes(), before)

    def test_eof_cancel_sigint_hidden_failure_no_config_or_provision(self):
        for stage in ('hidden-failure', 'hidden-eof', 'interrupt', 'decline', 'eof'):
            with self.subTest(stage=stage):
                b = Boundary()
                hidden = lambda _: 'secret\n'
                answers = ''
                if stage == 'hidden-failure': hidden = lambda _: (_ for _ in ()).throw(OSError())
                if stage == 'hidden-eof': hidden = lambda _: ''
                if stage == 'interrupt': hidden = lambda _: (_ for _ in ()).throw(KeyboardInterrupt())
                if stage == 'decline': answers = '1\n\n-\nno\n'
                with self.assertRaises(InitError) as caught:
                    self.run_init(b, answers=answers, hidden=hidden)
                self.assertEqual(caught.exception.status, 130 if stage == 'interrupt' else 1)
                if stage == 'hidden-failure':
                    self.assertEqual(caught.exception.phase, 'terminal setup')
                    self.assertIn('cannot hide input', str(caught.exception))
                    self.assertFalse(b.requests)
                self.assertNotIn('secret', str(caught.exception))
                self.assertFalse((self.root / 'config').exists())
                self.assertFalse(b.mutations)
                with exclusive_lock('check', self.root): pass

    def test_discovery_failure_never_becomes_empty_account(self):
        for payload in (full(projects=None), full(user={}), full(items=None)):
            b = Boundary([payload])
            with self.assertRaises(InitError):
                self.run_init(b, env={'TODOIST_TOKEN': 'secret'}, answers='\n\n\nyes\n')
            self.assertFalse(b.mutations)
            self.assertFalse((self.root / 'config').exists())

    def test_saved_configuration_is_reported_separately_from_preflight_failure(self):
        bad = item(); del bad['checked']
        b = Boundary(remote=full(items=[bad], labels=[]))
        with self.assertRaises(InitError) as caught:
            self.run_init(b, answers='1\n\n-\nyes\n', env={'TODOIST_TOKEN': 'secret'})
        self.assertTrue(caught.exception.config_saved)
        self.assertIn('Configuration was saved', str(caught.exception))
        self.assertEqual(caught.exception.phase, 'preflight')
        self.assertFalse(b.mutations)
        self.assertEqual(load_config(self.root).project, 'root')
        self.assertFalse((self.root / 'binding.json').exists())

    def test_current_checked_null_creation_optional_description_and_precision_reload(self):
        payload = full(labels=[LABEL], items=[item('known', added_at=CREATED), item('unknown', added_at=None)],
                       notes=[note('unknown-note', 'unknown', posted_at=None)])
        self.initialize_existing(payload)
        state = StateStore(self.root).load_consistent_state()
        for snapshot in (state.snapshot, state.history.snapshot):
            self.assertEqual(d.instant_text(snapshot.items['known'].added_at), CREATED)
            self.assertIsNone(snapshot.items['unknown'].added_at)
            self.assertIsNone(snapshot.comments['unknown-note'].added_at)
            self.assertFalse(snapshot.items['known'].completed)
            self.assertEqual(snapshot.items['known'].description, '')
        self.assertFalse(state.snapshot.account.capabilities.activity_history)
        self.assertEqual(state.snapshot.account.capabilities.history_limit, 0)
        self.assert_protected()

    def test_binding_instant_after_final_read_and_cache_only_context_joins_pending(self):
        self.put('config', CONFIG)
        b = Boundary()
        ticks = iter((NOW, LATER))
        self.run_init(b, clock=lambda: next(ticks))
        self.assertEqual(d.instant_text(self.store.load_cursor()), d.instant_text(LATER))
        self.assertEqual(d.instant_text(self.store.load_consistent_state().synced_at), d.instant_text(LATER))
        state = self.store.load_consistent_state()
        from dataclasses import replace
        pending = replace(empty_history(state.snapshot), coverage=(Coverage(NOW, LATER),))
        with exclusive_lock('fixture', self.root): self.store.save_history(pending)
        omitted = full(labels=[LABEL], items=[])
        self.run_init(Boundary([omitted, omitted]))
        state = self.store.load_consistent_state()
        self.assertFalse(state.snapshot.items)
        self.assertIn('task', state.history.snapshot.items)
        self.assertEqual(state.history.coverage, (Coverage(NOW, LATER),))
        self.assertFalse(state.history.complete)

    def test_invalid_tasks_tree_and_required_timestamps_block_provisioning(self):
        self.put('config', CONFIG.replace(b'default_sections=cat', b'default_sections=cat,missing'))
        values = []
        for field, value in (('checked', 'false'), ('added_at', 'bad'), ('added_at', 12),
                             ('completed_at', 'bad'), ('description', 12), ('parent_id', 'absent')):
            values.append(item(**{field: value}))
        for field in ('checked', 'added_at', 'completed_at'):
            value = item(); del value[field]; values.append(value)
        for bad in values:
            with self.subTest(bad=bad):
                before = self.bytes()
                b = Boundary([full(items=[bad], labels=[])])
                with self.assertRaises(InitError) as caught: self.run_init(b)
                self.assertEqual(caught.exception.phase, 'preflight')
                self.assertIn('correction', str(caught.exception))
                self.assertFalse(b.mutations)
                self.assertEqual(self.bytes(), before)

    def test_ineligible_ambiguous_roots_and_category_collision(self):
        self.put('config', CONFIG)
        structures = [
            [project('root', None), project('duplicate', None, name='root')],
            [project('root', None, is_shared=True)],
            [project('root', None, inbox_project=True)],
            [project('root', None, workspace_id=123)],
            [project('root', None), project(), project('collision', name='CAT')],
        ]
        for projects in structures:
            with self.subTest(projects=projects):
                b = Boundary([full(projects=projects, labels=[])])
                with self.assertRaises(InitError): self.run_init(b)
                self.assertFalse(b.mutations)

    def test_binding_deleted_config_does_not_authorize_account_or_root_switch(self):
        self.initialize_existing()
        cursor = (self.root / 'report-cursor').read_bytes()
        (self.root / 'config').unlink()
        b = Boundary([full(user={'id': 'other', 'tz_info': {'timezone': 'UTC'}})])
        with self.assertRaises(InitError):
            self.run_init(b, env={'TODOIST_TOKEN': 'secret'})
        self.assertFalse(b.mutations)
        self.assertFalse((self.root / 'config').exists())
        b = Boundary([full(projects=[project('root', None), project(), project('other', None)], labels=[LABEL])])
        with self.assertRaises(InitError):
            self.run_init(b, env={'TODOIST_TOKEN': 'secret'}, answers='2\n')
        self.assertFalse(b.mutations)
        self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)

    def test_authoritative_local_errors_before_http_and_credentials(self):
        self.initialize_existing()
        for name, data in (('report-cursor', b'bad'), ('binding.json', b'{}'), ('history.json', b'{}'), ('cache.json', b'{}')):
            saved = (self.root / name).read_bytes()
            self.put(name, data)
            before = self.bytes()
            b = Boundary()
            with self.assertRaises(InitError) as caught: self.run_init(b)
            self.assertEqual(caught.exception.phase, 'local validation')
            self.assertFalse(b.requests)
            self.assertEqual(self.bytes(), before)
            self.put(name, saved)
        (self.root / 'report-cursor').unlink()
        b = Boundary()
        with self.assertRaises(InitError): self.run_init(b)
        self.assertFalse(b.requests)

    def test_repeat_preserves_cursor_and_preflight_edits_through_omission(self):
        initial = full(labels=[LABEL], items=[item('A', added_at=CREATED), item('B', parent_id='A', added_at=CREATED)],
                       notes=[note('own', 'B', posted_at=POSTED)])
        self.initialize_existing(initial)
        cursor = (self.root / 'report-cursor').read_bytes()
        raw_due = due('2026-10-25T10:00:00', timezone=None)
        edited = full(labels=[LABEL], items=[item('A', added_at=None, content='Edited parent', description='Parent body'),
            item('B', parent_id='A', content='Edited step', description='Step body', priority=2,
                 added_at=CREATED, due=raw_due)], notes=[note('own', 'B', content='Edited own body', posted_at=None)])
        omitted = full(labels=[LABEL], items=[], notes=[])
        self.run_init(Boundary([edited, omitted]), now=LATER)
        self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)
        state = self.store.load_consistent_state()
        self.assertFalse(state.snapshot.items)
        pending = state.history.snapshot
        self.assertEqual(pending.items['A'].title, 'Edited parent')
        self.assertEqual(pending.items['A'].description, 'Parent body')
        self.assertIsNone(pending.items['A'].added_at)
        self.assertEqual(pending.items['B'].title, 'Edited step')
        self.assertEqual(pending.items['B'].description, 'Step body')
        self.assertEqual(pending.items['B'].priority, 3)
        self.assertEqual(pending.items['B'].parent_id, 'A')
        self.assertEqual(pending.items['B'].attention.raw_due, raw_due)
        self.assertEqual(d.instant_text(pending.items['B'].added_at), CREATED)
        self.assertEqual(pending.comments['own'].body, 'Edited own body')
        self.assertIsNone(pending.comments['own'].added_at)
        observations = dict(state.history.observations)
        self.run_init(Boundary([omitted, omitted]), now=LATER)
        reloaded = StateStore(self.root).load_consistent_state()
        self.assertEqual(reloaded.history.snapshot, pending)
        self.assertEqual(reloaded.history.observations, observations)
        self.assertFalse(reloaded.history.complete)
        self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)

    def test_pending_only_note_actual_edit_then_omission_tombstone_and_ownership_loss(self):
        self.initialize_existing()
        empty = full(labels=[LABEL], items=[], notes=[])
        self.run_init(Boundary([empty, empty]))
        edited = full(labels=[LABEL], items=[], notes=[note(content='Current retained-owner edit', posted_at=POSTED),
                                                    note('new', content='New own note', posted_at=None)])
        self.run_init(Boundary([edited, empty]))
        for _ in range(2):
            pending = self.store.load_history().snapshot
            self.assertEqual(pending.comments['note'].body, 'Current retained-owner edit')
            self.assertEqual(d.instant_text(pending.comments['note'].added_at), POSTED)
            self.assertEqual(pending.comments['new'].body, 'New own note')
            self.assertIsNone(pending.comments['new'].added_at)
            self.run_init(Boundary([empty, empty]))
        removed = full(labels=[LABEL], items=[], notes=[{'id': 'note', 'is_deleted': True},
            note('new', 'private-owner', content=42, file_attachment={'unsupported': True})])
        self.run_init(Boundary([removed, empty]))
        self.assertFalse(self.store.load_history().snapshot.comments)

    def test_invalid_retained_owner_note_blocks_all_provisions(self):
        self.initialize_existing()
        self.put('config', CONFIG.replace(b'default_sections=cat', b'default_sections=cat,missing'))
        values = [note(**{field: value}) for field, value in
                  (('content', 123), ('posted_at', 'bad'), ('posted_at', 12))]
        for field in ('posted_at', 'is_deleted'):
            value = note(); del value[field]; values.append(value)
        for bad in values:
            with self.subTest(bad=bad):
                before = self.bytes()
                b = Boundary([full(items=[], labels=[], notes=[bad])])
                with self.assertRaises(InitError) as caught: self.run_init(b)
                self.assertEqual(caught.exception.phase, 'preflight')
                self.assertFalse(b.mutations)
                self.assertEqual(self.bytes(), before)

    def test_required_ancestor_context_and_current_completion_reopen_supersession(self):
        initial = full(labels=[LABEL], items=[item('A'), item('B', parent_id='A')])
        self.initialize_existing(initial)
        completed = full(labels=[LABEL], items=[item('B', parent_id='A', checked=True, completed_at=POSTED)])
        omitted = full(labels=[LABEL], items=[])
        self.run_init(Boundary([completed, omitted]))
        pending = self.store.load_history().snapshot
        self.assertEqual(set(pending.items), {'A', 'B'})
        self.assertTrue(pending.items['B'].completed)
        self.assertEqual(d.instant_text(pending.items['B'].completed_at), POSTED)
        reopened = full(labels=[LABEL], items=[item('B', parent_id=None, content='Promoted', added_at=None)])
        self.run_init(Boundary([reopened, omitted]))
        pending = self.store.load_history().snapshot
        self.assertFalse(pending.items['B'].completed)
        self.assertIsNone(pending.items['B'].completed_at)
        self.assertIsNone(pending.items['B'].added_at)
        self.assertIsNone(pending.items['B'].parent_id)

    def test_current_renames_timezone_and_floating_fixed_due_authority(self):
        for raw_due, expected in ((due('2026-10-25T10:00:00', timezone=None), '2026-10-25T14:00:00Z'),
                                  (due('2026-10-25T10:00:00Z', timezone=None), '2026-10-25T10:00:00Z')):
            initial = full(labels=[LABEL], items=[item(due=raw_due)])
            if not (self.root / 'binding.json').exists(): self.initialize_existing(initial)
            else: self.run_init(Boundary([initial, initial]))
            cursor = (self.root / 'report-cursor').read_bytes()
            changed = full(labels=[LABEL], items=[], projects=[project('root', None, name='Renamed Root'),
                project(name='Renamed Cat')], user={'id': 'u', 'tz_info': {'timezone': 'America/New_York'}})
            self.put('config', CONFIG.replace(b'default_sections=cat', b'default_sections=Renamed Cat'))
            self.run_init(Boundary([changed, changed]))
            state = self.store.load_consistent_state()
            self.assertEqual(state.binding.root_id, 'root')
            self.assertEqual(state.binding.root_name, 'Renamed Root')
            self.assertEqual(state.history.snapshot.categories['cat'].name, 'Renamed Cat')
            self.assertEqual(state.history.snapshot.account.timezone, 'America/New_York')
            self.assertEqual(d.instant_text(state.history.snapshot.items['task'].attention.instant), expected)
            self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)
            self.put('config', CONFIG)

    def test_bound_root_rename_with_old_name_competitor_and_explicit_switch(self):
        self.initialize_existing()
        cursor = (self.root / 'report-cursor').read_bytes()
        config = (self.root / 'config').read_bytes()
        renamed = full(labels=[LABEL], items=[], projects=[
            project('root', None, name='Renamed Root'), project(),
            project('competitor', None, name='root')])
        # The second repeat consumes the newly published binding name while
        # configuration still names the original root. Neither is a selection
        # of the unrelated project now using that name.
        for _ in range(2):
            b = Boundary([renamed, renamed])
            self.run_init(b)
            state = self.store.load_consistent_state()
            self.assertEqual(state.binding.root_id, 'root')
            self.assertEqual(state.binding.root_name, 'Renamed Root')
            self.assertEqual(state.binding.categories, {'cat': 'cat'})
            self.assertEqual(d.instant_text(state.history.snapshot.items['task'].added_at), CREATED)
            self.assertEqual(d.instant_text(state.history.snapshot.comments['note'].added_at), POSTED)
            self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)
            self.assertEqual((self.root / 'config').read_bytes(), config)
            self.assertFalse(b.mutations)
        (self.root / 'config').unlink()
        before = self.bytes()
        for answers in ('2\n', 'root\nq\n', 'Another Root\nq\n'):
            with self.subTest(answers=answers):
                b = Boundary([renamed])
                out = Terminal()
                with self.assertRaises(InitError):
                    self.run_init(b, env={'TODOIST_TOKEN': 'secret'}, answers=answers, stdout=out)
                self.assertNotIn('Work categories are', out.getvalue())
                self.assertFalse(b.mutations)
                self.assertEqual(self.bytes(), before)
        b = Boundary([renamed, renamed])
        self.run_init(b, env={'TODOIST_TOKEN': 'secret'}, answers='1\n\n-\nyes\n')
        self.assertEqual(self.store.load_consistent_state().binding.root_id, 'root')
        self.assertEqual((self.root / 'report-cursor').read_bytes(), cursor)
        self.assertFalse(b.mutations)

    def test_first_init_retained_floating_due_uses_post_read_account_timezone(self):
        self.put('config', CONFIG)
        raw_due = due('2026-10-25T10:00:00', timezone=None)
        before = full(labels=[LABEL], items=[item(added_at=CREATED, due=raw_due)])
        after = full(labels=[LABEL], items=[], user={'id': 'u', 'tz_info': {'timezone': 'America/New_York'}})
        self.run_init(Boundary([before, after]))
        state = self.store.load_consistent_state()
        self.assertFalse(state.snapshot.items)
        self.assertEqual(state.binding.last_synced_account_timezone, 'America/New_York')
        attention = state.history.snapshot.items['task'].attention
        self.assertEqual(attention.raw_due, raw_due)
        self.assertEqual(d.instant_text(attention.instant), '2026-10-25T14:00:00Z')

    def test_explicit_delete_scope_departure_and_unrelated_unsupported_data(self):
        self.initialize_existing()
        unrelated = note('private', 'private-task', content=123, file_attachment={'file': 'private sentinel'})
        for evidence in ({'id': 'task', 'is_deleted': True}, item(project_id='outside')):
            current = full(labels=[LABEL], items=[evidence], notes=[unrelated])
            self.run_init(Boundary([current, current]))
            state = self.store.load_consistent_state()
            self.assertFalse(state.history.snapshot.items)
            self.assertFalse(state.history.snapshot.comments)
            for data in self.bytes().values(): self.assertNotIn(b'private sentinel', data)
            self.run_init(Boundary([full(labels=[LABEL]), full(labels=[LABEL])]))

    def test_partial_remote_creation_is_reported_and_explicit_rerun_reuses(self):
        self.put('config', CONFIG.replace(b'default_sections=cat', b'default_sections=cat,missing'))
        remote = full(labels=[], items=[item(added_at=CREATED)])
        expected = [('project_add', {'name': 'missing', 'parent_id': 'root'}), ('label_add', {'name': 'waiting'})]
        b = Boundary(remote=remote, expected=expected, rejected=2)
        with self.assertRaises(InitError) as caught: self.run_init(b)
        b.assert_done()
        self.assertEqual([p.outcome for p in caught.exception.provisions], ['accepted', 'rejected'])
        self.assertFalse((self.root / 'binding.json').exists())
        b = Boundary(remote=b.remote, expected=[('label_add', {'name': 'waiting'})])
        self.run_init(b)
        self.assertEqual(len(b.mutations), 1)
        self.assertIn('created-1', self.store.load_binding().categories)

    def test_interrupt_after_command_receipt_preserves_acceptance_no_replay(self):
        self.put('config', CONFIG.replace(b'default_sections=cat', b'default_sections=cat,missing'))
        class InterruptBoundary(Boundary):
            def __call__(inner, request, *, timeout):
                if inner.mutations:
                    raise KeyboardInterrupt()
                return super().__call__(request, timeout=timeout)
        b = InterruptBoundary(remote=full(labels=[]),
            expected=[('project_add', {'name': 'missing', 'parent_id': 'root'})])
        with self.assertRaises(InitError) as caught: self.run_init(b)
        self.assertEqual(caught.exception.status, 130)
        self.assertEqual([p.outcome for p in caught.exception.provisions], ['accepted', 'unattempted'])
        self.assertEqual(caught.exception.provisions[0].target_id, 'created-1')
        self.assertEqual(len(b.mutations), 1)
        self.assertFalse((self.root / 'binding.json').exists())
        with exclusive_lock('check', self.root): pass

    def test_unknown_creation_stops_later_work_and_rerun_discovers_without_replay(self):
        self.put('config', CONFIG.replace(b'default_sections=cat', b'default_sections=cat,missing'))
        class UnknownBoundary(Boundary):
            def __call__(inner, request, *, timeout):
                result = super().__call__(request, timeout=timeout)
                if 'commands' in parse_qs(request.data.decode()):
                    return Response(b'{}')  # no UUID receipt; matching text never proves acceptance
                return result
        b = UnknownBoundary(remote=full(labels=[]),
            expected=[('project_add', {'name': 'missing', 'parent_id': 'root'})])
        with self.assertRaises(InitError) as caught: self.run_init(b)
        self.assertEqual([p.outcome for p in caught.exception.provisions], ['unknown', 'unattempted'])
        self.assertFalse((self.root / 'binding.json').exists())
        b = Boundary(remote=b.remote, expected=[('label_add', {'name': 'waiting'})])
        self.run_init(b)
        self.assertEqual(len(b.mutations), 1)

    def test_saved_wizard_config_survives_provision_failure_then_normal_rerun(self):
        remote = full(labels=[])
        b = Boundary(remote=remote, expected=[('label_add', {'name': 'waiting'})], rejected=1)
        with self.assertRaises(InitError) as caught:
            self.run_init(b, answers='1\n\n-\nyes\n', env={'TODOIST_TOKEN': 'secret'})
        self.assertTrue(caught.exception.config_saved)
        self.assertEqual(caught.exception.provisions[0].outcome, 'rejected')
        saved = (self.root / 'config').read_bytes()
        b = Boundary(remote=b.remote, expected=[('label_add', {'name': 'waiting'})])
        result, _, _ = self.run_init(b, env={'TODOIST_TOKEN': 'secret'}, stdin=StringIO(), stdout=StringIO())
        self.assertFalse(result.config_saved)
        self.assertEqual((self.root / 'config').read_bytes(), saved)

    def test_config_populated_during_confirmation_is_not_overwritten(self):
        def reader(stream):
            value = stream.readline()
            if value == 'yes\n': self.put('config', CONFIG)
            return value
        b = Boundary()
        with self.assertRaises(InitError) as caught:
            self.run_init(b, answers='1\n\n-\nyes\n', reader=reader, env={'TODOIST_TOKEN': 'secret'})
        self.assertIn('became populated', str(caught.exception))
        self.assertFalse(caught.exception.config_saved)
        self.assertEqual((self.root / 'config').read_bytes(), CONFIG)
        self.assertFalse(b.mutations)

    def test_interrupt_after_config_replacement_reports_saved_configuration(self):
        real_replace = os.replace
        def interrupt(source, destination):
            real_replace(source, destination)
            if Path(destination).name == 'config': raise KeyboardInterrupt()
        b = Boundary()
        with patch('todo_lib.local.safety.os.replace', side_effect=interrupt):
            with self.assertRaises(InitError) as caught:
                self.run_init(b, answers='1\n\n-\nyes\n', env={'TODOIST_TOKEN': 'secret'})
        self.assertEqual(caught.exception.status, 130)
        self.assertEqual(caught.exception.phase, 'configuration publication')
        self.assertTrue(caught.exception.config_saved)
        self.assertIn('Configuration was saved', str(caught.exception))
        self.assertEqual(load_config(self.root).project, 'root')
        self.assertFalse(b.mutations)
        self.assert_protected()

    def test_task_scope_departure_removes_pending_subtree_and_current_note_owner_wins(self):
        self.initialize_existing()
        changed = full(projects=[project('root', None), project(), project('cat2', name='Other')], labels=[LABEL],
            items=[item('new-owner', project_id='cat2')], notes=[note(owner='new-owner', content='Moved note', posted_at=None)])
        self.run_init(Boundary([changed, changed]))
        self.assertEqual(self.store.load_history().snapshot.comments['note'].item_id, 'new-owner')
        self.assertIsNone(self.store.load_history().snapshot.comments['note'].added_at)
        self.put('config', CONFIG.replace(b'default_sections=cat', b'default_sections=Other'))
        departed = full(projects=[project('root', None), project(), project('cat2', name='Other')],
                        labels=[LABEL], items=[item(project_id='outside')], notes=[])
        self.run_init(Boundary([departed, departed]))
        state = self.store.load_consistent_state()
        self.assertIn('cat', state.history.snapshot.categories)
        self.assertNotIn('task', state.history.snapshot.items)
        self.assertEqual(state.history.snapshot.comments['note'].body, 'Moved note')

    def test_current_task_category_move_wins_through_later_omission(self):
        self.initialize_existing()
        self.put('config', CONFIG.replace(b'default_sections=cat', b'default_sections=Other'))
        projects = [project('root', None), project(), project('cat2', name='Other')]
        moved = full(projects=projects, labels=[LABEL],
                     items=[item(project_id='cat2', content='Moved task', added_at=None)])
        omitted = full(projects=projects, labels=[LABEL], items=[])
        self.run_init(Boundary([moved, omitted]))
        self.run_init(Boundary([omitted, omitted]))
        state = self.store.load_consistent_state()
        task = state.history.snapshot.items['task']
        self.assertEqual(task.category_id, 'cat2')
        self.assertEqual(task.title, 'Moved task')
        self.assertIsNone(task.added_at)
        self.assertEqual(state.history.snapshot.comments['note'].item_id, 'task')
        self.assertIn('cat', state.history.snapshot.categories)

    def test_bound_category_movement_or_missing_with_known_work_blocks_provision(self):
        self.initialize_existing()
        omitted = full(labels=[LABEL], items=[], notes=[])
        # Exercise both cache-backed and pending-only known task/note context.
        for pending_only in (False, True):
            if pending_only:
                self.run_init(Boundary([omitted, omitted]))
            for freshness_move in (False, True):
                moved = project('cat', 'outside')
                projects = [project('root', None), project('outside', None), moved]
                payload = full(projects=projects, labels=[], items=[item(added_at=CREATED)],
                               notes=[note(posted_at=POSTED)])
                observed = (full(labels=[], items=[], notes=[]), delta(projects=[moved])) if freshness_move else payload
                before = self.bytes()
                boundary = Boundary([observed])
                with self.subTest(pending_only=pending_only, freshness_move=freshness_move):
                    with self.assertRaises(InitError) as caught:
                        self.run_init(boundary)
                    self.assertEqual(caught.exception.phase, 'preflight')
                    self.assertFalse(boundary.mutations)
                    boundary.assert_done()
                    self.assertEqual(self.bytes(), before)
                    pending = StateStore(self.root).load_history().snapshot
                    self.assertEqual(d.instant_text(pending.items['task'].added_at), CREATED)
                    self.assertEqual(d.instant_text(pending.comments['note'].added_at), POSTED)
            missing = full(projects=[project('root', None)], items=[], notes=[], labels=[])
            boundary = Boundary([missing])
            before = self.bytes()
            with self.assertRaises(InitError) as caught:
                self.run_init(boundary)
            self.assertEqual(caught.exception.phase, 'preflight')
            self.assertIn('discard managed work', str(caught.exception))
            self.assertFalse(boundary.mutations)
            self.assertEqual(self.bytes(), before)
        # A harmless unrelated project/category discovery still succeeds, and
        # the rejected reads have not discarded the precise pending work.
        valid = full(projects=[project('root', None), project(), project('outside', None),
                               project('private', 'outside')], labels=[LABEL], items=[], notes=[])
        self.run_init(Boundary([valid, valid]))
        state = StateStore(self.root).load_consistent_state()
        self.assertEqual(state.binding.categories, {'cat': 'cat'})
        self.assertEqual(d.instant_text(state.history.snapshot.items['task'].added_at), CREATED)
        self.assertEqual(d.instant_text(state.history.snapshot.comments['note'].added_at), POSTED)

    def test_deleted_config_wizard_cannot_replace_moved_bound_category(self):
        self.initialize_existing()
        (self.root / 'config').unlink()
        before = self.bytes()
        moved = full(projects=[project('root', None), project('outside', None), project('cat', 'outside')],
                     labels=[], items=[item(added_at=CREATED)], notes=[note(posted_at=POSTED)])
        boundary = Boundary([moved])
        with self.assertRaises(InitError) as caught:
            self.run_init(boundary, answers='1\n', env={'TODOIST_TOKEN': 'secret'})
        self.assertEqual(caught.exception.phase, 'terminal setup')
        self.assertFalse(caught.exception.config_saved)
        self.assertFalse(boundary.mutations)
        boundary.assert_done()
        self.assertEqual(self.bytes(), before)

    def test_bound_category_movement_after_preflight_preserves_local_bytes(self):
        self.initialize_existing()
        valid = full(labels=[LABEL], items=[], notes=[])
        moved = full(projects=[project('root', None), project('outside', None), project('cat', 'outside')],
                     labels=[LABEL], items=[], notes=[])
        before = self.bytes()
        boundary = Boundary([valid, moved])
        with self.assertRaises(InitError) as caught:
            self.run_init(boundary)
        self.assertEqual(caught.exception.phase, 'post-provision validation')
        self.assertFalse(boundary.mutations)
        boundary.assert_done()
        self.assertEqual(self.bytes(), before)

    def test_first_publication_failure_complete_bytes_binding_last_manual_recovery(self):
        self.put('config', CONFIG)
        before = self.bytes()
        real = os.replace
        def fail_binding(source, dest):
            if Path(dest).name == 'binding.json': raise OSError('controlled binding failure')
            return real(source, dest)
        with patch('todo_lib.local.safety.os.replace', side_effect=fail_binding):
            payload = full(labels=[LABEL], items=[item(added_at=CREATED)])
            with self.assertRaises(InitError) as caught: self.run_init(Boundary([payload, payload]))
        error = caught.exception
        self.assertEqual(error.phase, 'local publication')
        self.assertTrue(error.publication_started)
        self.assertIn('delete the entire ~/.todo', str(error))
        self.assertIn('pending history and report cursor', str(error))
        self.assertIn('Remote Todoist data is unchanged', str(error))
        self.assertFalse((self.root / 'binding.json').exists())
        self.assertEqual((self.root / 'config').read_bytes(), before['config'])
        for name in ('cache.json', 'history.json'):
            self.assertEqual(loads((self.root / name).read_bytes())['schema'], 1)
        self.assertEqual(d.instant_text(self.store.load_cursor()), d.instant_text(NOW))
        self.assert_protected()
        with self.assertRaises(LocalError): StateStore(self.root).load_consistent_state()
        available = self.bytes()
        b = Boundary()
        with self.assertRaises(InitError): self.run_init(b)
        self.assertFalse(b.requests)
        self.assertEqual(self.bytes(), available)

    def test_candidate_failure_preserves_bytes_and_repeat_late_failure_rejects_mixed(self):
        self.initialize_existing()
        before = self.bytes()
        with patch('todo_lib.workflows.init.prepare_candidates', side_effect=LocalError('controlled preparation failure')):
            with self.assertRaises(InitError) as caught: self.run_init()
        self.assertFalse(caught.exception.publication_started)
        self.assertEqual(self.bytes(), before)
        with patch('todo_lib.local.safety.os.replace', side_effect=OSError('controlled first replacement failure')):
            with self.assertRaises(InitError) as caught: self.run_init()
        self.assertFalse(caught.exception.publication_started)
        self.assertEqual(self.bytes(), before)
        real = os.replace
        def fail_binding(source, dest):
            if Path(dest).name == 'binding.json': raise OSError('controlled binding failure')
            return real(source, dest)
        with patch('todo_lib.local.safety.os.replace', side_effect=fail_binding):
            payload = full(labels=[LABEL], items=[item(added_at=CREATED)])
            with self.assertRaises(InitError) as caught: self.run_init(Boundary([payload, payload]))
        self.assertTrue(caught.exception.publication_started)
        self.assertEqual((self.root / 'report-cursor').read_bytes(), before['report-cursor'])
        self.assertEqual((self.root / 'binding.json').read_bytes(), before['binding.json'])
        with self.assertRaises(LocalError): self.store.load_consistent_state()
        pending = loads((self.root / 'history.json').read_bytes())['snapshot']
        self.assertEqual(pending['items']['task']['added_at'], CREATED)


if __name__ == '__main__':
    unittest.main()
