# todo

`todo` is a personal command-line helper for Todoist.  Todoist remains the
source of truth; this tool keeps a local mirror under `~/.todo` for matching,
listing, and report generation.

It is not created by, affiliated with, or supported by Doist.

## Data model

- Todoist project: `Work`
- Todoist child projects under `Work`: dynamic categories
- Suggested initial categories: `Operations`, `Engineering`, `Admin`, `Someday`
- Hidden-from-now categories: configured in `~/.todo/config`, default `Someday`
- Todoist label: `waiting`
- Due date: "needs attention on this date"
- New task priority: P2 unless `-p1`/`-p2`/`-p3`/`-p4` is given
- Subtasks: next or missing steps
- Comments: report history

Local files:

```text
~/.todo/config
~/.todo/cache.json
~/.todo/report-cursor
~/.todo/lock
```

## Setup

```sh
todo init --token TODOIST_TOKEN
```

This creates or validates the `Work` project, default categories, and the
`waiting` label.  The token can also be supplied through `TODOIST_TOKEN`.

## Commands

```sh
todo help
todo help task
todo help due
todo help schedule
```

`todo help ...` displays the same help as `todo ... --help`.

```sh
todo --color=auto now
todo --color=always task website
todo --color=never now
```

Color defaults to `auto`: enabled for terminals, disabled for redirected
output, `NO_COLOR`, and `TERM=dumb`. The palette uses Solarized Dark colors.

```sh
todo category
todo category --refresh
todo category --add training
```

List or add categories. Categories are Todoist child projects under `Work`.

Shortcut commands cover common edits:

```sh
todo add task engineering "Update website dependencies" "build/test" "review"
todo add step website "send review"
todo add comment website "fixed test failure; staging deploy still running"
todo rename review "send review"
todo done review
todo close review
todo unclose review
todo delete --yes review
todo wait --due 2d website "waiting for review"
todo resume website "review returned"
todo due website 2d
todo due website "tomorrow 11:00"
todo due --reminder 10m website "friday 11:00"
todo move website engineering
todo priority website 1
todo comment website "fixed test failure; staging deploy still running"
```

`todo add task`, `todo add step`, and `todo add comment` are shorter forms
for the corresponding creation commands. `rename`, `done`/`close`, `unclose`,
`delete`, and `due` search task and direct step titles. If multiple items
match, an interactive terminal shows numbered choices. `schedule` is an alias
for `due`. `wait`, `resume`, `move`, `priority`, and `comment` are task-only
shortcuts.

```sh
todo task "website"
todo task --refresh "website"
todo task --add --due "friday 11:00" --reminder 10m -p1 engineering "Update website dependencies" "build/test" "review"
todo task --add -p1 engineering "Update website dependencies" "build/test" "review"
todo task --add engineering "Update website dependencies" "build/test" "review"
todo task --add operations "Deliver 224" "check dashboard table" "close build"
todo task --done website "deployed"
todo task --unclose website
todo task --delete website
todo task --delete --yes website
todo task --wait website "waiting for review"
todo task --wait --due friday website "waiting for review"
todo task --resume website "review returned; addressing comments"
todo task --priority website 1
todo task --due website 2d
todo task --due website 2bd
todo task --due website monday
todo task --due website ask
todo task --due --reminder 10m website "friday 11:00"
todo task --reminder 10m website
todo task --move website engineering
todo task --rename website "Website dependency update"
```

Show, add, complete, wait/resume, prioritize, set due dates, or move tasks.
New tasks default to P2; pass `-p1`, `-p2`, `-p3`, or `-p4` with `--add` to
override that initial priority.
`--new` is accepted as an alias for `--add`; `--close` and `--closed` are
accepted as aliases for `--done`.
`--unclose` is accepted as an alias for `--undone`.
Due dates accept Todoist text plus local shortcuts: `2d`, `4h`, `2bd`,
weekday names such as `monday`, ISO dates/times, `clear`, and `ask`.
`--due ask` prompts, previews the parsed due date, and accepts Enter/`y`,
`n`, or a different due input. Weekday names mean the next occurrence,
excluding today.
`--due` on `todo task --wait` sets the waiting follow-up date; if omitted,
the default is `default_wait_due` from `~/.todo/config`, falling back to
`2bd`. The value uses the same syntax as `--due`, so `1d` means one calendar
day and `1bd` means one business day. `clear` is rejected for waiting tasks.
`todo due ITEM DATE` sets or clears the due date for either a task or a direct
step. If ITEM matches multiple tasks or steps, an interactive terminal prompts
for a choice. `todo schedule` is accepted as an alias:

```sh
todo due website 2d
todo due website clear
todo due "send review" friday
todo due website "tomorrow 11:00"
todo due --reminder 10m website "friday 11:00"
todo schedule website "tomorrow 11:00"
todo schedule --reminder 10m website "friday 11:00"
```

`--reminder` creates a Todoist relative reminder for an item that has a due
date with a time. It accepts offsets such as `0`, `10m`, `2h`, `1d`, and
`at due`; repeat it to create multiple reminders. Reminders are displayed by
`todo task`, `todo step`, and `todo now`.

```sh
todo step website
todo step --refresh website
todo step --add --due "friday 11:00" --reminder 10m website "build/test"
todo step --add --due ask website "publish the release notes"
todo step --add website "build/test" "review" "publish" "deliver"
todo step --reminder 10m website "build/test"
todo step --done website review
todo step --unclose website review
todo step --delete website review
todo step --delete --yes website review
todo step --rename website review "send review"
```

Show steps, add one or more steps, mark one step done, rename one step, or
delete one step.
Step commands accept the same `--new`, `--close`, and `--closed` aliases.
`--unclose` is accepted as an alias for `--undone`.

```sh
todo comment website
todo comment --refresh website
todo comment website "fixed test failure; staging deploy still running"
todo comment --add website "fixed test failure; staging deploy still running"
todo comment --add website "unit tests passed" "staging still running"
todo comment --edit website
```

Shows task comments, creates one comment per text argument, or edits
all comments in `$EDITOR`.

The edit buffer uses bracket headers:

```text
[id: COMMENT_ID posted: TIMESTAMP]
existing comment text

[new]
new comment text
```

Removing an existing `[id: ...]` header deletes that comment. If the body is
left in place under the previous comment, it is merged into the previous
comment. Multiple `[new]` blocks are allowed.

```sh
todo now
todo now --refresh
todo now --category engineering
todo waiting
todo waiting --refresh
todo someday
todo someday --refresh
```

Show the daily work queue, all waiting tasks, or hidden-from-now tasks.
Recurring due dates display Todoist's recurrence string after `↻`. A
`starting ...` tail is hidden because the next due date is already shown.

```sh
todo report
todo report --final
todo report --since 2026-06-03T12:00:00Z --until 2026-06-09T12:00:00Z
```

Generate a plain-text report from the current report cursor to now. `--final`
prints the report and advances the cursor to now. Reports always sync Todoist
and fetch activity before generating the report. Comments added during the
report period are included as progress entries; edited comments are not
included.

If no cursor exists, the report starts at the current Wednesday 00:00 UTC.

Read-only display commands use the local cache by default. Use `--refresh` to
sync Todoist first. Commands that modify Todoist always refresh before making
the change.
Transient Todoist API failures are retried for safe reads and Sync API
requests. Each retry prints a warning to stderr. Task and comment mutations
use Sync API commands.

## Matching

Task selectors are free-form text matched against active task titles,
descriptions, and subtasks:

```sh
todo task website
```

If multiple tasks match, `todo` prints choices and asks for a number. The
number is valid only for that prompt.
