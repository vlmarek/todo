# Report recovery and explicit incomplete finalization — revision 22

Status: **Accepted**

Scoped agreement selected as the planning baseline.

## Agreement, purpose and precedence

The operator's `todo report --final` failed on an unresolved archived owner.
Read-only diagnosis found that the task was completed and then deleted between
observations. The task was absent from saved managed state, active retrieval and
usable completed-owner evidence; its completion activity survived. The existing
five-event activity filter omitted task-deletion events. The operator requested
Design discussion after a temporary implementation was exported and reverted.

They agreed to reconcile deletion in reports and ordinary refresh, requested
diagnostics that pinpoint missing information while allowing useful output, and
specified `--final --override` as explicit acceptance of omitted information.
They selected all discussed retrieval failures, including entire unavailable
history sources, accepted clearly marked cached fallback, and agreed that cached
activity needs evidence placing it in the report interval. The final approval
covers this file and README.md, left uncommitted for subsequent planning. Their
additional instruction separately authorizes creating the plan and implementing
through CML with existing operational settings and limits. Actual excerpts and
question/proposal context are retained separately from this interpretation.

Earlier definitions and accepted effective assignments remain historical inputs.
The following successors govern new and follow-up work only:

| Successor | Narrow effect on existing obligations |
| --- | --- |
| REQ-SYNC-040 | Supplements REQ-SYNC-005/013/025/032 and REQ-CACHE-006 with explicit task-deletion activity evidence. Extends the five-event selection in REQ-SYNC-032; preserves its encoding and pagination. |
| REQ-CLI-042 | Extends report grammar/help in REQ-CLI-024 and REQ-REPORT-003/013/014 with `--final --override`; existing boundary/cursor incompatibilities remain. |
| REQ-REPORT-019 | Qualifies fail-before-all-normal-output in REQ-REPORT-011/014/009 and complete-or-error interpretations in REQ-SYNC-025/032, REQ-REPORT-016/017 and OUT-ARCHIVE-001 for partial report display and explicitly overridden finalization. Ordinary finalization remains complete-only. |
| REQ-REPORT-020 | Qualifies current-only/fresh-evidence presentation in REQ-REPORT-005/006/011/014/016/017 and REQ-CACHE-011 only for explicitly identified cached fallback under override. Does not make cached observations current-resource or interval-coverage proof. |
| REQ-OUT-030 | Supplements REQ-OUT-019/020 and narrowly qualifies REQ-OUT-015's unprinted-ID rule for report diagnostics. Allows successful overridden finalization with disclosed omissions. |
| REQ-VERIFY-040 | Adds distinguishing recovery/override evidence; qualifies old assertions that the newly recoverable cases always produce no report output or never advance a cursor even with explicit override. |

No mutation-verification failure can be overridden by this report option.
REQ-SYNC-036/037/038 retain affected-state retrieval and evidence reuse after
ordinary writes. Per-file publication limitations, account association, safe
paths/modes, credential redaction, output-before-cursor ordering, accepted
assignment protection and still-required unrelated behavior remain binding.

### REQ-SYNC-040 — Explicit deletion evidence in reports and refresh

Reports and explicit refresh must consume supported task-deletion evidence when
establishing required managed lifecycle state. A task completed and deleted
between observations must not remain an unresolved report owner solely because
active/completed responses omit it or no usable Sync tombstone was retained.
Include `item:deleted` alongside the existing completion, undo and comment event
types in required shared activity retrieval, retaining the single JSON-array query
encoding, supported scopes, precise interval coverage and exhausted pagination.

During explicit refresh, establish required known owners' deletion where supported
evidence supplies it before treating disappearance as unresolved or preserving
stale archived context. Reuse already complete evidence and choose bounded scoped
or shared activity reads as appropriate. Do not add unconditional account-wide
historical retrieval to ordinary writes or contact Todoist for cached reads.

Confirmed deletion removes the task, its contributions and descendants established
by available authoritative/known hierarchy evidence. Fresh authoritative item
state and parentage supersede older observations: an independently surviving or
reparented child is not deleted merely because an old saved parent was deleted.
Do not infer complete enumeration of unknown archived descendants or construct
missing parentage from an activity field that only establishes note ownership.

Absence, an empty completed response, failed retrieval and active-task HTTP 404
alone prove neither deletion nor departure. Required unresolved refresh state
still fails under existing preservation rules. Confirmed scope departure retains
its existing handling; this revision adds no general move-history reconstruction.
The report-specific incomplete mode below does not change strict refresh or
mutation-verification outcomes.

### REQ-CLI-042 — Explicit acceptance with report --final --override

Add `todo report --final --override`, accepting normal option positioning and
existing common report options. `--override` is a report-only boolean valid only
with `--final`. It cannot combine with `--since`, `--until`, `--show-cursor` or
`--set-cursor`; existing `--yes` rules and duplicate/unknown option validation
remain. Reject invalid combinations before state-dependent work or HTTP.

The flag explicitly accepts missing information through the report's fixed end.
No further confirmation prompt is required. After complete delivery of the
available report and successful cursor saving, return success despite disclosed
retrieval failures or omissions. Omitted activity will not be retried automatically
in later default report intervals; this does not prevent explicit older previews
where provider/local evidence remains available.

Teach the syntax, scope, cached fallback and loss consequence in report help and
user operations documentation. Without the flag, retain complete-only successful
finalization and the existing local-only cursor-setting workflow. This option
does not apply to other commands or authorize replay/repair of remote mutations.

### REQ-REPORT-019 — Partial report output and overridden finalization

Continue attempting the required report retrieval and resolution. When task or
comment context remains unresolved, diagnose the affected entries and render the
other resolvable entries in the existing Finished, Progress and Hidden framing.
Do not fabricate missing current role, parentage, scope or lifecycle. Without
override, such an incomplete report returns nonzero and leaves its cursor
unchanged, including when `--final` was requested. Preview never advances a cursor.

With `--final --override`, produce the best available report despite all the
discussed information-retrieval failures: unresolved task/comment/ancestor or
lifecycle context, unavailable single-owner comments, expired activity intervals,
failed/incomplete activity or completed-task pages, unavailable activity-history
capability, network/authentication failure, and unusable required provider data.
Use independently usable validated evidence, with cached fallback under
REQ-REPORT-020. Identify failed or missing sources and known date ranges; explicitly
state when the number or identity of missing entries cannot be determined. Do not
require identifying every omission before an overridden report may finish.

An entirely unavailable history source or no recoverable eligible activity may
produce a report with empty event sections and explicit incompleteness diagnostics.
The flag accepts that result and the missing information when output and cursor
saving succeed. A stale report start may use the still-available history portion,
disclosing the expired portion; activity access/retention failures remain fatal
without override. Existing timestamp/eligibility rules apply to known events.

An account mismatch makes the incompatible remote results unusable. Discard them
and use only independently validated evidence associated with the bound account.
Unusable cache/history portions may contribute no fallback; never mix accounts or
publication generations or claim corrupted bytes establish missing evidence.
Usable account association and report-boundary information remain prerequisites.
The flag does not infer/reset an unknown cursor or repair unsafe paths, binding
or required local storage; existing explicit recovery remains available.

After successful report delivery, save the same fixed-end cursor an ordinary
successful final report would use. Failed or interrupted report writing/flushing,
failed required diagnostic delivery, failed cursor saving or inability to operate
on safe bound local state remains nonzero, with truthful publication facts and no
claim of successful finalization. Retain existing accepted per-file failure
limitations; no multi-file transaction, rollback or new recovery engine is added.

### REQ-REPORT-020 — Marked cached fallback without invented event eligibility

Under override, prefer fresh validated evidence. Where fresh retrieval or context
resolution is unavailable, use independently valid saved bound-account metadata,
occurrences and comments when useful. Clearly identify fallback information and
its last established observation/synchronization time; explicitly say when that
time is unknown. Cached title, hierarchy, category, completion and Hidden state
may be outdated. Do not present them as freshly verified current truth.

Cached context can describe a qualifying fresh or retained event when its role and
available ancestry can be represented without inventing missing values. Cached
activity itself needs evidence placing it in `(start, fixed end]`. A cache's
synchronization time is an observation time, never an activity timestamp. A
comment's original creation time does not prove a later edit. If timing or other
essential eligibility information is unknown, omit the uncertain contribution and
diagnose that limitation rather than showing an old event as new activity.

Fresh authoritative deletion, departure, reopen or changed parentage takes
precedence over stale fallback. Do not resurrect a proved deleted/departed object
or canceled occurrence. Preserve existing completion-source reconciliation,
deduplication and precise ordering for evidence that remains usable.

Partial or failed retrieval never establishes a complete empty collection, current
Sync baseline, historical coverage or successful remote synchronization. Do not
replace valid cache/history with a fabricated complete snapshot assembled from
failed sources, nor overwrite unusable protected state with a guessed empty store.
When complete candidate publication is unavailable, preserve prior cache/history
and finalize only the allowed cursor transition after output. Conservative extra
retained context is acceptable. History cleanup remains after successful output
and cursor publication and must preserve context for later unreported activity;
no override-specific permanent skipped-event ledger is required.

### REQ-OUT-030 — Actionable incompleteness and fallback diagnostics

Report diagnostics go to stderr and identify the original reason, failed source
or request scope, affected task/comment IDs and titles where safely available,
and missing fields or known time ranges. Distinguish omitted entries, cached
fallback and unknown amounts of missing information. Summarize incompleteness
and whether override accepted it or finalization was refused. These diagnostics
cannot be suppressed by the existing limited-history warning preference.

Mark cached entries or groups clearly and provide their available observation
time. Preserve escaping/redaction and disclose no credentials, raw responses or
unrelated account data. Diagnostic wording/layout is delegated; do not introduce
a debug mode, new exact report section, persistent log or extra diagnostic API
requests. A report containing `None.` in an incomplete section must not imply
that the application proved no activity occurred; its diagnostics explain the gap.

Recommend recovery only where applicable. Repeating ordinary refresh is not a
promised repair for unresolved archived metadata or expired history. If usable,
the explicit override is the disclosed report-finalization route accepting loss;
it does not silently change normal reporting or refresh behavior.

### REQ-VERIFY-040 — Distinguishing deletion and report recovery evidence

Use proportional offline controlled-provider and real-consumer evidence covering:

- A never-observed task completed and deleted between synchronizations no longer
  blocks final reporting; unrelated completions/comments remain. Explicit refresh
  reconciles a known owner's supported deletion without requiring its live fields.
- Deleted-parent handling removes established descendants while fresh surviving
  parentage wins; missing metadata/HTTP 404 without deletion proof remains uncertain.
- An unresolved entry produces useful diagnostics and other report output, with
  nonzero status and unchanged cursor without override, and accepted omission plus
  cursor advancement with `--final --override` after successful delivery.
- Expired history, failed paginated/owner-scoped retrieval and unavailable entire
  history sources exercise the broad override policy and unknown-loss diagnostics.
  Include authentication/account-mismatch fallback without using incompatible data.
- Fallback is marked with known/unknown observation time; known qualifying cached
  occurrences can appear, while unknown comment edit timing is omitted. Fresh
  deletion/reopen/departure evidence cannot be undone by fallback.
- Incomplete evidence cannot replace complete saved current provenance/history.
  Usable-boundary/account prerequisites and output/flush/cursor failures still
  prevent successful finalization; interruption never becomes accepted success.
- Grammar/help expose the new flag, reject standalone override and incompatible
  boundaries early, and retain ordinary complete-report behavior and strict
  refresh/mutation verification.

Reuse adequate shared tests and required release checks. Planning chooses test
organization, synthetic fixtures and scoped integration slices. No automated
live-account calls, new test framework, performance target or exhaustive failure
matrix is required.

## Provider evidence, implementation evidence and delegated choices

Use the unchanged pinned [Todoist API-v1 evidence](external/todoist/README.md)
and [history responsibility notes](history-context.md). The retained specification
documents `item:deleted` under GET activities/object_event_types, ActivityEvents
required identity/type/time with optional annotations, and deletion of a task and
its subtasks. A note's parent_item_id establishes note ownership, not a general
item ancestor chain. The existing snapshot digest is unchanged; no provider
refresh or new authenticated-account action is required for this Design.

Earlier read-only diagnosis in this conversation observed completion followed by
deletion for the reported owner. A temporary deletion-only implementation passed
its offline checks and an isolated live preview before the operator exported its
diff and requested reversion. Those observations are limited implementation
evidence, not proof of this broader override behavior or a new provider guarantee.
The current workspace application remains unchanged by this Design pass; the
external temporary patch is not an implementation assignment or a required input.

This is application behavior for incomplete evidence. It does not require a
complete historical archive, speculative owner enumeration, stale active-state
promotion, permanent event/deletion ledger, general scope-move reconstruction or
automatic remote/local repair. Existing JSON storage and normal transport retry
limits remain; override does not add an unbounded retry loop. Planning owns
request scoping, evidence representation, fallback/failure isolation, compatible
state handling, exact worker assignments and meaningful verification.
