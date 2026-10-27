# Consumed tolerance and reminder contracts

Status: **Accepted**

Planning interpretation for TODO3-PLAN-007, inspected 2026-10-27. Product authority
is confirmed Design revision 8, especially its explicit successor table. This
note supplies technical navigation and bounded implementation choices, without
changing that agreement or the original provider evidence. Older provider notes
and task packets describe earlier supported scope; do not restore their superseded
attachment, absolute-reminder, sharing, text or convention restrictions.

## Evidence and contradictions

Use the original `docs/design/external/todoist/upstream/api-v1.openapi.json`,
authenticated by the unchanged adjacent manifest, retrieval date 2026-10-24.
`external/todoist/tolerance-notes.md` records the Design interpretation and limits.
The official source is https://developer.todoist.com/api/v1/ . A documentation
recheck in this planning pass failed because the browser's response limit rejected
the page; no newer source bytes or live account behavior were established.

The JSON `tags[name=Sync].description` contains `## Reminders`, `## Add a reminder`,
`## Update a reminder`, `## Delete a reminder`; it is not a REST request schema.
Its offset description says minutes before task due and requires timed task due.
The generic type prose says minutes from now and its relative example uses type
absolute: those two fragments conflict with the dedicated offset description,
`NotificationSyncView.minute_offset` and REST Create Reminder. Use the consistent
field-specific contracts and accepted relative-offset meaning. Do not edit the
upstream bytes, copy a placeholder temp-ID mismatch or call an example executable
provider proof.

`paths["/api/v1/reminders"].post.description` independently distinguishes relative
minute_offset from absolute due, and explicitly permits date/string plus optional
lang/timezone/is_recurring. `components.schemas.ReminderDueAttribute` describes
the latter fields; `NotificationSyncView` describes returned ID, item_id, type,
minute_offset, due, notify_uid, is_urgent and is_deleted. The due response is an
open object, not the task due validator's closed required-field list.

## Commands and authoritative results

Keep the existing POST `/sync` form, command UUID and create temp ID architecture.
Relative add arguments are item_id, type relative, minute_offset (integer >=0,
excluding boolean). Absolute add uses item_id, type absolute, due. English
unknown/recurring input uses due.string and lang en; locally resolved absolute
input uses due.date in the documented exact representation. No REST task_id or
reminder_type belongs in Sync. Update requires id and only the chosen update
fields; delete requires id. There is no requirement to introduce another transport.
Preserving a reminder by ID normally needs no reminder update at all.

For retained task or reminder recurrence, original language, rule, supplied flag
and applicable timezone remain together. Existing commands.due_arguments currently
sets lang en unconditionally: fix that shared choke point and any caller which
reconstructs the due object. Preserve supplied notify_uid/is_urgent and scheduling
metadata through model, _seed, comparison, delta merge, local history and unrelated
mutations, without exposing public recipient/urgent options or consuming every
unknown field as a validation predicate.

Exact UUID status and temp_id_mapping prove acceptance, then current authoritative
state proves actual scheduling. Text or matching first-firing time does not prove
create acceptance. A known exact prediction uses inclusive +/-2s reconciliation
only with strict account-local day, exact kind, recurrence and timezone semantics;
store actual returned values. Unknown provider expressions have no locally predicted
recurrence/date; require a valid actual absolute time and show it. Accepted date-only
normalization is nonzero partial failure with actual outcomes, never rollback or
an accepted absolute-reminder receipt. Keep sequential stopping, read-only
reconciliation of ambiguous outcomes, unknown/unattempted and publication facts.

## Due response mapping and bounded identity comparison

The Due dates tag distinguishes account-floating offset-free dates with null
zone from UTC fixed instants with a named recurrence zone. Use those full examples
for floating/fixed/recurring fixtures, preserving fractions and original metadata.
Task due keeps its required meaningful recurrence fields; only its documented
omitted timezone defaults to null under this amendment.

The independent `NotificationSyncView.properties.due.examples[0]` contains
`date: 2025-02-12T09:00:00`, `lang: en`, `timezone: Europe/Madrid`, without string or
is_recurring. This reminder-specific example must not acquire task due's invented
required string/flag predicates. It also differs from the Due dates tag's UTC
fixed example. Handle the supplied named-zone local reminder datetime as wall time
in that named zone, retaining its raw representation and fixed-zone semantics;
reuse remote wall-time overlap/gap policy for resolution. This is a bounded
application interpretation of an internally inconsistent published example,
not live confirmation. Do not extend it to task due or silently treat the named
zone as account-floating. Add a fixture with a different account timezone so that
incorrect account-zone interpretation is observable. Fixed resolved instants keep
their instant when the account zone changes; only account-floating values re-resolve.

Use the smallest reminder-specific adapter around shared time primitives needed
for supported response shapes. Keep raw due metadata, validate supplied consumed
values, preserve known recurrence information and its original language. The open
object does not justify making every field optional for task due, coercing null or
wrong types into successful schedules, inferring recurrence by parsing arbitrary
rule text, or dropping metadata because it lacks a CLI editor. Missing wording for
a known recurring reminder uses the specified `recurring` display fallback. When
metadata cannot establish complete local scheduling equivalence, retain it without
claiming equivalence; explicit keep preserves its identity. Workers must document
any additional concrete source contradiction and affected behavior, rather than
inventing a provider guarantee or expanding product scope.

Local matching is deliberately bounded: type, exact scheduling/offset and complete
applicable fixed/floating/recurrence/rule/language/zone semantics must establish
identity-compatible scheduling. Same next instant alone is insufficient. A new
locally fixed explicit input need not match an existing floating schedule at that
instant. Recurring/unknown English input stays an unresolved requested addition;
no local recurrence parser, read-only provider parser, automatic deduplication or
ID-preservation guarantee follows. Known duplicates including overlaps with keep
are rejected locally. Kept and locally established matches retain IDs and metadata;
other existing IDs are proposed removals before any task/reminder write. Preview
unknown input with `expression (Todoist): ...`; consent precedes submission.
Actual equivalent normalization can therefore legitimately use a new ID.

## Text, relevance and independent fixtures

`NoteSyncView.content` has default empty string and is not required. Inspect the
actual REST scoped-comment response as well; request-derived owner is legitimate,
not an invented mandatory item_id. Preserve identity/time for blank comments.
Attachment fields are completely unconsumed even when a schema lists them;
metadata differences cannot create a consumed-record conflict. Text update sends
same comment ID/content and omits attachment properties, without claiming live
attachment preservation. Activities no longer request note annotations or consume
extra_data.content; required owner/event/time and useful move/scope metadata remain.

Current._signature/_merge happen before _map, and init._Catalogue.projects/_discover
currently map all project/label display fields. Apply relevance at these choke
points too. Identity, owner/scope, lifecycle and interval are still mandatory to the
extent needed to decide contribution. Out-of-window or deleted live-body fields
are unconsumed, not fabricated defaults for retained records. Unknown ownership
fails. Keep endpoint pagination/event-ID/capability contracts and privacy intact.

Use a few source-cited minimal raw fixtures: the unchanged ItemSyncView due example
without timezone; NoteSyncView empty/default content; comments with absent or
non-null attachment data; NotificationSyncView minimal absolute due; full Due dates
floating/fixed recurrence examples. A factory that always inserts timezone,
attachment, recurrence and owner fields cannot establish support for omissions.
Keep real request assertions and representative malformed required identity/time/
control/pagination cases. Adapt superseded fixture assumptions, not production
behavior to a fake. Preserve no-normal-partial-report and unchanged-cursor evidence.

Controlled contract handling does not certify live notifications, recurring
advancement/delivery or attachment preservation. No live gate is added.
