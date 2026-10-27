"""Pure argv normalization. No config, filesystem, terminal, or HTTP access.

Selectors are tuples of original phrases, not joined strings. TextGroup retains
shell boundaries and literal insertion positions alongside validated values.
Options are sorted (name, value) pairs; repeatable reminder values are tuples.
Move destinations distinguish positional, category, parent, and promotion forms.
"""
from dataclasses import dataclass
from todo_lib.domain import DomainError, validate_title, validate_body, parse_reminder, with_waiting_reason
from .help import ALIASES, SYNOPSES, EXAMPLES, HelpRequest


class UsageError(ValueError):
    status = 2

    def __init__(self, command, problem, offending=None):
        self.command, self.problem, self.offending = command, problem, offending
        self.synopsis = 'todo ' + SYNOPSES.get(command, 'help [COMMAND]')
        self.example = EXAMPLES.get(command, 'todo now')
        super().__init__(f'{command}: {problem}' + (f': {offending!r}' if offending is not None else '')
                         + f'\nUsage: {self.synopsis}\nExample: {self.example}')
        if command == 'report':
            self.args = (str(self) + '\nBoundaries: YYYY-MM-DD, local YYYY-MM-DDTHH:MM[:SS], aware RFC3339; positive Nd ago or N days ago.',)


@dataclass(frozen=True)
class Word:
    value: str
    literal: bool = False


@dataclass(frozen=True)
class TextGroup:
    kind: str
    arguments: tuple[str, ...]
    values: tuple[str, ...]
    literal_indices: tuple[int, ...] = ()


@dataclass(frozen=True)
class CommandRequest:
    command: str
    target: str = 'item'
    selector: tuple[str, ...] = ()
    parent: tuple[str, ...] = ()
    groups: tuple[TextGroup, ...] = ()
    options: tuple[tuple[str, object], ...] = ()
    destination: tuple[str, ...] | None = None
    destination_kind: str | None = None
    selector_literals: tuple[int, ...] = ()
    parent_literals: tuple[int, ...] = ()
    destination_literals: tuple[int, ...] = ()
    reminder_markers: tuple[tuple[str, str], ...] = ()

    def option(self, name, default=None):
        return dict(self.options).get(name, default)


def creation_values(arguments, kind='title'):
    """REQ-CLI-012 splitting: inspect U+0020 before trimming each result."""
    arguments = tuple(arguments)
    if not arguments:
        raise DomainError('empty creation group')
    values = arguments if any(' ' in a for a in arguments) else (' '.join(arguments),)
    validator = validate_body if kind == 'comment' else validate_title
    return tuple(validator(value.strip(' ')) for value in values)


def _words(argv):
    result, i = [], 0
    while i < len(argv):
        if argv[i] == '--literal':
            i += 1
            if i == len(argv):
                # Defer diagnostics until the workflow has been identified.
                return result, True
            result.append(Word(argv[i], True))
        else:
            result.append(Word(argv[i]))
        i += 1
    return result, False


def _parts(word):
    if word.literal:
        return word.value, None
    name, sep, value = word.value.partition('=')
    return name, value if sep else None


def _literal_indices(words):
    return tuple(i for i, word in enumerate(words) if word.literal)


def _values(words):
    return tuple(w.value for w in words)


READS = {'now', 'waiting', 'someday', 'task', 'step', 'category', 'search', 'lookup'}
GLOBAL = {'color', 'refresh', 'clear-cache'}
SCALAR = {'color', 'at', 'reason', 'category', 'reminder', 'reminder-at', 'priority', 'since', 'until', 'set-cursor'}
BOOL = {'refresh', 'clear-cache', 'all', 'hide', 'done', 'yes', 'edit', 'final', 'show-cursor'}
OPTION_ALIASES = {'due': 'at', 'schedule': 'at', 'close': 'done', 'closed': 'done'}


def parse(argv):
    """Return CommandRequest or HelpRequest; all syntax failures have status 2."""
    argv = list(argv)
    if not all(isinstance(a, str) for a in argv):
        raise UsageError('todo', 'arguments must be strings')
    words, missing_literal = _words(argv)
    options = {}
    reminder_markers = []
    command = 'now'

    def fail(problem, offending=None):
        raise UsageError(command, problem, offending)

    def check_literal():
        if missing_literal:
            fail('missing literal argument', '--literal')

    def store(name, value):
        if name in ('reminder', 'reminder-at'):
            reminder_markers.append((name, value))
            options[name] = options.get(name, ()) + (value,)
        elif name in options:
            fail('duplicate or conflicting option', '--' + name)
        else:
            options[name] = value

    def scalar_value(seq, i, inline, name, allow_empty=False):
        if inline is None:
            if i + 1 >= len(seq) or (not seq[i + 1].literal and seq[i + 1].value.startswith('-')):
                fail('missing scalar value', '--' + name)
            i += 1
            inline = seq[i].value
        if not inline.strip() and not (allow_empty and inline == ''):
            fail('empty scalar value', '--' + name)
        return inline, i

    # Only documented global prefixes can precede workflow selection.
    i = 0
    while i < len(words):
        name, inline = _parts(words[i])
        if words[i].literal or name not in ('--color', '--refresh', '--clear-cache'):
            break
        key = name[2:]
        if key == 'color':
            value, i = scalar_value(words, i, inline, key)
        else:
            if inline is not None:
                fail('boolean option takes no value', words[i].value)
            value = True
        store(key, value)
        i += 1
    words = words[i:]
    if words and not words[0].literal and words[0].value in ('help', '--help'):
        check_literal()
        topic = words[1].value if len(words) == 2 else None
        if len(words) > 2 or (topic is not None and ALIASES.get(topic, topic) not in SYNOPSES):
            fail('invalid help command', _values(words))
        return HelpRequest(ALIASES.get(topic, topic))
    if words and not words[0].literal and ALIASES.get(words[0].value, words[0].value) in SYNOPSES:
        spelling = words.pop(0).value
        command = ALIASES.get(spelling, spelling)
    elif words:
        command = 'lookup'
    if any(not w.literal and w.value == '--help' for w in words):
        check_literal()
        return HelpRequest(None if command == 'lookup' else command)

    target = 'item'
    force_comment_creation = False
    alias_operands = None
    action_value = None
    action_literal = False
    wait_alias = False
    if command in ('task', 'step', 'comment', 'category') and words:
        action, inline = _parts(words[0])
        noun = command
        creation = {'--add', '--create'} | ({'--new'} if noun in ('task', 'step') else set())
        simple = {'--done': 'done', '--close': 'done', '--closed': 'done',
                  '--undone': 'reopen', '--unclose': 'reopen', '--delete': 'delete'}
        scalar_actions = {'--at': 'schedule', '--due': 'schedule', '--schedule': 'schedule',
                          '--priority': 'priority', '--reminder': 'schedule', '--reminder-at': 'schedule',
                          '--rename': 'rename', '--move': 'move'}
        fixed = action in {f'{prefix}p{n}' for prefix in ('-', '--') for n in range(1, 5)}
        if not words[0].literal and action in creation:
            if inline is not None:
                fail('action takes no assignment', words[0].value)
            words.pop(0)
            command, target = 'add', noun
            if noun == 'comment':
                command, target = 'comment', 'item'
                force_comment_creation = True
        elif noun in ('task', 'step') and not words[0].literal and (
                action in simple or action in scalar_actions or fixed or action in ('--comment', '--step', '--wait', '--waiting')):
            if action == '--step' and noun == 'step':
                fail('unsupported step action', action)
            words.pop(0)
            if action in scalar_actions:
                command = scalar_actions[action]
                check_literal()
                action_literal = inline is None and bool(words) and words[0].literal
                action_value, index = scalar_value([Word(action)] + words, 0, inline, action,
                                                   allow_empty=action == '--move')
                if inline is None:
                    words = words[index:]
                if command == 'schedule':
                    store(action[2:] if action in ('--reminder', '--reminder-at') else 'at', action_value)
            elif fixed:
                if inline is not None:
                    fail('fixed priority takes no value', action)
                command, action_value = 'priority', action[-1]
            else:
                if inline is not None:
                    fail('action takes no assignment', action)
                command = simple.get(action, {'--comment': 'comment', '--step': 'add',
                                              '--wait': 'schedule', '--waiting': 'schedule'}.get(action))
                if action == '--step':
                    target = 'step'
                wait_alias = action in ('--wait', '--waiting')
            # Retained aliases have fixed one-task or parent/direct-child operands.
            check_literal()
            count = 1 if noun == 'task' or action == '--step' else 2
            if len(words) < count or any(not w.literal and w.value.startswith('-') for w in words[:count]):
                fail('missing item operand', action)
            alias_operands, words = words[:count], words[count:]
            if noun == 'step':
                target = 'step'
            if wait_alias:
                store('hide', True)
    if command == 'add' and target == 'item':
        if words and not words[0].literal and words[0].value in ('task', 'step', 'category', 'comment'):
            target = words.pop(0).value
        else:
            target = 'task'
        if target == 'comment':
            command, target = 'comment', 'item'
            # add comment requires text, unlike the ordinary read form.
            require_comment = True
        else:
            require_comment = False
    else:
        require_comment = force_comment_creation

    check_literal()
    allowed = set(GLOBAL)
    if command == 'now': allowed |= {'all', 'category'}
    if command == 'search': allowed |= {'all'}
    if command == 'add' and target in ('task', 'step'):
        allowed |= {'done', 'at', 'hide', 'reason', 'reminder', 'reminder-at'}
        if target == 'task': allowed |= {'priority', 'category'}
    if command == 'schedule': allowed |= {'at', 'hide', 'reason', 'reminder', 'reminder-at'}
    if command == 'hide': allowed |= {'at', 'reason'}
    if command == 'delete': allowed |= {'yes'}
    if command == 'comment': allowed |= {'edit'}
    if command == 'report': allowed |= {'since', 'until', 'set-cursor', 'final', 'yes', 'show-cursor'}

    markers = set()
    if command == 'add' and target == 'task': markers = {'title', 'step'}
    if command == 'add' and target == 'step': markers = {'step'}
    if command in ('comment', 'done'): markers = {'comment'}
    if command == 'rename': markers = {'to'}
    if command == 'move': markers = {'task', 'category'}
    segments = [('positional', [])]
    seen_markers = set()
    i = 0
    while i < len(words):
        word = words[i]
        name, inline = _parts(word)
        key = name[2:] if name.startswith('--') else name
        key = OPTION_ALIASES.get(key, key)
        if command == 'move' and key == 'to': key = 'category'
        fixed = name in {f'{prefix}p{n}' for prefix in ('-', '--') for n in range(1, 5)}
        if word.literal or not word.value.startswith('-'):
            segments[-1][1].append(word)
        elif key in markers:
            # Text/destination markers deliberately do not support equals syntax,
            # except the documented empty --task= promotion spelling.
            if inline is not None and not (command == 'move' and key == 'task' and inline == ''):
                fail('text marker does not take assignment', word.value)
            repeatable = key == 'step' or (key == 'comment' and command == 'comment')
            if key in seen_markers and not repeatable:
                fail('duplicate marker', word.value)
            seen_markers.add(key)
            segments.append((key, [Word('')] if inline == '' else []))
        elif fixed:
            if 'priority' not in allowed or inline is not None:
                fail('unsupported fixed priority', word.value)
            store('priority', name[-1])
        elif key in allowed:
            if key in SCALAR:
                value, i = scalar_value(words, i, inline, key, allow_empty=key == 'reason')
            else:
                if inline is not None:
                    fail('boolean option takes no value', word.value)
                value = True
            store(key, value)
        else:
            fail('unknown or inapplicable option', word.value)
        i += 1

    positional = segments[0][1]
    marked = segments[1:]
    groups = []
    selector, parent = [], []
    destination = None
    destination_kind = None

    def nonempty(seq, label='selector'):
        if not seq or any(not w.value.strip() for w in seq):
            fail('missing or empty ' + label, _values(seq))
        return seq

    def group(kind, seq):
        try:
            values = creation_values(_values(seq), kind)
        except DomainError as exc:
            fail(str(exc), _values(seq))
        groups.append(TextGroup(kind, _values(seq), values, _literal_indices(seq)))

    def joined(seq, label):
        nonempty(seq, label)
        return ' '.join(_values(seq))

    if alias_operands is not None:
        if len(alias_operands) == 2:
            parent, selector = alias_operands[:1], alias_operands[1:]
        else:
            selector = alias_operands
        nonempty(selector)
        if parent: nonempty(parent, 'parent')

    if command == 'add':
        if target == 'category':
            if marked: fail('category has no text markers')
            store('name', joined(positional, 'category name'))
        elif target == 'task':
            if 'category' not in options:
                if not positional: fail('missing category')
                store('category', joined(positional[:1], 'category'))
                positional = positional[1:]
            if positional and 'title' in seen_markers:
                fail('positional titles conflict with --title', _values(positional))
            if positional: group('title', positional)
            for kind, seq in marked: group(kind, seq)
            if not any(g.kind == 'title' for g in groups): fail('missing task title')
            if sum(len(g.values) for g in groups if g.kind == 'title') > 1 and 'step' in seen_markers:
                fail('inline steps require exactly one new task')
        elif target == 'step':
            if alias_operands is not None:
                parent, selector = selector, []
            elif 'step' in seen_markers:
                parent, positional = positional, []
            else:
                parent, positional = positional[:1], positional[1:]
            nonempty(parent, 'parent selector')
            if positional: group('step', positional)
            for kind, seq in marked: group(kind, seq)
            if not groups: fail('missing step title')
    elif command in ('comment', 'done'):
        if options.get('edit'):
            if marked or alias_operands is not None or require_comment:
                fail('--edit conflicts with comment creation')
            selector = positional
        elif alias_operands is not None:
            if positional: group('comment', positional)
            for kind, seq in marked: group(kind, seq)
        elif marked:
            selector = positional
            for kind, seq in marked: group(kind, seq)
        else:
            selector, text = positional[:1], positional[1:]
            if text: group('comment', text)
        nonempty(selector)
        if require_comment and not groups: fail('missing comment text')
    elif command in ('move', 'rename'):
        if action_value is not None:
            if positional or marked: fail('unexpected operands after noun-action target', _values(positional))
            destination = [Word(action_value, action_literal)]
            destination_kind = 'positional' if command == 'move' else 'name'
        elif command == 'rename':
            selector = positional
            if len(marked) != 1: fail('rename requires --to NEW_NAME')
            destination = [Word(joined(marked[0][1], 'new name'), any(w.literal for w in marked[0][1]))]
            destination_kind = 'name'
        elif marked:
            selector = positional
            # Keep category and parent marker semantics independent; category is
            # joined prose while parent preserves selector phrase boundaries.
            for kind, seq in marked:
                if kind == 'category':
                    store('category', joined(seq, 'category destination'))
                else:
                    destination, destination_kind = seq, 'parent'
            if destination is None: destination_kind = 'category'
        else:
            selector, destination = positional[:1], positional[1:]
            if not destination: fail('move requires a destination')
            destination_kind = 'positional'
        nonempty(selector)
        if command == 'rename':
            try: validate_title(destination[0].value)
            except DomainError as exc: fail(str(exc), destination[0].value)
        elif destination is not None:
            if not destination or _values(destination) == ('',):
                destination, destination_kind = [Word('')], 'promotion'
            else:
                nonempty(destination, 'move destination')
                if destination_kind == 'positional':
                    destination = [Word(' '.join(_values(destination)), any(w.literal for w in destination))]
    elif command == 'priority':
        if alias_operands is None:
            if len(positional) < 2: fail('priority requires a selector and priority')
            selector, value = positional[:-1], positional[-1].value
        else:
            if positional: fail('unexpected priority operands', _values(positional))
            value = action_value
        store('priority', value)
        nonempty(selector)
    elif command == 'schedule':
        if alias_operands is None: selector = positional
        elif wait_alias:
            store('reason', joined(positional, 'waiting reason'))
        elif positional: fail('unexpected scheduling operands', _values(positional))
        if not any(key in options for key in ('at', 'reminder', 'reminder-at')) and selector and selector[-1].value == 'clear' and not selector[-1].literal:
            selector = selector[:-1]
            store('clear', True)
        if not any(key in options for key in ('at', 'reminder', 'reminder-at', 'clear')):
            fail('schedule requires --at VALUE, --reminder VALUE, --reminder-at VALUE, or clear')
        if wait_alias and 'at' not in options: fail('waiting requires --at VALUE')
        nonempty(selector)
    elif command in ('task', 'step', 'lookup', 'search', 'reopen', 'delete', 'hide', 'unhide'):
        if alias_operands is None: selector = positional
        elif positional: fail('unexpected operands', _values(positional))
        nonempty(selector)
    elif positional:
        fail('unexpected operands', _values(positional))

    if 'priority' in options:
        value = str(options['priority']).lower().removeprefix('p')
        if value not in ('1', '2', '3', '4'): fail('priority must be P1 through P4', options['priority'])
        options['priority'] = 'P' + value
    if 'color' in options and options['color'] not in ('auto', 'always', 'never'):
        fail('color must be auto, always, or never', options['color'])
    for kind in ('reminder', 'reminder-at'):
        values = options.get(kind, ())
        if values.count('keep') > 1:
            fail('keep may appear once per reminder type', values)
        if any(v.lower() in ('keep', 'clear') and v not in ('keep', 'clear') for v in values):
            fail('reserved reminder values must be lowercase', values)
        if 'clear' in values and (kind != 'reminder' or len(reminder_markers) != 1 or command != 'schedule'):
            fail('reminder clear is exclusive and only valid with --reminder', values)
        if kind == 'reminder' and 'clear' not in values:
            try:
                offsets = tuple(parse_reminder(v) for v in values if v != 'keep')
            except DomainError as exc:
                fail(str(exc), values)
            if len(set(offsets)) != len(offsets): fail('duplicate reminder offsets', values)
    if 'at' in options and options['at'].strip().lower() in ('ask', 'none', '-'):
        fail('invalid attention value', options['at'])
    if 'reason' in options and options['reason']:
        try:
            with_waiting_reason('', options['reason'])
        except DomainError as exc:
            fail(str(exc), '--reason')
    if 'reason' in options and command != 'hide' and not options.get('hide'):
        fail('reason requires --hide --reason VALUE', '--reason')
    if options.get('hide') and command in ('add', 'schedule') and 'at' not in options:
        fail('--hide requires --at VALUE; reasons use --hide --reason VALUE')
    if options.get('done') and any(k in options for k in ('at', 'hide', 'reason', 'reminder', 'reminder-at')):
        fail('completed creation cannot have scheduling, hiding or reminders')
    cache_read = command in READS or (command == 'comment' and not groups and not options.get('edit'))
    if options.get('refresh') and not cache_read:
        fail('--refresh is inapplicable to this workflow', '--refresh')
    if options.get('clear-cache') and (not cache_read or not options.get('refresh')):
        fail('--clear-cache requires an applicable read with --refresh', '--clear-cache')
    if command == 'report':
        if options.get('final') and any(k in options for k in ('since', 'until', 'set-cursor', 'show-cursor', 'yes')):
            fail('--final conflicts with boundary/cursor options')
        if options.get('show-cursor') and any(k in options for k in ('since', 'until', 'set-cursor', 'yes')):
            fail('--show-cursor conflicts with boundary/cursor options')
        if 'set-cursor' in options and any(k in options for k in ('since', 'until')):
            fail('--set-cursor conflicts with boundary options')
        if options.get('yes') and 'set-cursor' not in options: fail('--yes requires --set-cursor')
    return CommandRequest(command, target, _values(selector), _values(parent), tuple(groups),
                          tuple(sorted(options.items())), None if destination is None else _values(destination),
                          destination_kind, _literal_indices(selector), _literal_indices(parent),
                          () if destination is None else _literal_indices(destination), tuple(reminder_markers))
