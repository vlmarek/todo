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

```sh
todo task "website"
todo task --refresh "website"
todo task --add --due 7d -p1 engineering "Update website dependencies" "build/test" "review"
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
todo task --move website engineering
```

Show, add, complete, wait/resume, prioritize, schedule, or move tasks.
`--new` is accepted as an alias for `--add`; `--close` and `--closed` are
accepted as aliases for `--done`.
`--unclose` is accepted as an alias for `--undone`.
Due dates accept Todoist text plus local shortcuts: `2d`, `4h`, `2bd`,
weekday names such as `monday`, ISO dates/times, `clear`, and `ask`.
`--due ask` prompts, previews the parsed due date, and accepts Enter/`y`,
`n`, or a different due input. Weekday names mean the next occurrence,
excluding today.
`--due` on `todo task --wait` sets the waiting follow-up date; if omitted,
the default is two business days. `clear` is rejected for waiting tasks.

```sh
todo step website
todo step --refresh website
todo step --add --due 7d website "build/test"
todo step --add --due ask website "publish the release notes"
todo step --add website "build/test" "review" "publish" "deliver"
todo step --done website review
todo step --unclose website review
todo step --delete website review
todo step --delete --yes website review
```

Show steps, add one or more steps, mark one step done, or delete one step.
Step commands accept the same `--new`, `--close`, and `--closed` aliases.
`--unclose` is accepted as an alias for `--undone`.

```sh
todo comment website
todo comment --refresh website
todo comment --add website "fixed test failure; staging deploy still running"
todo comment --add website "unit tests passed" "staging still running"
todo comment --edit website
```

Shows task comments, creates one comment per `--add` text argument, or edits
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
and fetch activity before generating the report.

If no cursor exists, the report starts at the current Wednesday 00:00 UTC.

Read-only display commands use the local cache by default. Use `--refresh` to
sync Todoist first. Commands that modify Todoist always refresh before making
the change.
Transient Todoist API failures are retried for safe reads and Sync API
requests. Each retry prints a warning to stderr.

## Matching

Task selectors are free-form text matched against active task titles,
descriptions, and subtasks:

```sh
todo task website
```

If multiple tasks match, `todo` prints choices and asks for a number. The
number is valid only for that prompt.
