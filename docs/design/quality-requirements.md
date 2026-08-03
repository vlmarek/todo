# Quality requirements

Status: Proposed

## Safety

- Validation must complete before any Todoist mutation.
- Completing a parent with open steps must obtain explicit confirmation before
  completing any item; cancellation must leave the whole task tree unchanged.
- Once Todoist accepts an operation in a confirmed multi-item completion, a
  later failure must not trigger compensating reopens. The partial failure must
  be reported clearly with a nonzero exit status.
- An ambiguous mutation must not guess which task or step to change.
- Exact title equality must not bypass ambiguity handling when other items also
  match the selector.
- Deletion must require either interactive affirmative confirmation or the
  explicit `--yes` option; otherwise no mutation may be sent.
- Interactive deletion of a parent must display every open and completed step
  before requesting confirmation, so no cascade target is omitted from the
  preview.
- `--yes` deletion must retain the same pre-mutation scope preview while
  omitting only the confirmation prompt.
- Integration tests must verify direct deletion of an open task, completed
  task, open step, and completed step under a completed parent without
  reopen/reclose mutations.
- Acceptance tests must distinguish a quoted contiguous-phrase selector from
  multiple all-terms selectors, including reversed and non-contiguous terms.
- Selection tests must distinguish task-only noun commands from implicit
  task-and-step selection, including a matching step under a nonmatching parent.
- Mutation and inspection selector tests must prove that descriptions and
  comments cannot cause an item to be targeted.
- Failed synchronization must prevent mutation.
- A report cursor must not advance unless synchronization and report generation
  both succeed.
- A successfully generated empty final report must advance the cursor.
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
- Report tests must verify that the `Hidden` snapshot includes currently
  suppressed tasks with no activity inside the report period.
- Report tests must verify that optional task-completion text becomes a normal
  `Done: TEXT` progress comment in the same reporting period.
- Report tests must verify that deleting a task before generation removes all
  of that task tree's Finished, Progress, and Hidden entries.
- Report tests must verify the same erasure semantics when only a step or
  comment is deleted while its parent remains.
- Report tests must verify that renames and category moves are reflected using
  current Todoist titles and category names rather than event-time values.
- Report tests must ignore non-recurring completion events for items that are
  currently open, while retaining recurring completion events whose next
  occurrence is open.
- Reopen tests must verify automatic task or parent-task progress comments,
  optional explanatory text, and partial failure after a successful reopen but
  failed comment creation.
- State-transition tests must reject already-satisfied completion and reopening
  requests without mutation or audit comments.
- Mutation tests must reject complete no-op proposals before any Todoist
  request, while allowing operations that preserve one field but change
  another and allowing creation of distinct duplicate-text comments.
- Report tests must verify that all three section headings remain present for
  empty and partially empty reports.
- Cursor-boundary tests must verify start-exclusive, end-inclusive periods and
  prove that an event cannot appear in two consecutive finalized reports.
