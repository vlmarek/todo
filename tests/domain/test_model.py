import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from todo_lib.domain import *

NOW = datetime(2026, 10, 23, 8, tzinfo=timezone.utc)
ZONE = 'Europe/Prague'


def due(text):
    return parse_attention(text, NOW, ZONE)


def snap(*items, **kwargs):
    base = Snapshot(Binding('a', 'r', frozenset({'c'})), Account('a', ZONE, Capabilities(reminders=True)),
                    Project('r', 'Root'), {'c': Category('c', 'Work', 'r')}, {i.id: i for i in items})
    return replace(base, **kwargs)


class ModelTests(unittest.TestCase):
    def test_exact_instants_order_lifecycle_and_validation(self):
        early = instant_from_wire('2026-10-23T08:00:00.123456001Z')
        late = instant_from_wire('2026-10-23T08:00:00.123456999Z')
        s = snap(Item('a', 'c', 'Early', added_at=early),
                 Item('z', 'c', 'Late', added_at=late), Item('null', 'c', 'Unknown'))
        validate(s)
        self.assertEqual([i.id for i in ordered_siblings(s, 'c')], ['z', 'a', 'null'])
        tree = snap(Item('root', 'c', 'Root'),
                    replace(s.items['a'], parent_id='root'), replace(s.items['z'], parent_id='root'))
        self.assertEqual([i.id for i in subtree(tree, 'root')], ['root', 'z', 'a'])
        self.assertEqual([i.id for i in completion_order(tree, 'root')], ['z', 'a', 'root'])
        done = replace(s, items={k: replace(v, completed=True, completed_at=v.added_at)
                               for k, v in s.items.items() if k != 'null'})
        cursor = instant_from_wire('2026-10-23T08:00:00.123456500Z')
        for helper in (recent_reopen_candidates, completed_deletion_candidates):
            self.assertEqual([c.item_id for c in helper(done, cursor, late)], ['z'])
            self.assertEqual([c.item_id for c in helper(done, NOW, late)], ['a', 'z'])
        recurring = snap(Item('r', 'c', 'Recurring', attention=due('every day')),
                         occurrences={'z': Occurrence('z', 'r', early, True),
                                      'a': Occurrence('a', 'r', late, True, True)})
        self.assertEqual(recent_reopen_candidates(recurring, NOW, late), ())
        for bad in ('2026-10-23T08:00:00Z', datetime(2026, 1, 1), 42):
            with self.subTest(bad=bad), self.assertRaisesRegex(DomainError, 'item.added_at'):
                validate(snap(Item('x', 'c', 'X', added_at=bad)))
            with self.assertRaises(DomainError):
                validate(snap(Item('x', 'c', 'X'), occurrences={'o': Occurrence('o', 'x', bad)}))
        with self.assertRaises(DomainError):
            validate(snap(Item('x', 'c', 'X'), occurrences={'o': Occurrence('o', 'x', None)}))

    def test_out_of_order_depth_four_roles_and_traversal(self):
        items = [Item(str(n), 'c', str(n), str(n - 1) if n else None) for n in range(5)]
        s = snap(*reversed(items))
        self.assertIs(validate(s), s)
        self.assertEqual(hierarchy_depths(s), {'0': 0, '1': 1, '2': 2, '3': 3, '4': 4})
        self.assertEqual([i.id for i in ancestors(s, '4')], ['0', '1', '2', '3'])
        self.assertEqual([i.id for i in subtree(s, '0')], ['0', '1', '2', '3', '4'])
        self.assertEqual(subtree_depths(s, '3'), {'3': 3, '4': 4})
        self.assertEqual(root_task(s, '4').id, '0')
        self.assertEqual(items[4].role, 'step')
        self.assertEqual(replace(items[4], parent_id=None).role, 'task')
        self.assertIsNone(s.items['4'].added_at)

    def test_invalid_graphs(self):
        cases = [snap(Item('a', 'c', 'a', 'missing')),
                 snap(Item('a', 'c', 'a', 'b'), Item('b', 'c', 'b', 'a')),
                 snap(Item('a', 'r', 'a')),
                 snap(Item('a', 'c', 'a', completed=True, completed_at=NOW), Item('b', 'c', 'b', 'a')),
                 snap(*(Item(str(n), 'c', str(n), str(n - 1) if n else None) for n in range(6)))]
        cross = snap(Item('a', 'c', 'a'), Item('b', 'd', 'b', 'a'))
        cases.append(replace(cross, binding=replace(cross.binding, category_ids=frozenset({'c', 'd'})),
                             categories={'c': cross.categories['c'], 'd': Category('d', 'Other', 'r')}))
        for s in cases:
            with self.subTest(s=s), self.assertRaises(DomainError):
                validate(s)
        # Long cycle must fail safely rather than hit recursion depth.
        s = snap(*(Item(str(n), 'c', str(n), str((n + 1) % 1500)) for n in range(1500)))
        with self.assertRaisesRegex(DomainError, 'cycle'):
            hierarchy_depths(s)

    def test_stable_scope_identity_and_enrollment(self):
        s = snap(Item('a', 'c', 'a'))
        self.assertIs(validate(replace(s, root=replace(s.root, name='Renamed'))).items, s.items)
        with self.assertRaisesRegex(DomainError, 'stable ID'):
            validate(replace(s, root=Project('replacement', 'Root')))
        self.assertEqual(bind_root('a', [s.root], 'Root').root_id, 'r')
        with self.assertRaises(DomainError):
            bind_root('a', [s.root], 'root')
        self.assertEqual(lookup_category(s, 'wOrK').id, 'c')
        for bad in (replace(s.root, shared=True), replace(s.root, workspace_id='w'),
                    replace(s.root, personally_owned=False), replace(s.root, archived=True),
                    replace(s.root, deleted=True), replace(s.root, parent_id='elsewhere')):
            with self.assertRaises(DomainError):
                validate(replace(s, root=bad))
        with self.assertRaises(DomainError):
            enroll_categories(s.binding, s.root, {}, s.items)
        self.assertEqual(enroll_categories(s.binding, s.root, {}, {}).category_ids, frozenset())
        categories = {**s.categories, 'd': Category('d', 'New', 'r')}
        enrolled = enroll_categories(s.binding, s.root, categories, s.items)
        self.assertEqual(enrolled.category_ids, frozenset({'c', 'd'}))
        with self.assertRaises(DomainError):
            validate(replace(s, binding=enrolled, categories={**s.categories, 'd': Category('d', 'WORK', 'r')}))

    def test_active_uniqueness_unicode_and_completed_reuse(self):
        a = Item('a', 'c', 'École')
        b = Item('b', 'c', 'e\u0301COLE')
        validate(snap(a, b))
        with self.assertRaises(DomainError):
            validate_sibling_uniqueness((a, b))
        done = replace(b, completed=True, completed_at=NOW)
        validate(snap(a, done, replace(done, id='d')))
        validate(snap(a, replace(b, parent_id='a')))
        with self.assertRaises(DomainError):
            reopen_chain(snap(a, done), 'b')
        self.assertEqual(a.title, 'École')

    def test_creation_order_known_precision_and_unknown(self):
        s = snap(Item('z', 'c', 'z'), Item('b', 'c', 'b'),
                 Item('a', 'c', 'a', added_at=NOW),
                 Item('d', 'c', 'd', added_at=NOW + timedelta(microseconds=1)))
        validate(s)
        self.assertEqual([i.id for i in ordered_siblings(s, 'c')], ['d', 'a', 'b', 'z'])
        self.assertIsNone(s.items['b'].added_at)
        with self.assertRaisesRegex(DomainError, 'aware'):
            validate(snap(Item('a', 'c', 'a', added_at=NOW.replace(tzinfo=None))))

    def test_effective_copy_but_own_now_rank(self):
        parent = Item('p', 'c', 'parent', priority=4)
        child = Item('c1', 'c', 'child', 'p', priority=3)
        grandchild = Item('g', 'c', 'grand', 'c1', priority=1, attention=due('today'))
        other = Item('o', 'c', 'other', priority=2)
        s = snap(parent, child, grandchild, other)
        validate(s)
        self.assertEqual(effective_priority(s, 'p'), 1)
        self.assertEqual(creation_priority(s, 'c1'), 1)
        self.assertEqual(creation_priority(s), 2)
        self.assertEqual(effective_attention(s, 'p'), grandchild.attention)
        self.assertEqual([i.id for i in now_queue(s, NOW)], ['g', 'o', 'c1', 'p'])
        done = replace(grandchild, completed=True, completed_at=NOW)
        s2 = snap(parent, child, done)
        self.assertEqual(effective_priority(s2, 'p'), 3)
        self.assertIsNone(effective_attention(s2, 'p'))

    def test_urgency_exact_equality_calendar_limits(self):
        for expression, expected in [('2026-10-23T07:59:59Z', Urgency.OVERDUE),
                                     ('2026-10-23T08:00:00Z', Urgency.TODAY),
                                     ('2026-10-23T08:00:01Z', Urgency.TODAY),
                                     ('2026-10-22', Urgency.OVERDUE), ('2026-10-23', Urgency.TODAY),
                                     ('2026-10-30', Urgency.NEXT_7_DAYS), ('2026-10-31', Urgency.LATER)]:
            with self.subTest(expression=expression):
                self.assertEqual(urgency(Item('a', 'c', 'a', attention=due(expression)), NOW, ZONE), expected)
        self.assertEqual(urgency(Item('a', 'c', 'a'), NOW, ZONE), Urgency.NO_DATE)
        # +7 calendar days spans fall-back and is longer than 168 hours.
        self.assertEqual(urgency(Item('a', 'c', 'a', attention=due('2026-10-30T22:59:59Z')), NOW, ZONE), Urgency.NEXT_7_DAYS)

    def test_now_sort_own_keys_and_date_start(self):
        s = snap(Item('late', 'c', 'late', priority=1, attention=due('2026-11-01')),
                 Item('no', 'c', 'no', priority=1),
                 Item('over', 'c', 'over', priority=4, attention=due('2026-10-22')),
                 Item('b', 'c', 'same', attention=due('today')),
                 Item('a', 'c', 'Same', attention=due('today'), parent_id='no'),
                 Item('timed', 'c', 'aaa', attention=due('2026-10-23T09:00:00Z')))
        self.assertEqual([i.id for i in now_queue(s, NOW)], ['over', 'a', 'b', 'timed', 'no', 'late'])

    def test_hiding_union_day_not_time_and_optional_reason(self):
        parent = Item('p', 'c', 'p', attention=due('tomorrow'), labels=frozenset({'waiting'}))
        child = Item('s', 'c', 's', 'p')
        sibling = Item('o', 'c', 'o')
        s = snap(parent, child, sibling)
        validate(s)
        self.assertEqual(visibility(s, 's', NOW).ancestor_hidden, True)
        self.assertFalse(visibility(s, 'o', NOW).own_hidden)
        self.assertEqual([i.id for i in now_queue(s, NOW)], ['o'])
        # Midnight local makes policy visible even with a later exact time.
        p = replace(parent, attention=due('2026-10-24T18:00:00Z'))
        s = snap(p, child)
        midnight = datetime(2026, 10, 23, 22, tzinfo=timezone.utc)
        self.assertTrue(visibility(s, 'p', midnight).actionable)
        self.assertTrue(visibility(s, 's', midnight).actionable)
        validate(s)  # expired waiting label remains valid
        with self.assertRaisesRegex(DomainError, 'future'):
            validate_hiding_enable(s, 'p', midnight)
        validate_hiding_enable(s, 'p', NOW)
        # Step's own hiding never hides parent.
        s = snap(Item('p', 'c', 'p'), replace(parent, id='s', parent_id='p'))
        self.assertTrue(visibility(s, 'p', NOW).actionable)

    def test_hiding_ancestor_and_category_invariants(self):
        parent = Item('p', 'c', 'p', attention=due('tomorrow'), labels=frozenset({'waiting'}))
        for child_due in ('today', '2026-10-23T20:00:00Z'):
            with self.assertRaisesRegex(DomainError, 'ancestor'):
                validate(snap(parent, Item('c1', 'c', 'c1', 'p', attention=due(child_due))))
        validate(snap(parent, Item('c1', 'c', 'c1', 'p', attention=due('2026-10-24T01:00:00Z'))))
        for item in (Item('a', 'c', 'a', labels=frozenset({'waiting'})),
                     Item('a', 'c', 'a', description='[todo waiting]\nreason\n[/todo waiting]')):
            validate(snap(item))
        s = snap(parent)
        self.assertTrue(visibility(s, 'p', NOW, ['Work']).category_hidden)
        self.assertFalse(visibility(s, 'p', NOW, ['work']).category_hidden)
        validate(s, ['Work'])
        validate(s, [])
        validate(snap(Item('a', 'c', 'a')), ['Work'])

    def test_reminders_comments_and_raw_attention_validation(self):
        item = Item('a', 'c', 'a', attention=due('2026-10-23T08:00:00Z'))
        s = snap(item, reminders={'r0': Reminder('r0', 'a', 0)}, comments={'c0': Comment('c0', 'a', 'body')})
        validate(s)
        for bad in (replace(s, reminders={'r0': Reminder('r0', 'a', True)}),
                    replace(s, account=replace(s.account, capabilities=Capabilities())),
                    replace(s, comments={'c0': Comment('c0', 'missing', 'body')}),
                    replace(s, items={'a': replace(item, attention=due('today'))})):
            with self.assertRaises(DomainError):
                validate(bad)
        raw = resolve_remote_due({'date': '2026-10-25T02:30:00.123456789'}, ZONE)
        validate(snap(replace(item, attention=raw)))
        with self.assertRaisesRegex(DomainError, 'raw due'):
            validate(snap(replace(item, attention=replace(raw, raw_due={'date': '2026-10-26T02:30:00'}))))

    def test_completion_and_reopen_chain(self):
        s = snap(Item('p', 'c', 'p'), Item('s', 'c', 's', 'p'), Item('g', 'c', 'g', 's'))
        self.assertEqual([i.id for i in completion_order(s, 'p')], ['g', 's', 'p'])
        recurring = resolve_remote_due({'date': '2026-10-24', 'is_recurring': True, 'string': 'every day'}, ZONE)
        with self.assertRaisesRegex(DomainError, 'recurring descendant'):
            completion_order(snap(s.items['p'], replace(s.items['s'], attention=recurring)), 'p')
        self.assertEqual([i.id for i in completion_order(snap(replace(s.items['p'], attention=recurring)), 'p')], ['p'])
        completed = [replace(i, completed=True, completed_at=NOW) for i in s.items.values()]
        done = snap(*completed)
        validate(done)
        self.assertEqual([i.id for i in reopen_chain(done, 'g')], ['p', 's', 'g'])
        with self.assertRaises(DomainError):
            require_editable(completed[0])
        # Finishing the last child does not change its open parent.
        validate(snap(s.items['p'], replace(s.items['s'], completed=True, completed_at=NOW)))

    def test_recent_lifecycle_interval_latest_and_survival(self):
        cursor = NOW - timedelta(days=1)
        recurring = resolve_remote_due({'date': '2026-10-24', 'is_recurring': True, 'string': 'every day'}, ZONE)
        items = [Item('r', 'c', 'recurring', attention=recurring),
                 Item('at', 'c', 'at', completed=True, completed_at=NOW),
                 Item('before', 'c', 'before', completed=True, completed_at=cursor),
                 Item('future', 'c', 'future', completed=True, completed_at=NOW + timedelta(seconds=1))]
        events = {'e0': Occurrence('e0', 'r', cursor + timedelta(hours=1), recurring=True),
                  'e1': Occurrence('e1', 'r', NOW, recurring=True)}
        s = snap(*items, occurrences=events)
        validate(s)
        self.assertEqual({(c.item_id, c.occurrence_id) for c in recent_reopen_candidates(s, cursor, NOW)}, {('r', 'e1'), ('at', None)})
        self.assertEqual([c.item_id for c in completed_deletion_candidates(s, cursor, NOW)], ['at'])
        undone = replace(s, occurrences={**events, 'e1': replace(events['e1'], undone=True)})
        self.assertEqual([c.item_id for c in recent_reopen_candidates(undone, cursor, NOW)], ['at'])
        with self.assertRaises(DomainError):
            validate(replace(s, occurrences={'lost': Occurrence('lost', 'deleted', NOW)}))

    def test_completion_postorder_preserves_inspection_siblings(self):
        s = snap(Item('p', 'c', 'parent'),
                 Item('b', 'c', 'unknown child', 'p'),
                 Item('a', 'c', 'known child', 'p', added_at=NOW),
                 Item('g', 'c', 'grandchild', 'a'),
                 Item('done', 'c', 'completed', 'a', completed=True, completed_at=NOW))
        validate(s)
        self.assertEqual([i.id for i in ordered_siblings(s, 'c', 'p')], ['a', 'b'])
        order = completion_order(s, 'p')
        self.assertEqual([i.id for i in order], ['g', 'a', 'b', 'p'])
        # Apply the proposed operations in order: every intermediate model is valid.
        for item in order:
            s = replace(s, items={**s.items, item.id: replace(item, completed=True, completed_at=NOW)})
            validate(s)
        self.assertTrue(all(i.completed for i in s.items.values()))

    def test_lifecycle_overlap_uses_instants_and_preserves_supplied_times(self):
        zone = ZoneInfo(ZONE)
        cursor = datetime(2026, 10, 25, 2, 15, tzinfo=zone, fold=0)
        early = datetime(2026, 10, 25, 2, 50, tzinfo=zone, fold=0)
        late = datetime(2026, 10, 25, 2, 10, tzinfo=zone, fold=1)
        now = datetime(2026, 10, 25, 2, 45, tzinfo=zone, fold=1)
        recurring = resolve_remote_due({'date': '2026-10-26', 'is_recurring': True, 'string': 'every day'}, ZONE)
        s = snap(Item('late', 'c', 'late', completed=True, completed_at=late),
                 Item('early', 'c', 'early', completed=True, completed_at=early),
                 Item('cursor', 'c', 'cursor', completed=True, completed_at=cursor),
                 Item('now', 'c', 'now', completed=True, completed_at=now),
                 Item('r', 'c', 'recurring', attention=recurring),
                 occurrences={'old': Occurrence('old', 'r', early, recurring=True),
                              'latest': Occurrence('latest', 'r', late, recurring=True)})
        validate(s)
        reopened = recent_reopen_candidates(s, cursor, now)
        self.assertEqual([(c.item_id, c.occurrence_id) for c in reopened],
                         [('early', None), ('late', None), ('r', 'latest'), ('now', None)])
        self.assertIs(reopened[1].completed_at, late)
        self.assertEqual([c.item_id for c in completed_deletion_candidates(s, cursor, now)],
                         ['early', 'late', 'now'])
        # Undoing the true latest event must not expose the older fold's occurrence.
        undone = replace(s, occurrences={**s.occurrences, 'latest': replace(s.occurrences['latest'], undone=True)})
        self.assertEqual([c.item_id for c in recent_reopen_candidates(undone, cursor, now)],
                         ['early', 'late', 'now'])
        # Wall-clock order is reversed but this absolute interval is valid.
        self.assertEqual([c.item_id for c in completed_deletion_candidates(s, early, late)], ['late'])
        for select in (recent_reopen_candidates, completed_deletion_candidates):
            with self.assertRaisesRegex(DomainError, 'cursor'):
                select(s, late, early)

    def test_malformed_own_fields_raise_domain_errors(self):
        base = Item('a', 'c', 'a')
        for item in (replace(base, priority=True), replace(base, priority=5),
                     replace(base, labels='waiting'), replace(base, completed=True),
                     replace(base, attention=due('every Tuesday')),
                     replace(base, parent_id=3), replace(base, category_id=None)):
            with self.subTest(item=item), self.assertRaises(DomainError):
                validate(snap(item))
        s = snap(base)
        for bad in (replace(s, items={'a': object()}),
                    replace(s, items={'wrong': base}),
                    replace(s, root=replace(s.root, shared=None))):
            with self.assertRaises(DomainError):
                validate(bad)

    def test_move_known_subtree_depth(self):
        s = snap(*(Item(str(n), 'c', str(n), str(n - 1) if n else None) for n in range(5)), Item('other', 'c', 'other'))
        validate_move_depth(s, '0', None)
        with self.assertRaisesRegex(DomainError, 'depth'):
            validate_move_depth(s, '0', 'other')
        with self.assertRaisesRegex(DomainError, 'cycle'):
            validate_move_depth(s, '1', '4')


class TextTests(unittest.TestCase):
    def test_titles_and_bodies_reject_every_forbidden_control(self):
        self.assertEqual(validate_title('  Hello  '), 'Hello')
        self.assertEqual(validate_body(' \nHello\tworld\n '), 'Hello\tworld')
        for n in (*range(32), *range(127, 160)):
            with self.subTest(n=n), self.assertRaises(DomainError):
                validate_title('a' + chr(n) + 'b')
            if n not in (9, 10):
                with self.subTest(body=n), self.assertRaises(DomainError):
                    validate_body('a' + chr(n) + 'b')
        for text in ('', '  ', '\n\t'):
            with self.assertRaises(DomainError):
                validate_body(text)

    def test_optional_block_roundtrip_and_preserved_text(self):
        ordinary = 'Line one\nLine two  '
        result = with_waiting_reason(ordinary, '  Why\nMore  ')
        self.assertEqual(result, ordinary + '\n\n[todo waiting]\nWhy\nMore\n[/todo waiting]')
        self.assertEqual(split_waiting(result), (ordinary, 'Why\nMore'))
        self.assertEqual(with_waiting_reason(result, None), ordinary)
        self.assertEqual(split_waiting(''), ('', None))
        self.assertEqual(split_waiting('text [todo waiting]'), ('text [todo waiting]', None))
        self.assertEqual(split_waiting(with_waiting_reason('', 'why')), ('', 'why'))
        self.assertEqual(with_waiting_reason('body\n\n', 'why'), 'body\n\n[todo waiting]\nwhy\n[/todo waiting]')

    def test_malformed_blocks(self):
        for text in ('[todo waiting]', '[/todo waiting]', '[todo waiting]\n[/todo waiting]',
                     '[todo waiting]\n \n[/todo waiting]', '[todo waiting]\nwhy\n[/todo waiting]\n',
                     'body\n[todo waiting]\nwhy\n[/todo waiting]',
                     'body\n\n\n[todo waiting]\nwhy\n[/todo waiting]',
                     '[todo waiting]\nwhy\n[/todo waiting]\nother',
                     '[todo waiting]\n[todo waiting]\nwhy\n[/todo waiting]',
                     '[todo waiting]\n why \n[/todo waiting]'):
            with self.subTest(text=text):
                self.assertEqual(split_waiting(text), (text, None))
                with self.assertRaises(DomainError):
                    with_waiting_reason(text, 'new')
        for reason in ('[todo waiting]', 'x\n[/todo waiting]', ''):
            with self.assertRaises(DomainError):
                with_waiting_reason('', reason)
