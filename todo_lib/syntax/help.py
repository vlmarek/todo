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
    'schedule': 'schedule SELECTOR... [--at WHEN] [--hide] [--reason VALUE] [--reminder OFFSET|keep]... [--reminder-at WHEN|keep]... | schedule SELECTOR... --reminder clear | schedule SELECTOR... clear',
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


DESCRIPTIONS = {
    'now': 'View actionable tasks and steps ordered by urgency. No arguments means now.',
    'waiting': 'View hidden work waiting for its attention day.',
    'someday': 'View work in configured hidden categories, rather than all undated tasks.',
    'task': 'Inspect a task by title; ambiguous selectors require a terminal choice.',
    'step': 'Inspect a step by title, preserving its parent path and category.',
    'category': 'List dynamic work categories, or create a category with --add.',
    'search': 'Search titles, descriptions, waiting reasons and own comments; --all includes retained completed work.',
    'add': 'Capture tasks, steps or categories. Validate the entire batch before creation.',
    'comment': 'View or record progress on the selected task or step. --edit uses the configured editor.',
    'done': 'Complete selected work; descendants complete before parents. Accepted work is never rolled back.',
    'reopen': 'Reopen recently completed work. Accepts no comment creation; recurring undo affects an occurrence.',
    'delete': 'Delete selected work after confirmation; --yes bypasses only this confirmation. Deletion is destructive. Previews describe saved data; use todo --refresh now for a more current preview.',
    'schedule': 'Set attention, hiding or reminders. Use clear to remove scheduling; relative reminders require timed attention; absolute reminders are independent.',
    'hide': 'Hide until a future attention day, with an optional reason. Inherited hiding applies to steps.',
    'unhide': 'Remove own hiding while preserving attention and reminders; parent hiding may still apply.',
    'priority': 'Set task or step priority P1 through P4. A new step copies its immediate parent priority once; later priority changes are independent.',
    'rename': 'Rename selected work; new sibling-title collisions are rejected. Imported duplicates use ordinary ambiguity selection.',
    'move': 'Move work to a category or parent, or promote a step to a task. Cycles and excessive depth are rejected.',
    'report': 'Preview categorized progress since the report cursor. --final writes and flushes output before advancing the cursor.',
    'init': 'Initialize the configured personal root and categories, preserving populated configuration.',
}

DETAILS = {
    'add': 'Optional task/step creation flags: --at WHEN, --hide, --reason VALUE, --reminder OFFSET, --reminder-at WHEN, --done. '
           'Completed creation cannot have attention, hiding or reminders. --close/--closed alias --done. '
           'Creation aliases: task/step --add/--new/--create, task --step PARENT TEXT..., category --add/--create, add comment.',
    'category': 'Creation alias: todo category --create "Client Work". Categories are direct children of the bound root.',
    'init': 'First-time setup from no directory or missing/empty config requires stdin and stdout terminals. '
            'Choose Todoist-derived roots/categories; suggestions are root Work, categories engineer, manager, someday, and hidden category someday. '
            'Enter a hidden token or use TODOIST_TOKEN, review the choices and give final confirmation. '
            'Repeat init preserves populated configuration and valid report cursor/history. '
            'A failed first publication may require consistent-set restoration. An explicit full-directory fresh start '
            'deletes ~/.todo, losing configuration, binding, pending local history and report boundary; remote data is unchanged.',
    'move': "The first argument is the source selector; remaining positional words join into one target. "
            "Examples: todo move 'Release plan' Engineering; todo move 'Write tests' --task 'Release plan'; "
            "todo move 'Write tests' ''. Retained forms: --category NAME, --to NAME, --task and --task= for promotion. "
            "Ambiguous targets present typed category/task/step choices. A step-to-category move remains invalid without explicit promotion.",
    'comment': 'In the editor, delete the entire comment block to delete a comment. Removing an interior header alone '
               'makes its remaining body part of the preceding block. Deleting all shown comments requires confirmation. '
               'Creation aliases: todo add comment SELECTOR TEXT...; todo comment --add SELECTOR TEXT...; '
               'todo comment --create SELECTOR TEXT....',
    'report': 'Absolute boundaries: YYYY-MM-DD, local YYYY-MM-DDTHH:MM[:SS], or aware RFC3339 including fractions. '
              'Relative boundaries: positive Nd ago or N days ago, retaining account-local wall time. --set-cursor requires confirmation or --yes; '
              'moving backward may repeat work and moving forward may skip work. Final reports bypass the pager.',
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
                'Usage: todo [--color=auto|always|never] [--refresh] [--clear-cache] COMMAND ...\n'
                'No arguments means todo now. Inspect a title with todo "Release plan". Use todo help COMMAND.\n'
                '--color VALUE also works; auto uses terminal detection with NO_COLOR and TERM=dumb.\n'
                'Task/step selection and previous receipt values use saved data. --refresh applies only to cache-backed reads; --clear-cache requires --refresh and deletes only current cache.\n'
                'Choices require stdin and stdout terminals. Exit: 0 success, 2 syntax, 1 failure, 130 SIGINT.\n')
    if command not in SYNOPSES:
        raise ValueError('unknown help command: ' + command)
    result = f'Usage: todo {SYNOPSES[command]}\n{DESCRIPTIONS[command]}\nExample: {EXAMPLES[command]}\n'
    if command in DETAILS:
        result += DETAILS[command] + '\n'
    aliases = [a for a, c in ALIASES.items() if c == command]
    if aliases:
        result += 'Aliases: ' + ', '.join(aliases) + '\n'
    if command in ('add', 'done', 'comment'):
        prefix = {'add': 'todo add task Work', 'done': 'todo done "Release plan" --comment',
                  'comment': 'todo comment "Release plan" --comment'}[command]
        result += f'Joined: {prefix} a b; split: {prefix} "a b" c; single-word batch: {prefix} \'a \' b.\n'
        result += ('Creation groups: a b joins to "a b"; "a b" c creates two values; '
                   "'a ' b creates a and b. Each --step/--comment group is independent.\n")
    if command == 'comment':
        result += ('Incoming blank comments display [no text] and survive an unchanged editor buffer. '
                   'Removing a block deletes by ID; new empty text and emptying nonblank text are rejected. '
                   'The unused final [new] starter is harmless. Attachment/preview metadata is ignored.\n')
    if command in ('task', 'step'):
        result += ('Leading scalar actions take VALUE immediately: todo task --due "tomorrow 10:00" '
                   '"Release plan"; todo step --due tomorrow "Release plan" "Write summary".\n'
                   'Other adjacent scalar aliases: --priority P1, --reminder 10m, --reminder-at "Friday 09:00", --rename "New name", '
                   '--move "New parent". A multiword date, new name or move destination is one quoted shell argument. '
                   'Creation: --add/--create/--new; lifecycle: --done/--close/--closed, --undone/--unclose, --delete; '
                   'progress: --comment; scheduling: --at/--due/--schedule, --wait/--waiting; priority: -p1 through -p4 or --p1 through --p4.\n'
                   '--wait/--waiting retain a reason operand and require an explicit --at date; they do not choose a default date.\n')
        selectors = '"Release plan"' if command == 'task' else '"Release plan" "Write summary"'
        for action, value in (('priority', 'P1'), ('reminder', '1h'), ('rename', '"New name"'), ('move', '"Client Work"')):
            result += f'Alias example: todo {command} --{action} {value} {selectors}\n'
        if command == 'task':
            result += 'Add steps to a task or step parent: todo task --step "Release plan" "Write summary".\n'
    if command in ('schedule', 'hide', 'add'):
        result += ('Scalar values support --option=VALUE and --option VALUE. Quote multiword dates, category names and reasons. '
                   '--hide is boolean; --hide --reason "no time" sets a reason and --reason= removes only the reason.\n')
    if command in ('schedule', 'hide', 'task', 'step', 'add'):
        result += ('Each attention (--at/--due/--schedule) or --reminder-at value may end in an IANA location zone or UTC. '
                   'Quote the whole value: --at "2026-11-12 09:00 America/New_York" or '
                   '--reminder-at="Friday 08:30 Asia/Tokyo". Separated and equals forms apply to task/step actions and creation too. '
                   'Each omitted zone uses the account timezone independently. Named zones allow ISO local wall times; '
                   'without a zone ISO attention datetimes require an offset or Z. '
                   'Calendar dates/arithmetic use that value’s zone; minutes/hours are elapsed. '
                   'Unknown location zones and locally ambiguous/nonexistent times fail before writes. '
                   'Other English wording goes to Todoist with its named zone; CET/CEST/CST/EST stay in the wording without local mappings. '
                   'Attention may be date-only; absolute reminders require exact time. Moving an occurrence retains its existing recurrence zone.\n')
    if command in ('schedule', 'task', 'step', 'add'):
        result += ('Reminders form one complete set: repeat/mix --reminder OFFSET (before timed task due; 0m is at due) '
                   'and --reminder-at WHEN (independent exact time, also on undated/date-only tasks). '
                   'Absolute WHEN uses its named zone or account time: 2h is elapsed time, calendar units retain wall time; ambiguous/nonexistent local DST times fail. '
                   'Unknown/recurring English expressions such as "every Monday at 09:00" go to Todoist; exact time is required. '
                   'Omitting both options preserves all reminders. --reminder keep retains relative IDs/metadata; '
                   '--reminder-at keep retains absolute IDs/metadata. Keep is lowercase and occurs once per type. '
                   'Only keep or complete locally established matches guarantee retained IDs; equivalent Todoist-parsed wording may create a new ID. '
                   'Replacement removals show schedules, additions (including expression (Todoist): input) and keep hints before any writes. '
                   'Confirmation defaults to cancel and noninteractive removal replacement refuses; there is no --yes bypass. '
                   'Example: todo schedule "Release plan" --reminder keep --reminder-at "Friday 09:00". '
                   'Example: todo schedule "Release plan" --reminder-at keep --reminder 30m. '
                   'Direct --reminder clear removes both reminder types; schedule SELECTOR clear also removes attention, recurrence and hiding. '
                   '--reminder-at clear is invalid. Task/step leading --reminder-at VALUE takes its adjacent value before selector operands.\n')
    if command in ('task', 'step', 'add', 'comment', 'done', 'reopen', 'delete', 'schedule', 'hide', 'unhide', 'priority', 'rename', 'move', 'search'):
        result += ('Task/step selection and preflight use saved data. Previous receipt values are last-saved values. '
                   'Use todo --refresh now before retrying when current context is needed.\n'
                   '--literal ARG preserves an argument without option interpretation.\n')
    return result
