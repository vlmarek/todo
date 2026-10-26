# Verification requirements

Status: **Accepted**

todo-3 specification, revision 2. See [README](README.md).

### REQ-VERIFY-001 — Standard-library routine scripts/check

Provide executable `scripts/check`, using Bash and the pinned Python 3.11 standard
library only. It checks syntax of the launcher/runtime modules, the required
regular executable launcher/shebang and imports, and runs the complete current
offline unittest suite with failure propagation and no silent required skips.
It needs no pip, uv, pytest, Ruff, credentials or external service and leaves no
bytecode, coverage, cache or generated source in the repository. Planning chooses
suite organization and focused interim commands; this is not a prescribed test
count, module layout or repeated broad-suite loop.

### REQ-VERIFY-002 — Isolated copied-installation verification

Provide executable `scripts/verify-clean`. Record full Git status at entry; use a
temporary home and installation directory, copy the unchanged executable launcher
and complete runtime modules, exercise the copy through PATH, and verify Git status
and forbidden generated/credential state before cleanup. Establish that the copied
runtime works independently of the repository and tests. This check is required
for the completed deliverable; Planning chooses representative copied workflows
and how to compose routine/copy checks without redundant full-suite executions.
No packaging/dependency installation, source-contract edits, real ~/.todo, inherited
real token or uncontrolled network is permitted.

### REQ-VERIFY-003 — Isolated offline evidence

Automated tests use temporary homes/files, synthetic credentials and controlled
Todoist HTTP behavior. Exercise relevant requests, responses, pagination and
operation outcomes rather than a fake that simply accepts whatever the application
sends. Isolate editor, terminal, clock, pager and signal behavior when consumed.
Tests never contact a real account or uncontrolled network, read real credentials
or leave remote/local state. No additional production runtime dependency follows
from testing. Endpoint fixtures cite the retained primary source and inspection
date and are not derived solely from application expectations.

### REQ-VERIFY-004 — Behavioral coverage with Planning-owned test organization

Establish ordinary workflows and consequential failures with appropriate evidence:
setup/first work view, capture/refinement, comments/editor, scheduling/reminders,
hiding/moves, completion/reopen/deletion, search, cache recovery and reporting.
Prioritize wrong-target prevention, unreported-work retention, complete report
retrieval/output, correct cursor changes, remote outcome classification, credentials
and safe local replacement. Preserve the supported aliases and exact templates.

Planning chooses unit/domain, adapter, CLI and end-to-end test levels, representative
scenarios, fixture structure, commands and execution schedule. Use public CLI
evidence where it demonstrates important integration and user workflows; not every
rule/input spelling requires a separate full CLI workflow. Suitable focused tests
can establish shared parsing or domain behavior. There is no mandatory per-
requirement evidence ledger, contract-map file, fixed eight-workflow checklist or
separate suite for each requirement. Named TPL output remains exact; other errors
are checked for facts, stream, status and consistency under REQ-OUT-009.

The requirements below identify meaningful distinctions and risks, not an
instruction to multiply the same scenario across layers, entities and aliases.
Share evidence where it establishes the required behavior; use separate cases
where an independent failure mechanism or consequence warrants them. No load,
stress, portability, performance or live-account gate is added.

### REQ-VERIFY-007 — Current task wire mapping and initialization

Cover documented boolean checked mapping without invented is_completed, absence
of activity from Sync resources and no initialization dependency on /activities.
Valid unavailable/zero history capabilities do not prevent initialization.
Populated and new-root initialization, wizard continuation and repeat init preserve
valid IDs/content; invalid current fields or tree invariants reject provisioning
before any mutation. Use complete required current resources and documented
personal/shared/Inbox/workspace metadata.

Nullable creation time passes mapping, local serialization, inspection and
completion ordering; authoritative known-to-null remains unknown. Mixed known/
unknown siblings order correctly without invented timestamps. Missing required or
malformed timestamps still fail. No old implementation fixture or live account is
needed.

### REQ-VERIFY-019 — Optional descriptions

Documented omitted/null/empty descriptions are equivalent absence in all consumed
read paths. Preserve valid nonempty ordinary text and waiting blocks. Whitespace-
only nonempty values, wrong types, forbidden controls and excessive lengths remain
invalid. Valid populated task/step initialization and incremental clearing of an
existing description succeed without asking the user to repair legitimate data.

### REQ-VERIFY-013 — Endpoint conformance and mutation proof

Establish actual Sync form encoding, resource/field names, REST query/response
contracts and English due language. Include floating/fixed/date-only and fractional
due values, current metadata/timezone updates, ignored unknown fields, tombstones,
and ownership-first discard of unrelated unsupported data. Unsupported managed
features are accurately distinguished from malformed provider data.

Complete history/activity/comment retrieval follows each endpoint's continuation
and request interval. Distinguish terminal omitted completed cursor from malformed
required continuation. Preserve exact start/end and subsecond/window edges.
Supplied stable event IDs deduplicate; anonymous entries survive without an
elaborate identity guarantee and may duplicate in a report. Missing required report
data still fails without output/cursor advancement.

Completion disappearing from active Sync is reconciled using supported evidence,
including post-completion own comments. Plain-ok ordinary reopen reports restored
ancestors without invented result fields. Missing status, unchanged recurring state
or matching existing text cannot prove an attempted operation succeeded. Classify
accepted/rejected/unknown/unattempted and avoid unsafe replay. Reminder creation
uses its documented arguments and preserves earlier accepted work after a later
failure.

Exercise a server full replacement plus its one freshness delta, explicit cache
clearing/rebuild and preserved pending history. No guessed invalid-sync-token
classifier, unclassified-error replacement loop or credential-error fallback is
permitted. Failed synchronization retains the old cache; later offline use is
allowed without a persistent validity-state system.

### REQ-VERIFY-010 — Zero reminder offsets

Imported integer zero and CLI minute-zero aliases retain exact-time/capability,
preservation, replacement, clear, duplicate and no-op semantics. Write literal
minute_offset: 0 with relative reminder arguments. Scalar offset notation is 0m;
shared readable timing blocks use at due. Invalid zero-hour/day/week, signed,
fractional, leading-zero and wrong remote types remain rejected. Late reminder
failure retains accepted creation without rollback or duplicate replay.

### REQ-VERIFY-011 — Comment ownership, grouping and hierarchy moves

Preserve own task/step comments through sync, local reload, display/editor, search
and reporting. Completion comments belong to their selected owner after completion;
partial failure preserves accepted work and stops later operations. Resolve eligible
archived owners or fail with unchanged report cursor, without preseeded impossible
metadata or silent omissions.

Moves preserve item/comment IDs, relative subtree relationships and scheduling;
category changes, attachment and promotion survive reconciliation and reload.
Validate cycle/depth, sibling titles, hiding and category/parent conflicts before
mutation. Missing exhaustive archive proof alone is not rejection authority.

Creation grouping distinguishes real shell argument contents: joined single words,
mixed multiword splitting, trailing-space triggers, independent marker groups and
literal insertion. Aliases preserve boundaries. Batch validation occurs before
mutation; ordered failures preserve accepted work without rollback.

### REQ-VERIFY-012 — Positional move semantics

Establish first-argument source and joined destination, mixed typed destination
ambiguity without kind preference, and independent source ambiguity. Sole exactly
empty destination promotes; missing/whitespace/mixed-empty forms reject. Preserve
marker aliases, bare/empty --task promotion, category-only step refusal, identities,
no-op and whole-subtree validation. Representative shared tests may establish
common selection and operation safeguards.

### REQ-VERIFY-017 — Urgency queue and time boundaries

Establish all section boundaries and ordering, independent own-value step rows,
parent paths, counts, inclusion filters and exact TPL-NOW presentation. Distinguish
before/at/after an exact due instant, subminute direction, date-only midnight,
day +7/+8, elapsed countdown versus local calendar/DST and host-independent account
timezone. Retain recurrence wording, all reminder offsets, waiting reason context,
color-stripped equivalence and correct empty views. Cached views recompute time
without HTTP; refresh failure gives no synchronized normal queue.

### REQ-VERIFY-021 — Recurring policy and accepted-mutation failure

Own/sibling hiding in a visible category does not make that category hidden or
block valid recurring completion/undo. Configured hidden-category violations fail
preflight. Reconcile accepted occurrence advancement and unexpected server-normalized
invalidity with truthful partial outcomes. After reconciliation/publication failure,
report remote acceptance/unknown state and later failure, retain the old cache and
needed pending history, and provide read-only refresh recovery without completing
or undoing another occurrence. Later offline reads may use the saved old snapshot.

### REQ-VERIFY-005 — Manual disposable-account smoke procedure

Document an explicitly user-run smoke on a disposable personal root: setup, current
work, capture/refinement, scheduling/reminders, progress/completion/reopen, external
web/mobile changes observed after refresh, report preview/final and cursor display.
Give expected outcomes and cleanup. The runner must not execute it or automate real
credentials, destructive scenarios or deliberate partial failures. Automated failure
evidence remains isolated/offline.

### REQ-VERIFY-016 — Exact compact output and editor behavior

Keep exact named now/detail/waiting/comment/editor receipt templates and color-
stripped equality, actual due date/time plus countdown, compact timestamps and
chronological full-instant sorting. Preserve multiline Reason/Since presentation,
descriptions, nested ownership and one-line empty sections.

Editor evidence distinguishes an unchanged/removed empty starter, filling starters,
ordered additions/edits/deletions, delete-all confirmation, literal-header escaping,
malformed/foreign/duplicate blocks, concurrency, partial outcomes and cleanup. Count
receipts and body receipts retain their own contracts. Planning chooses focused
round-trip tests and representative public editor workflows.
Distinguish orphan text before the first header from removal of an interior header:
the latter joins its remaining body to the preceding block and requests deletion
of the missing existing ID, subject to ordinary validation and delete-all rules.
Do not require inferred-intent or accidental-header-loss detection.

### REQ-VERIFY-018 — Command and time consistency

Establish scalar equals/separated options, aliases and noun-action parity, literal
boundaries, duplicate/conflicting input refusal and space-sensitive creation.
Leading scalar noun-action aliases consume the adjacent date, priority, reminder,
new-name or move-destination value before their task or parent/step selectors;
multiword values remain one argument. Preserve canonical rename/move grammar and
the fixed-priority flags which already encode their value. Missing scalar values
or item operands fail before synchronization or mutation.
Cover month clamping/leap years, weekday/next-week semantics, elapsed versus
calendar arithmetic and local DST refusal. Remote floating overlap/gap interpretation
uses independent literal UTC expectations, preserves fractions/raw representation
and responds to account-timezone changes without remote mutation. Fixed instants
remain fixed. Recurrence-preserving occurrence moves and +/-2-second reconciliation
slack retain strict local-day/recurrence/timezone checks.

Keep optional reasonless hiding, parent inheritance, common prompt flush, useful
usage/selector errors and accepted comment-body receipts. Cursor setting works with
a valid prior timestamp, none or corrupted, with explicit supplied boundary,
existing confirmation and safe local-file rules, without HTTP or a cache prerequisite.
The full-directory fresh start is documented; another account cannot bypass an
existing binding by deleting config alone. Doctor and rebind are not registered
operations or advertised commands.

### REQ-VERIFY-020 — Paging, errors and simple cache retention

Default/empty pager configuration is direct; malformed values reject before HTTP.
Eligible read-only views, including short/empty views and non-final reports, use
the configured directly executed command and original-stdout color policy.
Non-interactive/dumb output, decisions/mutations/help and final reports bypass it.
Normal early quit succeeds; actual pager failure falls back completely without
refetching; SIGINT exits 130 with terminal/temporary-state cleanup. Use bounded
real-less evidence for less -FR and controlled process failures, without certifying
every pager or recreating navigation tests.

Implicit no-match is distinguished from local/sync errors; unknown hiding dates
are distinguished from missing input; accepted/unknown creation never returns
silently. Preserve old cache bytes on failed sync/replacement and report the failure
in its originating command. A later process may read the last valid saved snapshot
even after known remote change or a failed online validation. No persistent
clean/outdated/blocked metadata is required. Clearing removes only current cache;
pending history/binding/cursor remain, including when the rebuild fails.

### REQ-VERIFY-022 — Recursive work and unreported-history lifecycle

Establish valid out-of-order depth 0–4 mapping/reload and the invalid depth/cycle/
orphan/category/completed-ancestor boundaries. Representative nested scenarios
cover child creation, effective-priority copying, subtree moves/promotion, inherited
hiding, deterministic completion postorder and recurring-descendant refusal.
Preserve identities, own comments, ancestor paths and supported aliases across
views, search, reports and bounded deletion without a suite per depth or consumer.

Observe open parent A and nested step B with a comment, then externally complete B
while A stays open. Explicit provider evidence, not preseeded completed history or
active absence, establishes the transition. Refresh, process restart and explicit
cache clear/rebuild retain B/context/comment until reporting. A cold installation
without B still discloses incomplete history rather than inventing it. Confirmed
deletion/scope departure removes affected records under current-truth rules.

Preview, failed retrieval/output/flush/cursor replacement and interruption before
successful finalization preserve pending history and the old cursor. Successful
final output/cursor publication permits cleanup of covered history while preserving
context needed by newer work. Interruption/failure during cleanup can leave extra
records, never lose unreported data or undo successful finalization. Previously
reported objects may disappear from local inspection/search after cleanup.
Corrupt/missing required history is not silently reset by cache clearing. Include
appropriate local safety, account/publication association and separate-process
evidence; test fixture structure and internal APIs remain Planning choices.
