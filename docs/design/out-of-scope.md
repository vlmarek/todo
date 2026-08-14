# Out-of-scope possibilities

This document records possible future work explicitly excluded from the current
application contract. Entries are not requirements or roadmap commitments.
Implementing one requires a new accepted design decision.

## Deleted-object recovery

Cache deleted-object snapshots locally and provide an `undelete` operation.

The current contract treats deletion as terminal. Deleted tasks, steps,
comments, and their report contributions are not retained or recoverable by
`todo`.

Reconsidering this would require decisions about retention, storage growth,
task-tree restoration, stable identities, phone-side deletions, conflicts, and
whether recovery recreates an equivalent object or restores the original
Todoist object.

## Windows support

Support installation and execution on Windows.

The current contract supports Python 3.11 or newer on Linux and macOS only.
Windows remains unsupported because locking, file permissions, terminal
behavior, and installation assume POSIX facilities.

Reconsidering this would require Windows-specific behavior and tests for paths,
locking, atomic replacement and durability, permissions, terminals, editor
invocation, signals, packaging, and installation.

## Interface translation and localization

Translate command help, errors, timestamps, prompts, and other interface text,
or add locale-specific parsing behavior.

The current contract uses an English-only interface and local parser. Task,
step, category, comment, description, and hiding-reason content still supports
Unicode.

Reconsidering this would require message catalogs, locale selection and
fallbacks, translated golden fixtures, locale-aware date input and output, and
rules for interaction with Todoist's account-language date parser.

## Machine-readable output

Provide a stable machine-readable output mode, such as `--json`, for scripts
and other programs.

The current contract exposes deterministic human-readable output only. Normal
results use stdout, while warnings and errors use stderr; that presentation is
not a structured automation API.

Reconsidering this would require versioned schemas for every command, stable
representations for dates and identifiers, structured warnings and partial
failures, and compatibility rules for adding or changing fields.

## Automation-safe exact selectors

Provide selectors that guarantee one specific object is selected or fail
without prompting or falling back to fuzzy matching. Stable Todoist object IDs,
for example `--id ID`, are the reliable identity mechanism; exact title
matching alone cannot guarantee identity when titles are reused or changed.

The current contract uses human-oriented, case-insensitive substring selectors
and explicit ambiguity handling. Scripts therefore cannot rely on a selector
continuing to identify the same object.

Reconsidering this would require public ID and exact-match syntax, rules for
object type and managed-scope validation, deterministic missing/duplicate
failures, and corresponding machine-readable result and error schemas.

## OAuth and application authentication

Add OAuth, multiple account profiles, or distribution as a third-party Todoist
application.

The current contract uses one personal Todoist API token and binds one local
configuration to one Todoist account. Token rotation within that account is
supported; changing accounts requires explicit rebind behavior.

Reconsidering this would require authorization flows, callback handling, token
refresh and revocation, secure multi-profile storage, scopes, account switching,
and migration of each profile's binding, cache, and report cursor.

## Shared projects and team workspaces

Allow the managed root to be shared with collaborators or owned by a Todoist
team workspace.

The current contract requires an unshared personal root project. It does not
define assignment, collaborator permissions, attribution, concurrent invariant
violations, or whose activity belongs in reports.

Reconsidering this would require explicit ownership, attribution, permission,
assignment, conflict, and reporting rules.

## Complete historical search indexing

Guarantee that `todo search --all` covers every completed object in the
Todoist account, or add an explicit historical backfill interface.

The current contract searches completed objects accumulated in the disposable
cache and states that coverage honestly. It may search farther back than the
report cursor but does not claim complete account history.

Reconsidering this would require a backfill policy for Todoist's bounded date
windows, potentially expensive comment retrieval, coverage and gap repair,
progress and cancellation behavior, and cache-rebuild expectations.

## Todoist-free operation

Run `todo` without a Todoist account or API connection, using local storage or
another backend as the authoritative system of record.

The current contract requires Todoist for initialization, synchronization,
mutations, recurrence, history, comments, and reminders. Cache-backed views can
work temporarily without network access, but that is not a standalone
Todoist-free mode and cannot change authoritative state.

Reconsidering this would require an authoritative local or alternative backend,
data migration, durable event and recurrence models, date parsing, reminder and
notification behavior, conflict handling, backup/recovery, and a decision about
whether phone and web synchronization remain supported.
