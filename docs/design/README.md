# todo-3 product specification

Design revision: **2 — scalar alias grammar and scoped assessment corrections, 2026-10-26**.
State: **confirmed current specification; uncommitted**.

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
sync retains the last saved cache, which later offline reads may still display.
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

The `REQ-*` and `OUT-*` definitions specify current behavior; named TPL templates
remain exact. Each ID has one definition. Provider files are evidence rather than
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

There are no unresolved product decisions. The operator confirmed this written
revision; technical feasibility is not certified by that confirmation.
No old-plan task IDs, packets, preservation instructions or incident recovery are
inputs for a fresh implementation. Source chronology remains in todo-2 history;
the current behavior is defined inline here without an amendment overlay.
