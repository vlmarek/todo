# Report retrieval reuse and incremental synchronization — revision 11

Status: **Accepted**

## Agreement, provenance and precedence

The operator requested a one-at-a-time Design discussion after reporting slow
`todo report` execution with at least 60 comment pages fetched. The operator
accepted fresh synchronized comment reuse ("concurrent edits are not a concern.
I agree with this"), complete per-owner response reuse, incremental report sync,
conditional completion-cache investigation and retaining JSON storage. They
deferred concurrency ("agree, defer it"), rejected changed progress output ("no"),
and answered "yes" to the final complete scope. The external Design report
retains the actual questions/answers separately from this interpretation.
The confirmed operator decision is native action
`TX-0972c3c7ae434be183cdc6aef624cc8e:0`.

The goal is fewer unnecessary remote requests and downloads with unchanged report
eligibility, current-truth semantics, complete retrieval and cursor protection.
This is not a new offline report mode or an immutable snapshot guarantee.

| New definition | Narrow effect on earlier obligations |
| --- | --- |
| REQ-REPORT-016 | Succeeds only the requirement/interpretation in REQ-SYNC-025 that every required comment must be fetched separately through REST, and any REQ-REPORT-014 interpretation requiring a redundant read despite complete fresh evidence. Retains completeness and current surviving text. |
| REQ-SYNC-034 | Applies REQ-SYNC-013's normal incremental merging to report current-state retrieval; does not change replacement, token-failure or lifecycle rules. |
| REQ-CACHE-011 | Adds conditional reuse investigation within REQ-CACHE-006/008 and REQ-SYNC-025. Old observations alone still do not establish current archived state. |
| REQ-VERIFY-029 | Adds representative request-count and correctness outcomes to existing offline verification, without a benchmark suite or wall-clock gate. |
| OUT-REPORT-002 | Bounds this revision; earlier exclusions and unrelated requirements remain in force. |

Keep all earlier definitions and accepted effective assignments intact as history.
Planning owns impact assessment and supported successor work. No production code,
test, plan, commit or execution change is performed or authorized by this Design
pass. The confirmed agreement is complete; technical feasibility remains distinct.

## Evidence, system responsibilities and remaining investigation

The inspected baseline is `f3eb3b2c88d40bede17edf70a0c7437707c528bd`.
`Reporter._prepare` forces replacement current retrieval, then
`HistoryAdapter.required_comments` requests comments for every current and bounded
completed owner. Its shared counter counts response pages across owners; an empty
owner response still counts as one page. Reconciliation can also fetch an archived
owner before report comment preparation fetches it again. These are implementation
facts, not independent latency measurements or product authority.

Normal refresh already uses returned sync tokens when a saved cache exists. The
report's forced full read avoids mistaking retained archived observations for
current active evidence. Removing that forced read must preserve this distinction.
Persistence currently reads/writes whole JSON snapshots; the selected improvement
concerns incremental remote downloads, not partial record writes on disk.

Use the unchanged retained
[API v1 specification](external/todoist/upstream/api-v1.openapi.json) and
[history context](history-context.md). The Sync tag's Read resources and
Incremental sync sections document `notes`, sync tokens, replacements and the
freshness delta after a full response. Task comments carry owner identity under
Sync; REST `/api/v1/comments` supplies owner context through `task_id` and requires
cursor exhaustion. The completed endpoint and activity endpoint are separate
evidence sources; Sync does not provide complete archived-object enumeration or
activity history. No provider snapshot refresh or live-account access occurred.

The adapter establishes which fresh evidence is complete for the requested scope;
workflows reuse it and reconcile lifecycle/ownership; persistence keeps current
state separate from pending history and publishes the matching state/token.
Planning chooses representations, interfaces, cache schema compatibility and
evidence reuse. A new parallel path or second sync engine is not required.

Planning must establish whether verified completion-interval coverage plus fresh
supported evidence can safely replace repeated completed queries, especially for
renamed, reopened, moved or deleted archived owners and later comment changes.
Identify the exact provider operations/signals and the distinction between an
observed occurrence and current owner/parent metadata. If sufficient evidence is
unavailable, retain the existing scoped retrieval for that case and report the
limitation; do not promise completion caching from synthetic fixtures alone.
This uncertainty need not prevent independently supported comment reuse or
incremental-current-state improvements.

### REQ-REPORT-016 — Reuse complete fresh comment evidence within one report

Reports must reuse complete authoritative comment state retrieved during that
command's current synchronization for active managed tasks and steps wherever the
retained provider contract establishes sufficient evidence. Do not request each
active owner's comments separately merely because that owner exists. Adding
unchanged active tasks/steps with no relevant lifecycle transition or comment
activity must not add one REST comment request per owner when complete fresh Sync
evidence already supplies their comments.

Additional current comment evidence remains required where synchronization does
not cover the owner or cannot establish the needed surviving content/absence,
including eligible archived owners. Reuse each successful complete owner-scoped
comment retrieval throughout that command, including between reconciliation and
report preparation. One retrieval may require several pages; reuse cannot turn a
partial or failed response into complete evidence. Preserve actual step ownership,
ancestor context, duplicate/contradictory response checks and complete pagination.

Freshness means the authoritative state obtained by the command's required reads.
A later concurrent edit need not be observed by rereading an already covered
owner. There is no final comparison sync or atomic cross-endpoint snapshot.
Previously saved comments alone are not sufficient fresh evidence. Retain
REQ-REPORT-011/014's explicit required-data failure, unresolved archived-owner
limitation and unchanged cursor; preserve deleted-comment omission, current
surviving text, activity-time eligibility/order and repeated-event collapse.

### REQ-SYNC-034 — Incremental current-state retrieval for reports

With a valid saved current-state baseline and corresponding sync token, ordinary
reports must use the existing incremental synchronization mechanism rather than
force a full replacement solely because the command is `report`. Merge changed
resources and tombstones by stable ID, preserving unchanged current resources.
Retained archived observations must remain distinguishable from current active
evidence; neither delta omission nor old history makes an item currently active,
completed, deleted or in scope. Preserve lifecycle reconciliation and account,
root/category, timezone, capability and required-field validation.

Retain REQ-SYNC-013's necessary initialization/replacement/hydration and one
freshness delta after a full response, existing cache rebuilding, bounded recovery
and failure behavior. Generic network/protocol errors do not authorize a guessed
token-reset fallback. Publish only validated merged state with its matching token
under the existing locking and per-file publication guarantees. Preserve protected
pending history and accepted publication-failure limitations.

This changes online retrieval, not cache-first read behavior or command grammar.
Reports still obtain fresh required current and historical evidence and preserve
fixed-end eligibility, retention checks and final output-before-cursor ordering.

### REQ-CACHE-011 — Evidence-conditional completion-history reuse

Investigate reuse of already retrieved completion occurrences and verified
interval coverage so repeated reports can retrieve uncovered ranges rather than
re-download equivalent covered history. Adopt reuse only where supported evidence
preserves all required current owner/lifecycle/parent/scope/comment state, precise
eligibility and completeness. A stored completion occurrence or coverage marker
does not prove current surviving owner metadata or continued completion.

Keep category-scoped completed retrieval wherever safe reuse cannot be established;
no account-wide consolidation or automatic query-strategy selector is required.
Use the existing protected pending-history responsibilities and JSON storage.
Previously saved sync time is not automatically proof that a completion interval
was exhaustively retrieved. Planning determines the minimum supported coverage
representation and invalidation/reconciliation rules, or retains scoped queries
where evidence is insufficient.

Retrieval coverage and the report cursor have separate meanings. Successful
preview may save reusable evidence without advancing the reporting cursor or
pruning pending history. Only complete successful final output and cursor
publication authorize the existing cleanup. Reuse must respect explicit preview
intervals, gaps, binding changes, discarded coverage/context and existing corrupt
protected-state refusal; it must not invent a permanent archive or automatic
history repair. A failed/partial retrieval cannot establish complete coverage.

### REQ-VERIFY-029 — Evidence for fewer requests with unchanged report behavior

Under existing offline isolation, establish that additional unchanged active owners
do not add per-owner REST comment reads when fresh synchronized evidence covers
them, and that reconciliation/report preparation share complete archived-owner
comment responses. Exercise an actual incremental report request from saved
current state and a token, including meaningful changes/tombstones and retained
archived context, without a forced replacement or stale-active-state leakage.
Retain representative full-read/rebuild and required-read failure evidence.

Compare observable report content and cursor/history outcomes for edited/deleted
comments, nested/archived owners, reopen or scope changes and required missing
evidence. Reuse adequate existing cases; do not duplicate every case at every
layer. If completion caching is adopted, establish covered/uncovered ranges and
current-state corrections through supported contract-grounded evidence, and
retain scoped retrieval wherever reuse is not justified. Preview may update
reusable evidence but must not advance the reporting cursor or authorize pruning.

Request counts and phase timings can inform the remaining completion-cache
investigation without changing user-visible output or adding persistent telemetry.
No runtime-in-seconds promise, load/stress suite, benchmark gate, real-account
dependency, new test framework or repeated broad-suite requirement is introduced.
Planning owns test organization, focused commands and reuse of existing checks.

### OUT-REPORT-002 — Bounds of the retrieval optimization

Keep existing JSON storage; reading or atomically rewriting a whole local JSON
snapshot is allowed. Partial disk-record updates, a database, another persistence
mechanism, another sync engine, new configuration and an offline/stale-report mode
are outside this revision. Necessary representation/schema changes within existing
storage and compatibility rules remain delegated.

Defer concurrent retrieval and account-wide completion-query consolidation. Leave
progress output and its exact templates unchanged, including its current page
count meaning. Improvements concern remote requests and downloads, with no fixed
latency/capacity guarantee. Keep unrelated-data minimization, remote outcome
classification, manual recovery boundaries and all unaffected product guarantees.
