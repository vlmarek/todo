# Architecture and local runtime

Status: **Accepted**

todo-3 specification, revision 2. See [README](README.md).

### REQ-ARCH-002 — Logical responsibility boundaries and offline domain rules

The implementation must preserve these logical responsibilities through explicit
module and component boundaries where they improve ownership and testability:

```text
CLI parsing and presentation
        ↓
Application command workflows
        ↓
Domain rules and validation
        ↓
Todoist API adapter       Local persistence
```

CLI responsibility covers grammar, aliases, selectors, dates, reminders, prompts,
help, streams, and formatting. Workflow responsibility coordinates loading,
synchronization, selection, validation, ordered remote operations, reconciliation,
local replacement, and structured outcomes. Domain responsibility owns identity,
visibility, urgency, hierarchy, lifecycle, and report rules without depending on
network access. Adapter responsibility maps Todoist API v1, retrieves complete
state/history, and reports authoritative outcomes without leaking raw response
shapes into the public interface. Persistence distinguishes authoritative local
state, unreported history, and disposable current cache.

Shared behavior must have one direct implementation path where practical; aliases
must not fork semantics. Domain computation and formatting must be testable from
supplied values offline. Reconstructable JSON layout, helper boundaries, class or
function names, and internal data structures remain implementation choices and
must not create observable behavior beyond the Accepted requirements.
Represent the recursive hierarchy through stable item identities and parent
relationships in a shared model; task and step are current roles, not separate
implementations per depth. Storage layout and Python types remain delegated.
Domain traversal must validate cycles and resulting depths without relying on
provider response order or silently omitting nested nodes.
The common question/input function required by REQ-CLI-032 is an explicit shared
path: all prompt consumers must delegate to it rather than duplicate buffering,
terminal and cancellation handling. Preserve hidden credential input. The function
name, supporting reader callbacks and internal placement are delegated.

### REQ-CACHE-008 — Disposable current cache and last-successful-snapshot behavior

`~/.todo/cache.json` is a schema-versioned, reconstructable snapshot of current
managed state. Cache-backed reads make no Todoist request unless `--refresh` is
supplied. A missing, unreadable, malformed, identity-mismatched or incompatible
cache fails clearly, produces no partial normal view and suggests the same command
with `--refresh`. It is never interpreted as an empty account.

Build and validate a complete replacement before publishing it atomically. An
ordinary failed synchronization or failed file replacement preserves the previous
complete cache. Do not automatically delete it on input errors, rejection, network
failure, reconciliation failure or interruption. Explicit `--clear-cache` under
REQ-CLI-029 may delete only the disposable cache, never unreported history.

Report a synchronization or post-mutation reconciliation failure in the command
where it occurs. A later offline read may use the last successfully saved,
structurally valid, binding-compatible snapshot even when it is older than remote
state. No persisted clean/outdated/blocked state, generation-specific remote
invalidity block, or special stale-cache recovery mode is required. This accepts
that, for example, a completed task may still appear open in an older snapshot.
The ordinary last-successful-sync timestamp remains available; a normal view using
a snapshot older than 24 elapsed hours emits the existing age warning. Internal
loading for refresh does not emit advice about the snapshot being replaced.

Every synchronized workflow still validates its newly retrieved state and fails
without mutation or synchronized normal output when that state is invalid or
incomplete. Local cache validation, binding identity and file safety remain
mandatory. Using an old offline snapshot is not evidence that a remote operation
failed, succeeded, or is safe to repeat. The originating operation must retain its
accepted/failed/unknown/unattempted classification under REQ-CLI-032.

Cache rebuilding and explicit clearing preserve the separate unreported history
under REQ-CACHE-006. On successful refresh, compatible retained history is available
again without requiring the previous cache. Consistent account/root/publication
association is a local-file correctness duty, not a persistent remote-validity mode.

### REQ-CACHE-006 — Separate unreported history and report-bounded retention

Keep historical observations needed for work not yet covered by a successful final
report in protected local storage separate from the disposable current cache.
This includes known managed completed tasks and steps, required known ancestor
context, completion/occurrence evidence and retrieved surviving own comments needed
to compose that report. Associate it with the bound account and root. Filename,
schema and internal representation are delegated.

Unreported history survives process restart, ordinary full/incremental refresh,
current-cache replacement, rebuilding, explicit `--clear-cache`, and failed sync.
Do not drop it merely because active Sync omits archived objects. For a known item
completed through Todoist web/mobile, consume supported completion/lifecycle
evidence and preserve the known identity, ancestry, fields and own comments needed
for reporting. Active absence alone proves neither completion nor deletion. An
unresolved required transition fails the synchronization rather than inventing a
state. Newly retrieved eligible historical data joins the same store when needed
for an unreported interval. Fetching overlapping/older provider windows does not
require rebuilding a permanent archive of already-reported records.

Use stable object IDs for object identity; recurring occurrences do not create
duplicate search rows. Current authoritative evidence wins over retained values.
Reconcile reopen, moves, comment ownership and confirmed deletion/scope departure;
deleted or out-of-scope data is removed under the current-truth/privacy rules.
Retained observations do not make archived metadata current or waive unresolved
required report-owner failures. This is not an immutable audit ledger.

Release reporting history only after `report --final` has completely written and
flushed its output and successfully saved its fixed-end cursor. Preview, explicit
preview intervals, output/retrieval/cursor failure, interruption, or simply setting
the cursor do not authorize report-history cleanup. After successful finalization,
records no longer needed for unreported activity through that boundary may be
discarded. Keep context still needed by later, unreported activity. Cleanup is
idempotent and follows cursor publication, never precedes it; a cleanup failure
may leave extra records and must not undo the already successful report or cursor.

The locally authoritative cursor determines which interval remains unreported.
An explicit forward cursor change retains its warning that work may be skipped;
later finalization need not keep data solely for activity the user deliberately
excluded. Moving the cursor backward does not restore history already released
after an earlier final report. Requests still follow complete retrieval and
unchanged-cursor-on-failure rules; no permanent local archive is promised.

Offline detail and `search --all` may combine current state with compatible retained
unreported history without HTTP or duplicate objects. Display every known retained
descendant with its actual ancestry and own comments, using the existing coverage
templates. Reported completed detail may disappear after cleanup. Do not promise
lifetime inspection/search coverage, including on first use or after reporting.

New initialization creates explicitly incomplete empty history. Repeat init for
the same binding preserves pending observations. Missing required, unreadable,
corrupt, incompatible or identity-mismatched history must not silently reset or be
overwritten by cache clearing. Report the affected local-state problem and preserve
available bytes. Apply REQ-LOCAL-002/003 and REQ-SEC-005/007. Deleting the entire
`~/.todo` directory under REQ-INIT-002 deliberately discards all pending local
history; document that consequence. No automatic history repair or separate prune
command is introduced.

### REQ-CACHE-005 — Managed-root cache and history data minimization

Before any data is serialized, the implementation must discard task, comment,
reminder, project-detail, and activity payloads unrelated to the bound managed root.
The current cache and unreported history may persist only the data appropriate
to their respective roles:

- the bound root and managed category identities/names needed for validation;
- managed-root current tasks, all recursive steps, descriptions, comments, reminders,
  due/recurrence fields, labels, timestamps, and tombstones needed for correct merge;
- known managed completed objects and context still needed for unreported work,
  their retrieved own comments and coverage metadata under REQ-CACHE-006, retained independently
  of the disposable cache;
- the sync token, successful-sync time, and minimal account/current-capability metadata
  needed for the documented offline or next-command behavior.

The sole offline timezone authority belongs in binding state under `REQ-LOCAL-005`,
not as a competing cache copy. Unrelated Todoist account data must never reach disk,
normal output, diagnostics, test fixtures, or persistent logs, apart from the
transient wizard project/category selection display expressly permitted by
REQ-SEC-007. Discovery choices do not expand cache scope.

### REQ-LOCAL-005 — Single offline timezone authority and local-state contents

Local state under `~/.todo` must have these roles:

- `config`: user policy and optional personal token;
- `binding.json`: schema version, account ID and display identity, root ID and
  last-known name, managed category IDs and last-known names, and exactly one
  `last_synced_account_timezone` value;
- `report-cursor`: one UTC RFC 3339 instant followed by an LF;
- `cache.json`: disposable state defined by `REQ-CACHE-*`, without a second
  authoritative timezone field;
- unreported history under REQ-CACHE-006, separate from `cache.json`, scoped
  by account/root; filename and layout are delegated;
- `lock`: runtime coordination only.

Stable IDs must serialize as strings. Configuration, binding, and cursor are locally
authoritative and cannot be repaired by discarding cache. Unsupported binding
schemas must fail explicitly; no source-project state migration is required.
Current-cache schema changes may rebuild through explicit refresh; doing so must
preserve separate unreported history. History is locally irreplaceable observation
data when equivalent upstream retrieval is unavailable, while Todoist remains
authoritative for remote state. It is not a mutation journal or event-time ledger.

Every successful online synchronization must use Todoist's returned timezone for
that command and atomically update the one binding value with the reconciled local
state. Offline parsing, rendering, visibility, and due buckets must use that last
successfully synchronized value. A missing, invalid, or internally conflicting
timezone authority is invalid local state, not permission to use the host timezone.

### REQ-LOCAL-002 — Fail-fast exclusive locking and final-report ordering

Initialization, refresh, reports, cursor changes, comment editing,
and every mutation must acquire one exclusive process lock before reading state
whose freshness affects the operation. Acquisition must be fail-fast: if another
process holds it, exit nonzero immediately and identify the competing operation when
reliably available. The CLI must not wait for a timeout or queue local mutations.

Offline cache/history reads remain lock-free using consistent published state;
history updates use the same exclusive lock. Two final reports must each acquire the
lock before loading the cursor; the later process must observe the first process's
advanced cursor and cannot reuse a pre-lock interval. Lock release must occur on
normal completion, handled failure, and handled interruption.

### REQ-LOCAL-003 — Atomic replacement and process-interruption durability boundary

Every authoritative local, unreported-history, and cache replacement must use a
restrictive same-directory temporary file, validate complete candidate content, and atomically
replace the destination. A process interruption before replacement must preserve
the prior complete destination; a failed replacement must not leave a partial file.
Temporary files must be cleaned on handled exit and ignored as authoritative state.

No `fsync`, power-loss, storage-device, filesystem-corruption, or hardware durability
guarantee is made. Atomicity here means resistance to concurrent observation and
ordinary process interruption on the verified platform, not survival of a machine
or storage failure.

### REQ-LOCAL-006 — SIGINT stop, outcome classification, cleanup and exit 130

On SIGINT, stop initiating further Todoist mutations as soon as control returns
from any in-flight request. Do not roll back accepted remote changes. Report
accepted operations, any in-flight mutation whose outcome is unknown, and later
unattempted operations. Preserve known unreported observations under REQ-CACHE-006.

Without completed reconciliation/publication, retain the previous complete cache
under REQ-CACHE-008; a later offline view may still show it. Never replay a mutation
to recover local state or delete the cache as interruption cleanup unless explicit
`--clear-cache` authorized that deletion.

Clean unpublished temporary files, restore terminal state where applicable, release
the lock and exit 130. Leave the report cursor unchanged unless final output and
cursor replacement had both completed. Never clean reporting history before that
successful finalization boundary. Read-only interruption likewise exits 130 and
must not present an incomplete result as successful.

### REQ-PLAT-001 — Multi-file standard-library Python 3.11 runtime

The complete runtime deliverable must contain one executable repository-root
launcher named `todo`, beginning exactly with:

```python
#!/usr/bin/env python3
```

The launcher and its sibling runtime modules must run on Python 3.11 using only the
Python standard library. Their exact module decomposition is an implementation
choice constrained by `REQ-ARCH-002`. Installation is copying the unchanged
launcher and complete unchanged runtime module tree into one directory on `PATH`,
retaining the launcher's executable bit and relative module layout. There must be
no runtime package installation, generated wrapper, or dependency on `uv`, pip,
pipx, a wheel, zipapp, native compilation, or an installer program.

Tests and verification scripts may exist in the repository but are not runtime
dependencies of the copied runtime tree.

### REQ-PLAT-002 — Linux/amd64 CPython 3.11 verification baseline

Required implementation and verification must run on Linux/amd64 with CPython
3.11 in the pinned runner image. The program must not intentionally depend on
undocumented CPython internals, but no tested or guaranteed behavior is required
for macOS, Windows, ARM, PyPy, alternate runtimes, or future Python releases.

### REQ-BUILD-002 — Fresh Python implementation and direct Codex Docker execution

Build a fresh implementation from this specification in this workspace. The
runtime language and installation contract are REQ-PLAT-001, REQ-PLAT-002. The source
project supplies design provenance, not an application codebase to continue.
No previous implementation, test suite, runtime state, accepted assignment, or
local data format must be copied, preserved, ported, or migrated for this project.
Preserve the product behavior defined by the current requirements, including
all documented aliases and the explicit local-state safety/recovery rules.

For eventual implementation and verification work, use the runner at
`/home/neuron/Documents/ai-automated-runner` with Docker execution invoking the
Codex binary directly inside the container. An intermediary agent runtime is not
the selected execution path. Docker is a build/verification environment, not a
runtime dependency of the installed `todo` CLI. Planning owns the runner
configuration, image pin, executable/authentication setup, resource settings,
and readiness checks. This design session must not configure or start execution.

### REQ-PLAT-003 — Optional external pager runtime boundary

This extends REQ-PLAT-001 without changing its standard-library Python installation
contract.

REQ-OUT-018 explicitly permits invoking an optional external pager selected by
`[main] pager`. No pager is required or selected by default. The operator provides
the executable, for example GNU less for `pager = less -FR`; it is not bundled or
auto-installed. Without configuration, or on launch/failure fallback, direct output
remains available. The application must not implement its own navigation UI.
This boundary adds no Python package dependency or change to copying the runtime.
