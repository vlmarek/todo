"""Synthetic provider-shaped fixtures, not recorded traffic or schema defaults.

Offline authority inspected 2026-10-26: retained api-v1.openapi.json Sync tag,
Read resources/Incremental sync/Projects/Tasks/Task comments/Reminders/User plan
limits; Due dates tag; ItemSyncView and nullable NoteSyncView.posted_at.
PersonalProjectSyncView/WorkspaceProjectSyncView require boolean is_shared;
the retained Sync Projects prose contradicts them with shared. These synthetic
fixtures follow the typed schemas and deliberately omit shared.
Documented examples use many irrelevant fields. These fixtures deliberately omit
those and all invented aliases/activity. A numeric workspace_id is documented in
the Projects example even though its property table describes a string.
"""
from copy import deepcopy
from decimal import Decimal
import json
import unittest

from todo_lib.adapter.current import CurrentError, retrieve
from todo_lib.adapter.transport import Transport, Rejected, TransportError, ProtocolError
from todo_lib.domain import (Binding, DomainError, instant_key, instant_text,
                             ordered_siblings)
from todo_lib.local.codec import snapshot_data, snapshot_from, dumps, loads
from tests.support.http import ControlledHTTP, ExpectedRequest, Response


BINDING = Binding('u', 'root', frozenset({'cat'}))
STAMP = '2026-10-20T12:00:00.123456789Z'
MISSING = object()
RESOURCES = '["user","user_plan_limits","projects","items","labels","notes","reminders"]'


def project(identity='cat', parent='root', **changes):
    obj = dict(id=identity, name=identity, parent_id=parent, is_shared=False,
               is_archived=False, is_deleted=False)
    obj.update(changes)
    return obj


def due(value='2026-11-12T15:00:00.123456789Z', **changes):
    obj = dict(date=value, timezone='Europe/Prague', string='every day at 16',
               lang='en', is_recurring=False)
    obj.update(changes)
    return obj


def item(identity='task', **changes):
    obj = dict(id=identity, project_id='cat', parent_id=None, content=identity,
               priority=4, checked=False, labels=[], due=None, added_at=STAMP,
               completed_at=None, is_deleted=False)
    obj.update(changes)
    return obj


def note(identity='note', owner='task', **changes):
    obj = dict(id=identity, item_id=owner, content='own note', posted_at=STAMP,
               is_deleted=False, file_attachment=None)
    obj.update(changes)
    return obj


def reminder(identity='reminder', owner='task', **changes):
    obj = dict(id=identity, item_id=owner, type='relative', minute_offset=0,
               is_deleted=False)
    obj.update(changes)
    return obj


def full(**changes):
    obj = dict(full_sync=True, sync_token='full-token',
        user={'id': 'u', 'tz_info': {'timezone': 'Europe/Prague'}},
        user_plan_limits={'current': {'activity_log': False,
            'activity_log_limit': 0, 'reminders': True}},
        projects=[project('root', None), project()], labels=[],
        items=[item()], notes=[], reminders=[])
    obj.update(changes)
    return obj


def delta(**changes):
    obj = dict(full_sync=False, sync_token='delta-token')
    obj.update(changes)
    return obj


class CurrentTests(unittest.TestCase):
    def boundary(self, steps):
        script = []
        for token, response in steps:
            if not isinstance(response, (Response, Exception)):
                response = Response(json.dumps(response).encode())
            script.append((ExpectedRequest('POST', '/sync', 'secret', form={
                'sync_token': token, 'resource_types': RESOURCES}), response))
        http = ControlledHTTP(script)
        self.addCleanup(http.assert_done)
        return Transport('secret', opener=http, sleep=lambda _: None), http

    def initial(self, response=None, freshness=None):
        transport, _ = self.boundary([('*', full() if response is None else response),
            ('full-token', delta() if freshness is None else freshness)])
        return retrieve(transport, BINDING)

    def changed(self, prior, response):
        transport, _ = self.boundary([(prior.sync_token, response)])
        return retrieve(transport, prior.binding, prior=prior.snapshot,
                        sync_token=prior.sync_token)

    def test_full_and_one_delta_requests_minimal_wire_contract(self):
        result = self.initial()
        self.assertEqual(result.sync_token, 'delta-token')
        self.assertEqual(result.account.id, 'u')
        self.assertFalse(result.account.capabilities.activity_history)
        self.assertEqual(result.account.capabilities.history_limit, 0)
        self.assertEqual(result.snapshot.items['task'].priority, 1)
        self.assertFalse(result.snapshot.items['task'].completed)
        self.assertEqual(result.snapshot.items['task'].description, '')
        self.assertFalse(result.disappeared_ids)

    def test_precise_creation_completion_comment_and_snapshot_seeded_delta(self):
        response = full(items=[item(checked=True, completed_at=STAMP)], notes=[note()])
        first = self.initial(response)
        # Exercise actual local persistence too; exact values must seed the delta.
        restored = snapshot_from(loads(dumps(snapshot_data(first.snapshot))), first.account.timezone)
        transport, _ = self.boundary([('delta-token', delta())])
        result = retrieve(transport, restored.binding, prior=restored, sync_token='delta-token')
        task = result.snapshot.items['task']
        for value in (task.added_at, task.completed_at, result.snapshot.comments['note'].added_at):
            self.assertEqual(instant_text(value), STAMP)
        equivalent = '2026-10-20T14:00:00.123456789+02:00'
        later = self.changed(result, delta(items=[item(added_at=equivalent, checked=True,
            completed_at=equivalent)], notes=[note(posted_at=equivalent)]))
        self.assertEqual(instant_key(later.snapshot.items['task'].added_at), instant_key(task.added_at))
        self.assertEqual(instant_text(later.snapshot.comments['note'].added_at), STAMP)

    def test_authoritative_known_to_null_and_comment_null(self):
        first = self.initial(full(notes=[note()]))
        result = self.changed(first, delta(items=[item(added_at=None)], notes=[note(posted_at=None)]))
        self.assertIsNone(result.snapshot.items['task'].added_at)
        self.assertIsNone(result.snapshot.comments['note'].added_at)
        unchanged = self.changed(result, delta())
        self.assertIsNone(unchanged.snapshot.items['task'].added_at)

    def test_required_timestamps_reject_missing_naive_empty_or_wrong_type(self):
        for field in ('added_at', 'completed_at'):
            for value in (MISSING, '', '2026-10-20T12:00:00', 'invalid', 12, False):
                with self.subTest(field=field, value=value):
                    raw = item()
                    if value is MISSING:
                        raw.pop(field)
                    else:
                        raw[field] = value
                    transport, _ = self.boundary([('*', full(items=[raw])), ('full-token', delta())])
                    with self.assertRaises(DomainError):
                        retrieve(transport, BINDING)
        for value in (MISSING, '', '2026-10-20T12:00:00', 42):
            with self.subTest(comment=value):
                raw = note()
                if value is MISSING:
                    raw.pop('posted_at')
                else:
                    raw['posted_at'] = value
                transport, _ = self.boundary([('*', full(notes=[raw])), ('full-token', delta())])
                with self.assertRaises(DomainError):
                    retrieve(transport, BINDING)

    def test_descriptions_absent_null_empty_tasks_and_steps_and_delta_clear(self):
        for value in (MISSING, None, ''):
            with self.subTest(value=value):
                raws = [item(description='old'), item('step', parent_id='task', description='old')]
                first = self.initial(full(items=raws))
                for raw in raws:
                    if value is MISSING:
                        raw.pop('description')
                    else:
                        raw['description'] = value
                result = self.changed(first, delta(items=raws))
                self.assertTrue(all(i.description == '' for i in result.snapshot.items.values()))
                fresh = self.initial(full(items=raws))
                self.assertEqual(fresh.snapshot.items['step'].description, '')

    def test_descriptions_strict_and_preserve_waiting_reason(self):
        for value in ('a\rb', '\x00', 3, False, [], {}):
            with self.subTest(value=value):
                transport, _ = self.boundary([('*', full(items=[item(description=value)])),
                                               ('full-token', delta())])
                with self.assertRaises(DomainError):
                    retrieve(transport, BINDING)
        text = 'Ordinary text\n\n[todo waiting]\nA reason\n[/todo waiting]'
        result = self.initial(full(items=[item(description=text, labels=['waiting'], due=due())]))
        self.assertEqual(result.snapshot.items['task'].description, text)
        self.initial(full(items=[item(labels=['waiting'], due=due())]))
        for changes in (dict(description=text), dict(labels=['waiting'])):
            transport, _ = self.boundary([('*', full(items=[item(**changes)])), ('full-token', delta())])
            result = retrieve(transport, BINDING)
            self.assertEqual(result.snapshot.items['task'].description, changes.get('description', ''))

    def test_checked_only_boolean_and_priority_inversion_at_all_depths(self):
        raws = [item()]
        for depth in range(1, 5):
            raws.append(item(str(depth), parent_id='task' if depth == 1 else str(depth-1), priority=depth))
        result = self.initial(full(items=list(reversed(raws))))
        self.assertEqual([result.snapshot.items[str(d)].priority for d in range(1, 5)], [4, 3, 2, 1])
        result = self.changed(result, delta(items=[item('4', parent_id='3', checked=True, completed_at=STAMP)]))
        self.assertTrue(result.snapshot.items['4'].completed)
        for value in (MISSING, None, 0, 1, 'false', [], {}):
            with self.subTest(value=value):
                raw = item(is_completed=False)
                if value is MISSING:
                    raw.pop('checked')
                else:
                    raw['checked'] = value
                transport, _ = self.boundary([('*', full(items=[raw])), ('full-token', delta())])
                with self.assertRaisesRegex(DomainError, 'checked'):
                    retrieve(transport, BINDING)

    def test_plan_name_ignored_current_not_next_and_metadata_updated(self):
        for value in (MISSING, '', 'pro_legacy', 'future', {}, False, None):
            response = full()
            if value is not MISSING:
                response['user_plan_limits']['current']['plan_name'] = value
            response['user_plan_limits']['next'] = {'reminders': 'bad'}
            result = self.initial(response)
            self.assertEqual(result.account.capabilities.history_limit, 0)
            self.assertNotIn('plan_name', repr(result))
        result = self.initial(freshness=delta(
            user={'id': 'u', 'tz_info': {'timezone': 'America/New_York'}},
            user_plan_limits={'current': {'activity_log': True, 'activity_log_limit': -1, 'reminders': False}}))
        self.assertEqual(result.account.timezone, 'America/New_York')
        self.assertEqual(result.account.capabilities.history_limit, -1)
        self.assertFalse(result.account.capabilities.reminders)

    def test_strict_capabilities_and_account(self):
        for field, values in [('activity_log', (MISSING, None, 0, 'false')),
                              ('reminders', (MISSING, None, 1, 'true')),
                              ('activity_log_limit', (MISSING, None, True, -2, '7', 1.5))]:
            for value in values:
                with self.subTest(field=field, value=value):
                    response = full()
                    if value is MISSING:
                        response['user_plan_limits']['current'].pop(field)
                    else:
                        response['user_plan_limits']['current'][field] = value
                    transport, _ = self.boundary([('*', response)])
                    with self.assertRaises(DomainError):
                        retrieve(transport, BINDING)
        for user in ({'id': 'other', 'tz_info': {'timezone': 'UTC'}},
                     {'id': 'u'}, {'id': 'u', 'tz_info': {'timezone': 'not/zone'}}):
            transport, _ = self.boundary([('*', full(user=user))])
            with self.assertRaises(DomainError):
                retrieve(transport, BINDING)

    def test_documented_project_scope_fields_are_authority(self):
        for changes in ({'is_shared': True, 'shared': False}, {'inbox_project': True}, {'workspace_id': 'workspace'},
                        {'workspace_id': 12345}, {'is_archived': True}, {'parent_id': 'other'},
                        {'is_shared': None}, {'is_archived': 0}, {'inbox_project': None}, {'workspace_id': False}):
            for target in ('root', 'cat'):
                with self.subTest(target=target, changes=changes):
                    response = full()
                    raw = response['projects'][0 if target == 'root' else 1]
                    raw.update(changes)
                    transport, _ = self.boundary([('*', response), ('full-token', delta())])
                    with self.assertRaises(DomainError):
                        retrieve(transport, BINDING)
        for field in ('is_shared', 'is_archived', 'parent_id', 'is_deleted'):
            response = full()
            response['projects'][1].pop(field)
            transport, _ = self.boundary([('*', response), ('full-token', delta())])
            with self.assertRaises(DomainError):
                retrieve(transport, BINDING)
        result = self.initial(full(projects=[project('root', None, shared={'ignored': True}),
            project(is_inbox_project=True, is_organization=True, workspace_id=None)]))
        self.assertEqual(result.binding, BINDING)

    def test_is_shared_required_boolean_even_with_unknown_shared(self):
        for value, diagnostic in ((MISSING, 'missing'), (None, 'null'),
                                  (0, 'must be'), (1, 'must be'),
                                  ('false', 'must be'), ([], 'must be')):
            with self.subTest(value=value):
                raw = project(shared=False)
                raw.pop('is_shared')
                if value is not MISSING:
                    raw['is_shared'] = value
                with self.assertRaises(CurrentError) as caught:
                    self.initial(full(projects=[project('root', None), raw]))
                message = str(caught.exception)
                for fact in ('is_shared', 'boolean', diagnostic):
                    self.assertIn(fact, message)
        for unknown in (True, None, {'ignored': 'value'}):
            result = self.initial(full(projects=[project('root', None),
                                                project(shared=unknown)]))
            self.assertFalse(result.snapshot.categories['cat'].shared)
        with self.assertRaises(DomainError):
            self.initial(full(projects=[project('root', None),
                                       project(is_shared=True, shared=False)]))

    def test_project_duplicate_signatures_consume_is_shared_only(self):
        result = self.initial(full(projects=[project('root', None),
            project(shared=False), project(shared={'ignored': True})]))
        self.assertFalse(result.snapshot.categories['cat'].shared)
        for other in (True, 0):
            transport, _ = self.boundary([('*', full(projects=[project('root', None),
                project(), project(is_shared=other)]))])
            with self.assertRaisesRegex(CurrentError, 'contradictory live projects'):
                retrieve(transport, BINDING)

    def test_ownership_before_feature_validation_and_minimal_result(self):
        response = full(items=[item(), dict(id='private', project_id='elsewhere', checked='bad')],
            notes=[note(), dict(id='unrelated-note', item_id='private', content={'secret': 42},
                               file_attachment={'secret': 12}, posted_at='bad')],
            reminders=[dict(id='unrelated-reminder', item_id='private', type='location', minute_offset='bad')])
        response['user']['token'] = 'provider-secret'
        response['items'][0]['is_completed'] = True
        response['items'][0]['unknown'] = {'secret': 42}
        result = self.initial(response)
        self.assertEqual(set(result.snapshot.items), {'task'})
        self.assertEqual(set(result.snapshot.comments), {'note'})
        self.assertFalse(result.snapshot.reminders)
        self.assertNotIn('secret', repr(result))
        self.assertNotIn('private', repr(result))
        for name in ('notes', 'reminders'):
            response = full(**{name: [{'id': 'no-owner', 'type': 'location'}]})
            transport, _ = self.boundary([('*', response), ('full-token', delta())])
            with self.assertRaisesRegex(DomainError, 'item_id'):
                retrieve(transport, BINDING)

    def test_step_owns_comments_reminders_no_comment_length_cap(self):
        response = full(items=[item(), item('step', parent_id='task', due=due())],
            notes=[note(owner='step', content='x' * 50000, posted_at=None)],
            reminders=[reminder(owner='step')])
        first = self.initial(response)
        result = self.changed(first, delta())
        self.assertEqual(result.snapshot.comments['note'].item_id, 'step')
        self.assertEqual(len(result.snapshot.comments['note'].body), 50000)
        self.assertEqual(result.snapshot.reminders['reminder'].minutes, 0)
        restored = snapshot_from(loads(dumps(snapshot_data(result.snapshot))), result.account.timezone)
        self.assertEqual(restored.reminders['reminder'].minutes, 0)
        self.assertIsNone(restored.comments['note'].added_at)

    def test_reminder_type_before_offset_and_zero_offset_strictness(self):
        self.initial(full(items=[item(due=due(is_recurring=True))], reminders=[reminder()]))
        for value in (MISSING, None, -1, False, '0', 0.5):
            raw = reminder()
            if value is MISSING:
                raw.pop('minute_offset')
            else:
                raw['minute_offset'] = value
            transport, _ = self.boundary([('*', full(items=[item(due=due())], reminders=[raw])), ('full-token', delta())])
            with self.assertRaisesRegex(DomainError, 'minute_offset'):
                retrieve(transport, BINDING)
        for kind in ('location', None):
            transport, _ = self.boundary([('*', full(reminders=[reminder(type=kind, minute_offset='bad')])), ('full-token', delta())])
            with self.assertRaisesRegex(DomainError, 'type unsupported'):
                retrieve(transport, BINDING)

    def test_due_forms_and_dst_fractions_through_mapping(self):
        for value, zone, kind, seconds in [
            ('2026-10-25T02:30:00.123456789', None, 'floating', '1792888200.123456789'),
            ('2026-03-29T02:30:00.123456789', None, 'floating', '1774747800.123456789'),
            ('2026-11-12T15:00:00.123456789Z', 'Europe/Prague', 'fixed', '1794495600.123456789'),
        ]:
            with self.subTest(value=value):
                result = self.initial(full(items=[item(due=due(value, timezone=zone))]))
                attention = result.snapshot.items['task'].attention
                self.assertEqual(attention.kind, kind)
                self.assertEqual(attention.epoch_seconds, Decimal(seconds))
                self.assertEqual(attention.raw_due['date'], value)
                self.assertEqual(attention.language, 'en')
        result = self.initial(full(items=[item(due=due('2026-11-12', timezone=None))]))
        self.assertEqual(result.snapshot.items['task'].attention.kind, 'date')
        self.assertEqual(str(result.snapshot.items['task'].attention.date_value), '2026-11-12')

    def test_timezone_change_reresolves_floating_and_preserves_fixed(self):
        first = self.initial(full(items=[item(due=due('2026-11-12T16:00:00.123456789', timezone=None)),
                                         item('fixed', due=due())]))
        result = self.changed(first, delta(user={'id': 'u', 'tz_info': {'timezone': 'UTC'}}))
        before, after = first.snapshot.items, result.snapshot.items
        self.assertEqual(after['task'].attention.epoch_seconds - before['task'].attention.epoch_seconds, 3600)
        self.assertEqual(after['fixed'].attention.epoch_seconds, before['fixed'].attention.epoch_seconds)
        self.assertEqual(after['task'].attention.raw_due, before['task'].attention.raw_due)

    def test_new_category_enrolled_before_filtering_and_resources_follow_project_move(self):
        first = self.initial()
        new = project('new', 'root')
        # Only the project moves in the delta. Its unchanged item/note/reminder
        # are absent, so a minimal Snapshot cannot reconstruct them from delta.
        replacement = full(projects=[project('root', None), project(), new],
            items=[item(), item('entrant', project_id='new', due=due())],
            notes=[note('entrant-note', 'entrant')],
            reminders=[reminder('entrant-reminder', 'entrant')])
        transport, _ = self.boundary([('delta-token', delta(projects=[new])),
            ('*', replacement), ('full-token', delta())])
        result = retrieve(transport, first.binding, prior=first.snapshot, sync_token=first.sync_token)
        self.assertEqual(result.binding.category_ids, frozenset({'cat', 'new'}))
        self.assertEqual(result.snapshot.comments['entrant-note'].item_id, 'entrant')
        self.assertEqual(result.snapshot.reminders['entrant-reminder'].minutes, 0)
        # The same enrollment works during initial full+delta, including parent
        # references appearing after their children in the complete resource set.
        initial = self.initial(replacement)
        self.assertEqual(initial.binding, result.binding)

    def test_item_enters_scope_with_unchanged_own_resources(self):
        first = self.initial()
        entrant = item('entrant', due=due())
        transport, _ = self.boundary([('delta-token', delta(items=[entrant])),
            ('*', full(items=[item(), entrant], notes=[note(owner='entrant')],
                       reminders=[reminder(owner='entrant')])),
            ('full-token', delta())])
        result = retrieve(transport, first.binding, prior=first.snapshot, sync_token=first.sync_token)
        self.assertEqual(result.snapshot.comments['note'].item_id, 'entrant')
        self.assertEqual(result.snapshot.reminders['reminder'].item_id, 'entrant')

    def test_move_during_full_freshness_keeps_unchanged_resource_owners(self):
        result = self.initial(full(items=[item(), item('entrant', project_id='other', due=due())],
            notes=[note(owner='entrant')], reminders=[reminder(owner='entrant')]),
            delta(items=[item('entrant', due=due())]))
        self.assertEqual(result.snapshot.comments['note'].item_id, 'entrant')
        self.assertEqual(result.snapshot.reminders['reminder'].item_id, 'entrant')

    def test_new_invalid_category_fails_without_dropping_its_items(self):
        transport, _ = self.boundary([('*', full(projects=[project('root', None), project(),
            project('new', is_shared=True)], items=[item('entrant', project_id='new')])),
            ('full-token', delta())])
        with self.assertRaisesRegex(DomainError, 'scope'):
            retrieve(transport, BINDING)

    def test_hierarchy_only_after_complete_merge_and_full_depth_invariants(self):
        first = self.initial(full(items=[item(), item('step', parent_id='task')]))
        result = self.changed(first, delta(items=[item('step', parent_id=None),
                                                item(parent_id='step')]))
        self.assertEqual(result.snapshot.items['task'].parent_id, 'step')
        for raws in ([item(parent_id='missing')],
                     [item(parent_id='step'), item('step', parent_id='task')],
                     [item(), item('step', parent_id='task', project_id='othercat')],
                     [item(checked=True, completed_at=STAMP), item('step', parent_id='task')],
                     [item()] + [item(str(d), parent_id='task' if d == 1 else str(d-1)) for d in range(1, 6)]):
            with self.subTest(raws=[r['id'] for r in raws]):
                response = full(projects=[project('root', None), project(), project('othercat')], items=raws)
                transport, _ = self.boundary([('*', response), ('full-token', delta())])
                with self.assertRaises(DomainError):
                    retrieve(transport, BINDING)

    def test_tombstones_and_disappeared_ids_are_distinct_from_completion(self):
        first = self.initial(full(items=[item(), item('deleted'), item('departed')],
                                  notes=[note()], reminders=[]))
        result = self.changed(first, delta(items=[{'id': 'deleted', 'is_deleted': True},
            item('departed', project_id='elsewhere')], notes=[{'id': 'note', 'is_deleted': True}]))
        self.assertEqual(result.deleted_ids, frozenset({'deleted'}))
        self.assertEqual(result.departed_ids, frozenset({'departed'}))
        self.assertFalse(result.disappeared_ids)
        self.assertEqual(set(result.snapshot.items), {'task'})
        self.assertFalse(result.snapshot.comments)
        transport, _ = self.boundary([('delta-token', full(items=[])), ('full-token', delta())])
        replaced = retrieve(transport, result.binding, prior=result.snapshot, sync_token=result.sync_token)
        self.assertEqual(replaced.disappeared_ids, frozenset({'task'}))
        self.assertFalse(replaced.deleted_ids)
        self.assertFalse(replaced.snapshot.items)

    def test_later_tombstone_wins_live_without_live_fields(self):
        result = self.initial(full(notes=[note()], items=[item()]), delta(
            items=[{'id': 'task', 'is_deleted': True}],
            notes=[{'id': 'note', 'is_deleted': True}]))
        self.assertFalse(result.snapshot.items)
        self.assertFalse(result.snapshot.comments)
        result = self.initial(full(items=[item(), {'id': 'task', 'is_deleted': True}]))
        self.assertFalse(result.snapshot.items)

    def test_contradictory_live_duplicate_fails_but_later_delta_updates(self):
        for name, records in (('items', [item(), item(content='different')]),
                              ('projects', [project('root', None), project(), project(name='different')]),
                              ('notes', [note(), note(content='different')]),
                              ('reminders', [reminder(), reminder(minute_offset=1)])):
            transport, _ = self.boundary([('*', full(**{name: records}))])
            with self.assertRaisesRegex(DomainError, 'contradictory'):
                retrieve(transport, BINDING)
        result = self.initial(freshness=delta(items=[item(content='updated')]))
        self.assertEqual(result.snapshot.items['task'].title, 'updated')

    def test_full_required_resources_tokens_and_flag_strict(self):
        for field in ('user', 'user_plan_limits', 'projects', 'items', 'labels', 'notes', 'reminders',
                      'sync_token', 'full_sync'):
            response = full()
            response.pop(field)
            transport, _ = self.boundary([('*', response)])
            with self.assertRaises(DomainError):
                retrieve(transport, BINDING)
        for field, value in [('sync_token', ''), ('sync_token', '*'), ('sync_token', None),
                             ('sync_token', 1), ('full_sync', 1), ('full_sync', None),
                             ('full_sync', False), ('notes', {}), ('items', None)]:
            transport, _ = self.boundary([('*', full(**{field: value}))])
            with self.assertRaises(DomainError):
                retrieve(transport, BINDING)
        first = self.initial()
        for changes in ({'sync_token': ''}, {'full_sync': None}, {'items': {}}):
            transport, _ = self.boundary([('delta-token', delta(**changes))])
            with self.assertRaises(DomainError):
                retrieve(transport, first.binding, prior=first.snapshot, sync_token=first.sync_token)
        self.assertEqual(first.sync_token, 'delta-token')
        self.assertEqual(set(first.snapshot.items), {'task'})

    def test_server_full_and_client_replacement_are_bounded(self):
        first = self.initial(full(notes=[note()]))
        replacement = full(items=[item(content='new truth')])
        for explicit in (False, True):
            token = '*' if explicit else 'delta-token'
            transport, _ = self.boundary([(token, replacement), ('full-token', delta())])
            result = retrieve(transport, first.binding, prior=first.snapshot,
                              sync_token=first.sync_token, replace=explicit)
            self.assertEqual(result.snapshot.items['task'].title, 'new truth')
            self.assertFalse(result.snapshot.comments)  # Full omission is authoritative.
        transport, _ = self.boundary([('delta-token', replacement), ('full-token', full())])
        with self.assertRaisesRegex(DomainError, 'another full'):
            retrieve(transport, first.binding, prior=first.snapshot, sync_token=first.sync_token)
        transport, _ = self.boundary([('*', full()), ('full-token', full())])
        with self.assertRaisesRegex(DomainError, 'another full'):
            retrieve(transport, BINDING)

    def test_failures_do_not_trigger_guessed_token_recovery_or_mutate_prior(self):
        first = self.initial()
        original = deepcopy(snapshot_data(first.snapshot))
        for response, failure, text in (
            (Response(b'{"error":"invalid_token"}', status=401), Rejected, 'correct credentials'),
            (Response(b'{"error":"INVALID_SYNC_TOKEN"}', status=400), Rejected, '--clear-cache'),
            (TimeoutError(), TransportError, '--clear-cache'),
            (Response(b'not JSON'), ProtocolError, '--clear-cache')):
            with self.subTest(failure=failure):
                transport, _ = self.boundary([('delta-token', response)])
                with self.assertRaises(failure) as caught:
                    retrieve(transport, first.binding, prior=first.snapshot, sync_token=first.sync_token)
                self.assertIn('automatic sync-token recognition unavailable', str(caught.exception))
                self.assertIn(text, str(caught.exception))
                self.assertEqual(snapshot_data(first.snapshot), original)
                self.assertEqual(first.sync_token, 'delta-token')
        transport, _ = self.boundary([('*', full()), ('full-token', TimeoutError())])
        with self.assertRaises(TransportError):
            retrieve(transport, BINDING)

    def test_account_mismatch_in_freshness_and_no_prior_token_fail(self):
        transport, _ = self.boundary([('*', full()), ('full-token', delta(
            user={'id': 'other', 'tz_info': {'timezone': 'UTC'}}))])
        with self.assertRaisesRegex(DomainError, 'account'):
            retrieve(transport, BINDING)
        transport, _ = self.boundary([])
        with self.assertRaisesRegex(DomainError, 'prior Snapshot'):
            retrieve(transport, BINDING, sync_token='old-token')

    def test_known_unknown_creation_order_retains_exact_nanosecond(self):
        result = self.initial(full(items=[item('unknown', added_at=None), item('early'),
            item('late', added_at='2026-10-20T12:00:00.123456790Z')]))
        self.assertEqual([i.id for i in ordered_siblings(result.snapshot, 'cat', None)],
                         ['late', 'early', 'unknown'])

    def test_duplicate_live_values_do_not_coerce_boolean_to_integer(self):
        transport, _ = self.boundary([('*', full(items=[item(checked=0), item(checked=False)]))])
        with self.assertRaisesRegex(DomainError, 'contradictory'):
            retrieve(transport, BINDING)

    def test_completed_item_reopen_null_and_due_contract_omissions(self):
        first = self.initial(full(items=[item(checked=True, completed_at=STAMP)]))
        result = self.changed(first, delta(items=[item(checked=False, completed_at=None)]))
        self.assertFalse(result.snapshot.items['task'].completed)
        self.assertIsNone(result.snapshot.items['task'].completed_at)
        for field in ('date', 'string', 'lang', 'is_recurring'):
            raw_due = due()
            raw_due.pop(field)
            if field == 'date':
                raw_due['datetime'] = '2026-11-12T15:00:00Z'
            transport, _ = self.boundary([('*', full(items=[item(due=raw_due)])), ('full-token', delta())])
            with self.assertRaises(DomainError):
                retrieve(transport, BINDING)
        for priority in (0, 5, True, '4', None):
            transport, _ = self.boundary([('*', full(items=[item(priority=priority)])), ('full-token', delta())])
            with self.assertRaisesRegex(DomainError, 'priority'):
                retrieve(transport, BINDING)
        result = self.initial(full(items=[item(due=due(unknown={'private': 'value'}))]))
        self.assertNotIn('unknown', result.snapshot.items['task'].attention.raw_due)

    def test_reminder_tombstone_and_item_move_keep_own_identity(self):
        first = self.initial(full(items=[item(due=due()), item('child', parent_id='task')],
            notes=[note(owner='child')], reminders=[reminder()]))
        moved = self.changed(first, delta(items=[item('child', parent_id=None)]))
        self.assertEqual(moved.snapshot.comments['note'].item_id, 'child')
        self.assertEqual(moved.snapshot.reminders['reminder'].minutes, 0)
        result = self.changed(moved, delta(reminders=[{'id': 'reminder', 'is_deleted': True}]))
        self.assertFalse(result.snapshot.reminders)
        self.assertEqual(result.snapshot.comments['note'].item_id, 'child')

    def test_same_generation_offset_equivalent_instants_are_not_contradictions(self):
        result = self.initial(full(items=[item(), item(added_at='2026-10-20T14:00:00.123456789+02:00')],
            notes=[note(), note(posted_at='2026-10-20T14:00:00.123456789+02:00')]))
        self.assertEqual(instant_text(result.snapshot.items['task'].added_at), STAMP)
        self.assertEqual(instant_text(result.snapshot.comments['note'].added_at), STAMP)

    def test_hydration_retains_explicit_deleted_identity_evidence(self):
        first = self.initial()
        transport, _ = self.boundary([('delta-token', delta(items=[
            {'id': 'task', 'is_deleted': True}, item('entrant')])),
            ('*', full(items=[item('entrant')])), ('full-token', delta())])
        result = retrieve(transport, first.binding, prior=first.snapshot, sync_token=first.sync_token)
        self.assertEqual(result.deleted_ids, frozenset({'task'}))
        self.assertFalse(result.disappeared_ids)

    def test_hydration_retains_departure_until_explicit_item_supersedes_it(self):
        first = self.initial(full(notes=[note()]))
        for stage in ('omitted', 'full-return', 'freshness-return', 'deleted'):
            with self.subTest(stage=stage):
                replacement_items = [item('entrant')]
                freshness = delta()
                if stage == 'full-return':
                    replacement_items.append(item())
                elif stage == 'freshness-return':
                    freshness = delta(items=[item()])
                elif stage == 'deleted':
                    freshness = delta(items=[{'id': 'task', 'is_deleted': True}])
                transport, _ = self.boundary([('delta-token', delta(items=[
                    item(project_id='outside', content='private outgoing text'), item('entrant')])),
                    ('*', full(items=replacement_items)), ('full-token', freshness)])
                result = retrieve(transport, first.binding, prior=first.snapshot,
                                  sync_token=first.sync_token)
                self.assertFalse(result.disappeared_ids)
                self.assertEqual(result.departed_ids,
                                 frozenset({'task'}) if stage == 'omitted' else frozenset())
                self.assertEqual(result.deleted_ids,
                                 frozenset({'task'}) if stage == 'deleted' else frozenset())
                self.assertEqual('task' in result.snapshot.items, stage.endswith('return'))
                self.assertFalse(result.snapshot.comments)
                self.assertNotIn('private outgoing text', repr(result))
        self.assertIn('task', first.snapshot.items)
        self.assertIn('note', first.snapshot.comments)

    def test_managed_comment_ignores_attachment_metadata_after_ownership(self):
        first = self.initial(full(notes=[note()]))
        missing = note()
        missing.pop('file_attachment')
        for steps, prior in (([('*', full(notes=[missing])), ('full-token', delta())], None),
                             ([('delta-token', delta(notes=[missing]))], first)):
            with self.subTest(initial=prior is None):
                transport, _ = self.boundary(steps)
                result = retrieve(transport, BINDING, prior=prior.snapshot if prior else None,
                                  sync_token=prior.sync_token if prior else None)
                self.assertEqual(result.snapshot.comments['note'].body, 'own note')
        unrelated = dict(missing, id='private-note', item_id='outside', content={'secret': 1})
        result = self.initial(full(notes=[note(posted_at=None), unrelated,
                                          {'id': 'deleted-note', 'is_deleted': True}]))
        self.assertEqual(set(result.snapshot.comments), {'note'})
        self.assertIsNone(result.snapshot.comments['note'].added_at)
        unchanged = self.changed(result, delta())
        self.assertEqual(unchanged.snapshot.comments, result.snapshot.comments)

    def test_current_bound_project_departure_and_deletion_fail_closed(self):
        first = self.initial()
        for changed in (project(parent='outside'), project(is_shared=True),
                        {'id': 'root', 'is_deleted': True}):
            transport, _ = self.boundary([('delta-token', delta(projects=[changed]))])
            with self.assertRaises(DomainError):
                retrieve(transport, first.binding, prior=first.snapshot, sync_token=first.sync_token)
        self.assertEqual(first.binding, BINDING)

    def test_invalid_required_timestamp_cannot_equal_normalized_valid_duplicate(self):
        transport, _ = self.boundary([('*', full(items=[item(added_at='1'),
            item(added_at='1970-01-01T00:00:01Z')]))])
        with self.assertRaisesRegex(DomainError, 'contradictory'):
            retrieve(transport, BINDING)

    def test_invalid_arrivals_fail_without_hydration_replacement(self):
        first = self.initial()
        for response in (delta(projects=[project('new', is_shared=True)]),
                         delta(items=[item('entrant', checked=None)]),
                         delta(items=[item('entrant', description='\r')]),
                         delta(items=[item('entrant', added_at='invalid')])):
            transport, _ = self.boundary([('delta-token', response)])
            with self.assertRaises(DomainError):
                retrieve(transport, first.binding, prior=first.snapshot, sync_token=first.sync_token)

    def test_project_ownership_context_cannot_be_silently_missing(self):
        response = full()
        response['projects'].append({'id': 'unknown-context', 'shared': False})
        transport, _ = self.boundary([('*', response), ('full-token', delta())])
        with self.assertRaisesRegex(DomainError, 'parent_id'):
            retrieve(transport, BINDING)
