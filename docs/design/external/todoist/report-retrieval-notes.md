# Report retrieval implementation decisions

Status: **Accepted**

This is Planning's technical interpretation of Design revision 11, not a new
product requirement or provider observation. Earlier definitions and accepted
assignments remain intact. Use `docs/design/report-retrieval-reuse.md` for scope
and precedence. Reuse the integrated application at
`f3eb3b2c88d40bede17edf70a0c7437707c528bd`.

## Retained provider evidence

Inspected 2026-10-27 against the unchanged complete API v1 snapshot at
`docs/design/external/todoist/upstream/api-v1.openapi.json`, SHA-256
`9a7c4816042e5c1b66935f2be1cf83da953dc459649ee606ac364d1acbc4764c`.
Its manifest records the original 2026-10-24 retrieval and lack of an immutable
provider release. These are offline contract conclusions; no live-account or
latency measurement is claimed.

The Sync tag (`/tags/3/description`), Overview / Read resources and Incremental
sync, establishes all active resource data on `sync_token=*`, subsequent updates
under the returned token, `notes` as task comments and the full-response freshness
delta. Comments / Task comments supplies `item_id`, identity, content, `posted_at`
and deletion state. A complete, correctly merged active baseline plus a successful
delta therefore supplies current active owners' complete own comments, including
unchanged comments and authoritative absence. A raw delta alone does not.

`GET /api/v1/comments` requires exactly one task/project scope, exhausts
`results`/`next_cursor`, and returns NoteSyncView records. The task-scoped request
supplies owner identity where the REST record omits `item_id`. Reconciliation and
report preparation may share one successful, fully exhausted owner response in
the same command. A filtered response, partial response or failed page cannot
be promoted to complete owner evidence. Preserve duplicate/ownership checks.

## Active Sync baseline and protected pending context

The current `LocalState.snapshot` is the combined usable view, not proof that all
its items were returned by active Sync. `Synchronizer._known` additionally merges
protected pending context. `current._seed` currently reconstructs every supplied
item and its comments. Passing that combined view as an incremental baseline
would make archived observations appear current. Filtering by `completed` is
insufficient: lifecycle truth and resource provenance are distinct.

Keep the combined view and protected history available to offline readers and
lifecycle reconciliation. Separately preserve the minimum proven current-resource
provenance in the existing cache, paired with its matching token (for example,
current-resource membership sufficient to reconstruct its managed baseline).
Implementation chooses the smallest compatible representation. Only a baseline
actually established by current retrieval may seed incremental current state.
Preserve known archived identities separately when applying explicit tombstones,
scope departure, required disappearance reconciliation and recurring evidence.

Existing schema-1 files without this provenance remain usable for offline reads.
An online operation may hydrate them once with the existing bounded full plus
freshness path; it must not infer provenance from combined context or erase
protected history/cursor. New init, refresh and report publications should retain
a usable proven baseline. Other writers must preserve it with its actual token or
truthfully invalidate only disposable provenance when they cannot do so. Account,
root/category, timezone, required-field and publication checks stay in force.
Do not turn generic protocol/network errors into replacement authorization.

Trace every `prepare_candidates` and current-retrieval caller, including init,
move reconciliation, lifecycle discovery and gateway calls from capture, comments
and lifecycle. Adapt production callers and their directly affected doubles
together. Retain existing public invocation/result/error shapes where possible;
document any compatible optional fields in existing module docstrings. A new
public setting, storage engine, sidecar or general migration framework is not
needed. An unchanged active-owner report with a valid new baseline must actually
send the saved token rather than repeatedly hydrating.

## Completion-history investigation: retain scoped queries

Do not implement cross-command completion-query skipping in this revision. This
is the evidence-conditional outcome allowed by REQ-CACHE-011, not a deferral of an
unconditional caching promise. Reuse within-command exhausted completion evidence
as `_Evidence` already does. Retain complete category-scoped queries over required
covering intervals on each report.

The retained `GET /api/v1/tasks/completed/by_completion_date` supplies bounded
ItemSyncView records, occurrences and current owner fields used by this application.
A saved occurrence proves a completion observation, not the owner's surviving
current title, parent, scope or lifecycle on a later report. Active Sync omits
archived resources; active-task GET explicitly only returns non-completed tasks,
so a 404 is not deletion or archive metadata. ActivityEvents has optional parent
and `extra_data` fields and no guaranteed complete current archived parent chain.
Its `parent_item_id` describes note ownership, not an item's parent. The activity
parameter `ensure_last_state` explicitly has no implementation; parent annotations
only promise additional information such as names. Existing five-event filters
also do not retrieve every item rename/move/deletion. Broader event filtering
would still not establish the missing current metadata guarantee.

Consequently neither saved coverage, saved sync time, an event-free delta nor
synthetic fixture success justifies skipping covered completion windows while
promising all required archived-current-state corrections. No coverage schema,
permanent archive, new activity strategy or invalidation engine is warranted.
Required current archived comments still use scoped REST; unresolved owner/parent
metadata still fails before normal output with unchanged cursor. Keep the existing
unknown-archived-owner limitation even when old pending context contains that ID.

## Verification allocation

T27 implements this coupled retrieval slice, including storage/caller/fixture
adaptations and directed regression evidence. T28 audits observable report/request
and cursor/history outcomes and appends current acceptance evidence. Both preserve
the frozen contract map and historical evidence. The graph reuses existing local,
current/history adapter, synchronization and report checks; it introduces no new
framework or check command. `final-delivery` remains the runner's complete-suite
and copied-runtime gate on the settled integrated subject. Its script invokes
`scripts/check` once; harness self-tests use miniature synthetic suites.

The key distinguishing setup is observed active parent/step/comments followed by
an external completion, successful save/reload, then another report using an
actual saved-token delta. The archived observation must remain pending without
becoming an active owner or resolving missing current archived metadata. Combine
representative changes, tombstones, edited/deleted comments and extra unchanged
active owners with actual adapter requests and observable output. Count REST owner
requests at the controlled boundary; do not merely assert that a mocked method
was bypassed. Reuse existing full-read/failure/cursor/output and lifecycle cases.
