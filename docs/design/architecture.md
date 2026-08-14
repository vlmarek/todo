# Architecture

Status: Accepted

## System context

The user invokes `todo` from a shell. `todo` communicates with:

- Todoist, the authoritative task store and notification provider
- local files under `~/.todo`, used for configuration, binding, cache, cursor, and lock
- the terminal, used for output and ambiguous-match selection
- the user's phone indirectly through Todoist synchronization and reminders

Capabilities delegated to Todoist and the implications of replacing it are
catalogued in `todoist-dependencies.md`.

The supported runtime is Python 3.11 or newer on Linux and macOS. Windows is
unsupported because locking, permissions, terminal behavior, and installation
assume POSIX facilities. Distribution is a standard Python package with a
`todo` console entry point, installed through `pipx`.

## Responsibility boundaries

```text
CLI parsing and presentation
        ↓
Application command workflows
        ↓
Domain rules and validation
        ↓
Todoist adapter       Local persistence
```

### CLI parsing and presentation

Parses commands, aliases, flags, selectors, dates, and reminder offsets.
Formats normal output, previous-value feedback, warnings, and errors.

This layer owns a shared interaction policy rather than allowing each command
to invent its own diagnostics and formatting. Shared facilities cover:

- canonical help and alias presentation
- selector and ambiguity presentation
- previous/result mutation output
- empty-view messages
- actionable error and recovery formatting
- partial-failure summaries

### Application workflows

Coordinate refresh, matching, validation, mutation, cache update, and output.
Ensure that validation and synchronization precede mutation.

Workflows return structured outcomes containing the affected domain objects,
accepted changes, failures, and applicable recovery information. They do not
construct unrelated ad hoc terminal messages.

### Domain rules

Define actionability, visibility, task/step constraints, effective urgency,
Someday restrictions, report membership, and sorting. These rules must not
depend on network access.

### Todoist adapter

Maps Todoist projects and items to domain values, synchronizes task data,
performs mutations, handles idempotency and retries, and manages reminders.

The adapter preserves technical failure detail for diagnostics but does not
make raw Todoist response shapes part of the public command interface.

The adapter explicitly targets Todoist API v1 and its Sync endpoint. Its
contract documents resource and event mappings, pagination, sync-token
handling, tombstones, idempotency identifiers, and retry eligibility. Activity
and comment retrieval follows every page until exhaustion and prints progress
to stderr after every tenth page; reports are never silently truncated.

Unknown response fields are ignored. Unsupported shapes or values in recognized
fields that affect completion, attention, recurrence, hierarchy, reminders, or
other domain behavior fail clearly rather than being normalized.

### Local persistence

Local persistence separates authoritative and disposable state:

- `config` contains user policy and optional personal API token
- `binding.json` contains schema version, Todoist account/root/category IDs, and
  the last authoritative account timezone
- `report-cursor` contains the finalized UTC report boundary
- `cache.json` contains reconstructable current state plus best-effort
  accumulated completed-search history and coverage metadata
- `lock` coordinates synchronizing and mutating processes

Configuration, binding, and cursor are authoritative local state and are never
discarded as cache recovery. Binding schema changes require an explicit
migration. Cache schema changes may rebuild and lose accumulated completed
search history because the cache remains disposable.

Authentication resolves once at command start. A nonempty `TODOIST_TOKEN`
precedes `[todoist] token`. Only personal API-token authentication is supported;
init accepts no token option and OAuth is outside scope.

`~/.todo` has mode `0700`; configuration, binding, cache, cursor, and editor
temporary files have mode `0600`. Local encryption and persistent diagnostic
logging are outside scope.

Initialization, rebind, refresh, doctor, reports, cursor changes, and mutations
hold one exclusive runtime lock. Atomic cache-only reads remain lock-free. Lock
acquisition waits at most 30 seconds and then reports the competing command.

All persistent writes use same-directory temporary-file replacement. Binding
and cursor writes flush and `fsync` both file and containing directory. Cache
writes require atomic replacement but not durability synchronization. A failed
replace preserves the previous usable file.

`binding.json` minimally persists a schema version, account ID and display
identity, root ID and last-known name, managed category IDs and last-known
names, and the last account timezone. `report-cursor` is one UTC RFC 3339
instant with a trailing newline. `cache.json` minimally persists its schema
version, account/root identity, sync token, successful-sync time, current
projects/tasks/comments/reminders, tombstones needed for merging, accumulated
completed-search objects, and explicit coverage metadata. Stable IDs are
serialized as strings. Exact object nesting is an implementation choice.

## Initialization and binding flow

The user writes configuration before initialization. The schema is:

```ini
[todoist]
token = ...

[main]
project = Oracle
default_sections = ai, gatekeeper, engineer, Someday
hidden_from_now = Someday

[report]
warn_limited_history = true

[colors]
# optional Solarized Dark palette overrides
```

`project`, `default_sections`, and `hidden_from_now` are required recognized
settings; `hidden_from_now` may be empty. Names are trimmed and preserve case;
duplicates within either comma-separated list fail case-insensitively. The two
lists remain independent. Empty list elements are invalid, and configured
initial/hidden category names cannot contain a comma because the format has no
escaping convention. Unknown sections and keys are ignored for
compatibility, including legacy `default_wait_due`. Recognized invalid values
fail. Color values and slots follow `command-interface.md`.

`warn_limited_history` defaults to true and accepts only true/false. It suppresses
only the informational plan warning, never a history-retention error.

First init performs:

1. Validate config, credentials, and local permissions.
2. Synchronize identity, account timezone, plan capabilities, and projects.
3. Apply the exact root and category matching rules in `command-interface.md`;
   reject ambiguous/shared/workspace matches, otherwise reuse or provision the
   personal root, configured initial category projects, and `waiting` label.
4. Persist account ID, root ID, and category IDs in `binding.json`.
5. Build cache with a full sync followed by an incremental sync.
6. Create the initial report cursor at the captured binding time.

Remote provisioning may partially succeed, so rerunning init is idempotent and
provisions only missing objects. A local failure before binding persistence may
be retried normally. If binding persistence succeeds but cursor persistence
fails, init reports the captured intended boundary; because a binding now
exists, recovery is the explicit `report --set-cursor` workflow rather than a
fresh current-time cursor on the next init.

Subsequent init validates the bound account and stable IDs. Root/category names
may change without changing identity. A token resolving to another account
aborts before provisioning. Confirmed `init --rebind` deliberately establishes
a new account binding, provisions from current configuration, replaces the
cache, and creates a new cursor after successful new binding; it never mutates
the old account.

If binding exists but cursor is missing or corrupt, init fails and requires
explicit `report --set-cursor`. This prevents silent omission of an unknown
report interval.

## Read-only flow

Cache-backed reads load configuration, binding, cached account timezone, and
cached task data; validate the complete managed model; apply domain
rules; and format deterministic human output. They do not contact Todoist
unless `--refresh` is supplied.

A token change cannot be verified by an offline read, so cached output remains
explicitly associated with the stored binding. The next synchronizing workflow
validates account identity before any mutation.

`todo doctor` is a special read-only synchronizing flow. It continues after
individual model violations, collects all of them, and renders only diagnostics.
It never returns a normal partial view or performs a repair.

## Mutation flow

1. Validate local option syntax and acquire the runtime lock.
2. Load configuration and authoritative binding/cursor state as required.
3. Synchronize and verify account, root, categories, timezone, and model.
4. Resolve selector candidates and any interactive choice.
5. Validate the complete proposed result, capability, duplicate-title, and
   multi-object preconditions.
6. Send ordered idempotent Todoist mutation commands.
7. Reconcile and atomically update cache/binding state.
8. Render accepted changes and any partial failure.

A structural or domain-model violation blocks every normal mutation even when
another item appears unaffected; capability/resource checks such as reminder
support or the waiting label remain operation-scoped. Selection and complete
locally knowable validation precede the first mutation.

Multi-command workflows are ordered but not transactional. The first remote
failure stops later commands. Accepted changes remain and are never compensated
with automatic reopen/delete operations. Completion orders ordinary steps,
parent, then optional `Done:` comment. Creation and repeated marker values use
command-line order.

Unknown-shape Todoist date expressions are rejected when a locally resolved day
is required for preflight; otherwise they require post-acceptance
synchronization and full invariant/reminder reconciliation. An unexpected
reminder or invariant result is a nonzero partial failure, not a rollback.

Deletion always uses Todoist's direct operation. Non-recurring completed delete
candidates must currently be completed in `(report cursor, now]`; recurring
objects remain normal open candidates. No temporary reopen or local-only delete
is permitted.

## Report flow

1. Validate local option syntax, acquire the runtime lock, then load and
   validate configuration, binding, and cursor.
2. Resolve overrides and capture the automatic end instant immediately before
   the first Todoist request.
3. Synchronize current state, timezone, and plan limits.
4. Validate retention and model completeness.
5. Fetch all activity pages, completed-object pages, and required comments for
   `(start, end]`.
6. Apply current-scope/survival rules, regular reopen filtering, recurring
   complete/uncomplete pairing, and per-comment edit collapsing.
7. Build deterministic Finished, Progress, and Hidden sections in memory.
8. Write and flush the complete report.
9. If `--final`, atomically advance the cursor to the captured end.

A request, validation, rendering, write, flush, broken-pipe, or cursor failure
returns nonzero and leaves the old cursor. The design favors possible repetition
over omission. Reports do not claim an atomic remote snapshot and perform no
second comparison sync.

Plan limits are read from the synchronization already required. Limited history
warns on every report unless configured off; an interval outside retained
history is a hard pre-output error. Current managed scope, current names, and
surviving objects determine membership and presentation.
