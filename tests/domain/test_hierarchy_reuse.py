import unittest
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import patch

from todo_lib import domain as d, presentation as p
from todo_lib.domain import model
from todo_lib.workflows.reads import title_candidates


def snapshot(items):
    return d.Snapshot(d.Binding('a', 'r', frozenset({'c'})), d.Account('a', 'UTC'),
        d.Project('r', 'Root'), {'c': d.Category('c', 'Work', 'r')},
        {i.id: i for i in items})


class TraversalReuse(unittest.TestCase):
    def test_descendant_closure_handles_missing_roots_cycles_and_multiple_edges(self):
        graph = [d.Item('a', 'c', 'A', 'missing'),
                 d.Item('b', 'c', 'B', 'a'), d.Item('a', 'c', 'A', 'b'),
                 d.Item('other', 'c', 'Other')]
        self.assertEqual(d.descendant_ids(graph, {'missing'}), {'missing', 'a', 'b'})
        self.assertEqual(d.descendant_ids(graph, {'b'}), {'a', 'b'})
        self.assertEqual(d.descendant_ids(graph, {'absent'}), {'absent'})

    def test_large_queue_and_selection_do_not_revalidate_per_row(self):
        now = datetime(2026, 10, 23, tzinfo=timezone.utc)
        s = snapshot([d.Item('root', 'c', 'Root')] +
                     [d.Item(str(n), 'c', 'Step', 'root', labels=frozenset({'waiting'}))
                      for n in range(1000)])
        for operation in (lambda: d.now_queue(s, now),
                          lambda: title_candidates(s, ('Step',)),
                          lambda: p.render_now(s, now),
                          lambda: p.render_detail(s, 'root', now)):
            with self.subTest(operation=operation), patch.object(
                    model, 'hierarchy_depths', wraps=model.hierarchy_depths) as validate:
                operation()
                self.assertLessEqual(validate.call_count, 2)

    def test_public_helpers_reject_invalid_unrelated_graph(self):
        s = snapshot([d.Item('ok', 'c', 'OK'), d.Item('bad', 'c', 'Bad', 'missing')])
        for operation in (lambda: d.ancestors(s, 'ok'), lambda: d.subtree(s, 'ok'),
                          lambda: d.subtree_depths(s, 'ok')):
            with self.assertRaisesRegex(d.DomainError, 'orphan'):
                operation()

    def test_index_does_not_follow_mutated_snapshot_dictionary(self):
        s = snapshot([d.Item('root', 'c', 'Root'), d.Item('child', 'c', 'Child', 'root')])
        index = d.Hierarchy(s)
        s.items['child'] = replace(s.items['child'], parent_id=None)
        self.assertEqual([i.id for i in index.ancestors('child')], ['root'])
        self.assertEqual(d.ancestors(s, 'child'), ())
