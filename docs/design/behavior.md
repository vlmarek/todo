# Behavioral specification

Status: Proposed

## `todo now`

`todo now` shows all actionable tasks and every actionable open step belonging
to them. Step presentation makes its parent task clear.

It excludes:

- completed tasks and steps
- tasks in configured hidden categories
- future-hidden tasks and their steps
- future-hidden steps

`todo now --all` shows all open managed tasks and their open steps, including
future-hidden work and configured hidden categories. It still excludes
completed work.

Completed steps are visible in `todo task SELECTOR` with a checked square.

### Urgency ordering

Task groups are sorted using these keys in order:

1. Due bucket:
   1. overdue
   2. due today
   3. everything else
2. Effective priority: P1, P2, P3, P4
3. Effective attention value: earlier first
4. Category name, compared lowercase
5. Task title, compared lowercase

The effective attention value and priority include the parent task and all its
open steps as defined in `domain-model.md`.

For the effective-attention sort key, an absent attention value is treated as
infinitely far in the past. Consequently, among items in the same due bucket
and with the same effective priority, an undated item sorts before every dated
item.

Open steps displayed within a task group use the same urgency keys: due bucket,
step priority, step attention value, and lowercase title. A step has no separate
category key because it inherits its parent task's category. This ordering
replaces Todoist's manual step order in `todo now`.

Priority precedes the exact attention value within a bucket. For example, when
both items are due today, a P1 item due at 17:00 sorts before a P2 item due at
09:00. The same rule applies in the overdue bucket: a P1 item overdue by one
day sorts before a P2 item overdue by one month.

## Attention values and hiding

`wait`, `due`, and `schedule` are intended to be equivalent aliases.

Setting an attention value without `--hide` makes the item's own hiding policy
false. Setting it with `--hide` makes the policy true.

The own hiding policy is persisted as the Todoist `waiting` label. Setting an
attention value without `--hide` removes that label; setting it with `--hide`
adds it. Clearing the attention state also removes it. The label remains after
the attention day arrives and is removed only by an explicit later mutation.

The `waiting` label is required only by operations that add a hiding policy.
If it is missing, `--hide` fails before item mutation and directs the user to
run `todo init`. Unrelated commands do not perform or fail this label-existence
check. Removing an existing hiding policy does not require the label resource
to still exist.

A hidden task or step must store a non-empty hiding reason in a marked metadata
block in its Todoist description. Setting or changing temporary hiding updates
that block without replacing ordinary description text. Removing the hiding
policy also removes the metadata block while preserving the ordinary
description.

For a hidden item, list visibility begins at the start of its local attention
day, not at an exact attention time. Exact time remains relevant to display,
ordering within the day, and reminders.

Changing a value prints any previous attention value and the resulting value.
Changing reminders prints previous reminders, when present, and resulting
reminders. Output is printed only after successful mutation.

### Parent and step validation

If a task is hidden until Friday, a step attention value before Friday is
invalid, whether or not the step uses `--hide`.

| Hidden parent day | Step attention | Valid |
|---|---|---:|
| Friday | Thursday | No |
| Friday | Friday 10:30 | Yes |
| Friday | Saturday | Yes |
| Friday | none | Yes |

When hiding a task or moving its hidden attention day later, all open dated
steps are validated before any mutation. When adding or changing a step date,
the parent is validated before any mutation.

Date-time validation compares local calendar days. A parent hidden until
Friday 15:00 and a step due Friday 10:30 are compatible because both are
eligible for display from Friday morning.

## Recurrence

Completing a recurring task or step through `todo done` causes Todoist to move
its attention value to the next occurrence. The completion is included in the
report. A retained hiding policy applies to the next occurrence.

## Completing a task with open steps

When `todo done TASK` targets a task with open steps, it lists every open step
and asks whether all of them should be completed together with the parent. Only
an explicit `y` or `yes` authorizes the operation. After confirmation, it
completes every open step and then completes the parent task.

Any other answer, cancellation, end of input, or non-interactive invocation
leaves the parent and every step unchanged and returns a failure. A task with no
open steps is completed without this confirmation.

`todo done TASK TEXT` accepts optional completion text. Before completing the
task, it adds a task comment with the content `Done: TEXT`. That comment is a
normal progress event and is eligible for the report period. Steps do not
accept completion comments because steps cannot have comments.

After confirmation, open steps are completed sequentially before the parent.
If a later Todoist operation fails, previously accepted completions remain in
Todoist. The command does not attempt compensating reopens. It exits nonzero
and reports clearly which operation failed and that earlier changes may already
have succeeded.

## Reopening

`todo reopen TASK` reopens only the selected parent task. Its completed steps
remain completed. Reopening does not attempt to reconstruct or reverse the
state of the task tree.

Every successful reopen also records progress as a task comment:

- Reopening a task adds `Reopened` or `Reopened: TEXT` to that task.
- Reopening a step adds `Reopened step: STEP` or
  `Reopened step: STEP: TEXT` to its parent task.

The explanatory `TEXT` is optional. These are ordinary comments and require no
special report processing. If reopening succeeds but adding the comment fails,
the item remains reopened and the command reports the partial failure.

Reopening an already open item fails with a nonzero status, performs no
mutation, and adds no comment. Symmetrically, completing an already completed
item fails rather than reporting an unchanged success.

## No-op mutations

Every mutation compares its complete proposed result with current state after
selection and validation. If the operation would make no observable state
change, it fails before contacting Todoist. Examples include setting P1 on an
already-P1 item, moving a task to its current category, renaming to the current
title, and clearing an already-empty reminder set.

The comparison covers the complete operation. Keeping an attention date while
changing reminders or the own hiding policy is a real mutation and is allowed.
Creating another comment with identical text is also a real mutation because it
creates a distinct comment.

## Moving to a hidden category

Before moving a task into a configured hidden category, validate the task and
all of its steps. If any has an attention value, reminder, or own hiding policy,
reject the complete move without mutation. The command never clears scheduling
information implicitly to make the move valid.

Configured hidden categories are resolved by their current case-sensitive
Todoist names. If a configured name no longer exists because its project was
renamed or deleted in Todoist, it matches no category and produces no warning.
A renamed project is treated as an ordinary visible category unless its new
name is also configured as hidden. Todoist remains authoritative for the
project and for the disposition of its tasks.

The reverse rename takes effect immediately as well. If a Todoist project is
renamed to a configured hidden-category name, it is hidden even when it already
contains tasks or steps with attention values, reminders, or hiding policies.
Read operations diagnose each resulting invariant violation. They must not
ignore the scheduling data, treat the category as visible, or silently modify
Todoist to repair it.

Model validation precedes normal read output. If any such invariant violation
is found, the command prints diagnostic errors to stderr, exits nonzero, and
does not print a partial actionable list or other normal result.

## Clearing

`ITEM clear` removes the item's attention value, recurrence, reminders, and own
hiding policy. It is the supported way to return an item to an undated state.

`--reminder clear ITEM` removes reminders while preserving the attention value,
recurrence, and hiding policy.

## Reminders

An item may have multiple relative reminders. Reminder offsets are relative to
the exact occurrence time and are handled by Todoist so notifications appear
on the phone.

When one or more `--reminder OFFSET` arguments are supplied, they replace the
item's complete existing reminder set. They are not added to the previous set.
Repeating `--reminder` within one invocation defines multiple values in the new
set.

When an attention value is changed without any `--reminder` option, the
existing reminder set is preserved. Successful output explicitly prints the
retained reminders when the set is nonempty, even though they were not changed,
so the user can see that they now apply relative to the new attention time.

The local attention parser classifies proposed expressions as known date-only,
known timed, or unknown to the local parser. When an item has relative
reminders, changing it to a known date-only value is rejected before mutation
and instructs the user to clear or replace the reminders explicitly.

For an expression whose date/time shape is unknown locally, the command lets
Todoist parse it. Before mutation it snapshots the complete reminder set. After
Todoist accepts the update, it synchronizes and compares the authoritative due
value and reminders with that snapshot. It prints a warning to stderr if
Todoist changed or removed any reminder, or if the resulting item is date-only
while relative reminders still exist. It does not attempt to roll back an
accepted Todoist update.

Such a reconciliation warning makes the command exit nonzero even though
Todoist accepted the attention-value change. The output must state that the
date mutation succeeded and identify the resulting reminder discrepancy so the
user does not mistake the operation for an unchanged failure.

## Reporting

`todo report` synchronizes Todoist and creates a report beginning at the stored
report cursor. It does not change the cursor.

`--since TIMESTAMP` and `--until TIMESTAMP` may override either interval
boundary for debugging and recovery. Boundary inclusion remains
start-exclusive and end-inclusive. The command captures a single end time at
the beginning of report generation when `--until` is omitted.

An invocation using either interval override cannot use `--final` and never
advances the cursor.

Report generation requires a successful current-state synchronization,
complete activity-history retrieval for the interval, and every comment lookup
needed to evaluate or render report entries. Failure of any required source
aborts generation: no report is printed, the command exits nonzero, and the
cursor remains unchanged. A report is never intentionally produced from a
partial event or comment set.

`todo report --final` advances the cursor only after synchronization and report
generation succeed. A report period is start-exclusive and end-inclusive:
`(previous cursor, report end]`. An event exactly at the previous cursor is not
repeated, while an event exactly at the new report end belongs to the report
being generated. The reporting time zone is the local time zone of the
executing machine.

Successful `--final` advances the cursor even when the event-based `Finished`
and `Progress` sections contain no entries. An empty report is still a valid
finalized reporting period.

If no cursor exists, the effective beginning is infinitely in the past.

The report contains three sections:

The `Finished`, `Progress`, and `Hidden` headings are always printed in that
order, including when a section has no entries.

Within every section, categories are ordered alphabetically using lowercase
comparison. Todoist's manual project order does not affect report ordering.

Within the event-based `Finished` and `Progress` sections, content is ordered
chronologically from the oldest qualifying event to the newest. When multiple
progress events are grouped under one task, the task's position is determined
by its oldest qualifying event and its displayed events are ordered oldest
first.

### Finished

Lists completed tasks. Tasks cannot be completed until all their steps are
complete. A Finished entry does not append the task's comments; comments belong
to `Progress` in the period when they were added or edited.

A non-recurring task completion is included only if the task is still completed
when the report is generated. If it was reopened, its earlier completion event
is ignored. A recurring completion remains reportable even though Todoist has
advanced the item to its next occurrence and the item is open again.

### Progress

Lists completed steps and task comments that were added or modified during the
period. A completed step is presented in the context of its parent task.
Steps cannot have comments. Editing a comment resets its comment date, making
it eligible for a later report. Semantically, an edit deletes the old comment
and creates a new comment containing the edited text. The report presents that
new text like any other added comment and does not label it as edited. Deleted
comments are not shown.

A surviving comment is included only when its add/edit timestamp falls inside
the current report interval. Completing its task does not repeat comments from
earlier finalized periods.

A non-recurring step completion is likewise ignored if that step is currently
open because it was reopened after completion. This current-state check does
not apply to a recurring step advanced by Todoist.

### Hidden

Lists tasks currently suppressed by the temporary attention-date hiding policy
established by `--hide`. A task leaves this section when its local attention day
arrives, even though its stored hiding policy remains. Tasks are not included
merely because they belong to a configured hidden category such as `Someday`.
Within a category, hidden tasks are ordered alphabetically using lowercase task
title comparison rather than by attention date.

Each hidden task displays its hiding reason when one is stored.

A currently suppressed step with its own `--hide` policy is displayed beneath
its parent task with its own hiding reason, even when the parent itself is
visible. A step suppressed only because it inherits a hidden parent policy is
not listed as a separate hidden entry. When both parent and step have effective
own hiding policies, the parent is listed once and the step is nested beneath
it. Independently hidden steps beneath one parent are ordered alphabetically by
lowercase step title.

`Hidden` is a current-state snapshot rather than a cursor-bounded event list.
It includes every currently suppressed temporary-hidden task even when the task
was hidden before the report cursor and had no activity during the period.

Report entries use each task's and step's current title and the task's current
category, including when an item was renamed or moved after the recorded
activity.

A task deleted before report generation contributes no report entries. Its
earlier comments, completed steps, task completion, and temporary-hidden state
are omitted even when their events occurred inside the report period. Deleting
a parent likewise removes report entries belonging to its deleted steps.

The same rule applies to an individually deleted step or comment while its
parent survives: all report events belonging to the deleted object are omitted.
For reporting purposes, deletion makes the object behave as though it never
existed.

## Synchronization and cache

All managed task data is cached so read-only operations can run without
Todoist access. State-changing commands and `todo report` synchronize first.
A failed synchronization prevents mutation.

Changes made on a phone are observed on the next synchronization because
Todoist is authoritative.

`~/.todo/cache.json` can be deleted and recreated, for example with
`todo now --refresh`.

The following local state cannot be reconstructed solely from Todoist:

- `~/.todo/config`
- `~/.todo/report-cursor`

`~/.todo/lock` is runtime coordination state and need not be reconstructed.

## Category listing

`todo category` lists current child projects of the configured root project in
alphabetical order using lowercase name comparison. Todoist's manual project
order does not affect this view.

If the configured root project is missing or not unique after synchronization,
normal commands fail with a clear configuration/model error until the Todoist
project or local configuration is corrected. The CLI does not silently select
or create a replacement during ordinary operation.

If synchronization discovers a project nested beneath a category, model
validation fails. Read commands print the hierarchy error to stderr, exit
nonzero, and produce no normal output. The CLI does not flatten, ignore, or
silently reinterpret the deeper project.

The same validation behavior applies to a parent task placed directly in the
configured root project without a category. The task is not ignored or assigned
an implicit category.

Model validation also rejects nested steps deeper than one direct level. Read
commands abort rather than flattening, ignoring, or promoting nested items.
