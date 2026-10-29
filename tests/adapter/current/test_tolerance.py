"""Revision-8 consumed fields, using pinned API-v1 examples.

Source: docs/design/external/todoist/upstream/api-v1.openapi.json,
components.schemas.ItemSyncView.properties.due.examples[0] and
NoteSyncView.properties.content (default empty string); synthetic scope wrappers.
"""
import unittest
from copy import deepcopy
from todo_lib import domain as d
from todo_lib.adapter.current import retrieve, CurrentError
from todo_lib.adapter.commands import Gateway, Operation, due_arguments
from todo_lib.local.codec import snapshot_data, snapshot_from, dumps, loads
from tests.adapter.current import test_current as base


class ToleranceTests(unittest.TestCase):
    boundary = base.CurrentTests.boundary
    initial = base.CurrentTests.initial
    changed = base.CurrentTests.changed

    def test_default_blank_and_attachment_are_unconsumed_through_delta_codec(self):
        raw = dict(id='note', item_id='task', posted_at=base.STAMP, is_deleted=False)
        variants = [raw, dict(raw, content='', file_attachment={'file_url': 'synthetic'}),
                    dict(raw, file_attachment=False)]
        first = self.initial(base.full(notes=variants))
        self.assertEqual(first.snapshot.comments['note'].body, '')
        data = loads(dumps(snapshot_data(first.snapshot)))
        data['comments']['note']['file_attachment'] = {'ignored': True}
        restored = snapshot_from(data, first.account.timezone)
        transport, _ = self.boundary([('delta-token', base.delta())])
        again = retrieve(transport, restored.binding, prior=restored, sync_token='delta-token')
        self.assertEqual(again.snapshot.comments, first.snapshot.comments)
        self.assertNotIn(b'file_attachment', dumps(snapshot_data(again.snapshot)))
        normalized = self.initial(base.full(notes=[dict(raw, content='a\r\nb'), dict(raw, content='a\nb')]))
        self.assertEqual(normalized.snapshot.comments['note'].body, 'a\nb')
        for content in (' \t\r\n', 'a\r\nb'):
            result = self.changed(again, base.delta(notes=[dict(raw, content=content)]))
            self.assertEqual(result.snapshot.comments['note'].body, content.replace('\r\n', '\n'))
        for content in (None, 12, '\x00', '\r'):
            with self.subTest(content=content), self.assertRaises(d.DomainError):
                self.initial(base.full(notes=[dict(raw, content=content)]))

    def test_unchanged_official_due_example_and_required_negatives(self):
        due = {'date': '2025-02-12', 'is_recurring': False, 'lang': 'en', 'string': 'tomorrow'}
        value = self.initial(base.full(items=[base.item(due=due)])).snapshot.items['task'].attention
        self.assertIsNone(value.zone)
        for changes in ({'timezone': 'invalid/zone'}, {'timezone': 5}, {'date': 'bad'}, {'is_recurring': None}):
            with self.subTest(changes=changes), self.assertRaises(d.DomainError):
                self.initial(base.full(items=[base.item(due={**due, **changes})]))
        for key in ('date', 'lang', 'string', 'is_recurring'):
            invalid = deepcopy(due); del invalid[key]
            with self.subTest(missing=key), self.assertRaises(d.DomainError):
                self.initial(base.full(items=[base.item(due=invalid)]))

    def test_irrelevant_duplicates_ignore_bodies_but_unknown_context_fails(self):
        result = self.initial(base.full(items=[base.item(),
            dict(id='private', project_id='outside', content=123),
            dict(id='private', project_id='outside', content={})],
            notes=[dict(id='dead', is_deleted=True)],
            projects=[base.project('root', None), base.project(),
                      dict(id='other', parent_id=None, name=123),
                      dict(id='other', parent_id=None, name={})]))
        self.assertEqual(set(result.snapshot.items), {'task'})
        for context in ({}, {'project_id': []}, {'project_id': None}):
            with self.subTest(context=context), self.assertRaises(d.DomainError):
                self.initial(base.full(items=[base.item(), dict(id='unknown', content=123, **context)]))
        first = self.initial(base.full(notes=[base.note()]))
        gone = self.changed(first, base.delta(notes=[dict(id='note', is_deleted=True)]))
        self.assertFalse(gone.snapshot.comments)

    def test_real_wrappers_preserve_non_english_recurrence(self):
        due = dict(date='2026-11-12T15:00:00Z', timezone='Europe/Prague',
                   string='jeden Tag', lang='de', is_recurring=True)
        previous = d.resolve_remote_due(due, 'Europe/Prague')
        proposal = d.parse_attention('2026-11-13T15:00:00Z', d.instant_datetime(d.instant_from_wire(base.STAMP)), 'Europe/Prague')
        class Capture(Gateway):
            def execute(self, operation, **context):
                return operation
        g = Capture(None)
        prior = self.initial(base.full(items=[base.item(due=due)]))
        for op in (g.update_task('task', attention=proposal, before=prior),
                   g.complete('task', attention=proposal, before=prior),
                   g.reopen('task', attention=proposal, before=prior)):
            wire = op.command()['args']['due']
            self.assertEqual((wire['string'], wire['lang'], wire['is_recurring'], wire['timezone']),
                             ('jeden Tag', 'de', True, 'Europe/Prague'))
        from tests.adapter.commands.test_commands import Wire
        next_due = {**due, 'date': '2026-11-13T15:00:00Z'}
        wire = Wire(self, 'item_update', {'id': 'task', 'due': next_due},
                    [base.delta(items=[base.item(due=next_due)])], token='delta-token')
        self.addCleanup(wire.done)
        result = Gateway(wire).update_task('task', attention=proposal, before=prior)
        self.assertTrue(result.accepted)
        self.assertFalse(result.issues)
        new = due_arguments(d.parse_attention('every Friday', d.instant_datetime(d.instant_from_wire(base.STAMP)), 'UTC'))
        self.assertEqual(Operation('item_update', {'id': 'task', 'due': new}).command()['args']['due']['lang'], 'en')
