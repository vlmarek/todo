# Mutation retrieval reuse and historical scope — revision 17

Status: **Accepted**

## Agreement, scope and precedence

The operator requested a `cml-design` discussion after observing about twelve
seconds for `todo task --add --done gatekeeper bla`. They accepted scoped
historical retrieval for ordinary writes, explicitly retained broader retrieval
for existing `--refresh` and `report` workflows, and retained verification and
local publication of creation before completion is submitted. They declined a
performance target: "We just improve the algorithm and see how it goes". The
operator approved the concrete revision-17 documentation proposal with "yes".
The external Design report retains the questions, actual answers and separate
interpretation. Earlier timing/request-count estimates are not measurements of
an optimized implementation or promised results.

This amendment covers ordinary task/step writes, including creation, scalar and
scheduling/reminder changes, hierarchy moves, lifecycle operations and comment
mutations/editor operations. It changes retrieval scope and reuse, not selection,
grammar, requested remote effects or output. Initialization/provisioning, explicit
refresh and reports retain their existing workflow obligations. The established
applicability of `--refresh` is unchanged; no mutation refresh option is added.

Earlier definitions and accepted effective assignments remain historical inputs.
The following narrow successors govern changed and follow-up work:

| Successor | Earlier scope qualified or superseded |
| --- | --- |
| REQ-SYNC-036 | REQ-SYNC-035/026/005/025 and REQ-CACHE-006/008/010 only where ordinary-write reconciliation requires fresh unrelated historical state or refreshes all known archived comments/recurring activity. Affected-state verification, observed-state validation and pending-history protection remain required. |
| REQ-SYNC-037 | REQ-SYNC-013/026/035 only where callers interpret their duties as requiring repeated equivalent retrieval or full hydration solely because a task is newly created. Correct incremental merging, necessary hydration and full-response freshness remain required. |
| REQ-VERIFY-035 | Adds distinguishing ordinary-write reuse/scope evidence; existing correctness, offline isolation, publication, output and report-finalization requirements remain. |

REQ-CLI-038 and REQ-MUT-006/007 still establish cached selection and preflight.
REQ-CLI-032, REQ-LOCAL-002/003/006/007, REQ-CACHE-009/010 and the existing report
output/cursor boundaries retain their outcome, interruption, locking, per-file
publication and recovery obligations. No other behavior is superseded.

### REQ-SYNC-036 — Affected-state history after ordinary writes

After each accepted ordinary task/step mutation, synchronize current active state
using the existing supported incremental mechanism and verify the operation's
actual authoritative result and necessary related state before publishing or
claiming complete success. Incorporate and validate newly retrieved current
changes, including changes to unrelated active objects; this is not a patch-only
cache or permission to suppress known invalid state. Preserve complete required
current-resource merging, stable identities, binding/scope checks and all relevant
domain invariants.

Retrieve completion records, activity and archived-owner comments only when needed
to establish the operation's result, lifecycle or required related context. Such
context includes required owners/ancestors, affected descendants, reminders and
recurring occurrences under the existing operation-specific rules. Exhaust any
required scoped retrieval under its existing pagination and interval contract.
Do not enumerate unrelated categories' historical completions, every recurring
item's activity or every retained archived owner's comments merely because an
ordinary write succeeded. A required unresolved transition or invalid actual
result remains a reconciliation failure; absence from active Sync is still not
completion or deletion proof.

Unrelated historical observations and comments may remain at their last saved
state until explicit refresh or reporting. Preserve protected pending observations
and their required context rather than dropping them or promoting them to newly
verified current truth. A successful ordinary write does not certify historical
freshness for unrelated objects. Record newly established affected observations
under existing history-retention rules; do not advance the report cursor or prune
pending history because a write finished.

Existing explicit-refresh and report workflows still retrieve their required
historical evidence, including deferred information. A write's new Sync token or
current-state synchronization time must not be treated as evidence that deferred
completion/activity intervals were covered. Later refresh/report retrieval must
not skip those intervals or lose eligible work because intervening ordinary
writes advanced current-state synchronization. Reports retain current-truth,
complete-or-error retrieval, protected pending history and output/cursor ordering.

For composed commands, verify and publish each accepted operation before sending
the next. For example, `--add --done` verifies and saves creation, then submits
completion and verifies/publishes its result. Retain stable-ID ordering, actual
normalization checks and accepted/rejected/unknown/unattempted classifications.
Do not batch away the intermediate verification or defer necessary validation to
a later refresh. An accepted operation followed by verification/publication failure
remains a nonzero partial failure with existing recovery and no rollback/replay.

### REQ-SYNC-037 — Reuse complete evidence and retain incremental retrieval

Within an operation, reuse complete, validated current-state and scoped historical
evidence already retrieved by the mutation adapter or workflow when it satisfies
the same reconciliation/publication obligation. Do not repeat an equivalent Sync,
completion, activity or owner-comment request solely because another layer also
performs reconciliation. Preserve the evidence's matching token, resource
membership, identity, scope and coverage; a partial response or raw delta without
its proven baseline cannot substitute for complete required state. Reuse does not
turn evidence from an earlier operation into verification of a later operation.

Use a valid saved current-resource baseline and Sync token for normal incremental
retrieval. A newly created task alone must not force replacement when the returned
incremental evidence establishes the complete state required for that task and
its related resources. Retain necessary bounded hydration where required state
cannot otherwise be established, including scope expansion or missing compatible
current-resource provenance. Full candidates still receive the existing freshness
delta before publication. Do not weaken token/state atomicity, tombstone handling,
replacement validation or generic-error recovery restrictions.

Remote acceptance must still be attributable to the exact command UUID and, for
creation, its temporary-ID mapping. Valid-looking state or matching text alone
does not prove acceptance. Unknown outcomes still require the existing supported
reconciliation, explicit classification and no unsafe replay.

### REQ-VERIFY-035 — Distinguishing retrieval and correctness evidence

Use proportionate offline controlled-boundary evidence to distinguish evidence
reuse and scoped ordinary-write history from the previous repeated broad
retrieval. A representative composed creation/completion must retain verification
and publication between writes, necessary authoritative completion evidence and
accurate saved results while unrelated archived comments/recurring history do not
trigger reads. Establish that sufficient incremental creation evidence avoids
unnecessary full replacement and that required hydration still works.

Establish that a subsequent explicit refresh or report can retrieve historical
changes deferred across intervening writes, without dropping observations or
advancing the report cursor prematurely. Preserve meaningful existing evidence
for invalid actual results, partial/unknown outcomes, publication failure,
interruption, recurrence and hierarchy-dependent validation. Reuse existing checks
where they establish unchanged behavior rather than duplicating every command at
every layer. No wall-clock deadline, numerical request budget, benchmark gate,
automated live account call or new testing framework is added.

## Evidence, delegation and exclusions

The implementation inspected for this discussion has workspace HEAD
`5b99bbbccc2f317036faab2ca924ef88b2fb5684` plus existing revision-16 uncommitted
changes. `Gateway.execute` retrieves current state; the accepted-operation workflow
then independently retrieves it again. Shared reconciliation scans categories
when known owners are missing or recurring items exist, reloads retained archived
comments and requests each current recurring item's activity. Current retrieval's
new-item condition can trigger full hydration even for a newly created managed
task. These are implementation observations, not design authority or a live
request trace. The saved population inspected then contained five categories,
five recurring items and three archived owners; account contents can change.

Retained `external/todoist/upstream/api-v1.openapi.json` is the provider baseline:
the Sync tag's incremental-sync/current-resource contract and the completed-task,
activity and comments endpoints establish the consumed boundaries. Existing
`external/todoist/report-retrieval-notes.md` and completion-reconciliation notes
explain why active Sync is not complete archived-current-state evidence. No new
provider capability, endpoint or upstream evidence replacement is assumed.

Planning owns impact assessment across all ordinary-write consumers, the minimum
shared evidence interface, required dependency closure and correct distinction
between current-state progress and deferred historical coverage. It must preserve
accepted assignments and prepare supported successor work. These are delegated
implementation choices, not permission to omit affected-state proof or lose
deferred history. No unresolved product choice or new provider feasibility claim
is retained; evidence contradicting this boundary must be surfaced rather than
silently weakening correctness or restoring unrelated scans.

This revision adds no batching across verification boundaries, concurrent or
background retrieval, telemetry, command/verbosity option, output template,
alternate storage engine, cached-report mode or performance guarantee. The
operator approved documentation only; committing, Planning, implementation and
execution require their own existing authorization. Existing unrelated edits and
all unaffected decisions remain intact.
