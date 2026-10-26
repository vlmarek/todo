"""State-independent help data and dispatch, extensible by public CLI wiring."""
from dataclasses import dataclass

ALIASES = {'close': 'done', 'closed': 'done', 'unclose': 'reopen',
           'undone': 'reopen', 'wait': 'schedule', 'due': 'schedule',
           'comments': 'comment', 'categories': 'category'}
SYNOPSES = {
    'now': 'now [--all] [--category CATEGORY] [--refresh]',
    'waiting': 'waiting [--refresh]', 'someday': 'someday [--refresh]',
    'task': 'task [--refresh] SELECTOR...', 'step': 'step [--refresh] SELECTOR...',
    'category': 'category [--refresh] | category --add NAME...',
    'search': 'search [--all] [--refresh] TEXT...',
    'add': 'add task CATEGORY TITLE... | add step PARENT STEP... | add category NAME...',
    'comment': 'comment [--refresh|--edit] SELECTOR | comment SELECTOR... --comment TEXT...',
    'done': 'done SELECTOR [TEXT...] | done SELECTOR... --comment TEXT...',
    'reopen': 'reopen SELECTOR...', 'delete': 'delete [--yes] SELECTOR...',
    'schedule': 'schedule SELECTOR... --at WHEN [--hide --reason VALUE] [--reminder OFFSET]...',
    'hide': 'hide SELECTOR... [--at WHEN] [--reason VALUE]',
    'unhide': 'unhide SELECTOR...', 'priority': 'priority SELECTOR... P',
    'rename': 'rename SELECTOR... --to NEW_NAME...',
    'move': "move SELECTOR TARGET... | move SELECTOR '' | move SELECTOR... --task [PARENT...] [--category NAME...]",
    'report': 'report [--final | --since TIMESTAMP --until TIMESTAMP | --show-cursor | --set-cursor TIMESTAMP [--yes]]',
    'init': 'init',
}
# Examples are executable invocations, not synopses with optional operands or
# placeholders. Lookup has diagnostic data without registering a public command.
EXAMPLES = {
    'now': 'todo now --category Work',
    'waiting': 'todo waiting',
    'someday': 'todo someday',
    'task': 'todo task "Release plan"',
    'step': 'todo step "Write summary"',
    'category': 'todo category',
    'search': 'todo search "release notes"',
    'lookup': 'todo "Release plan"',
    'add': 'todo add task Work "Write code" "Write tests"',
    'schedule': 'todo schedule "Release plan" --at tomorrow --hide --reason "no time"',
    'hide': 'todo hide "Release plan" --at tomorrow --reason "no time"',
    'unhide': 'todo unhide "Release plan"',
    'move': 'todo move "Write tests" ""',
    'rename': 'todo rename "Release plan" --to New plan',
    'done': 'todo done "Release plan" --comment Reviewed',
    'reopen': 'todo reopen "Release plan"',
    'delete': 'todo delete "Release plan"',
    'comment': 'todo comment "Release plan" --comment Reviewed',
    'priority': 'todo priority "Release plan" P1',
    'report': 'todo report --since "2 days ago"',
    'init': 'todo init',
}


@dataclass(frozen=True)
class HelpRequest:
    command: str | None = None


def render_help(command=None):
    """Return help without consulting config, cache, or network."""
    command = ALIASES.get(command, command)
    if command is None:
        return ('todo: view work (now, waiting, someday); inspect (task, step, category, search); '
                'record progress (add, comment, done); maintain state (reopen, schedule, hide, '
                'unhide, priority, rename, move, delete, init); produce a report (report).\n'
                'Use todo help COMMAND. Globals: --color auto|always|never, --refresh, --clear-cache.\n')
    if command not in SYNOPSES:
        raise ValueError('unknown help command: ' + command)
    result = f'Usage: todo {SYNOPSES[command]}\nExample: {EXAMPLES[command]}\n'
    aliases = [a for a, c in ALIASES.items() if c == command]
    if aliases:
        result += 'Aliases: ' + ', '.join(aliases) + '\n'
    if command in ('add', 'done', 'comment'):
        result += ('Creation groups: a b joins to "a b"; "a b" c creates two values; '
                   "'a ' b creates a and b. Each --step/--comment group is independent.\n")
    if command in ('task', 'step'):
        result += ('Leading scalar actions take VALUE immediately: todo task --due "tomorrow 10:00" '
                   '"Release plan"; todo step --due tomorrow "Release plan" "Write summary".\n')
    return result
