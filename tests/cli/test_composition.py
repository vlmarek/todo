"""Representative public setup, moves, editor and archived lifecycle workflows."""
from copy import deepcopy
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from todo_lib import cli, domain as d
from todo_lib.adapter.transport import Transport
from todo_lib.local import StateStore
from tests.cli.test_cli import invoke
from tests.workflows.init import test_init as init_fixture
from tests.workflows.moves import test_moves as move_fixture
from tests.workflows.comments import test_workflow as comment_fixture
from tests.workflows.lifecycle import test_lifecycle as lifecycle_fixture
from tests.workflows.sync import test_sync as sync_fixture
from tests.adapter.current.test_current import full, delta, item, note, RESOURCES
from tests.support.http import ControlledHTTP, ExpectedRequest, Response


class PublicInit(unittest.TestCase):
    def test_init_config_and_hidden_wizard_token_redact_before_discovery_output(self):
        for wizard in (False, True):
            with self.subTest(wizard=wizard), tempfile.TemporaryDirectory() as temp:
                self.root = Path(temp) / '.todo'
                self.root.mkdir(mode=0o700)
                self.store = StateStore(self.root)
                if not wizard:
                    path = self.root / 'config'
                    path.write_bytes(init_fixture.CONFIG.replace(b'project=root', b'project=root secret'))
                    path.chmod(0o600)
                payload = full(projects=[init_fixture.project('root', None, name='root secret'),
                                        init_fixture.project(name='cat')], labels=[init_fixture.LABEL])
                wire = init_fixture.Boundary(remote=payload)
                hidden = unittest.mock.Mock(return_value='secret')
                initializer = cli.Initializer
                def actual_init(**kwargs):
                    return initializer(**kwargs, hidden_reader=hidden)
                with patch.object(cli, 'Initializer', side_effect=actual_init):
                    status, out, err, factory = invoke(self, ['init'], Transport('secret', opener=wire),
                        environ={'TODOIST_TOKEN': ''}, input=init_fixture.Terminal('1\n\n\nyes\n'),
                        output=init_fixture.Terminal())
                self.assertEqual(status, 0, err)
                factory.assert_called_once()
                self.assertEqual(factory.call_args.args, ('secret',))
                self.assertEqual(hidden.call_count, int(wizard))
                self.assertIn('root [REDACTED]', out)
                self.assertNotIn('secret', out + err)
                wire.assert_done()
                # Redaction must affect output only, never persisted identity.
                self.assertEqual(self.store.load_consistent_state().snapshot.root.name, 'root secret')
                status, _, err, factory = invoke(self, ['now'])
                self.assertEqual(status, 0, err)
                factory.assert_not_called()

    def test_wizard_discovery_failures_are_remote_and_publish_nothing(self):
        missing = full()
        missing['projects'][0].pop('is_shared')
        missing['projects'][0]['shared'] = False
        null = full()
        null['projects'][0].update(is_shared=None, shared=False)
        for payload, fact in ((missing, 'missing'), (null, 'null'),
                              (Response(b'private secret', status=401), '401'),
                              (OSError('private secret'), 'unavailable')):
            with self.subTest(fact=fact), tempfile.TemporaryDirectory() as temp:
                self.root = Path(temp) / '.todo'
                self.store = StateStore(self.root)
                request = lambda token: ExpectedRequest('POST', '/sync', 'secret',
                    form={'sync_token': token, 'resource_types': RESOURCES})
                steps = [(request('*'), payload if isinstance(payload, (Response, Exception))
                          else Response(json.dumps(payload).encode()))]
                if isinstance(payload, dict):
                    steps.append((request('full-token'), Response(json.dumps(delta()).encode())))
                wire = ControlledHTTP(steps)
                status, out, err, _ = invoke(self, ['init'],
                    Transport('secret', opener=wire), input=init_fixture.Terminal(),
                    output=init_fixture.Terminal())
                self.assertEqual(status, 1, err)
                self.assertIn('remote discovery failed', err)
                if isinstance(payload, dict):
                    for expected in (fact, 'is_shared', 'boolean'):
                        self.assertIn(expected, err)
                self.assertNotIn('terminal', err)
                self.assertNotIn('secret', out + err)
                self.assertNotIn('private', out + err)
                # Only the protected setup directory and lock may be created.
                self.assertTrue(self.root.is_dir())
                self.assertEqual({p.name for p in self.root.iterdir()}, {'lock'})
                wire.assert_done()  # no fallback reads or provisioning

    def test_wizard_terminal_failure_stays_distinct_from_discovery(self):
        with tempfile.TemporaryDirectory() as temp:
            self.root = Path(temp) / '.todo'
            self.store = StateStore(self.root)
            wire = ControlledHTTP([])
            status, _, err, _ = invoke(self, ['init'], Transport('secret', opener=wire))
            self.assertEqual(status, 1)
            self.assertIn('rerun in a terminal', err)
            self.assertNotIn('remote discovery', err)
            self.assertFalse(self.root.exists())
            wire.assert_done()

    def test_populated_setup_to_now_and_failed_first_publication_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp:
            self.root = Path(temp) / '.todo'
            self.root.mkdir(mode=0o700)
            self.store = StateStore(self.root)
            (self.root / 'config').write_bytes(init_fixture.CONFIG)
            (self.root / 'config').chmod(0o600)
            wire = init_fixture.Boundary()
            transport = Transport('secret', opener=wire)
            status, out, err, _ = invoke(self, ['init'], transport)
            self.assertEqual(status, 0, err)
            self.assertIn('Next: todo now', out)
            wire.assert_done()
            status, out, err, factory = invoke(self, [])
            self.assertEqual(status, 0, err)
            factory.assert_not_called()
            self.assertIn('task', out.lower())
        # First-init partial files are preserved and explicitly disclosed. No
        # claim that every such state can be recovered by init rerun is made.
        with tempfile.TemporaryDirectory() as temp:
            self.root = Path(temp) / '.todo'
            self.root.mkdir(mode=0o700)
            self.store = StateStore(self.root)
            (self.root / 'config').write_bytes(init_fixture.CONFIG)
            (self.root / 'config').chmod(0o600)
            wire = init_fixture.Boundary()
            replace = os.replace
            def failure(source, destination):
                if Path(destination).name == 'binding.json':
                    raise OSError('controlled first binding failure')
                return replace(source, destination)
            with patch('todo_lib.local.safety.os.replace', side_effect=failure):
                status, out, err, _ = invoke(self, ['init'], Transport('secret', opener=wire))
            self.assertEqual(status, 1)
            self.assertNotIn('Initialized', out)
            self.assertIn('local publication failed', err)
            self.assertIn('partially published', err)
            self.assertIn('pending history', err)
            self.assertIn('Remote Todoist data is unchanged', err)
            self.assertTrue((self.root / 'history.json').is_file())
            wire.assert_done()
            status, out, err, _ = invoke(self, ['init'])
            self.assertEqual(status, 1)
            self.assertIn('unbound partial initialization', err)
            self.assertIn('fresh start', err)


class PublicMoves(unittest.TestCase):
    setUp = move_fixture.MoveTests.setUp
    boundary = move_fixture.MoveTests.boundary
    sync = move_fixture.MoveTests.sync
    workflow = move_fixture.MoveTests.workflow
    after = move_fixture.MoveTests.after

    def test_step_alias_parent_selection_then_promotion_preserve_own_comments(self):
        # C is a nested parent; selection must resolve that parent before D.
        after = self.after('D', None, 'cat')
        workflow, _ = self.workflow(after, {'id': 'D', 'project_id': 'cat'})
        status, out, err, _ = invoke(self, ['step', '--move', '', 'C', 'D'], workflow.synchronizer.transport,
                                     now=move_fixture.NOW)
        self.assertEqual(status, 0, err)
        snapshot = StateStore(self.store.root).load_consistent_state().snapshot
        self.assertIsNone(snapshot.items['D'].parent_id)
        self.assertEqual(snapshot.items['E'].parent_id, 'D')
        self.assertEqual(snapshot.comments['nD'].item_id, 'D')
        self.assertEqual(d.instant_text(snapshot.comments['nD'].added_at), move_fixture.STAMP)
        self.assertIn('task', out)

    def test_positional_move_ambiguity_keeps_category_and_task_types(self):
        transport, _ = self.boundary([self.sync('delta-token', full(projects=self.projects,
            items=[*self.rows, item('ambiguous', content='other')], notes=self.notes)),
            self.sync('full-token', delta())])
        status, out, err, _ = invoke(self, ['move', 'A', 'other'], transport, now=move_fixture.NOW)
        self.assertEqual(status, 1)
        self.assertIn('category', out.lower())
        self.assertIn('task', out.lower())
        self.assertNotIn('Select 1', out)
        self.assertNotIn('Moved', out)



class PublicEditor(unittest.TestCase):
    setUp = comment_fixture.WorkflowTests.setUp
    refresh = comment_fixture.WorkflowTests.refresh
    editor = comment_fixture.WorkflowTests.editor
    operation = comment_fixture.WorkflowTests.operation
    cleaned = comment_fixture.WorkflowTests.cleaned

    def test_editor_add_actual_owner_then_search_and_comments(self):
        self.refresh()
        self.editor('path.write_text(text + "Public progress\\n")')
        self.refresh()
        notes = [*self.notes, note('public', 'C', content='Public progress', posted_at=comment_fixture.NEW)]
        self.operation('note_add', {'item_id': 'C', 'content': 'Public progress'}, notes, identity='public')
        with patch.dict(os.environ, self.environ):
            status, out, err, _ = invoke(self, ['comment', '--edit', 'Leaf'], self.wire, now=comment_fixture.NOW)
        self.assertEqual(status, 0, err)
        self.assertIn('1 added, 0 edited, 0 deleted', out)
        self.cleaned()
        for argv in (['search', 'Public progress'], ['comments', 'Leaf']):
            status, out, err, factory = invoke(self, argv, now=comment_fixture.NOW)
            self.assertEqual(status, 0, err)
            self.assertIn('Leaf' if argv[0] == 'search' else 'Public progress', out)
            factory.assert_not_called()
        self.assertEqual(self.store.load_consistent_state().snapshot.comments['public'].item_id, 'C')


class PublicLifecycle(unittest.TestCase):
    setUp = lifecycle_fixture.AdapterLifecycleTests.setUp
    seed = lifecycle_fixture.AdapterLifecycleTests.seed
    comments = lifecycle_fixture.AdapterLifecycleTests.comments

    def test_archived_done_comment_then_ordinary_reopen_through_public_main(self):
        f = self.fixture
        complete = lifecycle_fixture.CommandRequest(self, 'item_complete', {'id': 'B'})
        comment = lifecycle_fixture.CommandRequest(self, 'note_add', {'item_id': 'B', 'content': 'Done: public progress'}, target='public')
        rest = [dict(id='public', content='Done: public progress', posted_at=sync_fixture.COMMENT,
                     file_attachment=None, is_deleted=False)]
        steps = [f.sync('delta-token', delta()), complete.step(),
            f.sync('delta-token', full(items=[item('A', added_at=sync_fixture.CREATED)])),
            f.sync('full-token', delta()), f.completed([sync_fixture.completed_b()]),
            *f.external(), comment.step(), f.sync('delta-token', delta()), self.comments('B', rest),
            f.sync('delta-token', delta(notes=[note('public', 'B', content='Done: public progress', posted_at=sync_fixture.COMMENT)]))]
        transport, _ = f.boundary(steps)
        status, out, err, _ = invoke(self, ['done', 'B', '--comment', 'public progress'], transport, now=sync_fixture.NOW)
        self.assertEqual(status, 0, err)
        self.assertIn('Completed step: B', out)
        self.assertIn('Done: public progress', out)
        self.assertTrue(self.store.load_consistent_state().snapshot.items['B'].completed)
        reopened = lifecycle_fixture.CommandRequest(self, 'item_uncomplete', {'id': 'B'})
        restored = [item('B', parent_id='A', added_at=sync_fixture.CREATED)]
        transport, _ = f.boundary([f.sync('delta-token', delta()), f.completed([sync_fixture.completed_b()]),
            reopened.step(), f.sync('delta-token', delta(items=restored)),
            f.sync('delta-token', delta(items=restored))])
        status, out, err, _ = invoke(self, ['reopen', 'B'], transport, now=sync_fixture.NOW)
        self.assertEqual(status, 0, err)
        self.assertIn('Reopened step: B', out)
        snapshot = self.store.load_consistent_state().snapshot
        self.assertFalse(snapshot.items['B'].completed)
        self.assertEqual(snapshot.comments['public'].body, 'Done: public progress')
