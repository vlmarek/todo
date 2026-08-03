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
- Search tests must cover titles, descriptions, waiting reasons, and comments,
  and must prove that search results cannot implicitly select or mutate items.
- Failed synchronization must prevent mutation.
- A report cursor must not advance unless synchronization and report generation
  both succeed.
- Missing current state, activity history, or required comments must abort the
  entire report before normal output; partial reports are forbidden.
- Report tests must keep comments in `Progress`, include them only in their
  cursor-bounded add/edit period, and prove task completion does not repeat old
  comments in `Finished`.
- A successfully generated empty final report must advance the cursor.
- A task must not be hidden beyond the attention day of any open step.
- Hiding-policy tests must verify `waiting` label addition, removal, phone-side
  synchronization, and persistence after the attention day arrives.
- Hiding-reason tests must verify marked-block replacement/removal, preservation
  of ordinary description text, and display in task details and reports.
- Hiding operations must reject missing or whitespace-only reasons for both
  tasks and steps before mutation.
- Moving work into a configured hidden category must not implicitly discard
  dates, recurrence, reminders, or hiding policies.
- Invalid scheduling data discovered inside a configured hidden category must
  be reported during reads without exposing the category or modifying Todoist.
- Read output is atomic with respect to model validation: an invalid model must
  produce no partial normal output and must return a nonzero status.
- Model validation must reject any project deeper than a direct category child
  beneath the configured root and abort normal read output.
- Model validation must reject parent tasks directly in the configured root
  rather than ignoring or implicitly categorizing them.
- Model validation must reject any step that has a child, preserving the
  two-level parent-task/direct-step hierarchy.
- Normal commands must fail clearly when the configured root project is missing
  or ambiguous and must not silently select or create a replacement.
- Initialization tests must provision only missing root/category/label objects
  and verify that ordinary commands perform no implicit provisioning.
- A missing `waiting` label must fail `--hide` before item mutation but must not
  make unrelated commands fail. The error must direct the user to `todo init`.
- Secrets must not appear in logs, errors, caches committed to source control,
  or test fixtures.

## Reliability

- Todoist is the source of truth for task data.
- Read-only commands must work from the local cache without network access.
- Cache deletion must be recoverable through refresh.
- Every cached read command must support `--refresh`; refresh failure must exit
  nonzero without printing partial or stale normal output.
- Missing, unreadable, malformed, and unusable cache tests must verify a clean
  nonzero error that suggests `--refresh`, emits no normal view, and exposes no
  traceback.
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
- Date-change tests must preserve omitted reminders and display the retained
  reminder set in successful output.
- A known date-only proposal for an item with relative reminders must fail
  before mutation. Unknown-shape expressions must be reconciled after Todoist
  parsing, with warnings for changed reminders or a date-only/reminder
  inconsistency.
- A post-mutation reminder reconciliation warning must return nonzero while
  clearly reporting that Todoist already accepted the date change.
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
- Hidden-report tests must nest independently hidden steps with their reasons
  under the parent while excluding steps hidden solely through inheritance,
  and order those steps by lowercase title.
- Waiting-view tests must use the same effective-hiding membership and ordering
  as the report snapshot while excluding configured hidden categories and
  arrived waiting labels.
- Someday-view tests must include all configured hidden categories with their
  open task trees and exclude every completed item.
- Someday-view tests must order tasks by priority/category/title and nested
  steps by priority/title without date-related sorting.
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
- Task-creation tests must reject case-insensitive duplicate open titles within
  the target category before mutation while allowing that title in another
  category.
- Task creation that reuses only completed titles in the target category must
  warn on stderr and proceed with creation.
- Step creation must reject a case-insensitive duplicate open title under the
  same parent while allowing it under another parent.
- Step creation that reuses only completed titles under the same parent must
  warn on stderr and proceed.
- Category-list tests must verify lowercase alphabetical ordering independently
  of Todoist's manual project order.
- Category creation must reject case-insensitive name collisions before
  Todoist mutation while leaving ordinary category selection case-sensitive.
- Rename tests must enforce the same case-insensitive open-sibling uniqueness
  invariants as creation and reject collisions before mutation.
- Rename tests must reject completed tasks and steps without reopen/recomplete
  workaround mutations.
- Move tests must reject completed tasks and step targets without workaround
  mutations.
- Every ordinary editing workflow must reject completed targets before Todoist
  mutation. Only reopen and delete intentionally resolve completed parent
  items; normal task inspection remains open-only.
- Report tests must verify that all three section headings remain present for
  empty and partially empty reports.
- Cursor-boundary tests must verify start-exclusive, end-inclusive periods and
  prove that an event cannot appear in two consecutive finalized reports.
- Report interval tests must cover independent `--since` and `--until`
  overrides and a single captured end time when `--until` is absent.
- Report option validation must reject `--final` combined with either interval
  override before external requests and leave the cursor unchanged.
