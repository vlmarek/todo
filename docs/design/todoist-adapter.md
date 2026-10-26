# Todoist API v1 adapter contract

Status: **Accepted**

todo-3 specification, revision 2. See [README](README.md).

### REQ-SYNC-021 — API v1 authentication, capability, and domain mapping

The adapter must directly target `https://api.todoist.com/api/v1`, including the
POST-only `/sync` endpoint, without a third-party Todoist SDK and without silent API
version substitution. It must use the one resolved personal API token as a Bearer
credential.

Use the documented POST `/sync` form encoding
(`application/x-www-form-urlencoded`), with JSON-encoded `resource_types` and
`commands` form values. REST requests must use their own documented parameters
and bodies; SDK property names and another endpoint's shape are not wire contracts.

Every synchronization must obtain and validate authenticated account ID, IANA
timezone, project ownership/sharing/workspace state, and `user_plan_limits` before
provisioning or mutation. A mismatch with binding must abort. Capabilities must come
directly from `user_plan_limits.current`, never from `next` or a table indexed by
plan name. No separate plan-name lookup or report-time capability request is needed.

The current resource must provide `activity_log` as a boolean,
`activity_log_limit` as an integer (excluding booleans) with value `-1` or greater,
and `reminders` as a boolean. `-1` means unlimited history; zero means no retained
history; a positive integer is the retained number of days. Missing or malformed
required capability fields must fail clearly; do not invent defaults or infer
capabilities from a name or paid/free classification. These values must be refreshed
through normal synchronization even when the plan name has not changed.

`plan_name` is not an application capability or required account field. Do not map,
validate, display, or persist it for application behavior. Missing, empty, unfamiliar,
or malformed `plan_name` must have no effect when required account/capability fields
are valid. For example, otherwise identical responses containing `pro_legacy`, an
arbitrary future name, or no name must produce the same capability behavior.
An `activity_log` value of false or a retention limit of zero is valid account
metadata: it must not prevent setup, synchronization, or task/reminder operations.
Report rejection for those values is defined by REQ-REPORT-009.

The adapter must map and validate the behavior-affecting fields for:

- account identity, timezone, activity-history access, history limit, and reminder capability;
- project ID, name, parent/workspace, ownership, sharing, archive, and deletion;
- task ID, project/parent, title, description, priority, completion, labels,
  due/recurrence, and timestamps;
- comment ID, task ID, content, `posted_at`, activity, and deletion;
- reminder ID, task ID, relative offset, and deletion;
- activity type, object/parent context, timestamp, optional event ID, and annotated
  comment data where supplied.

For `/sync` projects, read `shared`, `inbox_project`, `workspace_id`, `parent_id`,
`is_archived`, and `is_deleted`. Do not substitute `is_shared`,
`is_inbox_project`, or `is_organization`. The documented absence of optional
Inbox/workspace fields on personal projects is valid; malformed supplied values
are not. Missing required safety metadata must not default to personal eligibility.
A shared, Inbox, or workspace-owned root/category must be rejected before
provisioning or task mutation, including when only documented wire fields are
present. Apply the same eligibility rule in discovery, preflight, refresh,
reconciliation, and diagnostics. Task `labels` are label names, not label IDs.

Establish a comment/reminder/activity object's managed ownership from documented
identity/context or the scoped request before validating its content or supported
feature subtype. Clearly unrelated objects must be discarded without applying
managed-domain text, scheduling, or reminder restrictions. Missing context needed
to establish ownership must fail clearly, without exposing unrelated payloads.
Managed task and step comments are both supported. Resolve each note's owning
item ID against the merged task/step hierarchy; preserve that ownership through
full/incremental mapping, diagnostics, mutation reconciliation and cache reload.
A valid comment on a managed step at any supported depth must not be discarded
or diagnosed as a top-level-only ownership violation. Resolve recursive parent
relationships by stable parent_id after merging full/incremental resources, then
apply REQ-DOM-009's depth, cycle, scope and completed-ancestor invariants. Nested
steps within depths 1–4 are valid. All item-owned fields retain the same mapping
at every depth; do not transfer comments to an ancestor or discard a branch.

Todoist priorities must map `4 -> P1`, `3 -> P2`, `2 -> P3`, `1 -> P4`, with
the inverse on writes. Due data must retain normalized date/date-time, timezone,
source expression, and recurrence flag without exposing the source as a second
editable property. Natural-language expressions must be submitted with English
date language (`due.lang: "en"`), including creation, scheduling, and hiding.
For a locally resolved occurrence-date move of a recurring item, preserve the
existing due string, is_recurring=true, language and applicable recurrence timezone
while changing its current date. Sync item_update can carry these fields together;
do not use a fresh is_recurring=false value or silently replace the rule with the
requested one-off date expression. Read back the exact item and validate its new
occurrence and preserved rule before success. This does not complete an occurrence
or establish future advancement from an unchanged valid object. Timed, floating,
fixed-time and DST cases require the evidence identified in open-questions.md.
Locally resolved date-times identify an explicit instant and must be serialized
in the documented fixed-time representation.

The Sync due object uses `date` for all three documented representations:

| Wire value | Domain interpretation |
| --- | --- |
| `2026-11-12` | Date-only attention in the account timezone |
| `2026-11-12T16:00:00`, `timezone: null` | Exact floating wall time in the Todoist account timezone |
| `2026-11-12T15:00:00Z`, `timezone: "Europe/Prague"` | Exact UTC instant; retain the named timezone for recurrence |

Accept documented fractional seconds as well. Read timed values from `due.date`,
not a required `due.datetime`. On writes, date-only values use `due.date`;
locally resolved exact instants use UTC `due.date` ending in `Z`, with the
documented timezone metadata where needed. Never send the invented `datetime`
key inside a Sync due object or truncate a timed value to a calendar date.
Preserve the difference between floating wall time and fixed instants across
account-timezone changes. The host timezone must not affect either interpretation.

For remote offset-free floating due values, apply this explicit application policy
in the authoritative account IANA timezone. At a repeated wall time (DST overlap),
choose the earlier absolute instant. At a nonexistent wall time (DST gap), shift
the wall time forward by the actual transition gap, retaining its minutes,
seconds and fractional seconds; do not snap to the first valid minute. For
Europe/Prague, `2026-10-25T02:30:00` resolves to `2026-10-25T00:30:00Z`, and
`2026-03-29T02:30:00` resolves as `03:30` local, `2026-03-29T01:30:00Z`.
Use that resolved attention instant/day consistently for sorting, overdue status,
countdowns, display and domain comparisons. Preserve the original floating due
representation and recurrence metadata; resolving it must make no remote change.
Re-resolve floating values in a newly synchronized account timezone; fixed UTC
values retain their absolute instant. This policy is an operator-selected
application interpretation, not an assertion of undocumented Todoist DST or
notification behavior. It does not change REQ-SCHED-013's refusal of ambiguous or
nonexistent locally entered/locally calculated wall times: that input still
requires an explicit ISO offset. Ordinary floating, fixed and date-only values
keep their existing semantics.

Supported relative reminders must be created with `reminder_add` arguments
including `item_id`, `type: "relative"`, and `minute_offset`, plus the ordinary
command UUID and create temporary ID. Creation-time and later scheduling paths
must use the same contract. For managed relative reminders, `minute_offset` must
be an integer greater than or equal to zero, excluding booleans. Accept an
existing `minute_offset: 0` as a reminder at the exact attention instant during
initialization, full/incremental synchronization, and reconciliation; retain its
identity and offset through cache serialization/reload and offline inspection.
A CLI `0m` request must write literal `minute_offset: 0`, with the ordinary
relative-reminder arguments and mutation safety rules. Missing, null, negative,
boolean, string, or fractional offsets remain invalid; do not default them to
zero, drop a present zero, or substitute another offset. Task and step reminders
share this invariant. The existing exact-attention and capability requirements
remain in force, including recurring timed attention.

Inspect reminder `type` before interpreting an offset;
do not interpret absolute/location reminders as relative. Unsupported managed
reminder state must produce a precise limitation/diagnostic under the existing
strict-domain rules; unrelated reminder types must not block managed workflows.
No additional reminder type or attachment workflow is introduced by this revision.

Unknown response fields must be ignored. Unsupported shapes or values in recognized
fields affecting identity, hierarchy, selection, visibility, scheduling,
completion, reporting, reminders, or mutation safety must fail clearly. Documented
wire representations must be mapped into the domain; this rule must not reject
valid API data merely because internal names/types differ, invent missing values,
or relax genuine domain invariants. Distinguish an adapter-contract failure or
unsupported product feature from invalid remote data in recovery guidance.

### REQ-SYNC-027 — Nullable creation-time wire mapping

`ItemSyncView.added_at` explicitly permits null when creation time is unknown.
Map that valid alternative to REQ-DOM-014's unknown creation time for tasks and
steps, including completed-object records using this schema. Preserve known aware
instants and their precision. Null is not malformed data or an unsupported feature.
Do not turn a missing required field, empty/malformed timestamp, naive value or
wrong recognized type into unknown; omission is allowed only where the consumed
endpoint contract permits it. Incremental omission of an unchanged item retains
its prior representation under REQ-SYNC-013; an explicit null on a returned item
is authoritative unknown. Comment and other timestamp contracts remain unchanged.

### REQ-SYNC-013 — Full/incremental synchronization, tokens, tombstones, and stable IDs

The `/sync` request must obtain all current resources needed for managed projects,
labels, tasks/items, comments/notes, reminders, user/current-capability state, and deletion
tombstones. Current project retrieval must be broad enough to detect a bound root
or category moved, archived, shared, transferred, or deleted.

For these current resources, request the documented Sync resource types `user`,
`user_plan_limits`, `projects`, `items`, `labels`, `notes`, and `reminders`.
`activity` is not a Sync resource type: do not request it or require an `activity`
collection in full or incremental `/sync` responses. Its absence does not make
current-state retrieval incomplete. Keep validation of the actual required
current resources and account/capability fields strict; this distinction does not
permit defaulting missing required data.

Initial or client-requested replacement synchronization must request `sync_token=*`, build a full
candidate snapshot, then perform one incremental sync with the returned token before
calling it current. Normal synchronization must merge by stable string ID and apply
tombstones in synchronization order. Partial incremental data must never be treated
as full state.

Automatic replacement requires evidence: a valid server response declaring
`full_sync: true` is a complete replacement candidate rather than a delta, and
must receive the same follow-up incremental freshness sync before publication.
A specifically established invalid synchronization-token signal may trigger a
new `sync_token=*` full-plus-incremental sequence only when retained authoritative
provider evidence defines how to recognize that signal. Do not guess error tags,
codes, message substrings or statuses. In particular, a Bearer credential failure
such as authentication `invalid_token` is not synchronization-token invalidation.
A dependency's typed signal is usable only when its production origin is supported
by that evidence; injecting a typed exception proves control flow alone.

When invalidation cannot be established, fail the incremental operation explicitly
with its actual classified cause; do not attempt a full replacement merely because
of a generic HTTP error, timeout, malformed response or validation failure. Preserve
published state/token and last-successful-snapshot rules under REQ-CACHE-008.
Explain that automatic sync-token recognition is unavailable for an unclassified
failure; where applicable offer the existing explicit
`todo --clear-cache --refresh now` recovery under REQ-CLI-029, with its disclosed
cache deletion and preserved history. Credential/configuration or authoritative
managed-state problems still require their specific correction; clearing is not
presented as fixing them. There is no guaranteed automatic recognition of every
expired/invalid synchronization token in the absence of a supported discriminator.
This is an accepted recovery limitation, not permission to invent provider behavior.

Replacement must be bounded to the full candidate and its one freshness delta;
a failed freshness request or another full response at that step fails without
publishing or restarting another replacement sequence. Existing transport retry
and backoff rules still apply to individual requests. Recovery reads do not replay
mutations, clear unreported history, reset binding, or advance the report cursor.

References may precede parents and must be validated after all requested resources
are merged. A later tombstone wins over an earlier live object. Contradictory live
representations within one response/generation are a synchronization failure;
a later authoritative delta may legitimately update an earlier object. This also
applies to `user` and current capability metadata: same-account timezone or other
metadata updates must replace earlier values, not fail because they changed.
Account identity changes must still abort. Omitted unchanged incremental resources
retain their prior state; omission in a full replacement must not inherit stale
current objects. The new token and merged cache must become visible in one atomic
replacement; a token must never advance
without its corresponding state. A compatible full replacement retains completed
history under REQ-CACHE-006 except authoritative deletions or confirmed departure
from managed scope. That history is separate from disposable cache replacement.

### REQ-SYNC-025 — Completed objects, activity, comments, and complete pagination

Sync `completed_info` is not a completed-object source. Completed tasks and steps
must be retrieved from:

```text
GET /api/v1/tasks/completed/by_completion_date
```

Each completed-object request must use explicit UTC `since` and `until`, cover no
more than three months, and exhaust the actual endpoint's documented continuation
mechanism. A next_cursor, when provided, is followed until its terminal value.
A valid completed-object response containing items but omitting next_cursor must
not fail solely because that cursor field is absent. Determine completeness using
endpoint-specific supported evidence; absence alone is not proof of exhaustion.
Before choosing the handling, establish the response/limit/continuation semantics
from current authoritative contract material and, where needed, scoped evidence;
retain that evidence with independent synthetic fixtures. Do not apply this
exception indiscriminately to activities/comments/other cursor-bearing endpoints.
When completeness genuinely cannot be established, fail with the operation and
useful history-retrieval context, leaving the cursor unchanged, rather than a raw
internal field error or a silently truncated report/delete preview. The uncertainty
and dependent implementation are retained in open-questions.md. Its wire interval is
`[since, until)`, while the product interval is `(cursor, fixed end]`. Retrieval
bounds must cover every eligible instant before local filtering; filtering cannot
recover an event omitted by the server. Preserve fractional-second precision, or
query a minimally widened documented interval and filter precisely. Window splits
must not drop or double-count boundary occurrences. Never round down the end and
then claim the discarded portion as covered. A completion exactly at the fixed end
is included; one exactly at the cursor is excluded. Merge eligible fetched objects
into separate unreported history under REQ-CACHE-006. Boundary widening is retrieval only:
it cannot extend report eligibility or advance the cursor beyond the fixed end.

Activity must be retrieved from cursor-paginated `/api/v1/activities`, including
task/item completed and uncompleted and comment/note added, updated, and deleted
events. Retrieve it separately for workflows that require event history; `/sync`
does not supply it. Do not interpret a missing Sync `activity` field as evidence
that no historical events exist or substitute an empty history for required
activity retrieval. A supplied stable event ID supports straightforward deduplication. When an
event has no ID, retain it in stable response order without elaborate anonymous
identity reconstruction. Possible duplicate anonymous report entries are accepted;
missing IDs or ambiguous multiplicity alone do not make retrieval fail. Do not
collapse anonymous entries solely by object ID and timestamp or claim unique-event
proof. This tolerance does not waive required pagination, fields or report data. Use the documented `date_from`/`date_to`
activity filters, not the completed endpoint's `since`/`until`; translate their
inclusive-start/exclusive-end semantics to the same precise product interval.
Use documented scope/event filters where applicable and retain complete retrieval.

Activity has separate `object_type` and `event_type` fields. Interpret
`object_type: "item", event_type: "completed"` as an item completion and
`object_type: "note", event_type: "updated"` as a comment edit. Comment
`object_id` identifies the comment; `parent_item_id` identifies its owning task
or step.
Do not expect invented `comment_added`/`comment_updated` wire event types or treat
a comment ID as its task ID. Accept documented integer event IDs (excluding
booleans), retaining a stable canonical identity for ordering/deduplication;
null IDs retain the accepted anonymous-entry/source-order rule. Task/project IDs remain strings.

`posted_at` is original comment time, not edit time. Reports must derive edit
eligibility/order from activity and render current surviving content. The adapter
may request `annotate_notes`, interpreting documented annotation fields such as
`extra_data.content` without requiring an invented nested `extra_data.note` object.
It must still fetch every page needed for complete current text and deletion status.

Interpret annotations according to object/event type and the documented field
shape. In particular `extra_data.content` can be a plain string, such as a task's
title or annotated note text; it is not universally a nested Comment object.
Do not pass every event's content through the comment-object mapper, require
comment ID/posted_at fields inside a string, or invent missing metadata. Note
ownership, identity and event time come from the documented event fields; fetch
required current surviving content through the comments endpoint. An event with
no content, such as a deletion, is not malformed merely because it lacks an
annotation. Required identity/time/ownership failures still fail explicitly;
never silently drop qualifying activity to make a report succeed.

The shared retrieval contract must support both report and bounded deletion
without rejecting valid string annotations. Deletion may use a narrower completed-
object retrieval path when activity/comments are unnecessary to its promised
preview/selection; that internal choice must preserve all bounded descendants,
history retention and refusal/confirmation guarantees. Reports still require
complete qualifying activity/current-comment evidence and unchanged cursor on
failure. No blanket skip-malformed-events policy is introduced.

Current REST comments use `GET /api/v1/comments?task_id=TASK_ID`, with
`results` and `next_cursor`. TASK_ID may be a parent task or a step. Associate
comments with that specific owner through the scoped
request; the documented response need not contain Sync's `item_id`. Sync `notes`
retain their own `item_id` contract. Required current comments must be retrieved
for every relevant surviving report task or step, including eligible archived
owners, rather than only parent task IDs or IDs present in active Sync. A step's
comments are not the parent's comments endpoint result. Deletion and unsupported managed
comment content retain the existing domain rules; attachment metadata must be read
from the documented `file_attachment`, not an invented top-level `file_name`.

For reports, required current archived owner/parent metadata that cannot be
established through supported evidence causes the explicit nonzero failure and
unchanged cursor in REQ-REPORT-011. Do not assume active-task lookup returns
archived objects, invent an archive endpoint or historical scan cutoff, or treat
an empty bounded completion window as proof of all-history absence. Successful
resolution of every arbitrarily old archived owner is not guaranteed. This
exception preserves complete retrieval for the requested supported scopes and
the known-owner post-completion mutation workflow under REQ-SYNC-026.

For move preflight, use available surviving-child evidence under REQ-MUT-004;
there is no obligation to enumerate all archived children or prove their absence.
Do not infer that comment-owner discovery provides a complete child enumeration.

Every cursor-bearing project, task, label, comment, activity and completed-object
response must be exhausted with identical query parameters under its actual
endpoint contract. Missing required, malformed, repeated or incompatible
continuation state remains a failure. The completed-object omission exception
above is valid only with endpoint-specific evidence of complete retrieval; it
must not weaken other endpoints or manufacture a terminal cursor.
Deduplicate by supplied stable object/event identity where available;
anonymous entries may repeat under the rule above. After every
tenth completed page of one endpoint, emit `TPL-PAGINATION-PROGRESS`; never impose
a hidden result limit or treat truncation as complete.

### REQ-SYNC-026 — Idempotent mutations, authoritative reconciliation, and no rollback

Every Sync mutation must use a unique command UUID and every create must also use a
unique temporary ID so safe replay and authoritative result matching are possible.
Ordered creates and multi-object mutations must be observed in workflow order and
must not be assumed transactional.

The adapter must use direct Todoist operations consistent with the domain:

- ordinary non-recurring reopen via `item_uncomplete`, returning any restored ancestors;
- recurring completion and undo via `item_update_date_complete`, with backward
  `is_forward=0` for undo;
- ordinary completion/close after local tree validation;
- identity-preserving category and parent moves under REQ-MUT-004;
- direct task and comment deletion without reopen workarounds.

For Sync `item_move`, send `id` and one destination only: `parent_id` for attaching
to the selected parent, or `project_id` for a standalone task in the selected
category project. The latter also implements explicit promotion in the current
category. Do not substitute `item_update` or combine Sync destination fields.
Comments use the owning item's ID through `note_add.item_id` or REST `task_id`;
neither conversion nor reparenting transfers comments to the parent or recreates
them. The destination parent may itself be a step. Reconcile the complete known
subtree's parent relationships, depths, category and identities after a move,
including promotion; never treat a valid recursive result as a partial failure.
Endpoint-shaped fakes must verify the chosen move's parent/category result.

An ambiguous mutation transport outcome must trigger synchronization and
authoritative reconciliation using stable IDs and idempotency identifiers before
the workflow classifies it. Read the result for the exact command UUID from
`sync_status`. A missing/malformed command status or unknown structured result is
not success and is not a definitive rejection: reconcile it as unresolved.
For a create, pre-existing matching text is not proof of a new object. For recurring
completion/undo, an unchanged valid recurring task is not proof of an occurrence
change. Use evidence attributable to the attempted operation; state validation
alone cannot prove acceptance. If acceptance still cannot be established, classify
the outcome as unknown, preserve the last successful cache under REQ-CACHE-008 and report the
unknown outcome in the originating command. An accepted remote change must never
be rolled back because a later operation, reconciliation, output, or local write
failed.

After every accepted mutation, synchronize the affected authoritative state and
validate every relevant invariant before publishing cache or claiming complete
success. A server-normalized invalid state is a partial failure with accepted state
reported explicitly. If a non-clearing attention expression was supplied but the
accepted object's authoritative state has no attention, report that discrepancy
as an accepted partial failure with read-only recovery, not successful scheduling.

When reconciling a locally predicted exact attention instant with authoritative
Todoist state, accept an absolute instant difference of up to and including two
seconds in either direction. Keep account-local day, exact-vs-date-only status,
recurrence flag/rule and applicable timezone semantics strict. A date crossing,
changed recurrence/timezone, missing attention or a larger difference is not
covered by this tolerance. Use absolute instants across offsets/DST. Store and
render the actual returned time, without rewriting the requested/returned values
merely to make them equal. A solely tolerated precision difference is successful:
no normalization warning, partial failure or cache invalidation. This comparison
slack is only for remote reconciliation; preflight no-op detection and explicit
small user-requested time changes remain exact. Differences outside it report
requested versus actual values with enough date/time/precision/timezone context
to explain the mismatch, not the unrelated old-to-requested date change.

For hierarchy moves, the validation evidence boundary is REQ-MUT-004: absence of
an all-history childlessness proof is not itself invalid state or partial failure.
An actually discovered descendant beyond depth 4 remains an invariant violation;
a descendant within the supported recursive depth is valid.

Ordinary `item_close`/`item_complete` moves completed objects into the archive;
active Sync absence after a successful completion is expected and must not itself
be a partial failure or deletion proof. Reconcile the completion against the
endpoint-specific completed-object record/current lifecycle, using required
bounded history where active Sync cannot establish it. Completion evidence must
not be substituted with an empty history or a requirement that archived objects
remain active. Preserve accepted completions and optional `Done:` comment ordering
for both parent and step owners, including several requested comments. Fetch
required archived owners rather than making active Sync presence a prerequisite
for the authorized post-completion comment operation.

`item_uncomplete` may restore ancestors while returning ordinary `"ok"` command
status. Determine and report every actually restored ancestor from authoritative
reconciled identities/lifecycle; do not require an undocumented
`sync_status[uuid].items_restored` result. Preserve completed-step state, duplicate
checks, recurring undo direction, and the existing no-rollback contract.

### REQ-SYNC-005 — Cache-first reads, online validation and external Todoist changes

Without `--refresh`, now/waiting/someday, task/step/category inspection, comment
display, search, implicit lookup and cursor inspection do not contact Todoist.
Help is independent of local state and network. `report --set-cursor` is the
explicit local-only boundary operation in REQ-REPORT-013.

Initialization, explicit refresh, every remote mutation, comment editing and
report generation synchronize before selection or state-dependent remote action.
A failed synchronization prevents that mutation and synchronized normal output.
Verify account/binding identity and incorporate valid web/mobile changes, including
new tasks/steps, completion, comments, names, categories, labels, reminders,
recurrence and deletion. Report invalid retrieved state with an actionable ordinary
error, without an all-problems diagnostic workflow or automatic data repair.

For previously known items completed externally, reconcile supported lifecycle
evidence and retain the unreported observations/context under REQ-CACHE-006.
Active absence alone proves neither completion nor deletion. Required unresolved
evidence fails synchronization; no exhaustive arbitrary-age archive scan is implied.

Externally introduced violations prevent using that newly retrieved state for
normal synchronized output or mutations. Retain the last successfully saved valid
cache on failure. A later offline read can use it under REQ-CACHE-008; no persisted
remote-invalidity block is required. Offline reads are associated with their stored
binding even if the environment token changed; the next online workflow detects
account mismatch before mutation. Never flatten, rename, move or otherwise repair
remote data to hide an invariant violation.

### REQ-SYNC-016 — Current Sync item completion contract

For live task/item resources read from API v1 `/sync`, completion must be read
from the documented `checked` boolean: `false` maps to OPEN and `true` to COMPLETED.
The same mapping applies to tasks and steps, full and incremental responses,
initialization, normal synchronization, mutation reconciliation, and diagnostics.
Deletion tombstones retain their separate handling under REQ-SYNC-013; a deleted
item must not require live-item fields before it can be removed.

An item with `checked: false` and no `is_completed` is valid completion data.
`is_completed` must not be required or used as an alternate completion source for
this endpoint. It is an unknown response field under REQ-SYNC-021. Missing or null
`checked`, strings, integers (including 0/1), and other non-boolean values must
fail validation for retained live managed items. Do not default missing completion
to OPEN or coerce arbitrary values by truthiness. Unrelated items remain subject
to the existing managed-scope privacy and discard rules.

This definition governs current Sync state. Completed-history records must retain
their endpoint-specific lifecycle interpretation under REQ-SYNC-025; a field name
alone must not erase the fact that an object was retrieved as completed history.
Other task fields remain governed by REQ-SYNC-021 and the domain requirements.

### REQ-SYNC-024 — Optional task and step descriptions on reads

On Todoist task/item reads, a missing `description`, JSON `null`, or exactly the
empty string `""` must map to no domain description for both tasks and steps.
These representations of an absent optional value are valid; they must not
produce a nonempty-description error or require an operator to add remote text.
Apply this interpretation consistently wherever remote task/step descriptions
enter the domain, including initialization preflight and post-provisioning
validation, full/incremental synchronization, mutation reconciliation, read-path
mapping, and completed-object retrieval when that endpoint supplies descriptions.

A nonempty string remains subject to REQ-DOM-009: it must contain text after
edge normalization, respect the length limit, and contain no forbidden controls.
For example, `" "`, `"\n\t"`, CR-containing text, and non-string values other than
`null` remain invalid. Do not use truthiness or trimming to turn malformed or
whitespace-only values into absence. A valid nonempty description, including a
valid hiding-reason block, must retain its existing content and interpretation.
The absence representation does not waive REQ-DOM-013 label/attention and optional-
reason consistency or any task-tree, title, completion or scheduling validation.
A waiting label plus valid attention without a reason block is valid under that
requirement; a malformed/orphaned block or missing required attention still fails.

This is an adapter interpretation of optional description absence, not remote
repair or a relaxation of the domain text value. It does not change CLI validation
of explicitly supplied descriptions, comments, titles, or hiding reasons.


### REQ-NET-001 — Todoist timeout, retry, and replay policy

Each Todoist HTTP request must have a 30-second timeout and at most four total
attempts. Only HTTP statuses `408`, `429`, `500`, `502`, `503`, and `504` are
retriable. Without a usable `Retry-After`, delays before attempts two through four
must be 1, 2, and 4 seconds.

A valid `Retry-After` delay no greater than 60 seconds must replace the corresponding
default delay; a value over 60 seconds is not automatically slept and the request
fails for operator retry. Every actual retry must first emit a stderr warning that
identifies the operation and delay without exposing credentials.

Reads and mutations proven safe by Todoist idempotency may be replayed. A mutation
whose outcome is ambiguous must be reconciled under `REQ-SYNC-026` before any replay;
it must not be blindly duplicated. Non-retriable responses, exhausted attempts,
unsafe replay, and unresolved outcomes must fail visibly with the accepted/unknown/
unattempted classification applicable to the workflow.
