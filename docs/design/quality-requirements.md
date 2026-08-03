# Quality requirements

Status: Proposed

## Safety

- Validation must complete before any Todoist mutation.
- An ambiguous mutation must not guess which task or step to change.
- Exact title equality must not bypass ambiguity handling when other items also
  match the selector.
- Acceptance tests must distinguish a quoted contiguous-phrase selector from
  multiple all-terms selectors, including reversed and non-contiguous terms.
- Selection tests must distinguish task-only noun commands from implicit
  task-and-step selection, including a matching step under a nonmatching parent.
- Mutation and inspection selector tests must prove that descriptions and
  comments cannot cause an item to be targeted.
- Failed synchronization must prevent mutation.
- A report cursor must not advance unless synchronization and report generation
  both succeed.
- A task must not be hidden beyond the attention day of any open step.
- Moving work into a configured hidden category must not implicitly discard
  dates, recurrence, reminders, or hiding policies.
- Invalid scheduling data discovered inside a configured hidden category must
  be reported during reads without exposing the category or modifying Todoist.
- Read output is atomic with respect to model validation: an invalid model must
  produce no partial normal output and must return a nonzero status.
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
- Ordering tests must verify that priority outranks exact date/time within each
  due bucket, including overdue items with substantially different dates.

## Testability

- Domain rules and ordering must be testable without Todoist or network access.
- Acceptance tests must cover stdout, stderr, exit status, Todoist requests,
  and absence of mutation after failure.
- Tests must cover local calendar-day boundaries and the configured machine
  time zone.
- Report tests must cover cursor boundaries, failed finalization, comments,
  completed steps, completed tasks, and current-category grouping.
- Report tests must verify case-insensitive alphabetical category ordering,
  independently of Todoist's manual project order.
- Report tests must verify oldest-to-newest ordering of tasks and events in the
  event-based sections, including multiple progress events grouped by one task.
- Report tests must verify lowercase alphabetical task ordering within each
  category of the non-event-based `Hidden` section.
- Cursor-boundary tests must verify start-exclusive, end-inclusive periods and
  prove that an event cannot appear in two consecutive finalized reports.
