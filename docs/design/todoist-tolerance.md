# Todoist coexistence and absolute reminders — revision 8

Status: **Accepted**

Confirmed product agreement, revision 8.

This amendment records the operator's discussion of
`/home/neuron/Documents/cml/brittle.txt` on 2026-10-27. That file contained
research and proposals, not prior approval. The operator selected the behavior
below one decision at a time. The last additional decision accepted `keep` values
for exact reminder retention. The operator answered “yes” to the final written
shared-understanding check on 2026-10-27, confirming revision 7.
No application, tests, task graph, runner configuration, execution or commit is
authorized by this Design pass.

Revision 8 applies the subsequently confirmed reminder clarification only. The
operator asked “Can this be let to todoist to handle that?” and answered “I agree
with that” to delegating expression parsing/normalization to Todoist, previewing
unresolved input before writes, and preserving identity for explicit `keep` and
locally established matches without guaranteeing identity for equivalent wording
resolved only by Todoist. Its actual instruction and interpretation are retained
separately in
`runtime/planning-reports/design-reminder-delegation-20261027/decision.md` and
the durable handoff. No repeated confirmation is pending. All other revision-7
choices and earlier accepted assignments remain unchanged.

## Precedence and protected history

Apply these scoped successor definitions to new follow-up work. All earlier
requirement/exclusion definitions and the accepted run-001 assignments remain
byte-for-byte intact. This amendment does not reopen accepted work or adopt a run
revision. Planning must assess affected work and prepare supported successors.

| Successor | Earlier scope superseded or extended |
| --- | --- |
| REQ-SYNC-029 | REQ-SYNC-021/025/013: unconsumed comment attachments and activity annotations, optional due timezone and retained recurrence language |
| REQ-SYNC-030 | REQ-SYNC-021/025/005/016/028 and REQ-INIT-003/008/010: relevance before remaining content validation; relevant project eligibility stays strict |
| REQ-COMMENT-009 | REQ-DOM-009, REQ-SYNC-021/025, REQ-COMMENT-006/007/008 and REQ-REPORT-011: inbound blank comments and editor preservation |
| REQ-SCHED-015 | REQ-DOM-012, REQ-SCHED-010/012/013, REQ-CREATE-007/008 and REQ-SYNC-021/026: relative and absolute reminders, expressions, keep/clear and preservation |
| REQ-SCHED-016 | REQ-SCHED-010 and REQ-CLI-032: whole-set replacement with confirmation before reminder removal |
| REQ-CLI-037 | REQ-CLI-024/031/033: reminder-at scalar syntax and applicable task/step aliases |
| REQ-DOM-015 | REQ-DOM-007/006, REQ-CREATE-007, REQ-MUT-005/004 and REQ-SYNC-005: imported duplicate task/step titles versus new CLI collisions |
| REQ-DOM-016 | REQ-DOM-013, REQ-SCHED-005 and hidden-category restrictions in scheduling, creation, moves and reconciliation |
| REQ-DOM-017 | REQ-DOM-013/009, REQ-SCHED-011/014/012 and REQ-SYNC-024: incomplete waiting conventions and literal malformed reason text |
| REQ-DOM-018 | REQ-DOM-009, REQ-SYNC-024, REQ-COMMENT-006 and text consumers: incoming CRLF, blank multiline text and multiline task/step titles |
| REQ-OUT-022 | REQ-OUT-015/020/021/017, REQ-CLI-021/027/034/035 and named templates: only the new value fragments, reminder-only timing and replacement preview below |
| REQ-VERIFY-027 | REQ-VERIFY-007/010/011/013/016/017/018/019/021/022/026: revised distinctions and still-required protections |
| OUT-FEATURE-002 | Clarifies the limits of OUT-FEATURE-001 and this amendment; no speculative protocol expansion |

Everything outside these scopes remains binding, including project ownership and
`is_shared` eligibility, account/root identity, task depth and lifecycle, complete
reports, per-file publication/manual recovery, command-time precision, privacy,
locking, operation proof, offline reads, standard-library runtime and isolation.
In particular, the unchanged earlier-descendant/hidden-ancestor date restriction
still rejects conflicting imported state and CLI requests. The operator explicitly
retained that restriction after discussing the concealed-earlier-work risk.

## Provenance and boundaries

The operator accepted ignoring attachment metadata; preserving blank incoming
comments with a display marker; full absolute reminder support; `--reminder-at`;
deletion-confirmed replacement; full scheduling expressions with exact times;
no reminder effect on urgency; absolute reminders without timed task due values;
relevance-first validation; imported duplicate task/step titles; hidden categories
as filters; tolerant waiting conventions; CRLF/blank text handling; safely displayed
multiline task/step titles; and type-specific `keep` values. Exact answers and
their preceding choices are retained separately in the external Design decision
report under `runtime/planning-reports/design-tolerance-20261027/decisions.md` and
the durable preparation publication. These are operator choices, not inferences
from tests or current code.

The omitted due-timezone correction, removal of unused activity-annotation
dependence and retained recurrence-language correction come from the supplied
research and the pinned provider evidence. They were explicit parts of the written
revision confirmed by the operator. They do not introduce new user workflows. Evidence,
source conflicts and unverified provider behavior are separated in
[external/todoist/tolerance-notes.md](external/todoist/tolerance-notes.md).

### REQ-SYNC-029 — Consume needed metadata without inventing constraints

For incoming comments, `file_attachment` is entirely unconsumed metadata. Do not
require, validate, persist, render or compare it, including when absent, null or
non-null. Apply this across initialization retained-note handling, current/full/
incremental mapping, scoped/archived comment retrieval, duplicate comparisons,
reconciliation and reload. Preserve required comment identity, owner, text and
time under REQ-COMMENT-009. Text comments accompanied by website previews or
actual files are accepted. No attachment classification or model is needed.

Text updates address the existing stable comment ID, send the intended text and
omit attachment fields. Do not recreate the comment or send empty/null attachment
values to implement omission. Verify request construction; controlled request
evidence does not prove live attachment preservation by Todoist.

Do not request activity note annotations for application behavior and ignore
unused annotation content, including `extra_data.content`, without validating its
shape. This does not discard consumed move/scope context in activity metadata.
Keep required event identity/type/time/ownership, deletion/lifecycle evidence,
pagination and separate retrieval of current surviving comment text for reports.

Accept the documented omission of `due.timezone` as null, using the existing
date-only/floating/fixed interpretation and authoritative account timezone.
Continue validating supplied timezone values and all meaningful required due
date/recurrence fields. This is not a default for a missing account timezone,
missing due date or unknown recurrence flag.

Use `lang: "en"` for newly entered English provider-parser expressions. When
retaining an existing provider recurrence, retain its original expression,
language, recurrence flag and applicable timezone together. Neither request
construction nor an operation wrapper may overwrite its language with English.
Preserve this distinction for task occurrences and absolute reminder schedules.

### REQ-SYNC-030 — Relevance before remaining record validation

Establish the minimal identity, ownership/scope, deletion and interval context
needed to decide whether a record contributes to the operation before validating
its remaining display fields or feature-specific content. Discard demonstrably
unrelated, deleted or out-of-window records without applying unused live-record
content restrictions. A deleted comment, for example, need not have a live
comment's text or posting timestamp once deletion and ownership are established.
A completed row outside the requested interval need not have a valid display
title solely to be discarded.

Initialization uses the same principle for unrelated projects and labels. An
unrelated project's unused fields or an irrelevant label's display text must not
block the selected root. Discovery may exclude an unsafe candidate, identifying
why without presenting it as eligible. A bound or selected project with missing
required safety metadata remains a failure; unknown sharing never means private.
Keep the revision-6 `is_shared` interpretation for relevant projects.

When required context cannot establish relevance, fail clearly rather than guess
that the record is unrelated. Still validate every retained live managed item and
required qualifying history record. Preserve whole-root hierarchy/lifecycle
checks, complete required resources, exact interval filtering and pagination.
No arbitrary record skipping, truncated report or partial normal snapshot follows
from this rule. Diagnostics identify the relevant owner/record where available,
separate unsupported app behavior from malformed required data, and never dump
credentials, attachment URLs or unrelated payloads. Do not suggest clearing local
state as a cure for a remote parsing or managed-data problem.

### REQ-COMMENT-009 — Incoming blank comments retain identity

Accept empty incoming text and documented omitted-content defaults for supported
comment responses; do not turn a wrong type or an undocumented missing required
field into blank content. Under REQ-DOM-018, permitted whitespace-only incoming
comments likewise have no readable text. Keep the comment's stable ID, owning item,
posting time and known activity association. Blank content is neither an absent
comment nor proof of deletion. Preserve the record through incremental merge,
current-cache/history serialization and reload, editor reconciliation, and relevant
report inclusion. Existing timestamp/ownership rules remain.

Views and qualifying report entries render `[no text]` in place of an empty body
under REQ-OUT-022. The marker is presentation only, never remote content. Ordinary
search matches actual comment content, not this marker. Blank comments still
count as existing comments and eligible activity is not silently omitted.

The editor includes an existing blank comment's ordinary ID/time header with an
empty body, not the display marker. Saving that block unchanged preserves the
same comment without a write. Replacing it with nonempty text is a normal update.
Removing its complete block requests deletion; the existing all-shown-comments
confirmation and concurrent-change rules still apply. Explicitly emptying a
previously nonblank existing comment remains invalid, as does an empty new block
except the one unused trailing starter permitted by REQ-COMMENT-006.

Explicit CLI new-comment input, including completion comments, still requires
nonempty text and must not silently disappear as a successful skipped creation.
The unused trailing `[new]` starter remains a successful no-op. Normalized editor
comparison must preserve unchanged inbound blank/CRLF records without rewriting
them. Attachment metadata is ignored under REQ-SYNC-029, not represented by a
fabricated comment body or special attachment editor block.

### REQ-SCHED-015 — Relative and independent absolute reminders

A reminder has stable identity/ownership and one of two supported scheduling
forms: a whole-minute relative offset, or an absolute scheduled date/time with
its applicable recurrence, language and timezone semantics. Import, persist,
reload, render, create and manage both forms on tasks and steps at supported
depths. Do not reinterpret an absolute reminder's unused offset as relative, or
require a relative reminder's unused absolute scheduling fields to drive behavior.
Validate fields needed for the actual type. Location reminders are excluded by
OUT-FEATURE-002, rather than silently called relative or cleared incompletely.

Relative offsets keep REQ-SCHED-010's exact grammar, zero semantics, duplicate
checks and timed-task-due requirement. Absolute reminders use `--reminder-at WHEN`
and supply their own exact time. They are valid on undated and date-only tasks;
adding one alone does not create or change the task's due value. Neither reminder
type affects urgency, overdue buckets or hiding visibility. Those remain based
on the item's own task attention and the agreed hiding policies.

Absolute WHEN reuses REQ-SCHED-012/013's English scheduling grammar, account-timezone
authority, elapsed/calendar arithmetic and local DST refusal. `"2h"` is an absolute
time two elapsed hours from the command's one time reference; it is not an offset
before task due. `"Friday 09:00"`, explicit ISO instants and recurring expressions
such as `"every Monday at 09:00"` are supported. New unknown/recurring expressions
use Todoist's English parser and normal authoritative reconciliation. Leave
parsing/normalization of those expressions to Todoist; no local recurrence or
general natural-language equivalence engine, read-only provider parsing facility,
or automatic provider deduplication guarantee is required. A result
without an exact time is not a successful absolute reminder: locally known
date-only input fails before writes; unexpected accepted date-only normalization
is reported as partial failure with actual outcomes, without rollback.

Preserve floating versus fixed schedules, recurrence and original provider
language through reads, persistence and unrelated mutations. Apply the existing
remote floating overlap/gap interpretation and new-account-timezone re-resolution;
fixed instants retain their instant. These are application interpretation rules,
not proof of notification delivery or provider DST/recurrence behavior.

Reminder options construct one desired complete set. `--reminder OFFSET` supplies
a relative reminder; `--reminder-at WHEN` supplies an absolute one. Both may repeat
and mix. `--reminder keep` contributes every existing relative reminder unchanged;
`--reminder-at keep` does the same for absolute reminders. The reserved `keep`
value is lowercase, appears at most once per type, and bypasses date parsing only
as this explicit retention instruction. Retain IDs and scheduling metadata; do
not delete/recreate kept reminders or reparse their existing non-English rules.
Keep on an empty type contributes nothing. No observable change is still a no-op
error. Known duplicate requested relative offsets or equivalent absolute schedules
fail before writes; a shared next-firing instant alone does not make different
recurrences equivalent. Unknown normalized results retain ordinary outcome rules.

Omitting every reminder option preserves the complete existing set. With any
reminder options, only explicitly supplied values and kept types belong to the
desired set; omissions are subject to REQ-SCHED-016's removal preview. Existing
reminders retained by `keep` or by a locally established equivalent schedule keep
identity and scheduling metadata. Establish local equivalence from the complete
supported scheduling semantics, including recurrence and floating/fixed timezone
behavior; a shared next-firing instant is insufficient. If equivalence depends on
Todoist parsing a supplied expression, it need not be established before writing.
Such an expression requests a replacement/addition, not implicit retention of an
existing reminder. Even equivalent wording may recreate a reminder with a different
ID after confirmation of the existing removal. Locally decidable duplicate/no-op
checks remain required; unknown semantic equivalence alone neither requires a new
local parser nor makes the request invalid. Reconcile and display actual outcomes
under the existing rules instead of claiming provider deduplication or preserved
identity. Omission of all reminder options and explicit `keep` retain their
stronger preservation obligations.
`--reminder clear` is exclusive of other reminder values and removes both types
while retaining task attention, recurrence and hiding. `--reminder-at clear` is
not a second clear syntax. Existing `schedule SELECTOR clear` deliberately clears
all scheduling, including task attention/recurrence, both reminder types, waiting
label and a valid associated reason. These explicit clear forms do not acquire
the replacement-only confirmation.

Changing task attention without reminder options preserves both types. An absolute
reminder retains its independent schedule across requested task rescheduling,
rename and moves. Do not send an absolute-reminder reschedule merely because a
task occurrence advances; reconcile provider lifecycle changes under the existing
completion/undo rules rather than inventing delivery or automatic-recreation proof.
Relative reminders continue following task
due semantics; a date-only/no-due proposal cannot silently retain an invalid
relative reminder or remove it. Tell the user to explicitly clear or replace the
relative reminders, using keep for absolute reminders if desired. Hidden-category
membership is no longer a scheduling prohibition under REQ-DOM-016.

Use current reminder capability for requested reminder writes; keep current
capability-field validation rather than invent support. Provider count limits,
UUID/temp-ID receipts, sequential failure stopping, authoritative reconciliation,
no rollback and truthful accepted/unknown/unattempted outcomes remain. Compare
locally predicted absolute instants using the existing scheduling reconciliation
allowance of at most two seconds, with strict day/type/recurrence/timezone semantics;
store actual returned values. Explicit-input no-op checks and stored precision
retain their existing exactness. Preserve valid existing local history through
the model/codec extension; cache rebuilding alone must not discard pending history.

### REQ-SCHED-016 — Confirm reminder removal caused by replacement

Before any remote writes, identify retained reminders using `keep` and locally
established matches under REQ-SCHED-015. Existing reminders not so retained are
proposed removals, including when a supplied expression might later normalize to
an equivalent schedule. If replacement proposes any removal, show the existing
schedules to remove and the requested additions, then request one confirmation,
default cancel. Show unresolved expressions as entered and explicitly identify
them as awaiting Todoist resolution; do not invent a resolved timestamp or require
provider parsing before this preview. A provider-ID change alone does not make an
otherwise retained reminder a removal, but equivalent provider-parsed wording
does not retrospectively guarantee that a confirmed replacement kept its ID.
A retained first firing instant does not prove recurrence/timezone preservation.
Perform all locally decidable validation and this confirmation before changing
task attention or any reminder. Do not first reschedule the task and then ask.

For each removed relative reminder, suggest the shell-usable `--reminder OFFSET`
needed to retain it; `--reminder keep` can retain the whole relative type. For
removed absolute reminders, suggest `--reminder-at keep` to preserve all existing
absolute schedules exactly. A representable one-off may additionally have a
correctly quoted explicit-date hint, but a timestamp must not masquerade as an
equivalent recurring/floating schedule. Use the exact fragments in REQ-OUT-022.

Use REQ-CLI-032's shared prompt and terminal rules. Decline, blank input or EOF
cancels with status 1 and no remote writes. Noninteractive removal replacement
prints the same useful preview/hints without prompting and fails unchanged with
status 1. There is no new `--yes` bypass. A non-removing addition/preservation
requires no deletion confirmation. `--reminder clear` and the existing explicit
all-scheduling clear remain direct, as agreed. No removal prompt is added to
ordinary task deletion/completion beyond those workflows' existing requirements.

### REQ-CLI-037 — Absolute reminder option surfaces and discoverability

Where scheduling or task/step creation accepts `--reminder`, also accept
`--reminder-at` as one adjacent scalar shell argument or its equivalent equals
form. Both repeat, mix and retain argument order during parsing. Creation applies
its options to the same new objects as before; inline-step scheduling exclusions
and grouping boundaries remain unchanged. Neither option is a text-group marker.
Keep existing relative grammar and the reserved keep/clear rules in REQ-SCHED-015.

Extend the applicable noun-action aliases with
`todo task --reminder-at VALUE SELECTOR` and
`todo step --reminder-at VALUE PARENT_SELECTOR STEP_SELECTOR`, using the existing
adjacent-value, selector and canonical-workflow conventions. Equivalent equals
forms and repeated reminder options follow the canonical scheduling behavior.
Do not silently add reminder options to unrelated commands such as `unhide`.

Help teaches offsets before task due versus independent absolute schedules,
undated-task eligibility, recurrence/exact-time rules, whole-set replacement,
the removal preview including unresolved expressions, the limited identity
guarantee and type-specific keep examples, direct clear and noninteractive
refusal. Keep creation, schedule aliases and task/step noun forms consistent.
Malformed/missing scalar values and incompatible keep/clear combinations follow
existing usage-status rules, without absorbing selectors into a date expression.

### REQ-DOM-015 — Imported duplicate task titles and action-local collisions

Accept imported open task titles duplicated within a category and imported open
step titles duplicated within an immediate parent. Preserve every stable object;
never merge or rename them automatically. Use the existing substring matching,
deterministic ambiguity chooser, cancellation and noninteractive refusal. Visually
identical candidates can remain hard to distinguish; no ID selector or new
automation-safe targeting guarantee is added.

CLI creation, rename, move and reopen must still reject newly introduced active
sibling collisions under the existing Unicode/case-insensitive comparison,
including within a batch and for restored ancestors. An unchanged imported
collision is not a reason to reject an unrelated operation, a new uniquely named
sibling, or an action that resolves a collision. Completed titles remain outside
the collision check. Preserve complete no-op rejection, hierarchy and lifecycle
rules. Category/project-name uniqueness is unchanged.

### REQ-DOM-016 — Hidden categories filter views without invalidating scheduling

`hidden_from_now` remains the exact case-sensitive category-name filter. Its
members may have task due dates, recurrence, relative/absolute reminders and
interpretable or incomplete waiting metadata under the other successor rules.
Such scheduling no longer invalidates a snapshot or blocks a category move,
creation, scheduling or reconciliation solely because the category is hidden.
Moves preserve scheduling; an external category rename applies the filter without
repairing data or causing this former scheduled-category violation.

Normal `now` excludes category-hidden work even if overdue. `now --all`, `someday`,
inspection and search retain their documented populations and can show those
items. Reminder notifications can still fire. A due date does not override the
category filter. Existing waiting/report-Hidden snapshots still exclude
category-hidden work; other report interval rules are unchanged. Removing the
category filter does not remove the item's independent waiting label or reason.
No automatic move, scheduling clear or unhide is implied.

### REQ-DOM-017 — Read incomplete waiting conventions without guessing repairs

The stored `waiting` label determines an own policy only when a valid attention
value supplies its visibility day. A label with no attention is tolerated as an
inactive own policy and diagnosed; it does not by itself suppress an item or
create an independent waiting/report-Hidden entry. A valid ancestor policy may
still suppress that item. A malformed supplied provider due value is still an
error, not a missing-date fallback. A valid label-plus-attention policy keeps its
existing day-based behavior even when its reason text is malformed.

Only an unambiguous canonical trailing reason block associated with an
interpretable own policy becomes a hiding reason. Malformed, duplicate, incomplete,
non-trailing, empty or orphaned marker blocks remain ordinary readable description
text. Preserve all their content and diagnose the convention issue; do not drop
it, invent a reason or rewrite remote data during reads. Never accidentally parse
an arbitrary fragment as authority to hide the item.

New CLI hiding requests still require the existing future-day and canonical
reason input rules. When a mutation needs to rewrite a malformed description
encoding and cannot determine which text to replace without guessing, fail that
rewrite before remote writes with an identifying diagnostic. Unrelated mutations
remain available. Explicit removal of the waiting label must preserve unparsed
literal text; a normal valid associated reason retains existing unhide/clear
removal semantics. Do not add repair commands or silently clean descriptions.

Keep whole-subtree suppression for valid own policies and the existing check that
an open descendant's attention day cannot precede an interpretable own-hidden
ancestor's day. Same-day times remain compatible, undated descendants can inherit
suppression, and expired valid labels stay visible under existing rules. Missing
dates and literal malformed reasons do not authorize a new inheritance model.

### REQ-DOM-018 — Tolerant incoming text with safe terminal representations

On inbound multiline descriptions/comments, normalize CRLF to LF. After permitted
line-ending and control validation, descriptions containing only ordinary spaces,
LF and tabs represent no readable description; comments with no readable text
retain identity under REQ-COMMENT-009. Preserve nonblank text and internal line
boundaries. Do not use trimming/truthiness to erase a forbidden control or accept
a wrong field type. Bare CR, ESC, NUL and other previously forbidden C0/C1 controls
remain errors. Reads make no remote writes because of this normalization.

Incoming task/step titles may contain LF or tab (and CRLF as a line break). Preserve
the title data internally and render line breaks and tabs as the visible literal
escapes `\n` and `\t` wherever a title is printed, keeping scalar rows/headers on
one terminal line. Bare CR and other forbidden controls remain invalid. Escape
literal backslashes in these scalar title representations as `\\` so display
escapes are distinguishable. This is display encoding, not a new selector escape
grammar; matching, identity, ordering and collision comparison use the actual
title under their existing normalization. Do not silently rename imported items.

CLI creation/rename still require single-line titles. Explicit CLI comments,
descriptions and reasons retain their nonempty/control rules and creation-group
semantics. Category-name rules are unchanged. Editor rendering/comparison uses
the permitted LF representation while an unchanged normalized buffer preserves
remote text without a write. Intentional edits use the ordinary normalized text
write contract, rather than attempting a remote whitespace repair.

### REQ-OUT-022 — Output fragments for retained blanks and both reminder types

All earlier exact template framing stays intact except the following scoped
substitutions/extensions. Every affected view and receipt uses REQ-DOM-018's safe
scalar title representation. A blank comment's body is exactly `[no text]` in
TPL-COMMENTS, owner/descendant TPL-DETAIL comments and eligible TPL-REPORT comment
entries. Timestamps, owner grouping, counts and event ordering retain their
existing meaning. The comment editor uses an empty body instead of this marker.

Relative shared timing remains `at due` for zero and `OFFSET before` otherwise,
sorted by offset ascending. Absolute shared timing is
`at YYYY-MM-DD HH:MM:SS IANA_TIMEZONE`, displaying the next authoritative firing
instant in the account timezone. A recurring absolute reminder appends ` ↻ RULE`
with its unchanged authoritative rule wording, or ` ↻ recurring` if wording is
unknown. Never infer task recurrence from reminder recurrence. Render absolute
reminders after relative ones, ordered by next firing instant then stable ID;
keep all distinct supported schedules. No reminder countdown becomes task due.

The existing ` reminders:` suffix contains the complete relative/absolute list,
comma-separated. For an undated NO DATE queue row, show a reminder-only block
`reminders:...` after the title, without inventing `due:none`. Detail can show
`Due: none reminders:...`; ambiguity keeps its existing explicit `due:none` and
adds the suffix. A reminder-only block is blue when color is enabled and never
overdue red based on reminder time. Present task due values retain the existing
due-based color for their complete block. For example:

```text
  P2 Read proposal  reminders:at 2026-10-30 09:00:00 Europe/Prague
Due: none reminders:at 2026-10-30 09:00:00 Europe/Prague
```

Scalar changed/retained reminder values in receipts keep relative `0m`/OFFSET
notation and use the same `at ...` absolute representation. A changed set uses
the ordinary `  Reminders: PREVIOUS -> RESULT` shape, with `none` for an empty
set. Successful creation requesting reminders shows their actual reconciled set
on a `  Reminders: RESULT` line, including creation with absolute reminders but
no task due. No accepted receipt precedes acceptance; unknown or invalid normalized
results retain partial-failure presentation. Other views keep their existing
formats; this adds no new reminder summary to search or report framing.

An inactive own waiting label without attention displays
`Waiting: inactive (no attention date)` in detail unless inherited hiding must
also be described; in that case retain the inherited context as well. Convention
diagnostics go to stderr, identifying the managed owner without dumping raw URLs
or unrelated data. Literal malformed/orphaned blocks remain visible Description
content, not an invented Reason field. The existing valid Waiting/Reason shapes
are unchanged. Use `inactive` as the old Hiding value in a receipt that actually
changes an incomplete stored policy, for example `  Hiding: inactive -> off` when
unhiding it or `  Hiding: inactive -> on` when valid scheduling activates it.
Removing a present waiting label is a real mutation even if it did not suppress
the item; do not reject that as a no-op merely because visibility was unchanged.

The replacement-removal preview goes to stdout under the selected owner's normal
task/step context. Its exact fragments are:

```text
Reminder replacement for: Team meeting
Remove:
  - 30m before
  - at 2026-10-30 09:00:00 Europe/Prague
Add:
  - at 2026-11-02 10:00:00 Europe/Prague
To keep existing reminders, include:
  --reminder 30m
  --reminder-at keep
Replace reminders and remove the listed existing reminders? [y/N]:
```

Substitute the owner title/path and known schedules. An unresolved absolute
addition instead uses this exact single-line fragment, with the supplied
expression preserved using safe scalar text display:

```text
  - expression (Todoist): every Monday at 9am
```

This denotes input to be resolved by Todoist after confirmation, not an
authoritative date or claim of equivalence with an existing reminder. After
acceptance, receipts show the actual reconciled schedule using the ordinary
absolute representation above. Use the existing readable
relative unit normalization (`30m before` above), indentation and newline rules.
An empty Add section contains `  None.`; omit duplicate keep hints and never show
non-equivalent timestamp-only retention for an imported recurring/floating value.
Kept reminders are neither Remove nor Add. The noninteractive form omits the final
prompt and reports the unavailable confirmation on stderr; cancellation follows
REQ-SCHED-016. This preview is a proposed change, never an accepted receipt.

### REQ-VERIFY-027 — Distinguishing evidence for the tolerance amendment

Use the existing offline/isolation, exact-template and copied-installation
contract. Establish the following consequential distinctions with proportional
representative cases; Planning chooses layers, fixture organization, commands
and decomposition. Do not multiply each distinction across every owner/depth/
consumer when a shared path and suitable composed evidence establish it.

- A text comment with website-preview or actual-file metadata and the same
  comment with metadata absent map identically; metadata-only differences do not
  create a consumed-record conflict. Text updates retain comment ID and omit
  attachment fields. Do not claim a live attachment-preservation test.
- Empty/default/whitespace-only incoming comments survive refresh/reload and an
  unchanged editor buffer, display `[no text]`, and contribute qualifying report
  activity. Explicit empty creation and emptying a nonblank existing body fail;
  the unused starter still succeeds. Deletion uses identity, not blankness.
- The unchanged official due example without timezone succeeds, supplied invalid
  timezone and malformed required dates fail, unused annotation shapes do not
  matter, and retained non-English recurrence language reaches the request intact.
- Relative zero and absolute one-off/recurring schedules survive import, codec
  reload and unrelated operations. Absolute reminders on undated/date-only tasks
  leave due/urgency unchanged; relative eligibility stays strict. Distinguish
  fixed/floating schedules, local DST refusal, task rescheduling and actual
  provider-normalized outcomes. Request evidence follows the pinned contract.
- Mixed whole-set replacement, keep and both clear forms are truthful. Removal
  replacement shows correct hints and prompts before all remote writes; cancel
  and noninteractive refusal write nothing. Non-removing additions, kept schedules
  and explicit clears do not acquire that confirmation. Kept recurrence metadata
  and IDs survive instead of being reconstructed from a displayed timestamp.
- An unresolved replacement previews the supplied expression and all existing
  reminders not retained by `keep` or local matches before any remote writes.
  Cancellation/noninteractive refusal leaves them unchanged without submitting
  the expression. On confirmation, Todoist resolves it and receipts show actual
  reconciled values. An equivalent normalized result may have a new reminder ID;
  no local recurrence parser or provider deduplication is assumed. Locally proven
  matches and `keep` still preserve IDs/metadata and need no removal confirmation.
- Demonstrably unrelated/deleted/out-of-window data cannot fail on unused text;
  unknown scope, relevant invalid required fields and incomplete pagination still
  fail. Preserve current ownership/privacy, complete-report and unchanged-cursor
  protections and current capability/event-ID/cursor checks.
- Imported duplicate task/step titles survive, with ordinary ambiguity handling;
  CLI new collisions still fail while resolving/unrelated changes succeed.
  Category uniqueness remains. Hidden-category scheduling survives moves and
  rename/filter changes; normal `now` still excludes it even when overdue.
- Missing-date waiting labels and literal malformed/orphaned reason text survive
  without guessed hiding or repair. Valid reasonless policies still hide, unsafe
  reason rewrites fail locally, and the earlier-child/hidden-ancestor restriction
  remains. CRLF/blank text and escaped title line breaks/tabs stay safe across
  relevant output/editor paths; forbidden controls still fail.

Provider-shaped fixtures must include a few independently sourced minimal examples
and permitted omissions, rather than a shared factory that always supplies the
parser's assumed fields. Preserve meaningful negative cases and prior accepted
behavior; a fixture count, full schema validator or live-account gate is not an
acceptance requirement.

### OUT-FEATURE-002 — Scoped coexistence limits and deferred compatibility

Attachment download/upload/preview models, location reminders, per-reminder public
ID selectors, notification-service or urgent-reminder configuration, a new reminder
recurrence engine, reminder-driven urgency, automatic metadata repair and new
confirmation bypass flags are excluded. Existing provider scheduling/recipient/
urgent metadata needed to preserve a retained reminder must not be discarded just
because no CLI setting edits it. Retention does not add new collaborator support.

Missing-capability tolerance, an unknown-capability model, unrecognized event-ID
types and pagination cursor formats outside the retained documented contract are
deferred. Keep current required capability/ID/cursor validation, endpoint terminal
rules and completeness checks; never invent support or silently drop history.
The extension accepts documented supported omissions, not guessed future schemas.
Category-name uniqueness/control rules and the ancestor hiding-date restriction
are retained. No live-account access, release smoke gate or production changes
are part of this Design pass.

## Capabilities, increments and remaining evidence

These are product capabilities and suggested slices, not implementation tasks:
(1) tolerant text-comment/current/report ingestion with existing safety checks;
(2) reminders from CLI through provider requests, persistence, display and
confirmation; (3) imported-data coexistence through duplicates, filtering and
waiting/text interpretation. Planning may combine or reorder them. Establish a
thin reminder workflow across boundaries before substantial dependent work, rather
than deferring the first composed evidence until every layer is finished.

The pinned source supports the necessary operations but contains contradictory
Sync reminder prose/examples and an open-ended reminder due object. Planning must
resolve consumed request/response details, recurrence/timezone field preservation,
local matching within REQ-SCHED-015's identity boundary and provider-normalization
proof from retained evidence, and
arrange a bounded investigation if needed. Do not turn a fake's invented shape
into provider proof. A contradiction affecting promised behavior returns to Design.
Live attachment preservation and actual reminder delivery/advancement were not
tested and are not certified. Controlled evidence establishes application contract
handling only. Existing open-questions.md investigations and earlier accepted
limitations remain; no product decision is silently delegated to implementation.
