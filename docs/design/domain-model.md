# Domain model

Status: Proposed

## Terms

### Root project

The configurable Todoist project containing all work managed by `todo`.
Currently named `Oracle`.

Exactly one current Todoist project must match the configured root name.

### Category

A direct child project of the configured root project. Category names and
membership come dynamically from Todoist. Category matching is case-sensitive;
task and step selector matching is independently case-insensitive.

Category names are unique under case-insensitive comparison even though normal
category selection is case-sensitive.

The supported project hierarchy is exactly two levels: the configured root and
its direct category children. A deeper descendant project is invalid model
state rather than another category.

### Hidden category

A category configured to be excluded from normal `todo now` output. `Someday`
is the conventional example. More than one hidden category may be configured.
Configuration identifies hidden categories by their current case-sensitive
Todoist names. A configured name that matches no current category has no effect
and is not an error.

If a Todoist rename causes a category with scheduled items to acquire a
configured hidden name, the category is nevertheless hidden. The contained
data is an invalid state that must be reported on read; it is not normalized
implicitly.

### Task

An open or completed Todoist item directly associated with a category. A task
may have zero or more direct steps.

### Step

A child item belonging to a task. A step inherits the task's category. Steps
can have their own priority, completion state, attention value, hiding policy,
and reminders. Steps do not have comments.

At creation, a parent task defaults to P2 unless another priority is explicitly
requested. A new step copies its parent task's effective priority, including any
elevation contributed by existing open steps. The copied value then belongs to
the new step independently; later priority changes do not propagate
automatically.

Only one step level is supported. A step cannot itself be a parent.

### Attention value

A Todoist due specification representing the date or exact date/time at which
an item requires attention. It may be recurring. Its purpose is intentionally
not classified further.

### Reminder

A relative offset before an exact attention time at which Todoist should send
a notification. An item may have multiple reminders.

### Own hiding policy

An item configured with `--hide` carries the Todoist `waiting` label and is
suppressed before its local attention day. The label remains after that day,
even though the item is then visible. Todoist is authoritative for the label,
so label changes made on the phone are observed after synchronization.

### Hiding reason

Human-readable context explaining why a task is temporarily hidden. It is
stored in a marked metadata block inside the Todoist task description so it
synchronizes across clients while remaining separable from ordinary
description text. A step may store its own reason in the same kind of marked
block in its own description.

### Effective visibility

Whether an item is displayed after considering completion, category hiding,
its own hiding policy, and its parent task's hiding policy.

### Actionable

An open item eligible for normal `todo now` output. Actionability is derived;
it is not an independently stored state.

## Core invariants

1. Every managed task belongs to a category under the configured root project.
2. A step inherits its parent task's category.
3. Completed steps are excluded from `todo now` but shown in task details.
4. A hidden item must have an attention value.
5. Relative reminders require an attention value containing an exact time.
6. A task in a hidden category, and all of its steps, cannot have attention
   values, reminders, or own hiding policies.
   Moving a task into a hidden category is rejected if the task or any of its
   steps violates this invariant; scheduling information is never cleared
   implicitly.
7. A hidden task hides all of its steps until the task's local attention day.
8. The local attention day of a step must not precede the local attention day
   of its hidden parent task.
9. The invariant in rule 8 is checked both when changing a step and when hiding
   or rescheduling its parent.
10. An exact time does not postpone list visibility within its calendar day.
    A meeting at 10:30 is eligible for display from the beginning of that local
    day.
11. A task remains open after all its steps are completed until the task itself
    is completed.
12. A task cannot be completed while it has open steps.
13. Completion requires an open item; reopening requires a completed item.
    Requesting either transition when the item is already in the target state
    is a user error, not an idempotent success.
14. Open task titles are unique within one category under case-insensitive
    comparison. The same title may exist in different categories. A completed
    title may be reused in its category with a warning.
15. Open step titles are unique within one parent task under case-insensitive
    comparison. The same step title may exist under a different parent. A
    completed step title may be reused under its parent with a warning.
16. Completed items are immutable through ordinary editing commands. They may
    be resolved by commands that reopen or delete them; editing requires
    reopening first. Normal parent-task inspection remains open-only.
17. Every item carrying an own hiding policy has a non-empty hiding reason.
18. No project may be nested below a category within the configured root tree.
19. Every parent task must belong to a direct category project; parent tasks
    directly in the configured root project are invalid.
20. Every step is a direct child of a parent task. A step with its own child is
    invalid model state.
21. The configured root project must exist uniquely in Todoist.

## Derived task urgency

For ordering in `todo now`, a task represents itself and its open steps.

- Effective task attention value: the earliest attention value among the task
  and its open steps.
- Effective task priority: the highest priority among the task and its open
  steps, where P1 is highest and P4 is lowest.

Completed steps do not contribute to these derived values.

Effective task priority is only an internal ordering value. A task itself has
one stored priority, and task details display only that stored value.

For urgency sorting, an absent effective attention value is treated as
infinitely far in the past. This rule is applied only after the due bucket and
effective-priority keys.

Open steps within a displayed task group are sorted by their own due bucket,
priority, attention value, and lowercase title. The same infinitely-past rule
applies to an absent step attention value.

## Visibility

An undated open task is normally actionable unless it is in a hidden category
or hidden by a parent rule.

An item without its own hiding policy is visible even when its attention date
is in the future. An item with its own hiding policy becomes visible at the
start of its local attention day and stays visible afterward.

A task's hiding policy applies to its entire task tree. A step may extend its
own hiding beyond the parent's visibility day, but cannot have an attention day
before the hidden parent's attention day.
