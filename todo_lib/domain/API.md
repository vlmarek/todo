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
  Known timestamps accept `ExactInstant` or aware `datetime` and retain full
  supplied precision. `completed_at` is required when `completed=True`.
  Role derives from the current parent: no parent means task, otherwise step.
- `Comment` and `Reminder` belong to an item ID. `Reminder(id, item_id, minutes)`
  remains the relative constructor (`type='relative'`); zero is present and
  requires timed task attention. `Reminder(id, item_id, type='absolute', due=a)`
  carries independent exact `Attention`, even on undated/date-only tasks.
  `resolve_reminder_due(raw, account_zone)` maps the reminder-specific open due
  object through shared fixed/floating resolution. It accepts omitted rule/flag
  and named-zone wall time; supplied scheduling fields remain validated. Known
  recurrence without wording displays `recurring`, without a local parser.
  `due.raw_due` retains absolute scheduling/language/recurrence/zone; `raw_due`
  preserves a relative reminder's unused due without interpreting it. Optional
  `notify_uid` and `is_urgent` retain supplied metadata. Reminder scheduling never
  contributes task urgency. Old stored relative records use these defaults.
- `Occurrence` records a completion fact separately from the current item. A
  recurring completion leaves the current item open. Deleted objects and their
  contributions must be removed by producers; no undelete representation exists.

`validate(snapshot, hidden_names=())` returns the candidate, or a copy with inbound
CRLF normalized and whitespace-only descriptions represented as empty text. It
raises `DomainError` for invalid fields/invariants and never writes or implicitly
enrolls records. Imported task/step duplicate titles and scheduled hidden categories
are valid. Category uniqueness, controls, identity and hierarchy remain strict. `bind_root` is for initial exact name
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
The reason is optional; a `waiting` label plus valid attention enables an own policy.
`incoming_text(value, *, title=False, description=False)` validates incoming text
without trimming nonblank content. `validate_title` and `validate_body` stay strict
CLI validators. `scalar_title(value)` escapes backslash/LF/tab for scalar terminal
output only; matching and collision keys use actual stored titles.
`split_waiting(description, active=True)` returns literal text and no reason for
malformed blocks or inactive policy. Consumers use `item_description(item)` to
associate canonical reasons only with valid own policies. `convention_diagnostic`
returns an issue fragment without echoing the description. `with_waiting_reason`
refuses unsafe additions/replacements with `DomainError`; label removal preserves
unparsed literal text.
`validate_sibling_uniqueness(items, before=())` rejects new colliding active ID
pairs relative to the before collection. Omit before for strict new batches.
Mutation callers must compare complete before/after collections, including reopened
ancestors. Existing collisions may persist or resolve. `visibility` treats an
undated waiting label as inactive; valid ancestor suppression still applies.
Provider length-limit failures must be translated to `DomainError` by the adapter.

`parse_attention(expression, now, account_zone)` returns `Attention` of kind
`date`, `fixed`, or `unresolved`; invalid known grammar raises `DomainError`.
The original scalar is in `expression`. ISO attention date-times require an
explicit offset. Relative local arithmetic refuses ambiguous/nonexistent walls;
minutes/hours use elapsed time. Months add directly and clamp only the target.
An unresolved expression is distinct from absent attention (`None`). Workflows
requiring a local comparison must reject it; calling `day(zone)` diagnoses it.

`parse_boundary(value, now, account_zone)` returns `ExactInstant` for fractional
ISO date-times, otherwise a UTC aware `datetime`, for ISO input or positive `Nd` / `N days ago`, without attention weekday grammar or
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

## Shared exact instants

`ExactInstant` is an immutable non-dataclass value exported by `todo_lib.domain`.
Its concrete constructor is `ExactInstant(second, fraction='')`: `second` must be
an aware whole-second UTC `datetime`, and `fraction` must be empty or ASCII digits.
Prefer `instant_from_wire(text)` to construct it from a provider timestamp.

- `instant_from_wire(text: str) -> ExactInstant` accepts aware RFC 3339 calendar
  date-times with seconds, optional decimal fraction of any length, and `Z` or
  a numeric `+/-HH:MM` offset (also lowercase `t`/`z`). Invalid dates, leap seconds,
  naive strings and wrong types raise `DomainError`. UTC must fit datetime years
  1–9999. Supplied trailing zeros are preserved; equivalent offsets compare equal.
- `instant_key(value: ExactInstant | datetime) -> fractions.Fraction` returns
  exact UTC seconds since the Unix epoch. Mixed keys are mutually comparable,
  including across DST folds. Arithmetic uses unbounded integers, with no float
  or Decimal context rounding, even for very long fractions.
- `instant_text(value: ExactInstant | datetime) -> str` emits UTC RFC 3339 with
  every supplied fractional digit. Datetime inputs retain their microseconds.
- `instant_datetime(value: ExactInstant | datetime) -> datetime` explicitly
  projects to an aware UTC datetime, truncating beyond microseconds. Use it only
  for human display, calendar arithmetic or safely widened retrieval bounds;
  filter exact intervals with `instant_key` afterward.

The last three helpers reject None, naive datetimes, strings and other types with
`DomainError`. `ExactInstant` equality/order use exact keys, including with aware
datetime inputs. The value is deliberately unhashable (`hash` raises `TypeError`):
Python datetime hashes ignore `fold`, so a single hash cannot agree with every
aware datetime that denotes the same exact instant. Use `instant_key(value)` for
both representations in dictionaries/sets; history coverage deduplication uses
these normalized endpoint keys. Model positional argument order is unchanged. `Item.added_at`,
`Item.completed_at`, `Comment.added_at`, `Occurrence.completed_at` and
`LifecycleCandidate.completed_at` accept either type. Only Item/Comment creation
and an uncompleted Item's completion field may be null; Occurrence completion and
lifecycle/boundary times are required. Validation never replaces null with an
older observation. Siblings/traversal/completion order, latest recurring occurrence
and recent lifecycle intervals use exact keys, retaining original candidate times.

Local schema-1 cache, separate pending history, coverage, observations, synced_at
and report cursor serialize these values as UTC strings and reload ExactInstant.
Existing schema-1 timestamp strings remain valid. Observations alone may also
be unknown (None); coverage endpoints, synced_at and cursor are required.
`dataclasses.asdict` retains immutable ExactInstant values for explicit codec
serialization rather than exposing internal slots. Local malformed required
stored timestamps raise `LocalError` without resetting bytes. No projection is
an authority for persistence, delta seeding, equality or ordering. Attention's
existing raw due/epoch_seconds API and reconciliation tolerance are unchanged.

`rebase_attention(value, account_zone, reminder=False)` resolves retained floating
raw due in current account authority; fixed values retain their instant.
`preserves_reminder(previous, actual, account_zone)` compares exact retained
identity, type, scheduling and known metadata without comparing raw encodings.
`preserves_item(previous, actual, account_zone)` checks owner scalar/lifecycle
preservation with equivalent due under that same account authority.

Per-value named scheduling (revision 15): `parse_attention(expression, now,
account_zone)` accepts a final slash-containing IANA location token or `UTC`.
It validates that token locally and uses it for supported calendar and ISO local
wall inputs; offset/Z instants retain their exact epoch and fractional digits.
Without a suffix, ISO attention datetimes still require an offset. Short codes
remain delegated wording. `parse_boundary` and account-day policy are unchanged.
`Attention.expression` retains the original scalar for unresolved previews;
`Attention.zone` is the applicable schedule zone, never an account authority.
Delegated named input uses `raw_due` for stripped `string` and `timezone` request
metadata, while resolved authoritative values retain the original complete due
object. Resolved local values need no raw object. Date-only values have no zone.
No constructor fields or stored schema were added.

`attention_prediction(value, account_zone)` supplies the provider's fixed-request
account-zone default for locally parsed nonrecurring unzoned values without
altering their omitted-zone wire request. Local no-op/reminder identity checks
apply this prediction explicitly; `same_attention` itself remains exact.
`reconciles_attention` permits inclusive two-second slack for known occurrences
with strict kind/day/rule/language/zone semantics. For delegated input it checks
that a timed result retains any explicit named zone; attention may normalize to
a date-only value. Absolute reminder callers additionally require exact time.

`retain_recurrence(proposal, previous, account_zone=None)` retains the previous
rule, language and recurrence zone only after resolving a local occurrence move.
The optional binding zone permits preserving a floating rule by expressing the
resolved instant as floating local wall text. Scheduling and Gateway callers pass
it. Date-only moves retain the rule but carry no clock zone; delegated replacement
expressions retain their new wording and explicit zone. `due_arguments` sends
exact UTC `date` plus applicable named timezone, or delegated stripped `string`,
`lang: en` and optional timezone. Recurring occurrence moves retain original
language/rule/zone without restoring an obsolete date. Current mapping and codec
continue retaining authoritative metadata and precise epochs through snapshots
and pending history; no last-input-zone field is persisted.

`validate(snapshot, hidden_names=(), *, cached_owner_ids=frozenset())` accepts
command-local diagnostic provenance for reminder owners. It does not change
validation, model equality, or persisted data. Reminder mapping/invariant errors
retain their exception class and reason and add bounded consumed-field context;
`managed_reminder` on these exceptions identifies a remote-data correction
condition for workflow diagnostics. Titles use scalar display escaping; malformed
objects are summarized, never dumped. Domain formatting remains offline.
