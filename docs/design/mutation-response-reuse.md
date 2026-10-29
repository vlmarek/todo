# Combined mutation and incremental Sync responses — revision 18

Status: **Accepted**

## Agreement, scope and precedence

After a slow `todo task --add --done gatekeeper bla`, the operator authorized a
diagnostic creation/completion and deletion. The observed command used separate
mutation and current-resource requests. The operator requested removing
unnecessary reads, redirected the proposed work from `cml-plan` to `cml-design`,
and asked where else combined reading and writing applies. They answered
"I agree" to the recommendation to cover all ordinary task/step mutations through
the shared gateway. The external Design report retains the actual instructions,
proposal context, measurements and separate interpretation.

This amendment applies to task and step creation; rename/priority and other
scalar changes; scheduling, hiding and unhiding; reminder creation, updates and
deletion; parent/category moves and promotion; completion, reopening/undo and
deletion; and comment additions, edits and deletions. It includes each operation
of reminder replacement, comment editing, subtree lifecycle changes and composed
creation/completion. Category creation, initialization/provisioning, explicit
refresh and report workflows retain their existing policies. No new command,
option, concurrency, background work or multi-operation batching is introduced.

Earlier definitions and accepted effective assignments remain historical inputs.
The narrow successors govern changed and follow-up work:

| Successor | Earlier scope qualified or superseded |
| --- | --- |
| REQ-SYNC-038 | REQ-SYNC-026/036/037 only where authoritative post-mutation synchronization or reuse is interpreted as requiring a separate read despite sufficient current-resource evidence returned with that mutation. REQ-SYNC-013's baseline, merging, replacement and freshness requirements remain. |
| REQ-VERIFY-036 | Adds distinguishing combined-request evidence; existing affected-state, historical scope, failure, publication, output and report obligations remain. |

REQ-SYNC-036/037 continue to require validation and publication between accepted
operations, affected-state historical reconciliation and later retrieval of
deferred history. No obligation is satisfied merely by an `ok` command status.

### REQ-SYNC-038 — Combine ordinary mutations with incremental resource retrieval

For an ordinary task/step mutation with a compatible proven saved current-resource
baseline and Sync token, request the required current resources in the same Sync
request as the mutation command. Use the existing resource scope for account,
capabilities, managed projects, items, labels, notes and reminders; do not narrow
it to the changed item and miss relevant remote changes. Keep command UUIDs and
temporary IDs under their existing attribution and replay rules.

Treat command attribution and resource completeness as separate obligations.
Validate the returned current-resource evidence against its actual full/delta
contract, merge a delta with its matching proven baseline, and use the resulting
authoritative state to verify the operation and necessary related state. Reuse
that state for reconciliation and local publication. When it establishes the
required state, do not issue another equivalent Sync read merely because one
layer submitted the command and another layer publishes its result. Apply the
same rule across all ordinary mutation workflows listed above.

Incorporate and validate all relevant returned current changes, including
unrelated active changes, account metadata, resource membership and tombstones.
Preserve identity, scope, normalization, timezone, hierarchy and reminder rules.
An `ok` status, temporary-ID mapping or locally predicted patch alone cannot
replace authoritative actual-state validation. Do not advance the saved token
independently of the complete validated state it describes, or use a receipt-only
token to skip changes not incorporated into that state.

Use additional supported retrieval when combined evidence cannot establish the
operation's actual result or required context. In particular, retain necessary
hydration without compatible current-resource provenance, scoped historical or
archived-owner retrieval, recurring-occurrence evidence and the existing bounded
freshness delta after any full candidate. A response marked `full_sync: true`
is not, by itself, proof of a complete fresh post-operation state. Missing
required evidence and invalid returned data retain their existing classified
failure and recovery behavior; this amendment adds no generic-error full-sync
fallback, unsafe replay or invented provider defaults.

The reuse rule also applies to historical or comment reads when already returned
authoritative evidence genuinely satisfies that same obligation. For example,
complete current notes for an active owner may establish an accepted comment's
actual text or deletion without a separate owner-comment query. A returned
ordinary completed item's authoritative lifecycle state and completion time may
satisfy its result check when all necessary related evidence is present. Absence
from active Sync alone is still not completion or deletion proof. Sync does not
certify complete archived comments, a recurring occurrence or historical interval
coverage merely because a mutation succeeded. Retrieve those separately whenever
their existing obligations are not met by the combined response.

For each accepted operation, complete required verification and local publication
before submitting the next operation. For `--add --done`, reuse the creation
response where sufficient, verify/save creation, then submit completion with the
updated proven baseline and token and verify/save that result. Do not combine
creation and completion into one command batch to remove the intermediate
boundary. Preserve ordered outcomes, nonzero partial failures after accepted
changes, protected pending history, report cursor behavior and no rollback.

### REQ-VERIFY-036 — Combined-request reuse without weakened verification

Use proportionate offline evidence through the actual mutation boundary to
establish that an ordinary mutation requests its command and incremental current
resources together, validates the returned normalized state and publishes it
without an equivalent separate current-state request when sufficient. Distinguish
resource evidence from a receipt-only response; do not make a permissive fake
that accepts incorrect request parameters or supplies assumed state.

A representative composed creation/completion must establish verification and
publication between commands and correct use of the resulting baseline/token.
Exercise another ordinary mutation consumer where needed to establish that the
shared mechanism is used beyond creation. Reuse adequate existing checks for
unchanged behavior rather than duplicating every operation at every layer.

Distinguish sufficient combined evidence from required fallback: preserve full-
candidate freshness, necessary lifecycle/history/comment retrieval and existing
invalid-result, unknown-outcome and accepted-publication-failure behavior. Retain
later explicit refresh/report retrieval of deferred history without cursor or
pending-data loss. No mandatory automated live calls, benchmark gate, numerical
latency target, universal request budget or new test framework is added.

## Evidence, delegated choices and limits

The diagnostic run against workspace HEAD
`b42d078b` plus existing unrelated uncommitted revision-16 edits took 2.17 seconds
for creation/completion and 1.02 seconds for deletion. Creation/completion used
five requests: create, current Sync, close, current Sync and completed-history
lookup. Its measured HTTP time was 1.772 seconds. Deletion used a mutation and a
current Sync read, with 0.731 seconds measured HTTP time. The diagnostic task was
deleted and its absence from saved snapshot and pending history was verified.
These are one-run observations, not reproduction of the operator's 5.79 seconds,
a post-optimization measurement or an acceptance guarantee.

The trace recorded `full_sync: true` on mutation responses. It did not capture or
establish completeness of their resource collections, freshness, or inclusion of
each mutation's own normalized result. Those flags alone do not establish that
the existing follow-up reads can simply be deleted without changing requests and
response handling.

Retained `external/todoist/upstream/api-v1.openapi.json`, Sync tag / Overview,
documents combined reading/writing, incremental tokens, read resource types,
command UUIDs, temporary-ID mappings and full-sync data delay. The official
[Todoist API reference](https://developer.todoist.com/api/v1/) was also consulted
on 2026-10-29 and supports the combined-request capability. No retained upstream
bytes or manifest are replaced. Provider capability is evidence, not permission
to bypass application verification or presume transaction semantics.

Planning owns the shared response-consumption interface, exact request and
resource provenance, operation-specific own-effect/normalization conformance,
necessary extra retrieval, consumer compatibility and proportionate checks.
Which responses are sufficient for each consumed mutation remains delegated
technical evidence work; the design promises no universal one-request completion.
Surface contrary provider evidence rather than assuming it or weakening the
agreed verification boundary. There is no unresolved product choice.

The scoped approval authorizes these design documents and retained Design
handoff only. It grants no new commit, Planning, implementation, adoption or
execution authority. Preserve accepted assignments, retained evidence and
unrelated existing edits.
