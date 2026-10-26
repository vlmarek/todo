# Explicit first-release exclusions

Status: **Accepted**

todo-3 specification, revision 2. See [README](README.md).

### OUT-PLAN-001 — No plan-name capability policy

Plan-name whitelists, plan-to-limit tables, paid/free inference, branded plan
labels, and separate plan-name discovery are excluded. Capabilities come from the
current resource in REQ-SYNC-021. Disposable incompatible cache data may be
replaced by explicit refresh under REQ-CACHE-008; unreported history,
binding, credentials and report cursor are preserved.

### OUT-DATA-001 — No deleted-object recovery

The product excludes undelete, deleted-object snapshots, recreated equivalents,
and recovery of deleted task, step, comment, report, or search data.

### OUT-PLAT-001 — No Windows support

Windows installation, paths, locking, permissions, terminals, signals, and runtime
behavior are unsupported and untested.

### OUT-PLAT-002 — No additional platform or runtime guarantee

The product excludes guaranteed or tested behavior on macOS, ARM, PyPy, alternate
Python implementations, Python versions other than the required 3.11 baseline, and
future Python releases.

### OUT-I18N-001 — No interface localization

Translated help/messages, locale selection, message catalogs, and locale-specific
input or date parsing are excluded. User-controlled task text remains Unicode.

### OUT-OUTPUT-001 — No machine-readable output

JSON, stable machine schemas, scripting output, and a structured warning/error API
are excluded; output is the documented human terminal interface.

### OUT-OUTPUT-005 — Presentation scope

The supported output surfaces are the specified urgency queue, compact task/step
detail, owner comments, waiting snapshot, categorized report, search and someday
views, including shared ambiguity timing. Opt-in external paging applies to the
read-only result views listed in REQ-OUT-018, with final reports always direct.
Default pager selection, app-owned navigation, top-N filtering, responsive
application reflow, sticky headers, terminal-width layout, background refresh
and a new priority/deadline/hide-until field are excluded. Use the exact current templates
rather than infer a wider redesign or uniform presentation across every view.

### OUT-SELECT-001 — No automation-safe identity selector

Public Todoist-ID selectors, guaranteed exact-title selection, and other
automation-safe targeting are excluded. Human substring matching and ambiguity
handling remain authoritative.

### OUT-AUTH-001 — No OAuth or multiple profiles

OAuth, token refresh/revocation flows, third-party app authentication, multiple
stored profiles, and implicit account switching are excluded.

### OUT-COLLAB-001 — No shared or team workflow

Shared roots, collaborators, assignments, team workspaces, permissions, attribution,
and multi-user conflict behavior are excluded.

### OUT-SEARCH-001 — No permanent completed-history archive or complete historical search

Complete account-history indexing, automatic historical backfill, guaranteed
completed-search coverage and `search --since` are excluded. Retention exists to
protect unreported work under REQ-CACHE-006. Successful final reporting permits
cleanup; already-reported completed objects need not remain locally inspectable or
searchable. Current open data is unaffected. Cache deletion/rebuilding, age or
storage quota alone does not discard needed unreported history. Evidence-based
deletion/scope cleanup and deliberate full-directory fresh start remain permitted.
No separate pruning command, time-based expiry or quota system is introduced.

### OUT-BACKEND-001 — No Todoist-free backend

A local authoritative store, alternate backend, backend plug-in system, and
Todoist-free mutation, recurrence, reporting, synchronization, or reminders are
excluded.

### OUT-OPS-001 — No automatic report scheduling or delivery

Timers, cron installation, background services, email/chat delivery, and automatic
report execution are excluded.

### OUT-OPS-003 — No automatic backup, repair, rollback, or transaction recovery

Backup/restore commands, repair commands, automatic rollback, transaction journals,
and guessed crash recovery are excluded. Only the documented manual procedure and
explicit initialization/cursor workflows and deliberate manual fresh start apply.

The explicit local --clear-cache/--refresh recovery in REQ-CLI-029 is permitted;
it is not a general repair, backup, rollback or transaction-recovery facility.
The saved cache sync timestamp does not authorize a mutation journal or automatic replay.

### OUT-FEATURE-001 — No full Todoist parity or unsupported legacy commands

Unspecified Todoist mutations/features and legacy `check`, `show`, `resume`, or
`ask` commands are excluded.

### OUT-TIME-001 — No semantic date classification or expanded calendar

Classifying a date as deadline/meeting/follow-up, holiday calendars, localized date
grammar, and local parsing beyond the Accepted grammar are excluded.

### OUT-PACKAGE-001 — No package or installer system

`uv`, pipx, distributable Python packages, wheels, zipapps, native compilation,
installer programs, and generated entry-point wrappers are excluded.

### OUT-SEC-001 — No stronger local-adversary protection

Encryption at rest, keyring storage, root-adversary protection, compromised-user
protection, malicious-kernel/filesystem defense, and sandboxing the application are
excluded.

### OUT-PRIVACY-001 — No unrelated Todoist data retention or display

Persisting, displaying, logging, indexing, or exposing data outside the bound
managed root is excluded, except minimal transient scope validation before discard
and the transient first-use project/category selection display expressly allowed
by REQ-SEC-007.

### OUT-HISTORY-001 — No full-history deletion preview

Fetching arbitrary completed descendant history, guaranteeing a complete historical
cascade preview, and backfilling older descendants before parent deletion are
excluded.

### Inspection coverage scope

Ordinary task/step inspection includes all current open descendants and known
completed descendants retained under REQ-CACHE-006, with the TPL-DETAIL coverage
disclosure. Reconstruction of every surviving old completed descendant on first
installation, or of completions never retrieved, is not guaranteed. This limit
does not permit dropping needed unreported observations during refresh or cache
clearing. Successful final reporting permits cleanup under REQ-CACHE-006.

### OUT-ARCHIVE-001 — No unconditional archive reconstruction or childlessness proof

Successful reconstruction of arbitrary old archived report owners and their parent
metadata is not guaranteed. Unresolved required metadata must cause the explicit
failure in REQ-REPORT-011; silent omission and automatic cursor skipping remain
prohibited. Repeated reports for the same interval may therefore remain blocked.

Exhaustive archive backfill and proof that no surviving archived children exist
are not required for moves. REQ-MUT-004 checks the complete known resulting
subtree against depth 4 and permits otherwise valid moves with children. Missing
archived descendants alone do not prove a move invalid. Later discovery triggers
invalid-state rules only for a real violation, such as depth beyond 4; valid
nested descendants remain supported. This does not exclude required interval history,
pagination, known-owner completion comments, or supported ordinary move validation.

### OUT-TEST-001 — No automated live Todoist tests

Automated use of real Todoist credentials/accounts or uncontrolled external network
services is excluded. The real-account smoke is manual only.

### OUT-NFR-001 — No performance or capacity guarantee

Latency targets, throughput, task-count limits, memory/CPU bounds, benchmarks, load
tests, stress tests, and scalability guarantees are excluded.

### OUT-NFR-002 — No availability or disaster-recovery guarantee

Availability targets, SLA, uptime, redundancy, failover, disaster recovery, and
service continuity guarantees are excluded.

### OUT-NFR-003 — No power-loss or hardware durability guarantee

Durability across power loss, kernel/storage failure, filesystem corruption, or
hardware failure beyond atomic ordinary-process replacement is excluded.

### OUT-NFR-004 — No additional terminal/accessibility guarantee

Beyond opt-in external paging in REQ-OUT-018, terminal-width layouts, application
reflow, terminal-size optimization, and screen-reader guarantees beyond untruncated
color-independent text are excluded. Automatic default pager selection, pager
installation/bundling, and an application-owned scrolling or less-like navigation
UI are excluded. The configured external command owns fit handling and navigation;
final reports and interactive decision flows are excluded from pager routing.

### OUT-CONC-001 — No waiting lock or parallel local mutations

Waiting for a busy local lock, mutation queues, lock timeouts, and parallel local
state-changing operations are excluded; synchronized/mutating operations fail fast.

### OUT-SIGNAL-001 — No rollback after interruption

Compensating deletion, reopen, reclose, or other rollback of a Todoist mutation
accepted before SIGINT is excluded.

### OUT-REPORT-001 — No atomic cross-endpoint snapshot or event-time ledger

An atomic Todoist snapshot across endpoints, a second comparison sync, immutable
event-time names/categories/scope, and a local audit ledger are excluded.


### OUT-LOGGING-001 — No persistent logs or telemetry

Application diagnostic log files, analytics, usage telemetry, crash uploads, and
remote observability are excluded.

### OUT-PROVISION-002 — No implicit structural defaults or general configurator

Implicit root/category choices, default waiting dates, and ordinary-command
structural provisioning are excluded. The explicit initial terminal wizard in
REQ-INIT-003 is permitted; its visible suggestions require user confirmation.
A general configuration editor, populated-config rewrite/reset wizard, setup by
non-interactive flags, and automatic repair of unrelated local or Todoist state
remain excluded.

### OUT-BUNDLE-001 — No generated single-file runtime bundle

A generated single-file executable, module flattener, source bundler, and any
guarantee that the multi-file runtime can later be combined automatically without
behavioral or verification changes are excluded.

### OUT-USABILITY-001 — Command and scheduling limits

No independent hide-until date, second attention/deadline, background hiding timer,
new schedule --clear aliases, command-typo correction, local recurrence translator,
new recurrence-off switch, missed-occurrence backlog or general repair mechanism
is included. Unknown top-level words use implicit lookup and report the actual
searched selector. Boolean --hide does not consume or guess a reason; all
remaining positional input follows the documented grammar.

The shared prompt adds no --yes bypass to commands without one. Task/step alias
parity adds no otherwise unsupported operation or creation-time step priority
option. Step nesting is supported only through depth 4 under REQ-DOM-009; no
unlimited-depth guarantee, path-selector grammar or nested-batch creation syntax
is introduced. Report boundaries, editor receipts, empty-search success,
explicit-mutation no-op failure, offline reads and synchronized writes keep their
specified distinct semantics.

### OUT-DIAG-001 — No comprehensive doctor or in-application account switching

The `doctor` command, collection of every independently detectable problem and
`init --rebind` account-switching workflow are excluded. Ordinary commands still
validate applicable state and give useful errors. The manual fresh start in
REQ-INIT-002 is the supported deliberate local account reset. `REQ-DIAG-002` is
retired and is not reassigned to another behavior.
