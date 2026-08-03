# Command interface

Status: Initial outline

This document will define the complete public CLI. The forms below record the
parts established so far; omitted commands still require documentation.

## Work views

```console
todo now
todo now --all
todo now --refresh
todo waiting [--refresh]
todo someday [--refresh]
todo task [--refresh] SELECTOR
todo category [--refresh]
todo search [--all] [--refresh] TEXT
```

`todo waiting` is the focused view of currently suppressed temporary-hidden
tasks and independently hidden steps. It excludes configured hidden categories
such as `Someday` and excludes items whose stored `waiting` label remains but
whose attention day has arrived.

`todo someday` is the focused view of every open task and open step in all
configured hidden categories. Completed items remain excluded.

Every read view (`now`, `waiting`, `someday`, `task`, `category`, and `search`)
accepts `--refresh`. Without it the command reads the local cache. With it the
command synchronizes from Todoist before validating and displaying the result.
A failed refresh exits nonzero and prints no normal view output.

## Discovery

`todo search TEXT` searches broadly across task titles, step titles, ordinary
descriptions, temporary-waiting reasons, and task comments. It only displays
matches and never selects an item or changes state. Its searchable fields do
not affect the title-only selector rules used by other commands.

Search examines open tasks and steps by default. `todo search --all TEXT`
expands the same search to completed tasks and steps as well; it does not mean
completed-only. Comments associated with an included task remain searchable.

Search results are grouped by parent task. Task groups are sorted by priority
(P1 through P4), lowercase category name, and lowercase task title. Matching
steps within a task are sorted by their own priority and lowercase step title.
Attention dates do not participate in search-result ordering.

Search uses the same argument structure as selectors: one quoted argument is a
contiguous phrase, while multiple unquoted arguments are independent terms that
must all match but may occur in any order and need not be contiguous. Matching
is case-insensitive.

One individual searchable field must satisfy the complete query. Terms cannot
be combined across a title, description, waiting reason, and comment, or across
multiple comments. Each comment is a separate searchable field.

## Initialization

```console
todo init [--token TOKEN]
```

`todo init` creates local configuration as needed and provisions the configured
root project, configured initial category projects, and Todoist `waiting` label
when absent. Provisioning is explicit to `init`; ordinary commands never create
missing structural objects implicitly.

## Progress and completion

```console
todo comment TASK COMMENT
todo done ITEM [TEXT]
todo reopen ITEM [TEXT]
```

Completing a parent task that still has open steps requires interactive
confirmation to complete all open steps first. Without explicit affirmative
confirmation, no item is completed.

Optional `TEXT` is supported when the selected item is a task and is stored as
a task comment prefixed with `Done: `. It is not valid for a step.

`todo reopen ITEM` changes only the selected task or step. Reopening a parent
does not reopen any of its completed steps.

A successful reopen always adds a progress comment. Task comments use
`Reopened` or `Reopened: TEXT`; step reopenings add `Reopened step: STEP` or
`Reopened step: STEP: TEXT` to the parent task. `TEXT` is optional.

## Creation and maintenance

```console
todo add CATEGORY TASK [STEP ...]
todo add step TASK STEP [STEP ...]
todo rename ITEM NEW_NAME
todo delete [--yes] ITEM
todo category [--refresh]
```

`todo category` lists categories alphabetically using lowercase comparison.
Creating a category fails before mutation when any existing category name is
equal under case-insensitive comparison.

Creating a task fails if the target category already contains an open task with
the same case-insensitive title. The duplicate check occurs before Todoist
mutation. This rule does not prohibit the same title in a different category.

If only completed tasks in the target category have the same case-insensitive
title, creation is allowed but the command prints a warning to stderr before
mutation. The warning identifies that completed title reuse is occurring.

Creating a step fails before mutation if its parent already contains an open
step with the same case-insensitive title. The same title under another parent
task is allowed.

If only completed steps under the selected parent have the same
case-insensitive title, creation is allowed after printing a warning to stderr.

Renaming an open task or step is subject to the same uniqueness rules as
creation. A rename that would collide case-insensitively with another open task
in the category or open step under the parent fails before Todoist mutation.

`todo rename` supports open tasks and steps only. Completed items are not
reopened temporarily for editing; attempting to rename one fails without
mutation.

`todo move TASK CATEGORY` supports open parent tasks only. Completed tasks are
not reopened temporarily for moving, and steps inherit their parent category
rather than being moved independently.

Ordinary editing commands operate on open items only. This includes changing
priority, attention values, hiding policy, recurrence, reminders, comments,
titles, categories, and adding steps. Completed items may be reopened or
deleted, but are not temporarily reopened for editing.

Normal `todo task SELECTOR` searches open parent tasks only. Its details include
completed steps belonging to the selected open task. Completed parent tasks are
resolved only by commands that explicitly require them, currently `reopen` and
`delete`. Historical parent inspection may be added later if actual usage
justifies the additional selection and presentation complexity.

`todo delete ITEM` requests interactive confirmation before mutation. Only an
explicit affirmative response authorizes deletion. `--yes` skips the prompt
and is required for non-interactive deletion. Cancellation, end of input, or a
non-interactive invocation without `--yes` leaves the item unchanged and exits
nonzero.

Deletion is supported for both open and completed tasks and steps. After
confirmation, the command uses Todoist's direct delete operation. It does not
reopen the selected item or its parent before deletion and does not implement
local-only deletion. If Todoist rejects the operation, the command reports the
API failure and leaves local state consistent with Todoist.

When the selected item is a parent task, the confirmation preview lists the
parent and all of its open and completed steps with their completion markers.
The prompt makes clear that confirming deletion removes the entire displayed
task tree. Confirmation is requested only after the complete scope is printed.
`--yes` skips only the confirmation prompt; it does not suppress this deletion
scope output, which is printed before the mutation in all modes.

## Attention and reminders

`wait`, `due`, and `schedule` are equivalent aliases.

```console
todo wait [--hide] [--reminder OFFSET ...] ITEM DATE
todo due [--hide] [--reminder OFFSET ...] ITEM DATE
todo schedule [--hide] [--reminder OFFSET ...] ITEM DATE

todo wait ITEM clear
todo wait --reminder clear ITEM
```

The equivalent `due` and `schedule` clearing forms are also accepted.

Every temporary-hiding form requires a non-empty reason after the item and
date. The reason is stored in a marked block inside the selected task or step
description and is shown in details and reports. Missing or whitespace-only
reasons fail before mutation.

Supplying a date without `--hide` removes the item's own hiding policy.
Supplying `--hide` enables it. Clearing the item removes attention, recurrence,
reminders, and its own hiding policy.

One or more supplied `--reminder OFFSET` arguments replace the complete
existing reminder set. Repeating the option defines multiple reminders in the
replacement set. `--reminder clear ITEM` removes the complete set without
changing the attention value.

Changing an attention value without a reminder option preserves all existing
reminders. The success output prints any retained reminder set as informational
state in addition to the previous and resulting attention values.

## Reporting

```console
todo report
todo report --final
todo report [--since TIMESTAMP] [--until TIMESTAMP]
```

`--since` and `--until` override report interval boundaries for debugging and
recovery. Without them, the interval begins at the stored cursor and ends at
the report invocation's captured current time.

`--final` cannot be combined with `--since` or `--until`. Interval overrides
are preview/debugging-only and never change the stored report cursor. Invalid
option combinations fail before synchronization or report generation.

## Selection

Selectors may match tasks or steps as allowed by the command. If a selector is
ambiguous in an interactive terminal, the command displays matching choices
and asks the user to select one. A non-interactive mutating command must refuse
to guess.

An exact title match does not take precedence over other matching results. For
example, selector `Deploy` remains ambiguous when both `Deploy` and
`Deploy staging` match, and both are presented for selection.

Task and step selectors are case-insensitive. This does not change category
matching, which remains case-sensitive.

Quoting controls selector structure:

- A single argument such as `todo task "deploy staging"` is one phrase and
  matches that contiguous phrase.
- Multiple arguments such as `todo task deploy staging` are independent terms.
  Every term must match, but the terms may occur in any order and need not be
  contiguous.

Shell quoting therefore affects matching semantics and is not merely a way to
preserve spaces in one equivalent selector string.

Candidate type depends on the command form:

- `todo task SELECTOR` searches parent tasks only. A matching step is not
  returned as the selected item.
- An implicit top-level selector such as `todo review` searches tasks and steps
  as independent candidates. A step may match even when its parent task title
  does not contain the selector.

If an implicit selector matches both tasks and steps, all matching candidates
participate in normal ambiguity handling.

Normal item selection matches titles only. Task descriptions, waiting metadata,
and comments do not make a task or step match a selector. `todo search` has
broader searchable fields, but does not change targeting semantics for mutation
and inspection commands.

## Mutation output

After a successful attention or reminder change, print previous values when
present and print the resulting values. Do not print successful-change output
until Todoist has accepted the mutation.

Warnings and errors go to stderr. Normal results and successful change details
go to stdout.
