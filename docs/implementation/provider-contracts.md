# Consumed provider contracts

Status: **Accepted**

Planning interpretation inspected 2026-10-26 against the retained bytes. This
document adds source navigation and implementation obligations already required
by the accepted design; it does not redefine product requirements or certify live
provider behavior. `docs/design/external/todoist/manifest.json` authenticates the
API-v1 JSON and subtask Help snapshot. The adjacent floating-time and GNU-less
manifests authenticate those separate sources. Preserve their bytes and provenance.

## Current resources and mutations

In `docs/design/external/todoist/upstream/api-v1.openapi.json`, the Sync tag's
description (`/tags/3/description`) owns the actual Sync resource and command
tables. Inspect Read resources, Incremental sync, Full sync data delay, Projects,
Tasks/Items, Task comments, Reminders and User plan limits. Use POST `/sync` with
form values containing JSON arrays, Bearer authentication, `sync_token` and
documented resources. No `activity` resource is supplied by Sync. Full/current
and omitted-unchanged delta fields have different interpretation. Account metadata
may change in the freshness delta; bound account identity cannot change.

Use documented `checked`, label names, `shared`, `inbox_project`, `workspace_id`,
`parent_id`, archive/deletion and ownership context. `ItemSyncView.added_at` is
nullable; a returned explicit null supersedes known time. Optional description
absence has the explicit accepted product mapping. Do not demand unrelated
optional fields or reject legitimate response alternatives by applying a generic
schema validator more strictly than consumed behavior. Retain strict behavior
fields and distinguish malformed, unsupported managed feature and invalid domain.

The Sync command response identifies the exact UUID in `sync_status`; creates
also need `temp_id_mapping`. Missing/malformed status is unknown, not accepted or
rejected. Command text/title matches do not prove acceptance. Reconciliation must
use evidence attributable to the attempted command/occurrence; an unchanged valid
recurring object is insufficient. No pinned invalid-sync-token discriminator has
been established. Credential invalid_token and generic HTTP failure cannot trigger
an invented automatic replacement. The explicit clear-and-refresh path remains.

The Sync Move a task table defines `item_move` with id and exactly one destination:
parent_id attaches; project_id makes a root task in that project, including explicit
promotion. Preserve the known subtree and reconcile its actual category/parents
without recreating IDs. The table specifies the selected item and does not prove
every archived-descendant propagation case. Controlled independent after-states
verify application behavior; indispensable contradictory provider evidence must
stop affected implementation and return that concrete issue to Planning/Design.
Do not introduce all-history childlessness discovery as a workaround.

Complete task archives the task/subtasks; ordinary child-first application ordering
still applies. Uncomplete item can restore ancestors and returns ordinary UUID ok;
it does not promise an items_restored payload. Complete a recurring task explicitly
supports is_forward 1/0 and reset_subtasks 0, preserving completed children.
Recurring undo must use this operation, not ordinary reopen. Archived completion
absence from active Sync is expected; bounded completed/lifecycle evidence is used
to reconcile it. Known archived owners remain eligible for their own supported
post-completion note_add; active lookup presence is not a prerequisite.

The reminder_add argument table specifies relative type, item_id and minute_offset
before an item's timed due. Its introductory relative-reminder example is
internally inconsistent (it says type absolute); use the explicit argument table
and accepted REQ-SYNC-021/026 mapping, and label the discrepancy in fixture notes.
Integer 0 must remain literal zero; never truth-test it as absence. Managed other
reminder types receive an accurate limitation; unrelated types are discarded
before managed restrictions. Mutations use ordinary UUID/create temp IDs.

Due dates tag and Sync item_add/item_update define date-only, floating date with
null timezone, and fixed UTC date plus recurrence timezone. Do not send a Sync
due.datetime key. English strings use lang en; occurrence moves preserve the
existing recurrence string/is_recurring/lang/timezone while updating date. The
floating DST policy is an application choice from REQ-SYNC-021, not a provider
notification guarantee. Local DST input refusal is different. Actual returned
precision within inclusive +/-2 seconds is accepted only with strict local day,
exact/date-only status and recurrence/timezone semantics; no-op comparison is exact.

## Historical retrieval and boundary coverage

`paths["/api/v1/tasks/completed/by_completion_date"].get` defines explicit UTC
since inclusive/until exclusive and requests of at most three months. Its
TasksCompletedDateResponse schema describes `items` and explicitly says
next_cursor is omitted when there is no next page. That is the retained evidence
for terminal omission, even on a full page; short page length is not the proof.
Reject malformed supplied continuation and keep all parameters fixed across
pages. The endpoint's ItemSyncView records describe occurrences; a recurring
completion record with checked false does not override a current active lifecycle.

`paths["/api/v1/activities"].get` supplies date_from inclusive/date_to exclusive,
opaque pagination and documented scope/object_event_types/annotation filters.
ActivityEvents uses separate object_type/object_id/event_type/event_date;
integer/null/omitted ID is distinct from string task/comment identity. Optional
parent_item_id identifies a note's owner, not an arbitrary item's parent.
extra_data.content may be a string; content-free deletion is valid. Supplied IDs
deduplicate; anonymous source order/multiplicity is retained under the accepted
duplicate tolerance. `PaginatedList_ActivityEvents_` requires results and
next_cursor (null terminal). Never extend the completed omission exception here.

Retrieve a covering interval then filter product eligibility exactly `(start,end]`.
A simple supported strategy requests from start through an exclusive upper bound
widened to the next whole UTC second after end (including when end is integral),
then filters full supplied instants. It uses documented datetime filters and
avoids dropping subsecond events or the exact fixed end. Completed window splitting
must keep every request within three calendar months; bounded shorter windows are
acceptable. Use nonoverlapping wire windows or stable identity deduplication for
overlap, preserving distinct recurring occurrences by item plus completion instant
rather than collapsing them to one item. No timestamp rounding changes cursor
advancement/eligibility. Consumers must fail explicit incompleteness rather than
silently claim a range whose endpoint could not be covered.

`paths["/api/v1/comments"].get` requires exactly one task_id/project_id; the
application uses task_id with complete results/next_cursor pagination. A task ID
may identify any supported step. `NoteSyncView` does not require item_id; scoped
request context supplies owner identity. Sync notes have their own item_id
contract. Attachment metadata is file_attachment; current surviving text and
deletion status require complete current comments, not activity annotation alone.

`paths["/api/v1/tasks/{task_id}"].get` is active-only. A 404 is unresolved identity,
not archive/deletion proof. For eligible archived owners and ancestors, use
supported completed/current evidence when available, and fail explicitly before
normal report output if necessary current metadata cannot be established. Local
last-observed records do not become authoritative current metadata. No arbitrary
archive scan endpoint or successful reconstruction promise is added. A move's
known-descendant validation is less demanding than a report's required owner
resolution; do not conflate them.

## Executable evidence and environment

T04–T07 inspect actual adapter requests with independent endpoint-shaped fixtures;
T08 and workflow tasks compose those results through storage/commands. Useful
negatives include missing/wrong identity, checked/capability types, malformed/repeated
continuation, valid nullable creation and optional description, scoped comments
without item_id, unknown annotations and content-free deletion. Use documented
variants without synthesizing exhaustive schema permutations. Fixtures cite their
source section and inspection date and do not imply live provider observations.

The retained GNU-less 590 manual supports -F fit, -R color, G navigation and q exit.
It does not certify the future runner image. Setup must supply less, zone data and
CPython 3.11 in pinned Linux/amd64 Docker; T17 performs bounded real-less PTY probes
there. Other pager failures and SIGINT use controlled processes. The pager gets
complete rendered input through a restrictive temporary file with inherited
terminal access, avoiding early-quit pipe ambiguity. No pager bundling/default,
full terminal UI test suite or real Todoist release gate is introduced.
