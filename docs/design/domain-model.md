# Domain model

Status: Proposed

## Terms

### Root project

The configurable Todoist project containing all work managed by `todo`.
Currently named `Oracle`.

### Category

A direct child project of the configured root project. Category names and
membership come dynamically from Todoist. Category matching is case-sensitive;
task and step selector matching is independently case-insensitive.

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

### Attention value

A Todoist due specification representing the date or exact date/time at which
an item requires attention. It may be recurring. Its purpose is intentionally
not classified further.

### Reminder

A relative offset before an exact attention time at which Todoist should send
a notification. An item may have multiple reminders.

### Own hiding policy

An item configured with `--hide` is suppressed before its local attention day.
The stored policy remains after that day, even though the item is then visible.

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

## Derived task urgency

For ordering in `todo now`, a task represents itself and its open steps.

- Effective task attention value: the earliest attention value among the task
  and its open steps.
- Effective task priority: the highest priority among the task and its open
  steps, where P1 is highest and P4 is lowest.

Completed steps do not contribute to these derived values.

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
