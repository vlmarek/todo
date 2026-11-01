import shlex
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from todo_lib.domain import parse_boundary
from todo_lib.syntax import parse, UsageError, HelpRequest, render_help


class GrammarTests(unittest.TestCase):
    def test_alias_equivalence(self):
        cases = [
            (['close', 'Release', 'Reviewed'], ['done', 'Release', 'Reviewed']),
            (['closed', 'Release'], ['done', 'Release']),
            (['undone', 'Release', 'plan'], ['reopen', 'Release', 'plan']),
            (['unclose', '--literal', '--due'], ['reopen', '--literal', '--due']),
            (['due', 'Release', '--due=next week'], ['schedule', 'Release', '--at', 'next week']),
            (['comment', '--add', 'Release', 'a', 'b'], ['comment', 'Release', 'a', 'b']),
            (['comments', 'Release', 'a', 'b'], ['comment', 'Release', 'a', 'b']),
            (['add', 'comment', 'Release', 'a', 'b'], ['comment', 'Release', 'a', 'b']),
            (['categories'], ['category']),
            (['category', '--create', 'Client', 'Work'], ['add', 'category', 'Client', 'Work']),
            (['task', '--new', 'Work', 'a ', 'b'], ['add', 'task', 'Work', 'a ', 'b']),
            (['task', '--add', '--p1', '--at', 'tomorrow', 'Work', 'a ', 'b'],
             ['add', 'task', 'Work', 'a ', '--priority=P1', 'b', '--at=tomorrow']),
            (['task', '--due', 'tomorrow 10:00', 'Release'], ['schedule', 'Release', '--at=tomorrow 10:00']),
            (['task', '--priority', 'p1', 'Release'], ['priority', 'Release', '1']),
            (['task', '-p1', 'Release'], ['priority', 'Release', 'P1']),
            (['task', '--p4', 'Release'], ['priority', 'Release', '4']),
            (['task', '--rename', 'New release', 'Release'], ['rename', 'Release', '--to', 'New', 'release']),
            (['task', '--move', 'Client Work', 'Release'], ['move', 'Release', 'Client', 'Work']),
            (['task', '--move=', 'Release'], ['move', 'Release', '']),
            (['task', '--reminder=1h', 'Release'], ['schedule', 'Release', '--reminder', '1h']),
            (['task', '--comment', 'Release', 'a ', 'b'], ['comment', 'Release', 'a ', 'b']),
            (['task', '--step', 'Release', 'a ', 'b'], ['add', 'step', 'Release', 'a ', 'b']),
            (['task', '--wait', 'Release', 'no', '--due=tomorrow', 'time'],
             ['schedule', 'Release', '--hide', '--reason=no time', '--at=tomorrow']),
            (['task', '--waiting', 'Release', 'no', 'time', '--due=tomorrow'],
             ['schedule', 'Release', '--hide', '--reason=no time', '--at=tomorrow']),
        ]
        for alias, canonical in cases:
            with self.subTest(alias=alias):
                self.assertEqual(parse(alias), parse(canonical))

    def test_step_scalar_adjacency(self):
        for action, value, command, option in [
            ('due', 'tomorrow 10:00', 'schedule', 'at'),
            ('at', 'tomorrow', 'schedule', 'at'),
            ('schedule', 'next week', 'schedule', 'at'),
            ('reminder', '1h', 'schedule', 'reminder'),
            ('priority', 'p1', 'priority', 'priority'),
            ('rename', 'New title', 'rename', None),
            ('move', '', 'move', None),
        ]:
            for args in [[f'--{action}', value], [f'--{action}={value}']]:
                with self.subTest(args=args):
                    r = parse(['step'] + args + ['Release plan', 'Write summary'])
                    self.assertEqual((r.command, r.target, r.parent, r.selector),
                                     (command, 'step', ('Release plan',), ('Write summary',)))
                    if option:
                        self.assertEqual(r.option(option), ('1h',) if action == 'reminder' else 'P1' if action == 'priority' else value)
                    else:
                        self.assertEqual(r.destination, (value,))

    def test_creation_boundaries_and_values(self):
        cases = [
            (['add', 'Work', 'a', 'b'], [('title', ('a', 'b'), ('a b',))]),
            (['add', 'task', 'Work', 'a ', 'b', '--at=tomorrow', 'c'],
             [('title', ('a ', 'b', 'c'), ('a', 'b', 'c'))]),
            (['add', '--category=Work', '--title', 'a b', '--step', 'x', '--at=tomorrow', 'y', '--step', 'z '],
             [('title', ('a b',), ('a b',)), ('step', ('x', 'y'), ('x y',)), ('step', ('z ',), ('z',))]),
            (['comment', 'task', '--comment', 'a', '--color=never', 'b', '--comment', 'c d', 'e'],
             [('comment', ('a', 'b'), ('a b',)), ('comment', ('c d', 'e'), ('c d', 'e'))]),
            (['add', 'step', 'parent', '--step', 'a b', 'c', '--step', 'd', 'e'],
             [('step', ('a b', 'c'), ('a b', 'c')), ('step', ('d', 'e'), ('d e',))]),
            (['comment', 'task', 'a\tb', 'c\nd'], [('comment', ('a\tb', 'c\nd'), ('a\tb c\nd',))]),
        ]
        for argv, expected in cases:
            with self.subTest(argv=argv):
                r = parse(argv)
                self.assertEqual([(g.kind, g.arguments, g.values) for g in r.groups], expected)

    def test_literal_survives_all_extraction(self):
        r = parse(['add', 'Work', '--literal', '--due=tomorrow', '--at=next week', '--literal', '--title'])
        self.assertEqual(r.groups[0].arguments, ('--due=tomorrow', '--title'))
        self.assertEqual(r.groups[0].literal_indices, (0, 1))
        for command in ('task', 'step', 'search', 'reopen', 'delete', 'hide', 'unhide'):
            r = parse([command, '--literal', '--help', '--literal', '--color=never']
                      + (['--at', 'tomorrow'] if command == 'hide' else []))
            self.assertEqual(r.selector, ('--help', '--color=never'))
            self.assertEqual(r.selector_literals, (0, 1))
        r = parse(['--literal', '--refresh', 'more'])
        self.assertEqual(r.command, 'lookup')
        self.assertEqual(r.selector, ('--refresh', 'more'))

    def test_unknown_top_level_is_complete_lookup(self):
        for name in ('schedle', 'check', 'show', 'resume', 'ask', 'promote', 'demote'):
            self.assertEqual(parse([name, 'some words', 'term']).selector, (name, 'some words', 'term'))
        self.assertEqual(parse([]), parse(['now']))

    def test_shorthand_and_marker_selectors(self):
        for command in ('done', 'comment'):
            self.assertEqual(parse([command, 'first', 'second']).selector, ('first',))
            r = parse([command, 'first', 'second', '--comment', 'text'])
            self.assertEqual(r.selector, ('first', 'second'))
        self.assertEqual(parse(['hide', '--at', '1 month', 'first', 'second']),
                         parse(['hide', 'first', '--at=1 month', 'second']))
        self.assertEqual(parse(['add', 'step', 'first', 'second', '--step', 'text']).parent, ('first', 'second'))

    def test_all_retained_step_actions(self):
        actions = {'--done': 'done', '--close': 'done', '--closed': 'done',
                   '--undone': 'reopen', '--unclose': 'reopen', '--delete': 'delete',
                   '--comment': 'comment'}
        for action, command in actions.items():
            with self.subTest(action=action):
                r = parse(['step', action, 'parent', 'child'])
                self.assertEqual((r.command, r.parent, r.selector), (command, ('parent',), ('child',)))
        for action in ('--add', '--new', '--create'):
            self.assertEqual(parse(['step', action, 'parent', 'title']), parse(['add', 'step', 'parent', 'title']))
        for action in ('--wait', '--waiting'):
            r = parse(['step', action, 'parent', 'child', 'no time', '--at=tomorrow'])
            self.assertEqual((r.parent, r.selector), (('parent',), ('child',)))
            self.assertEqual(r.option('reason'), 'no time')
        for prefix in ('-', '--'):
            for n in range(1, 5):
                r = parse(['step', f'{prefix}p{n}', 'parent', 'child'])
                self.assertEqual(r.selector, ('child',))
                self.assertEqual(r.option('priority'), f'P{n}')

    def test_step_creation_priority_options_preserve_groups_and_literals(self):
        forms = [['add', 'step'], ['step', '--add'], ['step', '--new'],
                 ['step', '--create'], ['task', '--step']]
        flags = [(['--priority', 'p1'], 'P1'), (['--priority=4'], 'P4'),
                 (['--priority=P3'], 'P3'), (['-p2'], 'P2'), (['--p1'], 'P1')]
        operands = ['--literal', '--parent', '--step', 'a ', 'b',
                    '--step', '--literal', '--p4']
        baseline = parse(['add', 'step', *operands])
        for form in forms:
            for flag, expected in flags:
                for position in (0, 5, len(operands)):
                    with self.subTest(form=form, flag=flag, position=position):
                        r = parse(form + operands[:position] + flag + operands[position:])
                        self.assertEqual((r.command, r.target), ('add', 'step'))
                        self.assertEqual(r.option('priority'), expected)
                        self.assertEqual(r.parent, ('--parent',))
                        self.assertEqual(r.parent_literals, (0,))
                        self.assertEqual(r.groups, baseline.groups)

    def test_move_grammars(self):
        r = parse(['move', '--literal', '--source', '--task', '--literal', '--parent'])
        self.assertEqual(r.selector_literals, (0,))
        self.assertEqual(r.destination_literals, (0,))
        r = parse(['move', 'source', '--literal', '--destination', 'more'])
        self.assertEqual(r.destination, ('--destination more',))
        self.assertEqual(r.destination_literals, (0,))
        self.assertEqual(parse(['move', 'my', 'project', 'release', 'preparation']).destination,
                         ('project release preparation',))
        r = parse(['move', 'my', 'project', '--task', 'parent phrase', 'term', '--category', 'Client', 'Work'])
        self.assertEqual(r.selector, ('my', 'project'))
        self.assertEqual(r.destination, ('parent phrase', 'term'))
        self.assertEqual(r.option('category'), 'Client Work')
        self.assertEqual(parse(['move', 'source', '--to', 'Client', 'Work']),
                         parse(['move', 'source', '--category', 'Client', 'Work']))
        for suffix in ([''], ['--task'], ['--task', ''], ['--task=']):
            self.assertEqual(parse(['move', 'source'] + suffix).destination_kind, 'promotion')

    def test_usage_errors_are_pure_and_informative(self):
        cases = [
            ['schedule', 'x', '--due', 'tomorrow', '--at=next week'],
            ['hide', 'x', '--reason'], ['hide', 'x', '--hide=reason'],
            ['hide', 'x', '--due='], ['done', 'x', '--yes'],
            ['add', 'step', '--priority=P0', 'x', 'title'],
            ['add', 'Work', 'a b', 'c', '--step', 'child'],
            ['add', 'Work', 'a ', ' ', 'b'], ['add', 'Work', 'a\tb'],
            ['comment', 'x', '--comment', 'a', '--comment'],
            ['done', 'x', '--comment', 'a', '--comment', 'b'],
            ['add', '--category=Work', '--title=a'],
            ['add', 'Work', '--title', 'a', '--title', 'b'],
            ['add', 'Work', 'a', '--reason=x'],
            ['hide', 'x', '--reason=[todo waiting]\nbad\n[/todo waiting]'],
            ['move', 'x'], ['move', 'x', ' '], ['move', 'x', '', 'y'],
            ['move', 'x', '--task', ' '], ['move', 'x', '--task', '', 'y'],
            ['move', 'x', '--category', 'Work', '--to', 'Work'],
            ['rename', 'x'], ['reopen', 'x', '--comment', 'text'],
            ['--refresh', 'now', '--refresh'], ['--color=never', 'now', '--color', 'auto'],
            ['--clear-cache', 'now'], ['done', 'x', '--refresh'],
            ['report', '--final', '--since=yesterday'], ['report', '--yes'],
            ['init', '--yes'], ['task', '--due'], ['task', '--due=tomorrow'],
            ['step', '--due=tomorrow', 'parent'], ['task', '--priority', 'P5', 'x'],
            ['task', '--p1=foo', 'x'], ['task', '--priority', '', 'x'],
            ['task', '--waiting', 'x', 'reason'],
            ['schedule', 'x', '--reminder=1h', '--reminder=60m'],
            ['schedule', 'x', '--reminder=clear', '--reminder=1h'],
            ['add', 'comment', 'x'], ['comment', '--create', 'x'],
            ['add', 'Work', 'x', '--hide'], ['schedule', 'x', '--hide', '--reminder=1h'], ['now', '--all=1'], ['reopen', '--literal'],
        ]
        with patch('builtins.open', side_effect=AssertionError('I/O forbidden')):
            for argv in cases:
                with self.subTest(argv=argv), self.assertRaises(UsageError) as caught:
                    parse(argv)
                self.assertEqual(caught.exception.status, 2)
                self.assertIn('Usage:', str(caught.exception))
                self.assertIn('Example:', str(caught.exception))

    def test_dangling_literal_keeps_command_context(self):
        cases = [
            (['reopen', '--literal'], 'reopen', 'todo reopen "Release plan"'),
            (['--color=never', 'unclose', '--literal'], 'reopen', 'todo reopen "Release plan"'),
            (['task', '--undone', '--literal'], 'reopen', 'todo reopen "Release plan"'),
            (['step', '--due=tomorrow', 'parent', 'child', '--literal'], 'schedule',
             'todo schedule "Release plan" tomorrow 10:00 --hide --reason "no time"'),
            (['task', '--move', 'Work', 'Release', '--literal'], 'move', 'todo move "Write tests" ""'),
            (['comments', 'Release', '--comment', 'Reviewed', '--literal'], 'comment',
             'todo comment "Release plan" --comment Reviewed'),
        ]
        for argv, command, example in cases:
            with self.subTest(argv=argv), self.assertRaises(UsageError) as caught:
                parse(argv)
            error = caught.exception
            self.assertEqual((error.status, error.command, error.offending), (2, command, '--literal'))
            self.assertEqual(error.problem, 'missing literal argument')
            self.assertIn('Usage: todo ' + command + ' ', str(error))
            self.assertEqual(error.example, example)
            self.assertIn('Example: ' + example, str(error))
        # Escaping the marker itself is valid, even in final position.
        request = parse(['unclose', '--literal', '--literal'])
        self.assertEqual(request.selector, ('--literal',))
        self.assertEqual(request.selector_literals, (0,))
        self.assertEqual(parse(['reopen', '--literal', '--help']).selector, ('--help',))
        with self.assertRaises(UsageError):
            parse(['reopen', '--help', '--literal'])

    def test_reminder_clear_with_attention(self):
        r = parse(['schedule', 'x', '--at=tomorrow 10:00', '--reminder=clear'])
        self.assertEqual(r.option('reminder'), ('clear',))
        self.assertEqual(r.option('at'), 'tomorrow 10:00')

    def test_empty_reason_and_globals(self):
        self.assertEqual(parse(['hide', 'x', '--reason', '']), parse(['hide', 'x', '--reason=']))
        self.assertEqual(parse(['--color=never', '--clear-cache', '--refresh', 'now']),
                         parse(['now', '--refresh', '--clear-cache', '--color', 'never']))

    def test_help_dispatch(self):
        for command in ('now', 'comment', 'comments', 'move', 'task', 'report'):
            self.assertEqual(parse(['help', command]), parse([command, '--help']))
            self.assertIn('Usage:', render_help(command))
        self.assertEqual(parse(['--help']), HelpRequest())
        self.assertIn('view work', render_help())

    def test_syntax_errors_supply_concrete_valid_command_examples(self):
        # Explicit expectations prevent synopsis placeholders or an unrelated
        # fallback from passing merely because an Example: line exists.
        examples = {
            'now': 'todo now --category Work',
            'waiting': 'todo waiting',
            'someday': 'todo someday',
            'task': 'todo task "Release plan"',
            'step': 'todo step "Write summary"',
            'category': 'todo category',
            'search': 'todo search "release notes"',
            'lookup': 'todo "Release plan"',
            'add': 'todo add task Work "Write code" "Write tests"',
            'comment': 'todo comment "Release plan" --comment Reviewed',
            'done': 'todo done "Release plan" --comment Reviewed',
            'reopen': 'todo reopen "Release plan"',
            'delete': 'todo delete "Release plan"',
            'schedule': 'todo schedule "Release plan" tomorrow 10:00 --hide --reason "no time"',
            'hide': 'todo hide "Release plan" next week --reason "no time"',
            'unhide': 'todo unhide "Release plan"',
            'priority': 'todo priority "Release plan" P1',
            'rename': 'todo rename "Release plan" New plan',
            'move': 'todo move "Write tests" ""',
            'report': 'todo report --since "2 days ago"',
            'init': 'todo init',
        }
        for command, example in examples.items():
            with self.subTest(command=command):
                argv = ['Release plan'] if command == 'lookup' else [command]
                with self.assertRaises(UsageError) as caught:
                    parse(argv + ['--literal'])
                error = caught.exception
                self.assertEqual((error.command, error.status), (command, 2))
                self.assertEqual(error.example, example)
                self.assertIn('Example: ' + example, str(error))
                request = parse(shlex.split(error.example)[1:])
                self.assertEqual(request.command, command)
                if command != 'lookup':
                    self.assertIn('Example: ' + example, render_help(command))
                if command == 'report':
                    # Syntax preserves raw boundaries; the domain consumer is
                    # authoritative about their accepted language.
                    self.assertEqual(
                        parse_boundary(request.option('since'),
                                       datetime(2026, 10, 26, 12, tzinfo=timezone.utc), 'UTC'),
                        datetime(2026, 10, 24, 12, tzinfo=timezone.utc))



class PositionalValueTests(unittest.TestCase):
    def test_joined_values_options_and_aliases(self):
        for command in ('rename', 'schedule', 'due', 'wait', 'hide'):
            for tail in (['next', 'week'], ['next', 'week', '10:00'], ['next', 'week', 'at', '10:00']):
                with self.subTest(command=command, tail=tail):
                    r = parse([command, 'A', *tail])
                    self.assertEqual(r.selector, ('A',))
                    self.assertEqual(r.destination if command == 'rename' else (r.option('at'),),
                                     (' '.join(tail),))
        for command in ('schedule', 'due', 'wait', 'hide'):
            for argv in (
                [command, '--reason= later ', 'Release plan', 'next', '--color=never', 'week', 'at', '10:00'],
                [command, 'Release plan', 'next', 'week', '--reason', ' later ', 'at', '10:00', '--color', 'never']):
                if command != 'hide':
                    argv += ['--hide']
                with self.subTest(argv=argv):
                    r = parse(argv)
                    self.assertEqual(r.selector, ('Release plan',))
                    self.assertEqual(r.option('at'), 'next week at 10:00')
                    self.assertEqual(r.option('reason'), ' later ')
        for argv in (['rename', '--color=never', 'A', 'New', 'task', 'title', 'today'],
                     ['rename', 'A', 'New', '--color', 'never', 'task', 'title', 'today']):
            r = parse(argv)
            self.assertEqual(r.selector, ('A',))
            self.assertEqual(r.destination, ('New task title today',))
            self.assertEqual(r.destination_kind, 'name')
        r = parse(['rename', '--literal', '--help', 'New name', '--literal', '--to', 'end'])
        self.assertEqual(r.selector, ('--help',))
        self.assertEqual(r.selector_literals, (0,))
        self.assertEqual(r.destination, ('New name --to end',))
        self.assertEqual(r.destination_literals, (0,))
        r = parse(['schedule', '--literal', '--help', ' next week ', '--literal', '--due=never'])
        self.assertEqual(r.selector_literals, (0,))
        self.assertEqual(r.option('at'), ' next week  --due=never')
        self.assertIsNone(parse(['wait', 'A', 'tomorrow']).option('hide'))
        self.assertEqual(parse(['rename', 'A', ' New ', '', 'title']).destination, (' New   title',))
        self.assertEqual(parse(['schedule', 'A', ' next ', '', 'week']).option('at'), ' next   week')

    def test_explicit_boundaries_keep_terms_and_scalar_arity(self):
        for command in ('schedule', 'due', 'wait', 'hide'):
            r = parse([command, '--due=tomorrow 10:00', '--literal', 'clear', 'nightly python', 'extra'])
            self.assertEqual(r.selector, ('clear', 'nightly python', 'extra'))
            self.assertEqual(r.selector_literals, (0,))
            self.assertEqual(r.option('at'), 'tomorrow 10:00')
            self.assertIsNone(r.option('clear'))
        r = parse(['rename', 'nightly', 'python', '--to', 'New name', 'tail'])
        self.assertEqual(r.selector, ('nightly', 'python'))
        self.assertEqual(r.destination, ('New name tail',))
        r = parse(['schedule', 'A', '--at', 'tomorrow', '10:00'])
        self.assertEqual(r.selector, ('A', '10:00'))
        self.assertEqual(r.option('at'), 'tomorrow')

    def test_sole_clear_and_reminder_boundaries(self):
        self.assertTrue(parse(['schedule', 'A', 'clear']).option('clear'))
        for tail, value in ((['B', 'clear'], 'B clear'), (['--literal', 'clear'], 'clear'),
                            (['clear '], 'clear '), (['B clear'], 'B clear')):
            r = parse(['schedule', 'A', *tail])
            self.assertEqual(r.selector, ('A',))
            self.assertEqual(r.option('at'), value)
            self.assertIsNone(r.option('clear'))
        for marker in (['--reminder', '10m'], ['--reminder-at', 'keep'],
                       ['--reminder', 'keep', '--reminder-at', 'Friday 09:00'], ['--reminder', 'clear']):
            r = parse(['schedule', 'A', 'tomorrow 10:00', *marker])
            self.assertEqual(r.selector, ('A',))
            self.assertEqual(r.option('at'), 'tomorrow 10:00')
            self.assertIsNone(r.option('clear'))
            r = parse(['schedule', 'A', *marker])
            self.assertIsNone(r.option('at'))
            self.assertEqual(r.selector, ('A',))
        r = parse(['schedule', '--reminder-at', 'keep', 'A', 'B', '--reminder=10m'])
        self.assertEqual(r.option('at'), 'B')
        self.assertEqual(r.reminder_markers, (('reminder-at', 'keep'), ('reminder', '10m')))
        self.assertIsNone(parse(['hide', 'A']).option('at'))

    def test_invalid_inputs_are_usage_errors(self):
        for argv in (
            ['rename', 'A'], ['rename', '', 'Name'], ['rename', 'A', 'Bad\nname'],
            ['rename', 'A', '--to'], ['rename', 'A', '--to=Name'],
            ['rename', 'A', '--to', 'B', '--to', 'C'],
            ['schedule', 'A'], ['schedule', 'A', 'none'], ['schedule', 'A', '--at'],
            ['schedule', 'A', 'tomorrow', '--at='],
            ['schedule', 'A', '--at=tomorrow', '--due=next week'],
            ['hide', 'A', '--at=tomorrow', '--schedule=next week'],
            *[['schedule', 'A', 'clear', *suffix] for suffix in (
                ['--hide'], ['--reason='], ['--reminder=clear'], ['--reminder-at=keep'])]):
            with self.subTest(argv=argv), self.assertRaises(UsageError) as raised:
                parse(argv)
            self.assertEqual(raised.exception.status, 2)
            self.assertIn('Usage: todo ', str(raised.exception))
            self.assertIn('Example: todo ', str(raised.exception))


if __name__ == '__main__':
    unittest.main()
