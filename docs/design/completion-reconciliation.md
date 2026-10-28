# Completion evidence reconciliation — revision 12

Status: **Accepted**

## Agreement and precedence

The operator requested Design discussion after one completed ordinary task
appeared twice in Finished. Investigation found the same task ID in completed-task
and activity responses, with timestamps differing by about 15 milliseconds.

The operator agreed: "I agree with that, activity timestamp with the
completed-task timestamp used only as fallback?" They objected to a new report
error for an inconsistency outside the user's control and said a tiny discrepancy
across a cutoff was not a concern. Native decision
`TX-41d10e23a8204542ac2271c94f13e2fa:0` retains the exact instruction separately
from its interpretation. The same understanding is confirmed; no further interview
or repeated confirmation is pending for this scope.

REQ-REPORT-017/018 clarify the source reconciliation and chosen timestamp for
completion occurrences under REQ-REPORT-006/011/014. REQ-VERIFY-030 supplements
REQ-VERIFY-013. Preserve those earlier definitions and all accepted assignments;
Planning owns the impact assessment and successor work. Existing stable activity-ID
deduplication and anonymous-entry tolerance under REQ-SYNC-025 remain unchanged.

### REQ-REPORT-017 — Reconcile completion evidence across endpoints

Continue obtaining complete required completed-task and activity evidence. Treat
these as evidence about completion occurrences, rather than adding one report
occurrence for each source record. A single completion represented in both sources
must contribute one row even when their timestamps differ slightly. The observed
ordinary completion at 18:11:14.704186Z in completed tasks and 18:11:14.719113Z in
activity is one occurrence, not two.

Activity establishes completion and undo history. Completed-task records establish
required archived task context and provide fallback completion evidence where the
occurrence is not already represented by activity. Do not require a completion to
appear in both sources or treat missing counterpart evidence or timestamp equality
alone as a new report failure. Active recurring tasks can have completion activity
without a matching completed-task record; report those effective occurrences using
current active task context. Apply the same reconciliation to task and step
completions in Finished and Progress.

Preserve separate recurring completions and the rule that an undo cancels the
latest unmatched preceding completion once. Cross-source representations of the
same occurrence must not leave a false residual occurrence after undo. Do not
collapse distinct activity events merely because they share a task ID or a close
timestamp. Supplied event IDs still deduplicate; anonymous activity entries retain
their existing source-order and possible-duplication tolerance. Cross-endpoint
reconciliation does not introduce universal occurrence identity proof.

Creation or completion through the CLI, web, Android or another synchronized
client does not select a different report policy. Preserve current surviving text,
parent/category/scope and ordinary reopened-task omission. Fallback does not
authorize replacing failed activity retrieval with empty history, ignoring a
required malformed record or incomplete page, or weakening existing required-owner
failure and output/cursor protections.

### REQ-REPORT-018 — Prefer activity completion timestamps

For a reconciled completion represented by activity, use its activity event_date
for report eligibility, chronological ordering and displayed completion time.
Use completed_at from the completed-task record only for fallback completion
evidence with no corresponding activity representation. Different source
timestamps are not themselves separate occurrences.

Apply existing precise `(start, fixed end]` eligibility to the chosen timestamp;
retain current timezone presentation, ordering and finalization behavior. Do not
round timestamps or require source equality as a reconciliation shortcut. The
operator accepts tiny source-time differences at cutoffs; this revision adds no
special cross-report ledger, late-evidence repair mechanism, or stronger
exactly-once guarantee across changing endpoint observations. Existing pending
history and cursor protections remain in force.

### REQ-VERIFY-030 — Distinguishing completion reconciliation outcomes

Establish that a single ordinary completion represented in both endpoints with
slightly different timestamps yields one completion row, with the activity time
used for interval eligibility and display. Establish the same shared behavior
for step completions without requiring a separate exhaustive entity matrix.

Establish that activity-only recurring completions remain reportable, distinct
recurring completions remain distinct, and one completion represented in both
sources followed by one undo leaves no effective occurrence. Establish fallback
completed-task evidence using completed_at without an extra counterpart lookup
or new absence error. Retain existing supplied-ID/anonymous-event behavior and
required retrieval/output/cursor protections. Use controlled synthetic provider
responses and existing verification machinery; no production account or new test
framework is required. Planning chooses meaningful cases and layers.

## Evidence and limitations

These are scoped observations, not provider guarantees. Read-only probes on
2026-10-28 found the ordinary-task timestamp pair above with the same task ID.
The current report selector compares exact instants to suppress a supplemental
completed record; unequal instants therefore yield two rows displayed at the same
second. Disposable composed-report probes also reproduced duplicate step rows and
a false residual recurring completion after undo. Adjacent preview intervals split
between the two times could both include the same completion. The last case is
documented as diagnostic evidence, not a new strong cutoff guarantee.

The two recurring meetings discussed by the operator had completed activity with:

| Observation | Completed occurrence attention, Prague | Advanced attention, Prague |
| --- | --- | --- |
| Weekly meeting | 2026-10-27 15:00 | 2026-11-03 15:00 |
| Fortnightly meeting | 2026-10-27 11:00 | 2026-11-10 11:00 |

Their activity extra_data included completed_due_date,
completed_due_date_local and due_date; active-task reads confirmed the advanced
dates. Neither meeting appeared in completely exhausted category-scoped or
account-wide completed-task reads covering the completion day through inspection.
Do not infer that every recurring event has these optional fields, that every
client supplies them, or that both endpoints expose every occurrence. Hypothetical
missing-history examples discussed in the interview are not observed provider
loss or a general permission to undercount.

Retain the unchanged [API-v1 evidence](external/todoist/README.md), especially
ItemSyncView, ActivityEvents, the completed/by_completion_date and activities
operations, and [history-context.md](history-context.md). The schema documents
optional activity extra_data and no shared cross-endpoint occurrence identifier or
timestamp equality guarantee. Official [activity documentation](https://www.todoist.com/help/todoist/features/view-reporting-in-todoist-oOra6D),
checked 2026-10-28, describes mobile/web/desktop/integration activity and limited
history by plan; it does not establish permanent one-to-one endpoint correspondence.
The live observations supplement interpretation without replacing pinned upstream
bytes or making live-account access an acceptance dependency.

## Delegation, exclusions and handoff

Planning must establish a proportionate reconciliation strategy using task
identity, available activity/lifecycle evidence and any useful supported optional
metadata. No numerical time tolerance or new local occurrence ledger has been
chosen. In particular, do not assume that task ID alone identifies a recurring
occurrence or that matching displayed seconds proves identity. Use existing
anonymous-event tolerance; do not add a general undercounting policy.

Assess shared occurrence handling in synchronization, bounded reopen discovery,
recurring undo selection and pending-history cleanup against their existing
obligations. Activity-only recurring evidence was observed; determine whether
existing consumers establish the evidence they already require. Report timestamp
priority does not automatically change mutation acceptance or prove command
success. Resolve any newly consequential product tradeoff with the operator
rather than silently expanding this correction.

This is one narrow report-correctness increment across retrieval, reconciliation
and presentation. Keep current endpoint scopes, JSON storage, report framing,
capability/retention checks, complete pagination and safe finalization. No new CLI
option, user repair workflow, provider-wide identity guarantee, cross-command
completion cache, or elaborate matching service is agreed. No runtime, tests,
task graph, provider snapshot, commit or runner execution is changed by this pass.

The original Design handoff was uncommitted. Planning binds the complete Design
tree to its prepared commit. The external handoff report retains evidence,
the actual operator decisions, limitations and remaining technical investigation.
When requested, a fresh Planning session must bind the committed complete Design
tree and preserve accepted assignments through supported successor work.
