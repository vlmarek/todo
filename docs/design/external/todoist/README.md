# Todoist provider evidence baseline

This is provider evidence for the current design, separate from the binding product
requirements in ../../todoist-adapter.md. The application restricts managed scope,
hierarchy, text, reminders, hiding and report behavior; those restrictions are not
claims about everything Todoist supports.

[upstream/api-v1.openapi.json](upstream/api-v1.openapi.json) is the complete original
OpenAPI JSON object embedded at `spec.data` in the official
[Todoist API v1 reference](https://developer.todoist.com/api/v1/), retrieved on
2026-10-24 without authentication. Its bytes were extracted unchanged from the
published HTML, not reconstructed from examples or an SDK. [manifest.json](manifest.json)
records URL, retrieval instant, provider/API version, extraction location, byte
counts and SHA-256 checksums. All its local JSON references resolve within this
retained object. The provider exposes API version 1, not an immutable release/build
identifier. Upstream text and examples remain upstream evidence, not synthetic tests.

Relevant initial pointers in the retained object:

- `paths["/api/v1/tasks/completed/by_completion_date"].get`: bounded completed
  retrieval, required since/until, optional cursor/limit and response contract.
- `paths["/api/v1/activities"].get`: event/scoped date filters, annotations and
  paginated response contract.
- `paths["/api/v1/comments"].get`: owner-scoped task_id/project_id queries and
  current paginated comments; Sync notes remain a different consumed shape.
- `tags[name="Sync"].description`: the complete Sync resource/command reference
  (Sync is documented here rather than as a structured paths operation). Use its
  Read resources, Incremental sync, Projects, Items, Notes, Reminders and User
  plan limits sections for the consumed resources and mutation commands.
- `tags[name="Due dates"].description`, `tags[name="Pagination"].description`
  and referenced `components`: due representations, pagination and shared schemas.
  Planning must check each consumed operation; names or prior application
  assumptions do not prove a contract.

## Activity-filter serialization clarification

Re-inspected the retained snapshot offline on 2026-10-27. Under
`paths["/api/v1/activities"].get`, the `object_event_types` parameter describes an
array of strings, while `x-codeSamples` (including "Multiple event types") sends
one JSON-encoded array query value. The schema has no explicit serialization
style; do not infer repeated scalar parameters from the array type alone.
The application's selected encoding and the preceding diagnosis's limited live
observation are documented separately in
[request-conformance.md](../../request-conformance.md), REQ-SYNC-032. The retained
bytes, manifest checksums and retrieval dates are unchanged. No new upstream
snapshot or authenticated response fixture is added.

The initial snapshot establishes an offline reference and supports focused
contract investigation. It is not a complete audit, successful live-account smoke,
or proof of uncertain cursor-omission, DST, precision or operation-specific replay
semantics. See ../../open-questions.md for dependent obligations and feasibility
questions. Plan resolves consumed details before finishing affected assignments,
using independent request/response fixtures and adapter-to-workflow evidence.
Missing or contradictory evidence cannot be filled with invented wire fields.
Provider evidence alone cannot amend promised product behavior. No authenticated
Todoist call or live mutation was performed, and no such test is required for this
handoff. Routine implementation should use these retained bytes offline.

## Creation timestamps and synchronization-token evidence

Re-inspected the pinned bytes offline on 2026-10-25; no provider refresh or live
request occurred. `components.schemas.ItemSyncView.properties.added_at` is
`anyOf` string/null, format date-time, described as creation time or null if
unknown. This is a provider fact, distinct from the operator's choice of where
unknown creation times sort. Items returned by the completed-object endpoint also
use ItemSyncView; use each consumed endpoint's required/optional field contract.

The Sync tag (`/tags/3/description`), Overview / Read resources, Incremental sync,
Full sync data delay, and Response / Error document `sync_token`, `*`, the
`full_sync` full-versus-delta flag, and the follow-up freshness request. Inspection
found no specified invalid-sync-token error tag, code or status discriminator.
Authorization's credential `invalid_token` is a different failure. This is a limit
of the pinned evidence, not a claim that the provider never invalidates sync tokens.
The source digest and manifest remain unchanged. An injected `InvalidSyncToken`
exception is synthetic control-flow evidence, not an observed wire response.

Application policy is defined inline in REQ-SYNC-013/021/027, REQ-DOM-009/014,
REQ-CLI-021/029 and TPL-DETAIL. The operator chose known times newest first,
unknown times last by stable ID, and evidence-based automatic replacement with
explicit clear-and-refresh otherwise. No guessed invalidation classifier or
unclassified-error full-refresh fallback is authorized. Planning must retain the
source traceability of any production discriminator and return contradictory new
evidence through the normal provider-update/design workflow.

## Recursive task depth evidence

The original official [Use sub-tasks in Todoist](https://www.todoist.com/help/todoist/features/use-sub-tasks-in-todoist-kMamDo)
HTML is retained unchanged as upstream/subtasks-help.html, retrieved 2026-10-24;
the article displays an October 15, 2026 update date. Its “Turn an existing task
into a sub-task” section states four indent levels below an unindented task:
root task at depth 0 and descendant steps at depths 1–4. The source file checksum
and retrieval details are in manifest.json under additional_sources. It contains
ordinary public help markup, not an authenticated response or synthetic fixture.

The official API v1 reference was also re-examined on 2026-10-24. Create Task,
Move Task, Sync item_add and item_move use parent_id; their documented contracts
do not state a numerical nesting maximum. The absence of such a field/schema
constraint does not establish unlimited backend support. The operator selected
the help-documented boundary for this product, not an empirically demonstrated
API rejection threshold. No authenticated account request, deeper test creation
or live mutation was made. The retained API and Help bytes here are the available provider evidence;
source-project research is provenance, not a required host-only implementation input.
The re-examined API specification bytes are identical to that retained snapshot;
no API contract update or version substitution is implied.

Relevant existing snapshot pointers: paths["/api/v1/tasks"].post parent_id;
paths["/api/v1/tasks/{task_id}/move"].post parent_id; the Sync tag's Tasks,
Add a task, Move a task, completion and uncompletion sections. Planning checks
operation-specific subtree propagation and archive/ancestor resolution before
claiming those composed workflows. Product roles, category inheritance, sibling
uniqueness, hiding and lifecycle restrictions remain application requirements,
not additional provider guarantees. Later provider evidence contradicting the
agreed behavior returns to Design rather than silently weakening the product.
