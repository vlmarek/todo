# Domain model

Status: Accepted

## Terms

### Root project

The unshared personal Todoist project containing all work managed by `todo`.
Its configured initial name is currently `Oracle`.

During first initialization or explicit rebind, the configured name is matched
exactly and case-sensitively. Thereafter the stable Todoist account and project
IDs in `~/.todo/binding.json` define identity; a rename does not rebind scope.
A shared or team-workspace root is outside the model.

### Category

A direct child project of the bound root. Current names and membership come
from Todoist; stable category IDs are retained in binding state so a rename does
not change identity and a move cannot silently discard managed work.
User-entered category, task, and step lookups are case-insensitive.

Open category names are unique under case-insensitive comparison. The supported
project hierarchy is exactly the bound root and its direct category children. A
deeper descendant project is invalid rather than another category.

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
suppressed before its attention day in the Todoist account timezone. The label
remains after that day,
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

### Account binding

Authoritative local identity tying one configuration to one Todoist account,
root project, and set of managed category IDs. Token rotation does not change a
binding. A different account requires explicit confirmed rebind.

### Report cursor

The locally authoritative UTC instant immediately through which a successful
final report has claimed activity. Default report and recent-completed
selection intervals begin strictly after it.

### Completion occurrence

One completion event for a task or step. A non-recurring object normally has one
current completion, while a recurring object can contribute several occurrences
and remains open at its next occurrence.

## User-facing vocabulary

The terms in this document are the vocabulary presented to the user. Commands,
help, normal output, warnings, and errors use these terms consistently.

- Use `task`, `step`, `category`, `attention`, `reminder`, and `hidden`.
- Do not expose Todoist API names such as `item`, `project_id`, `parent_id`,
  `checked`, or `sync_token` in ordinary user-facing output.
- A task has one stored priority and one own attention value. Derived effective
  priority and attention are internal ordering concepts and must not be
  presented as additional editable task properties.
- When Todoist terminology must be mentioned for recovery, explain its
  relationship to the corresponding `todo` concept.

## Core invariants

1. One local binding belongs to exactly one Todoist account and one unshared
   personal root-project ID.
2. Every managed parent task belongs to a direct managed category under the
   bound root; parent tasks directly in the root are invalid.
3. A step is one direct child of a parent task and inherits its category. A step
   with a child is invalid.
4. No project may be nested below a category inside the managed root.
5. Completed steps are excluded from `todo now` but may appear in task details.
6. An item with its own hiding policy has an attention value, the Todoist
   `waiting` label, and a nonempty hiding reason.
7. Relative reminders require an attention value containing an exact time and
   an account capability that supports the requested reminder.
8. A task in a configured hidden category, and all its steps, has no attention
   value, reminder, or own hiding policy. Moving work there never clears such
   state implicitly.
9. A hidden parent suppresses its complete open tree before the parent's
   attention day in the Todoist account timezone.
10. A step's account-local attention day cannot precede that of its hidden
    parent. Parent and step changes both validate this rule.
11. Exact time never delays list visibility beyond the beginning of its
    account-local calendar day.
12. A parent remains open after all steps complete until it is separately
    completed.
13. A parent cannot be completed while it has an open step. In particular, an
    open recurring step rejects parent completion because completing that step
    would advance it and leave it open.
14. Completion requires an open item. Ordinary reopen requires a currently
    completed item. An already-satisfied transition is an error rather than an
    idempotent success.
15. `reopen` considers only eligible completion occurrences in
    `(report cursor, now]`. Completed-item `delete` considers only currently
    completed non-recurring objects whose completion is in that interval. A
    recurring object remains an ordinary open delete candidate and is never
    duplicated as a historical completed candidate.
16. Only the latest completion occurrence of a recurring object can be undone;
    undo moves recurrence backward one occurrence.
17. Reopening a step may reopen its completed ancestor chain. The complete
    chain must preserve every open-sibling title-uniqueness invariant.
18. Open task titles are unique within a category under case-insensitive
    comparison. A completed title may be reused there with a warning.
19. Open step titles are unique within one parent under case-insensitive
    comparison. A completed sibling title may be reused with a warning.
20. Creation, rename, move, and reopen validate title uniqueness before their
    first mutation. They never merge or rename an object implicitly.
21. Completed items are immutable through ordinary editing. They may only be
    reopened or deleted through the explicitly bounded workflows.
22. Category names are unique under case-insensitive comparison.
23. Current managed-scope membership determines report inclusion. Current
    titles, parents, and categories determine report presentation.
24. Deletion is terminal. A deleted task, step, or comment has no report or
    completed-search contribution and no local undelete snapshot.
25. Offset-free dates, attention days, overdue buckets, and displayed instants
    use the Todoist account timezone. Explicit offsets identify an instant;
    persisted instants use UTC.
26. Task, step, category, comment, rename, and hiding-reason text must not be
    empty or whitespace-only and must not contain disallowed control
    characters. Todoist length limits remain authoritative and are translated
    into domain errors.
27. Phone-side or web-side state that violates any invariant is diagnosed and
    never silently repaired, flattened, ignored, or normalized.

Single-line task, step, and category titles reject line breaks, tabs, NUL,
escape, and the remaining C0/C1 control characters. Multiline descriptions,
comments, and hiding reasons may contain line feeds and tabs but reject NUL,
escape, carriage return, and all other C0/C1 controls. Matching normalization
never rewrites the stored user text.

## Derived task urgency

For ordering in `todo now`, a task represents itself and its open steps.

- Effective task attention value: the earliest attention value among the task
  and its open steps.
- Effective task priority: the highest priority among the task and its open
  steps, where P1 is highest and P4 is lowest.

Completed steps do not contribute to these derived values.

Effective task priority is only an internal ordering value. A task itself has
one stored priority, and task details display only that stored value.

Effective task attention is also only an internal ordering value. Task details
show the parent's own attention value, while each step shows its own.

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
start of its account-local attention day and stays visible afterward.

A task's hiding policy applies to its entire task tree. A step may extend its
own hiding beyond the parent's account-local visibility day, but cannot have an attention day
before the hidden parent's attention day.
