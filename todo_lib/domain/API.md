# Shared offline domain API

Import the public symbols from `todo_lib.domain`. This package uses only the
Python standard library. It makes no requests, reads no application files, uses
no host clock, and performs no persistence or remote mutation.

## Complete managed model

`Snapshot(binding, account, root, categories, items, comments, reminders,
occurrences)` represents the complete candidate after all pages/deltas are merged.
The five collections are ID-keyed mappings. All identities are strings.

- `Binding(account_id, root_id, category_ids)` contains stable enrolled identity.
- `Account(id, timezone, capabilities)` carries the authoritative IANA timezone.
  `Capabilities` describes reminders, activity history and the history limit.
- `Project` / `Category` holds current name, immediate project parent and explicit
  scope facts. Personal ownership is a domain fact supplied by the producer, not
  an invented required provider field.
- `Item` has one category ID, an optional immediate item parent ID, own title,
  description, product priority 1–4, attention, labels and lifecycle fields.
  `added_at=None` means unknown and is never filled from another observation.
  Known timestamps are aware `datetime` values and retain microsecond precision.
  Role derives from the current parent: no parent means task, otherwise step.
- `Comment` and `Reminder` belong to an item ID. `Reminder.minutes=0` is present.
- `Occurrence` records a completion fact separately from the current item. A
  recurring completion leaves the current item open. Deleted objects and their
  contributions must be removed by producers; no undelete representation exists.

`validate(snapshot, hidden_names=())` returns the same candidate, or raises
`DomainError` identifying an invalid field/invariant. It never repairs, drops,
normalizes or implicitly enrolls records. `bind_root` is for initial exact name
matching only; `enroll_categories` explicitly returns a new binding from current
valid child records, refusing retirement that could discard known work. Discovery
must preserve evidence of moved/invalid bound projects rather than omit them.

`ancestors` returns root-to-parent; `subtree` includes the selected item in
preorder; `hierarchy_depths` and `subtree_depths` return absolute depths.
`ordered_siblings` orders known creation times newest first, then unknown times
by stable ID. Helpers expect a complete valid snapshot unless they are themselves
preflight validators. `validate_move_depth` validates known resulting depths;
workflows must also validate the complete proposed model for other move rules.

`creation_priority` copies the pre-creation parent's `effective_priority`; neither
it nor `effective_attention` changes own fields. `now_queue` returns independent
items sorted using own values. `urgency` provides the five ordered sections.
`visibility` exposes own, ancestor, category and completion suppression separately.
`validate_hiding_enable` adds the strictly future day check for explicit hiding;
ordinary `validate` allows existing expired policies.

`completion_order` visits direct children in inspection sibling order, returning
open descendants before their parents and the selected root last. A recurring
descendant blocks it. `recent_reopen_candidates` and
`completed_deletion_candidates` use `(cursor, now]`; the former includes only the
latest eligible recurring occurrence, and the latter excludes recurrence history.
Interval bounds, occurrence recency and candidate ordering use absolute UTC
instants across DST folds; candidate timestamps retain the supplied values.
`reopen_chain` checks active uniqueness across the proposed ancestor reopen chain.
`require_editable` rejects ordinary edits of completed items. These helpers do not
compute report current-truth or report event eligibility.

## Text and account time

`validate_title` / `validate_body` normalize edges of user input and reject
forbidden controls. Snapshot validation leaves stored Unicode unchanged.
`title_key` is only a normalized case-insensitive comparison key.
`split_waiting` / `with_waiting_reason` share the canonical trailing reason block.
The reason is optional; only the `waiting` label enables an own policy.
Provider length-limit failures must be translated to `DomainError` by the adapter.

`parse_attention(expression, now, account_zone)` returns `Attention` of kind
`date`, `fixed`, or `unresolved`; invalid known grammar raises `DomainError`.
The original scalar is in `expression`. ISO attention date-times require an
explicit offset. Relative local arithmetic refuses ambiguous/nonexistent walls;
minutes/hours use elapsed time. Months add directly and clamp only the target.
An unresolved expression is distinct from absent attention (`None`). Workflows
requiring a local comparison must reject it; calling `day(zone)` diagnoses it.

`parse_boundary(value, now, account_zone)` returns a UTC aware datetime for ISO
input or positive `Nd` / `N days ago`, without attention weekday grammar or
workflow interval/future enforcement. `parse_reminder(value)` returns whole
minutes; command markers, arity and clearing belong to syntax/workflows.

`resolve_remote_due(raw_due, account_zone)` is supplied-value interpretation, not
wire mapping. It reads the due occurrence from `date`, preserves raw metadata
and fractions in `raw_due`, and distinguishes floating from fixed exact values.
Remote overlaps choose the earlier instant; gaps advance by the actual gap.
Re-resolve floating raw values when the authoritative account zone changes.
`instant` is UTC datetime at microsecond presentation precision;
`epoch_seconds` preserves finer supplied due precision for comparisons.
`attention_order` uses the full instant or account-local start of a date.
`same_attention` is exact semantic no-op comparison. `reconciles_attention` alone
allows up to two seconds of remote precision difference, with strict local day,
representation, recurrence rule and applicable zone checks. Language is compared
for recurring rules and unresolved expressions; parser language metadata does not
change the equality of resolved nonrecurring occurrences. Raw metadata is retained.
`retain_recurrence` copies existing rule metadata onto a resolved occurrence move;
a newly supplied unresolved provider expression can replace the rule instead.
