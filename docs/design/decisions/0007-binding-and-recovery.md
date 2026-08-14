# 0007: Stable account binding and explicit recovery

Status: Accepted

## Context

Project names can change and tokens can be replaced or point at another
Todoist account. A disposable cache cannot safely own the IDs needed to detect
an accidentally moved category or an account switch. Recreating a missing
report cursor at the current time after prior initialization could silently
skip unreported work.

## Decision

- First initialization binds the Todoist account ID, root-project ID, and
  managed category IDs in authoritative local binding state outside the cache.
- The root must be an unshared personal project. Subsequent synchronization
  validates account identity before provisioning or mutation.
- A different account requires confirmed `todo init --rebind`; rebind does not
  modify the old account and creates a new report cursor only after the new
  binding succeeds.
- A missing or corrupt cursor after an existing binding is an error requiring
  explicit `todo report --set-cursor`; init never silently replaces it.
- Phone-created invariant violations are never repaired automatically. Normal
  output and mutations stop, while read-only `todo doctor` lists every problem
  and concrete repair.

## Consequences

- Token rotation inside the same account is safe; accidental cross-account
  mutation is prevented.
- Binding state, configuration, and cursor require backup; cache remains
  disposable.
- Root/category renames retain identity, while unsafe hierarchy changes are
  detected instead of silently changing managed scope.
