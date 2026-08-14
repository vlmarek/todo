# 0006: Corrective reopen and operational reports

Status: Accepted

## Context

`reopen` exists to correct a recent mistaken completion, not to restore
arbitrary historical work. Reports summarize current operational truth rather
than preserving an immutable local audit ledger. Recurring items remain open
after completion, so their undo cannot be inferred from current state alone.

## Decision

- Reopen resolves only eligible completion occurrences in `(report cursor,
  now]`. Completed deletion resolves only non-recurring objects currently
  completed in that interval; a recurring object remains one normal open delete
  candidate.
- Reopen creates no comment and accepts no explanatory text.
- Reopening a step may reopen the required completed ancestor chain; output
  lists every affected ancestor. Duplicate-open-title conflicts are rejected
  before mutation.
- Only the latest recurring completion may be undone. A matching Todoist
  uncompleted activity cancels that recurring occurrence in the next report.
- Deleted objects and currently out-of-scope objects contribute no report
  entries. Regular reopened objects are omitted through current-state checks.
- Reports use one entry per recurring completion occurrence, collapse repeated
  comment edits within a period to the latest event/current text, and order
  category groups deterministically.

## Consequences

- Historical reactivation and undelete are not part of reopen.
- Report output follows current titles, categories, scope, and surviving
  objects rather than reconstructing event-time snapshots.
- Recurring undo needs explicit event pairing even though regular reopen does
  not need special report state.
