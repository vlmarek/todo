# Todoist adapter contract

Status: Accepted

## API and authentication boundary

The implementation targets `https://api.todoist.com/api/v1`, including its
POST-only `/sync` endpoint, without a third-party Todoist client. Authentication
uses one resolved personal API token as a bearer credential. OAuth and silent
API-version substitution are outside scope.

Every synchronizing command reads authenticated user/account ID, IANA timezone,
project ownership/sharing state, and `user_plan_limits`. A mismatch with the
local account binding aborts before provisioning or mutation. Plan information
controls activity-retention warnings/errors and reminder capability without a
separate report-time plan request.

## Synchronization

The `/sync` endpoint retains legacy Sync resource/command names even under API
v1. The adapter requests the current resources needed for projects, labels,
items/tasks, notes/comments, reminders, user identity, plan limits, and deletion
tombstones.

Initial or replacement synchronization uses `sync_token=*`. Todoist may return
a full snapshot generated before the response time, so every full sync is
followed by one incremental sync using its returned token before state is called
current. Normal incremental sync persists the returned token, merges objects by
stable ID, and applies tombstones. An invalid token triggers full-plus-incremental
replacement; partial incremental data is never treated as a full cache.

Each synchronization builds a complete candidate cache in memory. References
may arrive before their parents within a response and are validated only after
all requested resources are merged. A later tombstone wins over an earlier
object in synchronization order; conflicting live representations for one ID
are a synchronization failure. The new token becomes durable only in the same
atomic cache replacement as its merged state. Full replacement retains the
prior compatible completed-search index except for authoritative deletions; an
incompatible schema rebuild may lose it as explicitly documented.

Current project data is fetched broadly enough to detect a bound root/category
that was moved, archived, shared, or transferred outside managed scope. Binding
IDs, not names, establish identity after init.

## Domain mapping

The adapter maps and validates:

- account identity, account timezone, plan name, activity-history availability
  and day limit, reminder capability
- project identity, name, parent/workspace, sharing, archive, and deletion state
- task identity, project/parent identity, title, description, priority,
  completion state, labels, due/recurrence, and timestamps
- comment identity, task identity, current content, `posted_at`, and deletion
- reminder identity, task identity, relative offset, and deletion state
- activity object/event type, object/parent context, event timestamp, optional
  event ID, and annotated current comment data where available

Todoist numeric priorities map as `4 -> P1`, `3 -> P2`, `2 -> P3`, and
`1 -> P4`; writes apply the inverse mapping. A due object maps its normalized
date/date-time, timezone, source string, and recurrence flag without treating
the source string as another editable date. Natural-language due strings are
submitted with English date language. Locally normalized date-times include an
offset so the account timezone and daylight-saving resolution are explicit.

Unknown fields are ignored. Unsupported values or shapes in recognized fields
that affect identity, hierarchy, selection, visibility, scheduling, completion,
reporting, reminders, or mutation safety fail rather than being normalized.

Offset-free values use the Todoist account timezone. Explicit-offset values are
converted to instants and persisted in UTC. The cache retains the last synced
account timezone for offline rendering.

## Completed objects and activity

`/sync` `completed_info` supplies aggregate counts, not the completed objects
needed for selection or reports. The adapter retrieves completed tasks and
steps from:

```text
GET /api/v1/tasks/completed/by_completion_date
```

Each request has an explicit UTC `since`/`until` range no longer than three
months and follows `next_cursor` until null. Report and recent completed-item
workflows request only their `(cursor, end]` coverage; interval inclusivity is
normalized in the adapter so domain code receives start-exclusive/end-inclusive
events.

Completed objects fetched for any workflow are merged into the disposable
completed-search cache. Cache coverage remains best-effort and is not inferred
from object timestamps alone.

Activity comes from cursor-paginated `/api/v1/activities`. Required event types
include item/task completed and uncompleted plus note/comment added, updated,
and deleted. Activity event IDs may be null; deduplication and ordering then use
a canonical event fingerprint plus stable response order without collapsing two
distinct occurrences merely because their object and timestamp match.

A comment object's `posted_at` is its original posting time and is not a reliable
edit timestamp. Report edit eligibility/order comes from `note:updated` activity
events; rendered text comes from the surviving current comment. Request
`annotate_notes=true` where it reduces additional lookups, but still retrieve
any comment page required for complete current text and deletion checks.

## Pagination and completeness

Tasks, projects, sections, labels, comments, activity, and completed-task
endpoints that return `next_cursor` are followed until null with identical query
parameters on every page. Missing, repeated, malformed, or parameter-incompatible
continuation state is a retrieval failure. Retried pages deduplicate by stable
object ID or safe event identity.

After each completed tenth page of one endpoint, the adapter prints the fixed
nonsemantic progress line defined in `output-contract.md` to stderr. It imposes
no hidden local result limit and never marks truncated retrieval complete. Any
required report page failure aborts before normal report output.

## Mutations

Sync mutations use a unique command UUID and, for creation, a unique temporary
ID. Retry is allowed only when these identifiers make replay safe.

- ordinary regular reopen uses `item_uncomplete`; Todoist may reinstate required
  ancestors, which the adapter returns to the workflow for display
- recurring completion uses `item_update_date_complete` in the forward
  direction; recurring undo uses the same command with `is_forward=0`
- ordinary completion uses the relevant close/complete command after local tree
  validation
- delete uses direct task/comment deletion and never a reopen workaround
- repeated creates and multi-item completion are submitted/observed in the
  workflow's required order and are not assumed transactional

The normal REST reopen endpoint is not used to undo an active recurring task,
because active recurring tasks are ignored by that endpoint.

## Retries and reconciliation

Read requests and idempotent Sync requests follow the timeout, status, backoff,
and `Retry-After` policy in `quality-requirements.md`. An ambiguous transport
result triggers synchronization and authoritative reconciliation instead of an
unchanged-success guess. Accepted remote changes are not rolled back because a
later cache write or later command failed.

## Report consistency

The application captures the report end before the adapter's first request.
The adapter performs one current-state synchronization, validates plan history,
retrieves all interval activity/completed-object pages through that fixed end,
and retrieves all required comments. Todoist offers no atomic cross-endpoint
snapshot, so there is no final comparison sync.

Regular reopened items are filtered from current state. Recurring
`completed`/`uncompleted` events are exposed in sufficient order for the domain
to cancel the latest unmatched occurrence. Current managed-project membership
and survival are returned for final report inclusion.
