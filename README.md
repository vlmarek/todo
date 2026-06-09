# todo

`todo` is a personal command-line helper for Todoist.  Todoist remains the
source of truth; this tool keeps a local mirror under `~/.todo` for matching,
listing, and report generation.

It is not created by, affiliated with, or supported by Doist.

## Data model

- Todoist project: `Work`
- Todoist sections under `Work`: dynamic categories
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

This creates or validates the `Work` project, default sections, and the
`waiting` label.  The token can also be supplied through `TODOIST_TOKEN`.

## Commands

```sh
todo categories
todo category add training
```

List or add categories. Categories are Todoist sections under `Work`.

```sh
todo add engineering "Update website dependencies" -p 1
todo add operations "Deliver 224" --due 2026-06-09 -p 1
todo add someday "Create wiki for AI setup"
```

Add a top-level work item.

```sh
todo step website
todo step website "build/test" "review" "publish" "deliver"
todo check website review
```

Show steps, add one or more steps, or mark a step done.

```sh
todo comment website "fixed test failure; staging deploy still running"
```

Adds a Todoist comment with the `Progress:` prefix.

```sh
todo wait website "waiting for review"
todo wait website "waiting for BA approval" --due 2026-06-15
todo resume website "review returned; addressing comments"
```

`wait` adds the `waiting` label, sets the due date to a follow-up date, and
adds a `Waiting:` comment. The default follow-up is two business days.

`resume` removes `waiting`, clears the due date, and adds a `Resumed:` comment.

```sh
todo done website "integrated; publish accepted"
```

If open subtasks exist, the command prints them and asks whether to mark all
steps done before completing the parent task. Answering no leaves everything
unchanged.

```sh
todo priority website 1
todo due website tomorrow
todo due website clear
todo move website engineering
```

Adjust priority, attention date, or category.

```sh
todo now
todo now --all
todo now --category engineering
todo waiting
todo waiting --all
todo someday
```

Show active tasks, waiting tasks, or hidden-from-now tasks.

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
todo comment website "fixed tests"
```

If multiple tasks match, `todo` prints choices and asks for a number. The
number is valid only for that prompt.
