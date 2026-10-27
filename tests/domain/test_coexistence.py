"""Revision-8 coexistence distinctions using synthetic offline model state."""
import unittest
from dataclasses import replace
from todo_lib import domain as d
from todo_lib.local.codec import snapshot_data, snapshot_from
from todo_lib.workflows.moves import moved_snapshot
from tests.domain.test_model import snap, due, NOW


class CoexistenceTests(unittest.TestCase):
    def test_duplicate_reload_and_action_local_relationships(self):
        s = snap(d.Item('a', 'c', 'École'), d.Item('b', 'c', 'e\u0301COLE'),
                 d.Item('x', 'c', 'Other'))
        restored = snapshot_from(snapshot_data(d.validate(s)), s.account.timezone)
        self.assertEqual(set(restored.items), {'a', 'b', 'x'})
        for title in ('Unique', 'Other'):
            after = {**s.items, 'x': replace(s.items['x'], title=title)}
            d.validate_sibling_uniqueness(after.values(), s.items.values())
        resolving = {**s.items, 'a': replace(s.items['a'], title='Resolved')}
        d.validate_sibling_uniqueness(resolving.values(), s.items.values())
        for item in (replace(s.items['x'], title='École'), d.Item('new', 'c', 'École')):
            with self.assertRaises(d.DomainError):
                d.validate_sibling_uniqueness(({**s.items, item.id: item}).values(), s.items.values())
        done = replace(s.items['x'], title='École', completed=True, completed_at=NOW)
        d.validate_sibling_uniqueness(({**s.items, 'x': done}).values(), s.items.values())

    def test_reopen_restored_ancestors_and_unrelated_duplicates(self):
        s = snap(d.Item('a', 'c', 'Same'), d.Item('b', 'c', 'Same'),
                 d.Item('p', 'c', 'Parent', completed=True, completed_at=NOW),
                 d.Item('s', 'c', 'Step', 'p', completed=True, completed_at=NOW))
        self.assertEqual([i.id for i in d.reopen_chain(s, 's')], ['p', 's'])
        s = replace(s, items={**s.items, 'x': d.Item('x', 'c', 'parent')})
        with self.assertRaises(d.DomainError):
            d.reopen_chain(s, 's')

    def test_hidden_move_preserves_fields_and_existing_child_collision(self):
        parent = d.Item('p', 'c', 'Parent', attention=due('2026-10-24T13:00:00Z'),
                        labels=frozenset({'waiting', 'other'}), description='[todo waiting]')
        s = snap(parent, d.Item('a', 'c', 'Same', 'p'), d.Item('b', 'c', 'Same', 'p'),
                 reminders={'rem': d.Reminder('rem', 'p', 0)})
        s = replace(s, binding=replace(s.binding, category_ids=frozenset({'c', 'h'})),
                    categories={**s.categories, 'h': d.Category('h', 'Hidden', 'r')})
        result = moved_snapshot(s, parent, None, 'h', ['Hidden'])
        self.assertEqual(result.reminders, s.reminders)
        for item in s.items.values():
            self.assertEqual(result.items[item.id], replace(item, category_id='h'))
        self.assertEqual(d.now_queue(result, NOW, ['Hidden']), ())
        # A due date, even overdue, cannot override the category filter.
        overdue = replace(result, items={**result.items, 'p': replace(result.items['p'], attention=due('2026-10-22T13:00:00Z'))})
        self.assertEqual(d.now_queue(d.validate(overdue, ['Hidden']), NOW, ['Hidden']), ())

    def test_inactive_policy_and_literal_reasons_keep_ancestor_rule(self):
        p = d.Item('p', 'c', 'Parent', attention=due('tomorrow'), labels=frozenset({'waiting'}))
        child = d.Item('s', 'c', 'Step', 'p', labels=frozenset({'waiting'}), description='[todo waiting]')
        s = d.validate(snap(p, child))
        v = d.visibility(s, 's', NOW)
        self.assertFalse(v.own_hidden)
        self.assertTrue(v.ancestor_hidden)
        self.assertEqual(d.item_description(child), ('[todo waiting]', None))
        self.assertIn('inactive', d.convention_diagnostic(child))
        with self.assertRaises(d.DomainError):
            d.validate(replace(s, items={**s.items, 's': replace(child, attention=due('today'))}))
        canonical = d.with_waiting_reason('Body', 'why')
        self.assertEqual(d.item_description(replace(child, description=canonical)), (canonical, None))
        self.assertEqual(d.item_description(replace(p, description=canonical)), ('Body', 'why'))
        malformed = '[todo waiting]\nwhy\n[/todo waiting]\nextra'
        self.assertEqual(d.item_description(replace(p, description=malformed)), (malformed, None))
        with self.assertRaises(d.DomainError):
            d.with_waiting_reason(malformed, 'replacement')

    def test_unresolved_schedule_in_hidden_category_without_ancestor_policy(self):
        from todo_lib.workflows.scheduling import propose, validate_proposals
        from todo_lib.syntax import parse
        item = d.Item('a', 'c', 'A')
        s = snap(item)
        proposal = propose(parse(['schedule', 'A', '--at', 'next Christmas']), s, item, NOW)
        self.assertTrue(proposal.unresolved)
        validate_proposals(s, [proposal], ['Work'])

    def test_inbound_normalization_without_relaxing_cli_or_controls(self):
        s = d.validate(snap(d.Item('a', 'c', 'A\\B\r\nC\tD', description=' \r\n\t'),
                            comments={'n': d.Comment('n', 'a', '\r\n\t')}))
        self.assertEqual(s.items['a'].title, 'A\\B\nC\tD')
        self.assertEqual(s.items['a'].description, '')
        self.assertEqual(s.comments['n'].body, '\n\t')
        self.assertEqual(d.incoming_text('  body\r\nline\t ', description=True), '  body\nline\t ')
        self.assertEqual(d.scalar_title(s.items['a'].title), r'A\\B\nC\tD')
        for value in ('\r', '\x00', '\x1b', '\x85', 0, None):
            with self.subTest(value=value), self.assertRaises(d.DomainError):
                d.incoming_text(value, description=True)
        for value in ('A\nB', 'A\tB', 'A\r\nB'):
            with self.assertRaises(d.DomainError):
                d.validate_title(value)
        with self.assertRaises(d.DomainError):
            d.validate_body(' \n\t')
