# Development Handoff

This repository contains `todo`, a dependency-free Python command-line helper
for Todoist.

Todoist remains the source of truth. The CLI keeps local state in `~/.todo`
for fast matching, display, reporting, and recent command context.

## Goals

- keep day-to-day Todoist work manageable from a terminal
- make tasks easy to find by short free-form names
- track active, waiting, someday, and completed work
- support task steps, comments, priorities, due dates, and categories
- support Todoist relative reminders for due tasks and steps
- generate a plain-text weekly report draft
- keep Todoist web, mobile, and desktop useful alongside the CLI

## Data Model

Todoist structure:

- top-level project: `Work`
- categories: Todoist child projects under `Work`
- default categories: `Operations`, `Engineeringing`, `Admin`, `Someday`
- categories are dynamic; `todo category` discovers child projects
- hidden categories are configured in `~/.todo/config`
- default hidden category: `Someday`

State model:

- active: open task in a non-hidden category
- waiting: open task with Todoist label `waiting`
- someday: open task in a hidden category such as `Someday`
- done: completed Todoist task

Only one label is intentionally used:

```text
waiting
```

Due dates mean:

```text
needs attention on this date
```

For waiting tasks, the due date is the follow-up date. Default waiting
follow-up comes from `default_wait_due` in `~/.todo/config`, falling back to
`2bd`. The value uses the same syntax as `--due`, so `1d` means one calendar
day and `1bd` means one business day.

## Local Files

All local tool files are under:

```text
~/.todo
```

Expected files:

```text
~/.todo/config
~/.todo/cache.json
~/.todo/report-cursor
~/.todo/step-context.json
~/.todo/lock
```

The Todoist token is stored in `~/.todo/config` or supplied as
`TODOIST_TOKEN`. Do not commit tokens, cache files, or local state.

## Implementation

The tool is a single Python script:

```text
todo
```

Tests are in:

```text
tests/test_todo.py
```

Validate with:

```sh
python3 -m py_compile todo
python3 -m unittest discover -s tests
```

No third-party Python dependencies are required.

## Command Behavior

Read-only display commands use the local cache by default:

```sh
todo task TASK
todo step TASK
todo comment TASK
todo now
todo waiting
todo someday
todo search TEXT
```

Most read-only commands accept `--refresh` to sync Todoist first.

Mutation commands sync before changing Todoist and require Todoist access.
Task and comment mutations use Todoist Sync API commands, so transient Sync
API failures can be retried with command UUIDs.

Common shortcut commands:

```sh
todo rename ITEM NEW_NAME
todo done ITEM
todo close ITEM
todo unclose ITEM
todo delete [--yes] ITEM
todo wait [--due DATE] TASK REASON
todo move TASK CATEGORY
todo priority TASK P
todo comment TASK TEXT [TEXT ...]
```

`rename`, `done`/`close`, `unclose`, and `delete` search both parent task
titles and direct step titles. Ambiguous matches print a numbered choice list
in an interactive terminal and refuse to guess non-interactively. `wait`,
`move`, `priority`, and `comment` are task-only shortcuts.

Rename commands update Todoist item titles:

```sh
todo task --rename TASK NEW_NAME
todo step --rename TASK STEP NEW_NAME
```

Completed tasks or steps are reopened for the rename and then closed again.

`todo report` always syncs Todoist and fetches activity before generating
output. `todo report --final` also advances the report cursor.

## Matching

Task selectors are free-form text matched against active task titles,
descriptions, and direct steps. If exactly one task matches, the command uses
it. If multiple tasks match in an interactive terminal, the CLI prompts for a
number. In non-interactive mode, ambiguous mutation commands refuse to choose.

Numbers are only valid for the command that just printed the numbered list.

## Due Dates

Due shortcuts include:

```text
2d
4h
2bd
monday
fri 15:30
2026-06-16
2026-06-16 15:00
clear
ask
```

`--due ask` opens an interactive prompt. Weekday names mean the next occurrence
and do not count today.

Recurring due dates display Todoist's raw recurrence string after `↻`. A
`starting ...` tail is hidden because the next due date is already shown.

## Reminders

Reminder data is synced into the local cache from Todoist's `reminders`
resource and displayed by task, step, and now views.

Supported creation forms:

```sh
todo task --add --due "friday 11:00" --reminder 10m Engineering "meeting"
todo task --due --reminder 10m meeting "friday 11:00"
todo task --reminder 10m meeting
todo step --add --due "friday 11:00" --reminder 10m meeting "join call"
todo step --reminder 10m meeting "join call"
```

`--reminder` creates Todoist relative reminders only. Offsets accept `0`,
`10m`, `2h`, `1d`, combined forms such as `1d 2h 30m`, and `at due`.
The target item must have a due date with a time; date-only due values are
rejected before calling Todoist.

## Reports

Reports are grouped by section, then category:

```text
Finished
Progress
Waiting
```

Report inputs:

- finished tasks: Todoist completed activity events since the report cursor
- progress: relevant activity since the report cursor
- progress comments: note/comment activity where Todoist reports
  `object_type=note` and `event_type=added`; note updates/edits are ignored
- waiting: waiting tasks whose follow-up date is due in the report window

`todo report --final` prints the report and advances `~/.todo/report-cursor`.

## Public Repository Notes

This public copy should stay generic:

- do not add real company, client, project, bug, review, host, or meeting data
- keep examples fictional
- do not commit `~/.todo` files
- do not commit access tokens or generated cache data
