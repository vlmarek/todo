"""Literal titles and waiting convention display, without selector rewriting."""
import unittest
from dataclasses import replace
from todo_lib import domain as d, presentation as p
from todo_lib.presentation.report import ReportEvent
from tests.domain.test_model import snap, due, NOW


class CoexistenceTests(unittest.TestCase):
    def test_all_title_surfaces_are_scalar_and_matching_stays_literal(self):
        root = d.Item('r', 'c', 'Root\\name\nnext\ttab')
        child = d.Item('s', 'c', 'Child\\name\nnext\ttab', 'r')
        s = snap(root, child)
        expected = r'Child\\name\nnext\ttab'
        ancestor = r'Root\\name\nnext\ttab'
        docs = [p.render_now(s, NOW), p.render_detail(s, child, NOW),
                p.render_comments(s, child), p.render_search(s, [child]),
                p.render_someday(s, hidden_names=['Work']),
                p.render_ambiguity(s, 'name', [root, child], NOW),
                p.render_mutation(s, child, 'Completed'),
                p.render_move(s, child, replace(s, items={**s.items, 's': replace(child, parent_id=None)}), replace(child, parent_id=None)),
                p.render_report(s, NOW, NOW, progress=[ReportEvent(child.id, NOW)])]
        for doc in docs:
            with self.subTest(doc=doc.stdout):
                self.assertIn(expected, doc.stdout)
                self.assertNotIn(child.title, doc.stdout)
        from todo_lib.presentation.formatting import ancestor_path
        self.assertEqual(ancestor_path(s, child), ancestor)
        changed = p.render_mutation(s, child, changes=[('Title', root.title, child.title)])
        self.assertIn('Title: ' + ancestor + ' -> ' + expected, changed.stdout)
        from todo_lib.workflows.reads import title_candidates
        self.assertEqual([i.id for i in title_candidates(s, 'Child\\name\nnext')], ['s'])
        self.assertEqual(title_candidates(s, expected), ())

    def test_inactive_and_literal_detail_diagnostics_with_inherited_policy(self):
        literal = '[todo waiting]\nwhy\n[/todo waiting]'
        item = d.Item('s', 'c', 'Owner\nline', labels=frozenset({'waiting'}), description=literal)
        s = snap(item)
        doc = p.render_detail(s, item, NOW)
        self.assertIn('Waiting: inactive (no attention date)', doc.stdout)
        self.assertIn('Description\n  [todo waiting]', doc.stdout)
        self.assertNotIn('Reason:', doc.stdout)
        self.assertIn(r'Owner\nline', doc.stderr)
        self.assertIn('literal', doc.stderr)
        parent = d.Item('p', 'c', 'Parent\ttab', attention=due('tomorrow'), labels=frozenset({'waiting'}))
        item = replace(item, parent_id='p')
        doc = p.render_detail(snap(parent, item), item, NOW)
        self.assertIn('Waiting: inactive (no attention date)', doc.stdout)
        self.assertIn(r'Waiting: inherited from Parent\ttab', doc.stdout)

    def test_hidden_category_populations_and_valid_reasonless_policy(self):
        item = d.Item('a', 'c', 'Overdue', attention=due('2026-10-22'))
        waiting = d.Item('w', 'c', 'Future', attention=due('tomorrow'), labels=frozenset({'waiting'}))
        s = d.validate(snap(item, waiting), ['Work'])
        self.assertEqual(p.render_now(s, NOW, hidden_names=['Work']).stdout, 'No actionable items.')
        self.assertIn('Overdue', p.render_now(s, NOW, hidden_names=['Work'], all_items=True).stdout)
        self.assertIn('Overdue', p.render_someday(s, hidden_names=['Work']).stdout)
        self.assertIn('Overdue', p.render_search(s, [item]).stdout)
        self.assertEqual(p.render_waiting(s, NOW, hidden_names=['Work']).stdout, 'No waiting items.')
        self.assertIn('Waiting: enabled', p.render_detail(s, waiting, NOW).stdout)
        self.assertIn('Future', p.render_waiting(s, NOW).stdout)
        from types import SimpleNamespace
        from todo_lib.workflows.report import _select
        empty = SimpleNamespace(records=())
        self.assertEqual(_select(s, empty, empty, NOW, NOW, ['Work'])[2], [])
        self.assertEqual([i.id for i in _select(s, empty, empty, NOW, NOW, [])[2]], ['w'])
