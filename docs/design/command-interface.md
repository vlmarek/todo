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
todo step [--refresh] SELECTOR
todo category [--refresh]
todo search [--all] [--refresh] TEXT
```

`todo waiting` is the focused view of currently suppressed temporary-hidden
tasks and independently hidden steps. It excludes configured hidden categories
such as `Someday` and excludes items whose stored `waiting` label remains but
whose attention day has arrived.

`todo someday` is the focused view of every open task and open step in all
configured hidden categories. Completed items remain excluded.

Every read view (`now`, `waiting`, `someday`, `task`, `step`, `category`, and
`search`) accepts `--refresh`. Without it the command reads the local cache.
With it the command synchronizes from Todoist before validating and displaying
the result. A failed refresh exits nonzero and prints no normal view output.

## Discovery

`todo search TEXT` searches broadly across task titles, step titles, ordinary
descriptions, temporary-waiting reasons, and task comments. It only displays
matches and never selects an item or changes state. Its searchable fields do
not affect the title-only selector rules used by other commands.

Search examines open tasks and steps by default. `todo search --all TEXT`
expands the same search to completed tasks and steps as well; it does not mean
completed-only. Comments associated with an included task remain searchable.
The default open population includes items currently suppressed by `--hide` and
items in configured hidden categories. Search is not limited to actionable
work.

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

Search output shows only the matching task or step title, within its task group;
it does not print the matching description, waiting reason, comment, excerpt, or
field name. An item that matches through multiple fields is displayed once.

When a step matches but its parent task does not, the parent task title is still
shown as grouping context. The parent is not thereby considered a match, and
nonmatching sibling steps are omitted.

When a parent task matches, its nonmatching steps are not shown. Thus parent
context is added only upward for a matching step, never downward from a matching
parent to its steps.

An empty search prints `No matches.` and exits successfully. Finding no match is
not an error because search does not promise to select an item.

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
todo comment [--refresh] TASK
todo comment TASK COMMENT [COMMENT ...]
todo comment --edit TASK
todo done ITEM [TEXT]
todo reopen ITEM [TEXT]
```

`todo comment TASK` displays the selected open parent task's existing comments
without changing state and accepts `--refresh` like the other cached read views.
`todo comment TASK COMMENT [COMMENT ...]` creates one new task comment for each
trailing comment argument, in command-line order. Shell quoting defines the
boundary between comments. Steps cannot own comments, so both forms select
parent tasks only. Displayed comments are ordered chronologically from oldest to
newest.

Multiple comments are created sequentially. If Todoist accepts one or more and
a later creation fails, the accepted comments remain. The command stops, reports
which comments were created and which creation failed, and exits nonzero without
compensating deletion.

`todo comment --edit TASK` synchronizes first, resolves an open parent task, and
opens its current comments in `$EDITOR`. Saving a valid changed buffer applies
comment edits, deletions, and additions to Todoist. An unchanged buffer performs
no mutation and exits successfully. Steps and completed parent tasks are not
editable through this command.

The editor buffer uses marked blocks:

```text
[id: COMMENT_ID posted: TIMESTAMP]
existing comment text

[new]
new comment text
```

Each existing block carries its stable Todoist comment ID and displayed posting
timestamp. Each `[new]` block represents one new comment. Multiple existing and
new blocks may appear in the same buffer.

For an existing block, only `COMMENT_ID` identifies the Todoist comment. The
`posted: TIMESTAMP` value is informational and is ignored when applying the
buffer. Changing it does not attempt to alter Todoist history and does not by
itself invalidate the edit.

Deleting an existing comment requires removing its entire header-and-body block.
Removing only its header is not a deletion instruction and must not cause the
orphaned body to be merged into another comment.

The complete saved buffer is parsed and validated before any comment mutation.
Text outside a marked block, malformed or unknown headers, duplicate existing
IDs, or an existing ID that was not present in the generated buffer causes a
nonzero error with no Todoist changes.

Every retained existing block and every `[new]` block must contain a
non-whitespace body. An empty block invalidates the complete edit; it is never
interpreted as deletion and is never silently ignored. Deletion remains the
removal of the complete existing block.

After full local validation, the required Todoist comment operations are sent
sequentially. The command stops on the first API failure. Operations Todoist
already accepted remain in effect; the command reports the accepted operations
and the failed operation, exits nonzero, and performs no rollback.

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
todo add [--priority P|-p1|-p2|-p3|-p4] CATEGORY TASK [STEP ...]
todo add step TASK STEP [STEP ...]
todo rename ITEM NEW_NAME
todo priority ITEM P
todo delete [--yes] ITEM
todo category [--refresh]
```

A newly created parent task has P2 unless the creation command explicitly sets
another priority. A newly created step always receives its parent task's
effective priority at creation time. Step creation has no separate priority
override; `todo priority` may change the step afterward.

Task creation accepts both `--priority 1` through `--priority 4` and
`--priority P1` through `--priority P4`, with the `P` case-insensitive. The
convenience flags `-p1`, `-p2`, `-p3`, and `-p4` are equivalent. Supplying more
than one priority form in the same invocation is an option conflict and fails
before mutation.

`todo priority ITEM P` accepts `1` through `4` and `P1` through `P4` (with the
`P` case-insensitive) as equivalent forms. It can select either an open parent
task or an open step. Tasks and steps participate together in normal ambiguity
handling. Changing a step priority also changes its parent task's effective
priority when that step becomes or ceases to be the highest-priority open member
of the task tree.

After a successful priority change, the command prints the selected item title,
its previous priority, and its resulting priority. Setting the stored priority
to its existing value is a no-op error under the normal mutation rules.

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

After Todoist accepts a rename, the command prints the selected item type and
its previous and resulting titles. Renaming to the existing title is a no-op
error under the normal mutation rules.

`todo move TASK CATEGORY` supports open parent tasks only. Completed tasks are
not reopened temporarily for moving, and steps inherit their parent category
rather than being moved independently.

After Todoist accepts a move, the command prints the task title and its previous
and resulting categories. Moving a task to its current category is a no-op error.

Ordinary editing commands operate on open items only. This includes changing
priority, attention values, hiding policy, recurrence, reminders, comments,
titles, categories, and adding steps. Completed items may be reopened or
deleted, but are not temporarily reopened for editing.

Normal `todo task SELECTOR` searches open parent tasks only. Its details include
completed steps belonging to the selected open task. Completed parent tasks are
resolved only by commands that explicitly require them, currently `reopen` and
`delete`. Historical parent inspection may be added later if actual usage
justifies the additional selection and presentation complexity.

Task details display the parent task's single stored priority. They do not show
the derived effective priority used to order the task group; the priorities of
individual steps are visible on those steps.

Task details likewise display only the parent task's own attention date/time.
They do not show the derived effective attention value used to order the task
group. Each displayed step shows its own attention value.

Task details include every current task comment. `todo comment TASK` remains the
focused comment-only view and orders comments from oldest to newest.

Within task details, comments and open/completed steps are interleaved in one
reverse-chronological history. A step is positioned by its Todoist creation
timestamp (`added_at`); a comment is positioned by its current posting
timestamp. Newest records appear first. Each step retains its open/checked
completion marker and shows its own priority and attention value, but those
values do not affect ordering. Completing a step changes its marker in this
view; it does not add a separate task-detail history record.

Every history entry displays the timestamp that determines its position: the
step's creation timestamp or the comment's current posting timestamp. A
completed step still displays its creation timestamp in this timeline; its
completion state is conveyed by the marker. Timestamps are converted to and
displayed in the timezone of the machine running the command.

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
- `todo step SELECTOR` searches open steps only across every managed parent
  task. Parent tasks are not candidates. Steps with the same or similar titles
  under different parents participate in normal ambiguity handling. The
  selected step's detail view shows its parent task title and inherited category
  as context.
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

After a successful attention, reminder, priority, title, or category change,
print previous values when present and print the resulting values. Do not print
successful-change output until Todoist has accepted the mutation.

Warnings and errors go to stderr. Normal results and successful change details
go to stdout.
