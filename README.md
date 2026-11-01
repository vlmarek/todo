# todo

A Python standard-library CLI for personal Todoist work, nested steps, comments,
scheduling and reports. Verified target: Linux/amd64, CPython 3.11. Docker is the
build/verification environment; the installed CLI needs no Docker or Python packages.

Copy the executable and **entire sibling module tree** into a directory on PATH:

```sh
mkdir -p "$HOME/.local/bin"
cp -p todo "$HOME/.local/bin/todo"
cp -R todo_lib "$HOME/.local/bin/todo_lib"
export PATH="$HOME/.local/bin:$PATH"
todo help
todo init
```

Use an empty destination for a new installation, or replace the whole existing
`todo_lib` tree together with the matching launcher while no todo processes run.
Keep `todo` executable. Do not copy tests or install dependencies. `python3` on
PATH must be CPython 3.11; account timezone data must be available. GNU less is
optional for users and required in the pinned verification image.

`todo init` guides terminal setup when configuration is absent or empty. A
populated configuration is validated and used without rewriting it. Run `todo now`
for saved work, `todo --refresh now` to retrieve current work, and `todo help COMMAND`
for exact grammar and aliases. Reads use saved state unless refresh is requested.

See [configuration, backup and recovery](docs/user/operations.md), the
[explicitly user-run disposable-account smoke](docs/user/smoke.md), and
[observed acceptance evidence](docs/implementation/acceptance-evidence.md).

Offline release verification is `./scripts/verify-clean`: one complete
`scripts/check` suite, separate unchanged copied-runtime probes, real-less PTY
checks, and entry/end Git status and artifact checks. It uses temporary local state,
synthetic tokens and controlled transport only. It never runs the live smoke.

Rename, schedule (also `due` and `wait`) and hide use the first remaining
argument as the selector and join every following value argument with one space:

```sh
todo rename jklu New task title
todo schedule jklu tomorrow 10:00 --reminder 10m
todo hide 'Release plan' next week --reason 'no time'
```

Options may precede, interrupt or follow operands; their scalar values never
become operands. A quoted selector is one contiguous phrase. For independent
selector terms, retain the explicit boundary and quote each multiword scalar:

```sh
todo rename nightly python --to New task title
todo schedule nightly python --at 'tomorrow 10:00' --reminder 10m
todo hide nightly python --at tomorrow
```

Reminders do not change shorthand parsing. `schedule 'Release plan' --reminder
10m` changes only reminders; `schedule jklu tomorrow --reminder clear` changes
attention and clears only reminders. `schedule 'Release plan' clear` removes
attention, recurrence, reminders and own hiding/reason only when `clear` is the
sole unescaped value argument. It cannot combine with reminders, hiding or reason
changes. `schedule A B clear` requests attention `B clear` for selector `A`.
`--literal clear` prevents full clear; with an explicit date, positional `clear`
is a selector term. Use `--literal --to` for a literal rename value.

The compatibility cost: old unmarked multi-term schedule/hide commands now use
the extra arguments as attention. `schedule nightly python --reminder 10m`
selects `nightly` and requests attention `python`; a rejected date never retries
another selector split. Use explicit date options for independent selector terms,
or quote a contiguous phrase for reminder-only/full-clear selection. `hide
SELECTOR` reuses existing future attention, recurrence and reminders; schedule
without a date needs a reminder operation or full clear. `--hide` requires supplied
attention; canonical `wait` does not imply hiding. Noun actions still take adjacent
scalars, for example `todo task --due 'tomorrow 10:00' 'Release plan'`.

Reminders use a complete desired set. Repeat and mix `--reminder OFFSET` (before
an exact task due, with `0m` meaning at due) and `--reminder-at WHEN` (an independent
exact schedule, including on undated tasks). Both accept `--option=VALUE` and
`--option VALUE`. For example:

```sh
todo add task Work 'Read proposal' --reminder-at 'Friday 09:00'
todo schedule 'Team meeting' --reminder keep --reminder-at 'every Monday at 09:00'
todo task --reminder-at '2h' 'Read proposal'
todo step --reminder-at='Friday 09:00' 'Team meeting' 'Prepare notes'
todo schedule 'Team meeting' --reminder-at keep --reminder 30m
```

Omitting both reminder options preserves both types. Lowercase `keep`, once per
type, preserves every reminder of that type, including IDs and original metadata;
on an empty type it contributes nothing. Explicit values retain existing IDs only
when the application can establish a complete scheduling match. Unknown and
recurring English expressions go to Todoist, with no preflight parser request.
Equivalent provider-parsed wording can replace a reminder with a new ID. A common
next firing time does not establish recurrence or floating/fixed equivalence.

Absolute schedules use the synchronized command time and account timezone: `2h`
means two elapsed hours, calendar units retain wall time, and locally ambiguous or
nonexistent DST times are refused. Date-only input is invalid for an absolute
reminder. Receipts show the actual reconciled exact schedule; unexpected date-only
normalization is a partial failure, without rollback of accepted changes.

If replacement omits existing reminders, the command previews removals, additions,
unresolved `expression (Todoist): ...` values and retention hints before any write.
Confirmation defaults to cancellation; blank, EOF and decline cancel, and
noninteractive removal replacement refuses without prompting. There is no `--yes`
bypass. Additions that retain everything need no confirmation. `--reminder clear`
directly clears both reminder types; `schedule SELECTOR clear` also clears task
attention, recurrence and hiding. `--reminder-at clear` is invalid. Rescheduling a
task preserves absolute reminders independently; moving to a date-only task due
requires explicitly clearing/replacing surviving relative reminders, optionally
using `--reminder-at keep`.

Imported task/step titles may duplicate siblings; ordinary ambiguity selection
still applies. New CLI title collisions are rejected. Imported line breaks and
tabs in titles are escaped in views, prompts and receipts. Hidden-category work
stays out of normal `now`, even when overdue. A waiting label without an attention
date is inactive; malformed or orphaned reason text is preserved literally.
Valid hiding needs no reason, and a child cannot become actionable before its
hidden ancestor.

Incoming blank/default comments display `[no text]` and can qualify as report
activity. Leaving them unchanged in the editor preserves their IDs; deleting a
block deletes that comment. New empty comments and emptying existing nonblank
text are rejected; the unused final starter is harmless. Attachment/preview
metadata is ignored, and text updates send the comment ID and text only. Offline
verification does not establish live attachment preservation, notification
delivery or recurring reminder advancement.

Task and step creation accept `--priority P` / `--priority=VALUE` (1 through 4
or case-insensitive P1 through P4), `-p1` through `-p4`, and `--p1` through
`--p4`. P1 is highest. New tasks default to P2. Omitted step priority copies
the saved pre-creation parent's effective priority, including open descendants.
One explicit priority applies to all new siblings across the request's text
groups. Each new item's priority is independent of later parent/sibling changes.

```sh
todo step --add 'Release plan' --p1 'Write summary' --at monday
todo add step --priority=P4 'Release plan' --step 'Write summary' --step 'Check links'
todo task --step 'Release plan' 'Review results' -p1
```
