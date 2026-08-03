# Quality requirements

Status: Proposed

## Safety

- Validation must complete before any Todoist mutation.
- An ambiguous mutation must not guess which task or step to change.
- Failed synchronization must prevent mutation.
- A report cursor must not advance unless synchronization and report generation
  both succeed.
- A task must not be hidden beyond the attention day of any open step.
- Secrets must not appear in logs, errors, caches committed to source control,
  or test fixtures.

## Reliability

- Todoist is the source of truth for task data.
- Read-only commands must work from the local cache without network access.
- Cache deletion must be recoverable through refresh.
- Local persistent writes must not leave partially written state.
- Concurrent invocations must not corrupt local state.

## Retry policy

Todoist requests have a 30-second timeout per request. Retriable operations are
attempted at most four times.

HTTP status codes eligible for retry are:

```text
408, 429, 500, 502, 503, 504
```

Without a usable `Retry-After` value, delays are 1, 2, and 4 seconds. When
Todoist supplies `Retry-After` for a retriable response, it is honored up to a
maximum delay of 60 seconds.

Every retry prints a warning to stderr so the user understands the delay.

Only operations safe under the Todoist request/idempotency model may be
automatically retried.

## Usability

- `todo now` must provide a useful urgency ordering without requiring manual
  filtering during normal use.
- The public command vocabulary should remain small.
- Successful date and reminder changes must report replaced values and the
  resulting state.
- Errors must identify the conflicting item and rule in user terminology.
- Exact appointment times must not prevent items from appearing on the morning
  of their attention day.

## Testability

- Domain rules and ordering must be testable without Todoist or network access.
- Acceptance tests must cover stdout, stderr, exit status, Todoist requests,
  and absence of mutation after failure.
- Tests must cover local calendar-day boundaries and the configured machine
  time zone.
- Report tests must cover cursor boundaries, failed finalization, comments,
  completed steps, completed tasks, and current-category grouping.
- Cursor-boundary tests must verify start-exclusive, end-inclusive periods and
  prove that an event cannot appear in two consecutive finalized reports.
