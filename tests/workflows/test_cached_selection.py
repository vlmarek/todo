"""Revision 13 composition: saved operands, direct UUID writes, actual publication.

Synthetic responses follow retained Sync Tasks/Labels/Task comments tables and
ItemSyncView. ControlledHTTP distinguishes operation POST from read POST; setup
uses genuine full/delta retrieval, never an invented cached metadata default.
"""
from copy import deepcopy
from dataclasses import replace
from io import StringIO
import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs

from todo_lib import domain as d, presentation as p
from todo_lib.adapter.current import retrieve
from todo_lib.adapter.transport import Transport
from todo_lib.local import LocalError, exclusive_lock, prepare_candidates
from todo_lib.local.codec import loads, dumps
from todo_lib.syntax.input import Cancelled
from todo_lib.workflows.capture import CaptureWorkflow
from todo_lib.workflows.comments import CommentWorkflow
from todo_lib.workflows.lifecycle import LifecycleWorkflow
from todo_lib.workflows.reads import NoMatch, AmbiguityError, recent_candidates
from todo_lib.workflows.sync import Synchronizer, SyncError
from tests.adapter.current.test_current import delta, full, item, note, reminder, RESOURCES
from tests.support.http import ControlledHTTP, ExpectedRequest, Response
from tests.workflows.capture import test_capture as capture
from tests.workflows.comments import test_workflow as comments
from tests.workflows.moves import test_moves as moves
from tests.workflows.lifecycle.test_lifecycle import CommandRequest


class CachedSelectionTests(unittest.TestCase):
    def setUp(self):
        self.f = capture.CaptureTests('runTest')
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.wire_items += [item('child', content='Saved child', parent_id='parent'),
                              item('leaf', content='Saved leaf', parent_id='child')]
        self.f.seed()

    def read(self, response, token='delta-token'):
        return ExpectedRequest('POST', '/sync', 'secret', form={
            'sync_token': token, 'resource_types': RESOURCES}), response

    def workflow(self, steps=(), kind=CaptureWorkflow):
        http = ControlledHTTP([(r, v if isinstance(v, Response) else Response(json.dumps(v).encode()))
                               for r, v in steps])
        self.addCleanup(http.assert_done)
        sync = Synchronizer(Transport('secret', opener=http, sleep=lambda _: None),
                            self.f.store, clock=lambda: capture.NOW)
        return kind(sync, streams=self.f.workflow.streams), http

    def after(self, state):
        return [self.read(state), self.read(delta(), 'full-token')] * 2

    def test_parent_update_uses_cached_id_first_accepts_changed_title_and_context(self):
        # Remote parent changed title/priority context after it was selected from
        # saved data. Its complete known subtree keeps stable identities.
        rows = deepcopy(self.f.wire_items)
        rows[0].update(content='Remote parent name', description='Concurrent own text', priority=4)
        op = CommandRequest(self, 'item_update', {'id': 'parent', 'priority': 4})
        wf, http = self.workflow([op.step(), *self.after(self.f.state(items=rows))])
        result = wf.execute(['priority', 'Parent', 'P1'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertEqual(op.commands[0]['args']['id'], 'parent')
        self.assertIn('commands', parse_qs(http.requests[0][0].data.decode()))
        self.assertEqual(len(http.requests), 5)
        saved = self.f.store.load_consistent_state()
        self.assertEqual(saved.snapshot.items['parent'].title, 'Remote parent name')
        self.assertEqual(saved.snapshot.items['leaf'].parent_id, 'child')
        self.assertIn('P2 -> P1', result.document.stdout)

    def test_creation_parent_is_cached_before_first_item_add(self):
        row = item('created', content='New child', parent_id='child', priority=4)
        op = CommandRequest(self, 'item_add', dict(project_id='cat', content='New child',
            parent_id='child', priority=4, description='', labels=[], auto_reminder=False, due=None), target='created')
        wf, http = self.workflow([op.step(), *self.after(self.f.state(items=self.f.wire_items+[row]))])
        result = wf.execute(['add', 'step', 'Saved child', '--step', 'New child'])
        self.assertEqual(result.status, 0, result.document.stderr)
        self.assertEqual(len(http.requests), 5)
        self.assertEqual(self.f.store.load_consistent_state().snapshot.items['created'].parent_id, 'child')

    def test_schedule_then_relative_reminder_uses_reconciled_timed_owner(self):
        for previous in (None, capture.due('2026-10-23')):
            with self.subTest(previous=previous):
                self.f.wire_items[0]['due'] = previous
                self.f.seed()
                rows = deepcopy(self.f.wire_items)
                rows[0]['due'] = capture.due('2026-10-23T10:00:00Z')
                update = CommandRequest(self, 'item_update', {'id': 'parent',
                    'due': {'date': '2026-10-23T10:00:00Z', 'lang': 'en'}})
                add_reminder = CommandRequest(self, 'reminder_add', {'item_id': 'parent',
                    'type': 'relative', 'minute_offset': 60}, target='new-reminder')
                state = self.f.state(items=rows)
                final = self.f.state(items=rows, reminders=[
                    reminder('new-reminder', 'parent', minute_offset=60)])
                wf, http = self.workflow([update.step(), *self.after(state),
                                         add_reminder.step(), *self.after(final)])
                result = wf.execute(['schedule', 'Parent', '--at', '2026-10-23T10:00:00Z',
                                     '--reminder', '1h'])
                self.assertEqual(result.status, 0, result.document.stderr)
                self.assertEqual([o.outcome for o in result.outcomes], ['accepted', 'accepted'])
                self.assertEqual(len(http.requests), 10)
                saved = self.f.store.load_consistent_state().snapshot
                self.assertTrue(saved.items['parent'].attention.exact)
                self.assertEqual(saved.reminders['new-reminder'].minutes, 60)

    def test_reminder_replacement_stops_locally_after_owner_becomes_date_only(self):
        self.f.wire_items[0]['due'] = capture.due('2026-10-23T10:00:00Z')
        self.f.wire_reminders = [reminder('old-reminder', 'parent', minute_offset=30)]
        self.f.seed()
        rows = deepcopy(self.f.wire_items)
        rows[0]['due'] = capture.due('2026-10-23')
        deleted = CommandRequest(self, 'reminder_delete', {'id': 'old-reminder'})
        wf, http = self.workflow([deleted.step(), *self.after(self.f.state(items=rows, reminders=[]))])
        wf.streams = p.OriginalStreams(comments.Terminal('yes\n'), comments.Terminal(), StringIO())
        result = wf.execute(['schedule', 'Parent', '--reminder', '1h', '--reminder', '2h'])
        self.assertEqual(result.status, 1)
        self.assertEqual([o.outcome for o in result.outcomes],
                         ['accepted', 'unattempted', 'unattempted'])
        self.assertIn('relative reminder requires timed task due', result.document.stderr)
        self.assertIn('Not attempted: create reminder Parent', result.document.stderr)
        self.assertNotIn('unknown', result.document.stderr.lower())
        self.assertEqual(len(http.requests), 5)
        commands = [json.loads(form['commands'][0])[0]
                    for request, _ in http.requests
                    if 'commands' in (form := parse_qs(request.data.decode()))]
        self.assertEqual([c['type'] for c in commands], ['reminder_delete'])
        self.assertEqual(commands[0]['args'], {'id': 'old-reminder'})
        saved = self.f.store.load_consistent_state().snapshot
        self.assertEqual(saved.items['parent'].attention.kind, 'date')
        self.assertFalse(saved.reminders)
        # A later command consumes the published deletion and date-only owner,
        # rejecting the same relative reminder proposal without another request.
        with self.assertRaisesRegex(d.DomainError, 'timed'):
            wf.execute(['schedule', 'Parent', '--reminder', '1h'])
        self.assertEqual(len(http.requests), 5)

    def test_mixed_destination_preserves_source_and_complete_known_subtree(self):
        f = moves.MoveTests('runTest'); f.setUp(); self.addCleanup(f.doCleanups)
        wf, http = f.workflow(f.after('B', 'P', 'cat'), {'id':'B', 'parent_id':'P'})
        result = wf.execute(['move', 'B', 'P'])
        self.assertEqual(result.snapshot.items['B'].parent_id, 'P')
        first = json.loads(parse_qs(http.requests[0][0].data.decode())['commands'][0])[0]
        self.assertEqual(first['args'], {'id':'B', 'parent_id':'P'})
        self.assertEqual(result.snapshot.items['E'].parent_id, 'D')

    def test_move_accepts_changed_destination_category_and_detached_descendant(self):
        f = moves.MoveTests('runTest'); f.setUp(); self.addCleanup(f.doCleanups)
        rows = deepcopy(f.rows)
        for row in rows:
            if row['id'] in ('P','Q','B'):
                row['project_id'] = 'other'
            if row['id'] == 'B': row['parent_id'] = 'P'
            if row['id'] == 'C': row['parent_id'] = 'A'
        wf,http=f.workflow([r for r in rows if r['id'] != 'E'],{'id':'B','parent_id':'P'},archived=True)
        result=wf.execute(['move','B','P'])
        self.assertEqual(result.status,0)
        self.assertEqual(result.snapshot.items['B'].category_id,'other')
        self.assertEqual(result.snapshot.items['C'].parent_id,'A')
        self.assertEqual(result.snapshot.items['E'].category_id,'cat')
        first=json.loads(parse_qs(http.requests[0][0].data.decode())['commands'][0])[0]
        self.assertEqual(first['args'],{'id':'B','parent_id':'P'})

    def test_local_no_match_ambiguity_cancellation_and_invalid_proposal_zero_requests(self):
        wf, http = self.workflow()
        with self.assertRaisesRegex(NoMatch, 'missing.*whole.*saved data.*todo --refresh now'):
            wf.execute(['rename', 'missing', 'whole', '--to', 'Changed'])
        with self.assertRaises(AmbiguityError):
            wf.execute(['rename', 'Saved', '--to', 'Changed'])
        with self.assertRaisesRegex(d.DomainError, 'missing category.*saved data.*todo --refresh now'):
            wf.execute(['add','missing category','--title','New task'])
        with self.assertRaisesRegex(d.DomainError, 'sibling'):
            wf.execute(['rename', 'Parent', '--to', 'Known sibling'])
        lifecycle = LifecycleWorkflow(wf.synchronizer, streams=p.OriginalStreams(
            comments.Terminal('no\n'), comments.Terminal(), StringIO()))
        with self.assertRaises(Cancelled):
            lifecycle.execute(['delete', 'Parent'])
        self.assertFalse(http.requests)

    def test_missing_and_invalid_saved_context_are_local_errors_not_no_match(self):
        wf, http = self.workflow()
        path = self.f.root/'cache.json'; original = path.read_bytes()
        path.unlink()
        with self.assertRaises(LocalError): wf.execute(['rename','Parent','--to','Changed'])
        path.write_bytes(b'{invalid')
        with self.assertRaises(LocalError): wf.execute(['rename','Parent','--to','Changed'])
        self.assertEqual(path.read_bytes(), b'{invalid')
        path.write_bytes(original)
        self.assertFalse(http.requests)

    def test_missing_waiting_fact_requires_refresh_invalid_fact_preserves_bytes(self):
        self.f.wire_items[0]['due'] = capture.due('2026-10-23')
        self.f.seed()
        path = self.f.root/'cache.json'; raw = loads(path.read_bytes())
        raw.pop('waiting_label_ids')
        path.write_bytes(dumps(raw))
        wf, http = self.workflow()
        with self.assertRaisesRegex(LocalError, 'missing.*todo --refresh now'):
            wf.execute(['hide','Parent'])
        # Legacy cache remains usable for an operation not requiring labels.
        with self.assertRaisesRegex(d.DomainError, 'unchanged'):
            wf.execute(['priority','Parent','P2'])
        raw['waiting_label_ids'] = True; invalid = dumps(raw); path.write_bytes(invalid)
        with self.assertRaises(LocalError): wf.execute(['hide','Parent'])
        self.assertEqual(path.read_bytes(), invalid)
        self.assertFalse(http.requests)

    def test_legacy_current_provenance_hydrates_only_after_saved_hiding_write(self):
        f=self.f
        f.wire_items[0]['due']=capture.due('2026-10-23');f.seed()
        path=f.root/'cache.json'; raw=loads(path.read_bytes());raw.pop('current_resources')
        path.write_bytes(dumps(raw))
        self.assertEqual(f.store.load_consistent_state().waiting_label_ids,{'waiting'})
        rows=[dict(r,labels=['waiting']) if r['id']=='parent' else r for r in f.wire_items]
        state=f.state(items=rows)
        op=CommandRequest(self,'item_update',{'id':'parent','labels':['waiting']})
        wf,http=self.workflow([op.step(),self.read(state,'*'),self.read(delta(),'full-token'),
                               self.read(state,'*'),self.read(delta(),'full-token')])
        result=wf.execute(['hide','Parent'])
        self.assertEqual(result.status,0,result.document.stderr)
        self.assertEqual(len(http.requests),5)
        self.assertTrue(f.store.load_consistent_state().snapshot.items['parent'].waiting)

    def test_waiting_context_full_delta_rename_tombstone_and_legacy_unknown(self):
        wf, http = self.workflow([self.read(delta(labels=[dict(id='waiting', name='other', is_deleted=False)])),
                                 self.read(delta(labels=[dict(id='new', name='waiting', is_deleted=False)])),
                                 self.read(delta(labels=[dict(id='new', is_deleted=True)])),
                                 self.read(delta())])
        sync = wf.synchronizer
        self.assertEqual(self.f.store.load_consistent_state().waiting_label_ids, {'waiting'})
        for expected in (frozenset(), frozenset({'new'}), frozenset()):
            result = sync.refresh()
            self.assertEqual(result.state.waiting_label_ids, expected)
        # No provenance for a legacy delta: absence is unknown, never false.
        saved = sync.read_local().state
        current = retrieve(sync.transport, saved.snapshot.binding, prior=saved.current_snapshot,
                           sync_token=saved.sync_token)
        self.assertIsNone(current.waiting_label_ids)
        self.assertEqual(len(http.requests), 4)

    def test_label_relevance_and_malformed_required_context(self):
        saved=self.f.store.load_consistent_state()
        state=self.f.state()
        state['labels'].append({'id':'unrelated','name':123,'is_deleted':False})
        wf,http=self.workflow([self.read(state,'*'),self.read(delta(),'full-token')])
        current=retrieve(wf.synchronizer.transport,saved.snapshot.binding,replace=True)
        self.assertEqual(current.waiting_label_ids,{'waiting'})
        self.assertEqual(len(http.requests),2)
        for label in ({'id':'waiting','name':'waiting','is_deleted':None},
                      {'id':'waiting','name':None,'is_deleted':False}):
            with self.subTest(label=label):
                malformed=self.f.state();malformed['labels']=[label]
                wf,http=self.workflow([self.read(malformed,'*')])
                with self.assertRaises(d.DomainError):
                    retrieve(wf.synchronizer.transport,saved.snapshot.binding,replace=True,
                             waiting_label_ids=saved.waiting_label_ids)
                self.assertEqual(len(http.requests),1)

    def test_explicit_refresh_recovers_legacy_label_context_preserving_pending_history(self):
        f=self.f
        completed=item('retained',content='Retained',checked=True,completed_at='2026-10-21T00:00:00Z')
        f.wire_items.append(completed);f.seed()
        state=f.store.load_consistent_state()
        with exclusive_lock('setup',f.root):
            f.store.publish_snapshot(prepare_candidates(state.snapshot,replace(state.history,snapshot=state.snapshot),
                account_display='Person',sync_token=state.sync_token,synced_at=state.synced_at,
                current_snapshot=state.current_snapshot))
        before=f.store.load_consistent_state()
        self.assertIsNone(before.waiting_label_ids)
        wf,http=self.workflow([self.read(f.state(),'*'),self.read(delta(),'full-token')])
        wf.synchronizer.refresh()
        after=f.store.load_consistent_state()
        self.assertEqual(after.waiting_label_ids,{'waiting'})
        self.assertEqual(after.cursor,before.cursor)
        self.assertEqual(after.history.snapshot.items['retained'],before.history.snapshot.items['retained'])
        self.assertEqual(len(http.requests),2)

    def test_stale_id_rejection_never_substitutes_new_title_match(self):
        op = CommandRequest(self, 'item_update', {'id':'parent', 'content':'Changed'},
                            status={'error_code':1, 'error':'Task not found'})
        rows = [r for r in deepcopy(self.f.wire_items) if r['id'] not in ('parent','child','leaf')]
        rows += [dict(id=k,is_deleted=True) for k in ('parent','child','leaf')]
        rows.append(item('replacement', content='Parent'))
        wf, http = self.workflow([op.step(), self.read(self.f.state(items=rows)), self.read(delta(),'full-token')])
        result = wf.execute(['rename','Parent','--to','Changed'])
        self.assertEqual([o.outcome for o in result.outcomes], ['rejected'])
        self.assertEqual(len(op.commands), 1)
        self.assertEqual(op.commands[0]['args']['id'], 'parent')
        self.assertEqual(len(http.requests), 3)

    def test_cached_deletion_preview_omits_unseen_cascade_descendant(self):
        op = CommandRequest(self, 'item_delete', {'id':'parent'})
        # Remote cascade also deleted a never-observed child. No preview read is
        # scripted; its tombstone is learned only after item_delete acceptance.
        tombstones = [dict(id=k, is_deleted=True) for k in ('parent','child','leaf','unseen')]
        wf, http = self.workflow([op.step(), self.read(delta(items=tombstones)),
                                 self.read(delta(items=tombstones))], LifecycleWorkflow)
        result = wf.execute(['delete','--yes','Parent'])
        self.assertEqual(result.status, 0, result.document.stderr)
        preview = self.f.workflow.streams.stdout.getvalue()
        self.assertIn('  Saved child\n    Saved leaf', preview)
        self.assertNotIn('unseen', preview)
        self.assertEqual(len(http.requests), 3)
        self.assertNotIn('parent', self.f.store.load_consistent_state().snapshot.items)

    def test_accepted_mutation_then_reconciliation_failure_is_partial(self):
        op = CommandRequest(self, 'item_update', {'id':'parent', 'priority':4})
        rows = [dict(r, priority=4) if r['id']=='parent' else r for r in self.f.wire_items]
        wf, http = self.workflow([op.step(), self.read(self.f.state(items=rows)), self.read(delta(),'full-token'),
                                 self.read(Response(b'{invalid'))])
        result = wf.execute(['priority','Parent','P1'])
        self.assertEqual(result.status, 1)
        self.assertEqual([o.outcome for o in result.outcomes], ['accepted'])
        self.assertEqual(result.failure.remote_outcome, 'accepted')
        self.assertEqual(len(op.commands), 1)
        self.assertEqual(self.f.store.load_consistent_state().snapshot.items['parent'].priority, 2)

    def test_retained_completed_bounds_and_latest_recurring_undo_are_local(self):
        f = self.f; saved = f.store.load_consistent_state(); s = saved.snapshot
        cursor = d.instant_from_wire('2026-10-20T00:00:00Z')
        at = d.instant_from_wire('2026-10-21T00:00:00Z')
        recurrence = d.resolve_remote_due(capture.due('2026-10-25', is_recurring=True, string='every day'), 'UTC')
        rows = {**s.items, 'boundary':d.Item('boundary','cat','Boundary',completed=True,completed_at=cursor),
                'done':d.Item('done','cat','Retained done',completed=True,completed_at=at),
                'recurring':d.Item('recurring','cat','Recurring',attention=recurrence)}
        # Use the domain constructor's public occurrence fields, including an
        # explicitly observed undo of the latest recurring completion.
        from todo_lib.domain import Occurrence
        occurrences = {o.id:o for o in (Occurrence('old','recurring',at),
            Occurrence('latest','recurring',capture.NOW,undone=True))}
        snapshot = replace(s, items=rows, occurrences=occurrences)
        self.assertEqual([c.item_id for c in recent_candidates(snapshot,'Retained',cursor,capture.NOW)], ['done'])
        self.assertFalse(recent_candidates(snapshot,'Boundary',cursor,capture.NOW))
        self.assertFalse(recent_candidates(snapshot,'Recurring',cursor,capture.NOW))
        with exclusive_lock('test',f.root):
            history = replace(saved.history,snapshot=snapshot)
            f.store.publish_snapshot(prepare_candidates(snapshot,history,account_display='Person',
                sync_token=saved.sync_token,synced_at=saved.synced_at,current_snapshot=saved.current_snapshot,
                waiting_label_ids=saved.waiting_label_ids))
            f.store.write_cursor(cursor)
        wf,http=self.workflow(kind=LifecycleWorkflow)
        with self.assertRaises(NoMatch): wf.execute(['reopen','Boundary'])
        with self.assertRaises(NoMatch): wf.execute(['reopen','Recurring'])
        wf.streams = p.OriginalStreams(comments.Terminal('no\n'),comments.Terminal(),StringIO())
        with self.assertRaises(Cancelled): wf.execute(['delete','Retained'])
        self.assertFalse(http.requests)


class CachedEditorTests(unittest.TestCase):
    def setUp(self):
        self.f=comments.WorkflowTests('runTest');self.f.setUp();self.addCleanup(self.f.doCleanups)

    def test_cached_comments_seed_unchanged_and_invalid_buffers_without_requests(self):
        f=self.f
        with patch.object(f.workflow,'_edit',side_effect=lambda text:text):
            result=f.edit()
        self.assertEqual(result.status,0)
        self.assertFalse(f.wire.commands)
        with patch.object(f.workflow,'_edit',return_value='[id: foreign posted: none]\ntext\n'):
            with self.assertRaises(comments.CommentError): f.edit()
        self.assertFalse(f.wire.steps)

    def test_editor_first_request_updates_saved_comment_id(self):
        f=self.f
        f.save(comments.encode_buffer(f.owner_comments()).replace('\nolder\n','\nchanged\n'))
        returned=[dict(n,content='changed') if n['id']=='z-older' else n for n in f.notes]
        op = CommandRequest(self, 'note_update', {'id':'z-older','content':'changed'})
        def read(response, token='delta-token'):
            return (ExpectedRequest('POST','/sync','secret',form={
                'sync_token':token,'resource_types':RESOURCES}), response)
        scoped = [{k:v for k,v in n.items() if k!='item_id'} for n in returned if n['item_id']=='C']
        steps = [op.step(), read(comments.tree(returned)), read(delta(),'full-token'),
                 (ExpectedRequest('GET','/comments','secret',query={'task_id':'C','limit':'200'}),
                  {'results':scoped,'next_cursor':None}),
                 read(comments.tree(returned)), read(delta(),'full-token')]
        http = ControlledHTTP([(r,v if isinstance(v,Response) else Response(json.dumps(v).encode()))
                               for r,v in steps])
        self.addCleanup(http.assert_done)
        sync=Synchronizer(Transport('secret',opener=http,sleep=lambda _:None),f.store,clock=lambda:comments.NOW)
        wf=CommentWorkflow(sync,streams=f.streams,environ=f.environ)
        result=wf.execute(['comment','--edit','Leaf'])
        self.assertEqual(result.status,0,result.document.stderr)
        self.assertEqual(op.commands[0]['args']['id'],'z-older')
        self.assertEqual(len(http.requests),6)
        self.assertEqual(f.store.load_consistent_state().snapshot.comments['z-older'].body,'changed')

    def test_comment_receipts_use_reconciled_owner_title_and_hierarchy(self):
        for editing in (True, False):
            with self.subTest(editing=editing):
                f = comments.WorkflowTests('runTest')
                f.setUp()
                self.addCleanup(f.doCleanups)
                if editing:
                    f.save(comments.encode_buffer(f.owner_comments()).replace('\nolder\n', '\nchanged\n'))
                    returned = [dict(n, content='changed') if n['id'] == 'z-older' else n for n in f.notes]
                    f.wire.command('note_update', {'id': 'z-older', 'content': 'changed'})
                else:
                    returned = [*f.notes, note('new-comment', 'C', content='added')]
                    f.wire.command('note_add', {'item_id': 'C', 'content': 'added'})
                state = comments.tree(returned)
                state['items'][2].update(content='Remote leaf', parent_id='A')
                f.wire.sync('delta-token', state)
                f.wire.sync('full-token', delta())
                f.wire.comments(returned)
                f.wire.sync('delta-token', state)
                f.wire.sync('full-token', delta())
                result = f.edit() if editing else f.workflow.execute(['comment', 'Leaf', '--comment', 'added'])
                self.assertEqual(result.status, 0, result.document.stderr)
                prefix = 'Comments updated: ' if editing else 'Comments for: '
                self.assertIn(prefix + 'Remote leaf — Root', result.document.stdout)
                self.assertNotIn('Branch', result.document.stdout)
                self.assertEqual(result.selected.title, 'Remote leaf')
                saved = f.store.load_consistent_state().snapshot
                self.assertEqual(saved.items['C'].parent_id, 'A')
                self.assertEqual(saved.items['C'].title, 'Remote leaf')
