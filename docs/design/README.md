# todo-3 product specification

Design revision: **11 — report retrieval reuse and incremental synchronization, 2026-10-27**.
State: **accepted scoped revision; uncommitted Design handoff**.

## Current revision 11

Read [report-retrieval-reuse.md](report-retrieval-reuse.md) first. The operator
confirmed reuse of fresh synchronized comments and complete owner-scoped comment
responses, safe incremental synchronization for reports, and investigation of
completion-history reuse without weakening current-truth reporting. Concurrent
edits during retrieval are not a concern. Keep category-scoped completion reads,
JSON storage, existing progress output and existing recovery rules. Concurrency
and account-wide completion-query consolidation are deferred.

REQ-REPORT-016 narrowly succeeds the separate-comment-endpoint interpretation in
REQ-SYNC-025 and REQ-REPORT-014 where complete fresh Sync evidence already exists.
REQ-SYNC-034 applies the existing incremental synchronization contract to reports.
REQ-CACHE-011 makes completion caching conditional on evidence, and
REQ-VERIFY-029 identifies distinguishing offline outcomes. OUT-REPORT-002 records
the agreed scope. Earlier definitions and accepted effective assignments remain
unchanged; the new file identifies the exact precedence and affected guarantees.

The initial request was "$cml-design discuss that change with me". Individual
choices and the final "yes" to the complete scope after the JSON-storage
clarification establish this agreement; exact excerpts and their context are
retained separately from interpretation in the external Design report. This pass
changes documentation only, with no commit, plan authoring, implementation or
execution. Planning must use supported successor work and preserve accepted
assignments, bind the complete Design tree to committed inputs and assess the
remaining completion-cache evidence before preparing execution.

## Preserved revision 10

Read [request-conformance.md](request-conformance.md) first. REQ-SYNC-032 makes
the existing activity-retrieval contract explicit: send `object_event_types` as
one JSON-encoded array query value. REQ-SYNC-033 clarifies that the read-only
waiting-label check must call the real HTTP boundary with its required arguments,
including local operation metadata. REQ-VERIFY-028 identifies representative
evidence that distinguishes both defects from successful request construction.
No command grammar, scope, report eligibility, hiding policy or recovery behavior
changes.

The operator requested: "$cml-design I want to update the design documentation
to cover that change", after disclosure of both concrete defects and their
corrections. This applies that already-described scope; no new product choice is
introduced. Actual instruction, interpretation, evidence and limitations are
retained separately in the external Design handoff. Existing runtime/test edits
from the earlier report fix are preserved, not accepted or adopted by this Design
pass. The waiting-label implementation defect remains follow-up work.

All earlier requirement definitions, retained upstream bytes and accepted
effective assignments remain unchanged. The existing 25 accepted tasks are
historical; Planning must assess the current edits and prepare supported successor
work rather than reopen them. This pass edits documentation only and authorizes
no commit, Plan, runner adoption or execution. Its complete Design handoff was
explicitly uncommitted; subsequent Planning records the committed baseline. Prior
committed revision-9 provenance remains below.

## Preserved revision 9

Read [historical-reminder-contradiction.md](historical-reminder-contradiction.md)
first. REQ-SYNC-031 supersedes only REQ-SYNC-013's duty to remember earlier
same-response contradictory reminder representations after a later authoritative
hydration/full response replaces that reminder before its owner's relevance is
resolved. A consistent later authoritative record may be published after normal
ownership/scope and final-record validation. No extra historical contradiction
tracker is required for this case. All other validation and product promises remain.

The actual agreement is native operator decision
`TX-1ad3c948fe854798b23c9131a686a71b:1`, with exact scope and consequences in
`historical-reminder-contradiction.md`. The latest instruction, “run this throught
cml-design and cml-plan and continue the work”, authorizes this amendment,
necessary scoped commits, matching fresh Planning and supported continuation under
unchanged limits. Source:
`/home/neuron/Documents/cml/todo-3/runtime/operator/design-plan-continuation-20261027/authorization.md`.
The same product understanding is already confirmed; no new interview or
confirmation is pending. This Design pass changes documentation only and does
not adopt or execute work.

Preserve every earlier requirement definition and accepted effective assignment
as history. Planning must apply this narrow successor to affected unfinished work,
retain useful T23 implementation, and preserve all unrelated requirements. Historic
rejection ATT-a388aac9816a4c7f / INC-3a1b52cb4a5f4704 remains valid against its
historic assignment; this accepted limitation is not a verified implementation fix.
No new provider observation, unresolved product choice or live-account gate is
introduced. Existing evidence limits remain below. The complete Design directory
at the handoff commit is the Planning baseline.

## Preserved revision 8

Revision 8 clarifies only revision 7's reminder replacement behavior. Todoist
parses and normalizes unresolved expressions. Before any writes, the replacement
preview shows known existing removals and the requested unresolved expression as
entered, without inventing its resolved date. Explicit `keep` and locally
established equivalent schedules preserve reminder IDs and metadata. Equivalent
wording resolved only by Todoist may recreate a reminder with a different ID.
No local recurrence/equivalence engine or provider deduplication guarantee is
required. Existing local validation, removal confirmation, direct clears and
authoritative result/partial-failure handling remain.

The operator asked “Can this be let to todoist to handle that?” and answered
“I agree with that” to the policy above, including the possible changed ID.
That confirms this scoped understanding; no further interview question or
confirmation is pending. The actual instruction and interpretation are retained
separately under
`runtime/planning-reports/design-reminder-delegation-20261027/decision.md` and
the durable Design handoff. This pass authorizes no commit, Plan or execution.
Affected definitions are REQ-SCHED-015/016, REQ-CLI-037, REQ-OUT-022 and
REQ-VERIFY-027. All other revision-7 choices and earlier accepted assignments
remain unchanged.

## Preserved revision 7 scope, with the revision 8 clarification

Read [todoist-tolerance.md](todoist-tolerance.md) first. It adds scoped successor
requirements for ignored comment attachment/activity metadata, documented omitted
due timezone and preserved recurrence language; incoming blank comments; full
relative/absolute reminders with `--reminder-at`, type-specific `keep`, and a
replacement-removal preview; relevance-first validation; imported duplicate
task/step titles; hidden categories as filters; tolerant waiting conventions and
safe incoming text. The reminder schedules do not affect urgency. The operator
retained the earlier-child/hidden-ancestor date restriction and deferred speculative
capability/event-ID/cursor compatibility.

The operator requested this discussion through `$cml-design` after supplying
`brittle.txt`; its research proposals were not prior approval. Selected decisions,
their actual answers and final written confirmation are retained in the
external Design session. The operator answered “yes” to the presented written
revision on 2026-10-27. This is a Design-only revision. No application/test/plan
change, commit or execution is requested. Full reminder support and safe provider
handling still need Planning's consumed-contract investigation and normal isolated
implementation evidence; product confirmation does not certify technical feasibility.

All earlier requirement definitions and accepted execution assignments remain
unchanged. Revision 7's precedence table identifies only successor scopes for
future follow-up work. Revision 6 and the earlier accepted publication/time/manual-
recovery limitations remain binding outside those scopes. The current workspace
baseline before this draft was clean commit
`b392afec90759a8aa804c26f4e864c80c81909fd`.
The Git revision for this agreement is explicitly uncommitted.

Historical completion claims, prior scope-specific execution authorizations and
stop-before-further-change instructions below describe their recorded passes.
The current operator request opens this scoped Design discussion; it neither
reuses those authorizations for new execution nor approves every research proposal.

Source navigation and limits for the added behavior are in
[external/todoist/tolerance-notes.md](external/todoist/tolerance-notes.md).

## Preserved revision 6 and accepted-assignment boundary

Read [project-sharing-field.md](project-sharing-field.md) first. It supersedes
only the erroneous `shared`/`is_shared` provider-field rule in REQ-SYNC-021 and
makes the remote-discovery failure phase explicit for initialization inside the
wizard. Require the provider boolean `is_shared`, with no legacy `shared`
fallback or missing-value privacy default. Internal `Project.shared` and local
storage names may remain. Personal/unshared eligibility, Inbox/workspace rejection
and all unrelated safety behavior remain unchanged.

The actual operator instruction was “do that”, after disclosure of this exact
is_shared-only correction, matching Plan alignment, adapter/fixture correction and
accurate discovery error labeling. Source:
`/home/neuron/Documents/cml/todo-3/runtime/operator/is-shared-only-authorization-20261026.md`.
This settled instruction authorizes this correction and its matching Plan and
runner work; no repeated interview or confirmation is pending. Stop before any
additional Design/Plan scope change after this approved alignment. The older
dual-spelling proposal in the diagnosis is superseded.

Run-001 completed all 19 accepted assignments at
`ec9bd8da175ddc3fcfe715de3ff7a6721dc5eaad`. Preserve every accepted effective
assignment and its original binding bytes. Planning must use supported successor
obligations and follow-up work for this correction, without reopening accepted
tasks. The new definitions are REQ-SYNC-028, REQ-INIT-010 and REQ-VERIFY-026.
No application, test, plan or runner-configuration change belongs to this Design
revision. No new provider snapshot or live-account access is required.

## Preserved revision 5 agreement

Then read [partial-initialization-failure.md](partial-initialization-failure.md)
for the unchanged first-init local-publication
failure boundary and precedence.
The operator accepted error and rejection of inconsistent files with the existing
explicit manual fresh start, including its disclosed pending-history/report-cursor
loss. Rerunning init need not recover every partial state, including a timezone
change between attempts. Normal successful/repeat initialization, synchronization,
timezone semantics and local safety remain. The actual confirmation was “I agree
with that”; source:
`/home/neuron/Documents/cml/todo-3/runtime/operator/partial-init-write-failure-authorization.md`.
This authorizes this amendment and matching Plan alignment. Stop before every
subsequent Design or Plan change. No storage repair or new recovery mechanism is
part of this amendment.

Then read [command-time-precision.md](command-time-precision.md) for the unchanged
revision-4 time-calculation agreement and
[publication-failure.md](publication-failure.md) for the revision-3 publication
contract, subject only to the new scoped first-init recovery exception.
The time amendment permits ordinary aware Python datetime
precision for urgency, countdowns, relative scheduling and relative report-boundary
parsing; subsecond imperfections there are outside acceptance. Exact stored
timestamps and ordering, calendar/timezone correctness and unrelated report and
lifecycle obligations remain. The operator confirmed this exact scope with
“do that and continue the work. Stop before any future update to plan or design.”
Source: `/home/neuron/Documents/cml/todo-3/runtime/operator/subsecond-tolerance-authorization.md`.
That earlier amendment and its matching Plan alignment are settled.

The scoped successor definitions supersede only their stated promises for unfinished
and successor work. All earlier requirement/exclusion definitions remain byte-for-
byte intact as protected history for accepted T01/T02/T03/T04/T05/T06/T07/T08/T09/T19.
Planning must bind the current successors to affected unfinished work without
rewriting those accepted effective assignments or their original definitions.

The operator accepted: “A failed multi-file publication would report an error and
require explicit recovery; preserving the previous usable snapshot would no longer
be guaranteed.” The actual instruction was “implement that and continue the work”.
This confirms the same scoped understanding; no additional interview is pending.
Source: `/home/neuron/Documents/cml/todo-3/runtime/operator/publication-limitation-authorization.md`.
Per-file atomicity, pre-publication preservation, mixed-set refusal, existing
explicit recovery, remote outcomes and required pending-history protections remain.
No rollback, journal, transactional redesign or new recovery command is authorized.

The current workspace contains an initialized application and run-001. Historical
statements below about a fresh design-only project, uncommitted revision 2, lack of
implementation/assignments, or lack of authorization describe those earlier passes;
they are not current execution or preservation instructions. Current execution still
requires Planning alignment, a finished supported publication and runner adoption.
The Design amendment itself does not adopt or execute work.

## Historical revision 2 context

On 2026-10-26 the operator answered “yes” to the final shared-understanding check
of written revision 1. In the subsequent collaborative assessment, the operator
settled the alias, editor and NOW corrections below one at a time and then
instructed “update the design”. Revision 2 applies that confirmed scoped
understanding. It does not authorize a commit, plan authoring or execution.

This is a fresh design-only project at `/home/neuron/Documents/cml/todo-3`.
The source is todo-2 design revision 5, all 26 source documents at committed
baseline `b4cfa4dae68a0e3a2d0da06a3f0f34b7238ea9e4`, design-tree ID
`eca7af724dba109d371ced812c620e1971e5c7de`. The operator selected this new
destination after discussing the changes one at a time. The source workspace and
application remain unchanged. No application code, tests, task graph, old runtime
state, accepted assignment or implementation interface is imported into todo-3.

## Intended product and success

`todo` is a personal Python terminal CLI backed by one explicitly bound personal
Todoist account/root. It supports setup, urgency-ranked current work, recursive
task/step inspection and maintenance, comments including editor reconciliation,
scheduling/reminders, hiding, moves, completion/reopen/deletion, search and manual
cursor-bounded reports. Todoist owns remote truth; local configuration, binding and
report cursor have their stated local authority.

Current cache is disposable. Separate history protects known work still needed
for reporting across sync failure and cache rebuilding. It need not remain after
a successful final report covers it. Losing a disposable cache is different from
deliberately deleting the entire local directory, which discards pending history
and the old report boundary too.

Success examples: nested steps appear in their own urgency rows with ancestor
context; a completed step and its own comment survive cache rebuilding until
reported; final output/cursor failure leaves pending history intact; a successful
final report advances the cursor and permits covered-history cleanup. A failed
sync before any publication replacement retains the last saved cache. After a
partial multi-file publication, the old usable snapshot is not guaranteed; a mixed
set fails and requires explicit recovery under publication-failure.md and the
first-init exception in partial-initialization-failure.md.
Missing required report data fails the report and preserves its cursor. Possible
duplicate anonymous activity entries are accepted; omitted work is not.

## Reading order and authority

1. [product.md](product.md): user, primary workflow, scope and failure priorities.
2. [domain-model.md](domain-model.md): identities, depth, urgency, hiding and lifecycle.
3. [command-interface.md](command-interface.md): grammar, aliases, selections, prompts,
   help, configuration and explicit cache clearing.
4. [behavior.md](behavior.md): editor, creation, mutations, scheduling and reports.
5. [output-contract.md](output-contract.md): exact TPL templates, streams, time and paging.
6. [architecture.md](architecture.md): responsibilities, cache, unreported history,
   local state, concurrency, interruption and runtime/build constraints.
7. [todoist-adapter.md](todoist-adapter.md): consumed provider mapping and operations.
8. [security.md](security.md), [operations.md](operations.md): credentials, privacy,
   first-use setup, manual fresh start, backup and recovery.
9. [quality-requirements.md](quality-requirements.md): behavioral evidence and isolation;
   test levels, fixture structure and scheduling belong to Planning.
10. [out-of-scope.md](out-of-scope.md): deliberate exclusions and accepted limits.
11. [history-context.md](history-context.md), [floating-time-context.md](floating-time-context.md),
    [open-questions.md](open-questions.md): source navigation and remaining technical evidence.
12. [todoist-dependencies.md](todoist-dependencies.md): informative ownership context.

The `REQ-*` and `OUT-*` definitions specify behavior, with the scoped clarification
and successor precedence in request-conformance.md,
historical-reminder-contradiction.md, todoist-tolerance.md,
project-sharing-field.md, partial-initialization-failure.md,
command-time-precision.md and
publication-failure.md governing
current unfinished/successor work;
named TPL templates remain exact. Each ID has one definition. Provider files are evidence rather than
product authority. Binding documents carry `Status: **Accepted**` for the confirmed
specification. This is not execution readiness, a prepared plan or independent
review. No commit or execution is authorized by product confirmation.

## Revision 2 decisions and assessment outcomes

This was a collaborative `cml-design` assessment and revision, not an independent
`cml-review` publication. F1–F5 below are the conversation's concern labels, not
native review identities. Actual operator excerpts and separate interpretations
are retained in the external revision-2 Design report and decision artifact.

- F1, anonymous undo duplication: the operator said “this is not a concern, next”
  after the assessor acknowledged no evidence that Todoist duplicates undo events.
  No change to anonymous-event handling or recurring cancellation is made; the
  claimed high severity was withdrawn. Possible duplicate anonymous entries remain
  an accepted limit, not a claim of observed provider behavior.
- F2, retention cutoff: after distinguishing report cursor from earliest available
  provider history, the assessor withdrew this as a design issue. The operator
  proceeded to the next issue. Complete-or-error reporting and unchanged cursor on
  failure remain required. Establishing relevant provider retention semantics is
  ordinary Planning work, not a new product requirement or research stage.
- F3, scalar noun-action aliases: the operator required `--due` and its date/time
  value to be adjacent, then answered “yes” to the same rule for priority,
  reminder, rename and move aliases. Each consumes one adjacent scalar argument,
  or its equivalent equals form, before the task or parent/step selectors.
  Multiword scalar values require quoting. Canonical rename/move grammars,
  creation groups, fixed-priority flags and all unaffected aliases remain intact.
- F4, comment editor: the operator answered “yes” to observable block parsing.
  Remove the promise to detect accidentally deleted interior headers. Remaining
  text joins the preceding block, and a missing existing ID requests deletion;
  structural validation and existing delete-all confirmation remain required.
- F5, NOW output: the operator clarified that `now --all` is normal `now` with
  hidden tasks and steps included. Correct the stale TPL-LIST reference to the
  existing TPL-NOW annotations; exact templates and hiding behavior are unchanged.

Affected definitions: REQ-CLI-031/033, REQ-CLI-024, REQ-COMMENT-006,
REQ-CLI-034 and REQ-VERIFY-016/018. These changes are addressed by the author;
no independent verification of the revision is claimed. There is no prepared plan
or existing implementation whose assignments need adoption or preservation.

## Retained revision 1 operator choices

The interview selected these changes; actual excerpts and the exact source are
retained in the external Design session, separately from this interpretation.

- `--set-cursor` sets the explicitly supplied valid value. Its previous value is a
  timestamp, `none` or `corrupted`; keep existing confirmation and file safety.
- Remove `init --rebind`. The deliberate account fresh start is stopping processes,
  deleting all of `~/.todo` and running init. Deleting only config is insufficient.
- Remove `doctor` and the promise to collect every independently detectable problem.
  Ordinary validation and useful errors remain required.
- Keep aliases, noun-action forms, creation shorthands and task/step parity. The
  operator explicitly retained their convenience after considering removal.
- Keep the full comment editor and first-run wizard, including their existing safety
  and cancellation behavior.
- Keep current cache and unreported history separate. Protect pending historical
  information through refresh, cache clearing and failed/preview reporting. Permit
  cleanup only after successful final output and cursor publication. Do not promise
  a permanent completed-work archive or indefinite completed-search availability.
- Use the last successfully saved cache after sync failure. Report the failure in
  its originating command; omit a persistent clean/outdated/blocked state system.
- Keep complete-or-error reports and unchanged cursor on missing required data.
  Straightforward supplied-event-ID deduplication is enough; tolerate possible
  duplicate anonymous entries without elaborate identity reconstruction.
- Accept `--reminder 0m` input; shared readable timing blocks say `at due`. Scalar
  offset displays use `0m`. Keep all exact output templates.
- State important verification outcomes and consequential failures. Planning chooses
  test levels and representative workflows. No mandatory requirement-to-test ledger
  or fixed eight-workflow checklist; keep offline isolation, exact template evidence,
  essential workflows and verification of the copied installation.

Unchanged decisions include Python 3.11 standard-library runtime on Linux/amd64,
copied launcher/modules, Docker directly invoking Codex for eventual implementation,
personal managed-root scope, depth 0 tasks/depths 1–4 steps, aliases, account-timezone
authority, the selected remote floating DST policy, selection/no-op semantics,
locks, restrictive file handling, ordered outcomes without rollback, complete report
pagination and output-before-cursor ordering, optional configured paging with final
reports always direct, and the retained source provider/API baseline.

Principal affected definitions: REQ-INIT-002/003/008, REQ-OPS-001, REQ-REPORT-003/013,
REQ-CACHE-006/008, REQ-LOCAL-005/006, REQ-SYNC-005/025/026, REQ-CLI-021/029/032,
REQ-SCHED-010 and REQ-VERIFY-001/002/004/010/020/022. `REQ-DIAG-002` is retired,
not reused. Other retained IDs keep their identity; this is a fresh project with
no protected old assignments to reconstruct or silently adopt.

## Capabilities, shared responsibilities and possible increments

CLI handles grammar, prompts and presentation; workflows coordinate state and
ordered operations; domain rules operate offline; the adapter consumes retained
Todoist contracts; persistence separates binding/cursor, current cache and pending
history. Storage types, filenames for history and internal function boundaries are
delegated. Pending history is observation data for reports, not a mutation journal.

Possible capability slices, not an authored task graph: init-to-current/offline work;
capture/steps/comments and scheduling/hiding/moves; completed/unreported retention
through cache rebuilding and final reporting; final exact output, copied runtime
and user operations. Planning may combine or reorder these. Establish the history
producer-to-finalization path early enough to challenge publication/pruning
assumptions. Every retained product requirement belongs to the complete release.

## Evidence and handoff limits

The Todoist API JSON, subtask Help HTML, floating-time Help bytes and GNU less
manual are imported unchanged with their original manifests. Their recorded
2026-10-24/25 retrieval dates are not fresh todo-3 provider observations. No live
Todoist request or new prototype was performed. Inherited provider/less observations
are supporting context, not implementation acceptance. Remaining evidence needs
are explicit in open-questions.md, especially archived subtree moves, operation
proof, report-owner resolution and pending-history cleanup ordering.

Revision 6 has no unresolved product decisions and its written confirmation is
retained; technical feasibility was not certified by that confirmation.
Revision 7's individual choices and written agreement are confirmed. Its provider
evidence needs remain explicit. Revision 9's authorized Planning pass consumed its
retained handoff, assessed affected unfinished work and preserved accepted
assignments and useful implementation; revision 10 was subsequently planned and
implemented. Those authorizations and revision-7/8 Design-only restrictions
describe their historical scopes. Current revision 11 is Design-only; its confirmed
scope, uncommitted status and remaining evidence needs are recorded above and in
report-retrieval-reuse.md. Planning and execution are not started by this handoff.
