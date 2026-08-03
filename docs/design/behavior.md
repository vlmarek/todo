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

## Attention values and hiding

`wait`, `due`, and `schedule` are intended to be equivalent aliases.

Setting an attention value without `--hide` makes the item's own hiding policy
false. Setting it with `--hide` makes the policy true.

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

## Reporting

`todo report` synchronizes Todoist and creates a report beginning at the stored
report cursor. It does not change the cursor.

`todo report --final` advances the cursor only after synchronization and report
generation succeed. A report period is start-exclusive and end-inclusive:
`(previous cursor, report end]`. An event exactly at the previous cursor is not
repeated, while an event exactly at the new report end belongs to the report
being generated. The reporting time zone is the local time zone of the
executing machine.

If no cursor exists, the effective beginning is infinitely in the past.

The report contains three sections:

### Finished

Lists completed tasks. Tasks cannot be completed until all their steps are
complete.

### Progress

Lists completed steps and task comments that were added or modified during the
period. A completed step is presented in the context of its parent task.
Steps cannot have comments. Editing a comment resets its comment date, making
it eligible for a later report. Semantically, an edit deletes the old comment
and creates a new comment containing the edited text. The report presents that
new text like any other added comment and does not label it as edited. Deleted
comments are not shown.

### Hidden

Lists tasks currently suppressed by the temporary attention-date hiding policy
established by `--hide`. A task leaves this section when its local attention day
arrives, even though its stored hiding policy remains. Tasks are not included
merely because they belong to a configured hidden category such as `Someday`.

Report entries use each task's current category, including when it moved after
the recorded activity.

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
