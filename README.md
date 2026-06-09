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
todo category
todo category --add training
```

List or add categories. Categories are Todoist child projects under `Work`.

```sh
todo task "website"
todo task --add --due 7d -p1 engineering "Update website dependencies" "build/test" "review"
todo task --add -p1 engineering "Update website dependencies" "build/test" "review"
todo task --add engineering "Update website dependencies" "build/test" "review"
todo task --add operations "Deliver 224" "check dashboard table" "close build"
todo task --done website "deployed"
todo task --wait website "waiting for review"
todo task --resume website "review returned; addressing comments"
todo task --priority website 1
todo task --due website 2d
todo task --move website engineering
```

Show, add, complete, wait/resume, prioritize, schedule, or move tasks.
`--new` is accepted as an alias for `--add`; `--close` and `--closed` are
accepted as aliases for `--done`.

```sh
todo step website
todo step --add --due 7d website "build/test"
todo step --add website "build/test" "review" "publish" "deliver"
todo step --done website review
```

Show steps, add one or more steps, or mark a step done.
Step commands accept the same `--new`, `--close`, and `--closed` aliases.

```sh
todo comment website
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
todo now --category engineering
todo waiting
todo someday
```

Show the daily work queue, all waiting tasks, or hidden-from-now tasks.

```sh
todo report
todo report --final
todo report --since 2026-06-03T12:00:00Z --until 2026-06-09T12:00:00Z
```

Generate a plain-text report from the current report cursor to now. `--final`
prints the report and advances the cursor to now.

If no cursor exists, the report starts at the current Wednesday 00:00 UTC.

## Matching

Task selectors are free-form text matched against active task titles,
descriptions, and subtasks:

```sh
todo task website
```

If multiple tasks match, `todo` prints choices and asks for a number. The
number is valid only for that prompt.
