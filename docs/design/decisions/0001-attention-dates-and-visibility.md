# 0001: Attention values and visibility

Status: Accepted

## Context

Dates are used for deadlines, meetings, follow-ups, planned work, and recurring
activities. Requiring the user to classify these intentions during capture
would increase cognitive load without necessarily changing desired behavior.

An exact meeting time is important for display and notifications, but waiting
until that instant to show the item in `todo now` would be too late.

## Decision

Use one attention value for the date or exact date/time at which an item
requires attention. `wait`, `due`, and `schedule` are equivalent aliases for
editing it.

Visibility before the attention day is controlled independently by `--hide`.
A hidden item becomes visible at the beginning of its attention day in the Todoist account timezone. An
exact time remains relevant to display, urgency ordering, and reminders.

The policy is persisted using the Todoist `waiting` label so it synchronizes
across clients. Effective visibility is derived from that label and the current
attention day; reaching the day does not remove the label.

Tasks and steps provide separate levels at which attention values may be set.
A step may not have an attention day before the attention day of a hidden
parent task.

## Consequences

- Capture requires deciding whether the item should be visible now, not why the
  date exists.
- The same attention vocabulary and command behavior applies whether the date
  represents a deadline, meeting, follow-up, or planned work, reducing choices
  during capture.
- The model does not structurally distinguish a deadline from a follow-up.
- A task and its steps can express multiple dates.
- Parent/step validation is required before mutations.
- Exact times and list visibility use related but different comparisons.
- Validation errors must explain the visibility conflict using the affected
  task or step and its attention day.
