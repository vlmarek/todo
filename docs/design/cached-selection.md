# Cached selection and mutation preflight — revision 13

Status: **Accepted**

## Agreement, scope and precedence

The operator requested discussion of slow suggestions for `todo delete scdaemon`,
selected "every task/step selector", and then chose: "I want to make it simple,
just trust the cache. If the change cannot be applied user will know. If the
task/step cannot be found user can first refresh the cache." They explicitly
accepted that deletion by a cached parent ID can cascade to remotely added
descendants absent from its cached preview. They confirmed the complete summary,
including unchanged post-mutation synchronization and reports, and authorized
this amendment followed by fresh Planning. The external Design report retains
actual operator excerpts separately from interpretation.

These are successor duties for changed and follow-up work; preserve earlier
definitions and accepted effective assignments as history. REQ-CLI-038 succeeds
only the selection-population freshness and recovery portions of REQ-CLI-035,
REQ-SYNC-005 and operation-specific selection clauses. REQ-SYNC-035 and
REQ-MUT-006 succeed automatic synchronization and remotely fresh preflight duties
for ordinary task/step workflows in REQ-SYNC-005/021, REQ-CACHE-008,
REQ-CREATE-008, REQ-COMMENT-007, REQ-COMP-006/007/008, REQ-MUT-001/004,
REQ-SCHED-012/013/014 and other task/step mutation preflight clauses only to the
extent they require freshly retrieved state. REQ-MUT-007 succeeds the fresh,
retrievable-population preview duty in REQ-MUT-003. It also qualifies the
complete-current-subtree claims of REQ-COMP-006 and REQ-MUT-004: before mutation,
their reasoning applies to the complete locally known subtree.

Matching, grammar, eligibility rules, domain invariants and required local
validation are retained; the change is which evidence establishes preflight
state. A previously unknown external change need not be detected before mutation.
Reconciliation validates newly retrieved actual state under unchanged rules.
REQ-CLI-032, transport outcome/replay rules, REQ-LOCAL-002/003/006,
REQ-CACHE-006 and their existing publication-failure successors remain in force.
Initialization, explicit refresh, report retrieval/finalization and mutations
without task/step selection outside this scope retain their existing contracts.

### REQ-CLI-038 — Local task/step selection and explicit refresh recovery

Every task/step selector must match against the structurally valid, bound saved
snapshot and compatible locally retained history, without retrieving remote state
to populate, disambiguate or retry the search. This includes ordinary read and
implicit lookup selectors, mutation targets, completion/reopen/deletion,
comment/editor owners, creation parents, explicit task/step parent operands and
move source/destination selectors. Resolve multiple operands from local data
before the first mutation. Existing task/step eligibility filters, title-only
matching, argument boundaries, ordering, context, ambiguity and cancellation
behavior continue to apply to that population. Mixed move destination selection
uses saved category context alongside saved task/step candidates.

Eligible completed candidates come only from compatible locally retained
observations, applying existing report-cursor bounds and recurring-occurrence
rules. Do not scan remote completion/activity history to find additional matches.
The local population may omit new, renamed, moved or completed remote objects.
No match reports the selector actually searched, explains that the search used
saved data, and suggests `todo --refresh now` followed by retry. Do not silently
refresh or retarget. Missing or invalid required local state fails clearly and
uses existing explicit-refresh or protected-state recovery, never an empty
population or automatic cache reconstruction.

Existing explicitly requested refresh on supported read commands still retrieves
and publishes current state before the command searches the resulting saved
population. Keep existing `--refresh` applicability; do not add a mutation refresh
flag, new command, public ID selector or additional confirmation. Existing local
configuration and credential requirements remain; resolving a credential is not
permission to refresh the candidate population.

### REQ-SYNC-035 — Cached preflight, direct operations and unchanged reconciliation

Ordinary task/step workflows use their validated saved state for pre-mutation
context and validation. Do not automatically synchronize, load completion/activity
history or refresh owner comments before selecting or applying the requested
change. Existing initialization/provisioning and explicit refresh are distinct
workflows. Operation-specific remote writes and existing transport outcome
reconciliation are not state-refresh preflight.

Use the normal resolved credential and selected cached stable IDs. Do not rerun
title matching against remote results, replace a selected ID, or add a fresh
task/step eligibility gate before submission. Saved account/timezone, capabilities,
binding, scope and hierarchy provide the preflight facts previously obtained by
synchronization. Local binding/configuration/path validation, supported personal
account/root restrictions and credential redaction remain mandatory; this adds no
account switching or unsupported shared-data workflow. The cache is not proof
that remote metadata still agrees. A missing required saved fact causes the
existing local validation/recovery failure rather than a guessed default or an
automatic preflight refresh. Planning may extend existing protected JSON
representations where necessary to make required saved context available.

Preserve existing post-operation authoritative retrieval and synchronization,
accepted/rejected/unknown/unattempted classification, ordered-operation stopping,
normalization checks, pending-history retention, per-file publication and explicit
recovery. A provider rejection is an error; it is not permission to find another
target or replay a new mutation. Connection loss is not proof of rejection.
An accepted mutation followed by reconciliation/publication failure remains an
accepted mutation with a nonzero partial failure, not a cache-only success or
rollback. Multi-operation commands retain their existing reconciliation between
accepted operations and stable-ID operation ordering; do not reselect operands.

This removes pre-operation freshness work. Successful commands can still wait for
post-operation reconciliation. Reports retain fresh current-state and complete
history retrieval, revision-12 completion reconciliation, and existing cursor and
finalization guarantees. This revision does not turn reports into cached reports.

### REQ-MUT-006 — Cached validation and accepted stale-state consequences

Perform all existing syntax, no-op, source-state, scheduling/reminder, hiding,
sibling-title, subtree/depth/cycle and other locally decidable preflight checks
against the saved population. Invalid proposals under that state still fail
before mutation. Completion/reopen occurrence eligibility is evaluated from saved
evidence using the existing cursor and command-time rules. Preserve recursive
ordering, confirmations and known-recurring-descendant refusal over the known
subtree. Comment editing starts with cached owner comments and retains stable-ID
edit/add/delete semantics and the all-shown-comments confirmation.

Submit the operation for the selected ID even when an unseen remote rename,
move, lifecycle change or new descendant makes saved context outdated. Todoist
may reject the operation or accept it with effects the saved state did not show;
neither outcome is a promise of automatic stale-state detection. In particular,
cached no-op and eligibility checks can reject an operation that would be valid
after refresh, while an accepted operation may overwrite a concurrent field edit
or affect a changed subtree. Explicit refresh before retry is the operator's
remedy when current local context is needed. Do not introduce a new stale-state
comparison, conflict mode, automatic retry, extra warning prompt or identity ledger.

Actual returned/reconciled state controls accepted receipts and subsequent local
state, under existing output and failure rules. "Previous" values used from the
cache are last-saved values, not a claim of remotely verified pre-operation values;
help must explain that basis without changing exact receipt templates. Newly
retrieved invalid state remains a reconciliation failure even if the operation
was accepted. This accepts outdated preflight evidence, not suppression of known
invalid local data or of invalid actual results.

### REQ-MUT-007 — Cached deletion scope and confirmation

Before deletion, including `--yes`, render the selected subtree from cached open
descendants and locally retained completed descendants eligible under the existing
`(report cursor, now]` bounds. Do not retrieve additional descendants or refresh
the target to complete that preview. Retain recursive indentation, ancestor
context, the existing older-completed-descendants warning and affirmative
confirmation rules. `--yes` bypasses only the existing confirmation.

Deletion is sent directly for the selected stable ID. A remotely renamed or moved
item retains its identity; an ID does not freeze its subtree. The operator accepts
that remotely added or otherwise unobserved descendants can also be cascade-deleted
despite being absent from the cached preview. Help must explain that deletion
previews describe saved data and recommend explicit refresh when a more current
preview is wanted. No additional per-operation warning, fresh preview, temporary
reopen or undelete data is required. Provider errors and reconciliation remain
governed by REQ-SYNC-035 and existing outcome rules.

### REQ-VERIFY-031 — Cached selection and direct-mutation evidence

Under existing offline isolation, establish that task/step selection, ambiguity,
no-match and cancellation use local data without remote population retrieval.
Exercise representative mutation-target, parent and mixed move-destination paths,
including locally retained completed candidates and their existing bounds. Missing
matches must lead to explicit-refresh guidance without automatic fallback;
missing/invalid required state must not masquerade as no match. Preserve explicitly
refreshed reads and normal cache-only reads.

Trace a composed task/step mutation from saved state through the actual transport:
there is no pre-mutation freshness/history/comment retrieval, and the intended
operation uses the cached selected ID. Establish meaningful cached local rejection,
stale-ID rejection without substitution, and remote acceptance despite a changed
title or context. Cached deletion scope must not trigger descendant retrieval;
preserve `--yes`, confirmation, warning and cancellation behavior. Exercise a
representative cached-parent or subtree case beyond a leaf-only rename.

Retain post-acceptance synchronization and distinguish its failure from rejection
or unknown remote outcome. Preserve accepted/unknown/unattempted work, no unsafe
replay, protected pending history and report output/cursor safeguards. Use adequate
existing evidence for unchanged behavior and select additional cases by distinct
failure risk rather than duplicating every command at every layer. No live account,
fixed latency promise, benchmark gate, concurrency or new test framework is added.

## Evidence, delegation and exclusions

A read-only probe on 2026-10-28, using a temporary local-state copy with remote
writes blocked, measured 4.789 seconds before selection for `delete scdaemon`.
It made 18 sequential read requests: one Sync, ten category-scoped completed-task,
two comment and five recurring-item activity requests. Local matching took about
0.0002 seconds. This is an observation of one saved account state and network run,
not a performance guarantee or a provider contract. No new provider capability is
assumed; direct stable-ID commands use the retained API-v1 evidence.

Planning owns shared-workflow changes, minimal saved-context representation,
existing-operation contract assessment and meaningful verification. It must assess
the complete design index and interacting unchanged obligations, including comments,
recurrence, multi-operation reconciliation, scopes/privacy and copied installation.
Preserve all accepted assignments and earlier protected requirement definitions;
prepare supported successor work. No application code/tests are changed by Design.

Excluded from this amendment: pre-mutation fresh candidate/eligibility guarantees,
a fresh or complete remote cascade preview, automatic refresh after no match,
background refresh, new output/progress prompts, concurrent retrieval, persistent
telemetry, public ID selectors, another storage engine and cached report mode.
Post-mutation synchronization remains intentionally in scope of existing behavior.
There are no unresolved product decisions. Technical impact and minimal retained
context are delegated to Planning; evidence that makes the agreed boundary infeasible
must be surfaced rather than silently restoring preflight synchronization.
