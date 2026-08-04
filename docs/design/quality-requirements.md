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
- An ambiguous non-interactive read lookup must print its numbered candidates,
  exit nonzero, and display no candidate detail view.
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
- Implicit top-level lookup must not emit an unknown-command warning.
- An empty implicit lookup must report no matching item and exit nonzero, while
  an empty explicit search remains successful.
- Step-inspection tests must search only open steps across all managed parents,
  exclude parent tasks, and apply normal ambiguity handling across parents.
- A selected step detail view must display its parent task and inherited
  category.
- Mutation and inspection selector tests must prove that descriptions and
  comments cannot cause an item to be targeted.
- Search tests must cover titles, descriptions, waiting reasons, and comments,
  and must prove that search results cannot implicitly select or mutate items.
- Search visibility tests must exclude completed items by default and include
  both open and completed items with `--all`.
- Default search tests must include open temporary-hidden items and open items
  from every configured hidden category.
- Search-order tests must sort task groups by priority/category/title and their
  matching steps by priority/title, without attention-date sorting.
- Search tests must distinguish a quoted contiguous phrase from multiple
  case-insensitive all-terms arguments in different orders and positions.
- Search tests must require one individual field to satisfy every term and
  reject matches assembled across fields or across separate comments.
- Search-output tests must display each matching task or step once by title and
  must not expose matching-field excerpts or explanations.
- A step-only search match must display its nonmatching parent as context while
  omitting nonmatching sibling steps.
- A parent-only search match must omit all nonmatching steps.
- An empty search must print `No matches.`, exit zero, and perform no mutation.
- Failed synchronization must prevent mutation.
- A report cursor must not advance unless synchronization and report generation
  both succeed.
- Missing current state, activity history, or required comments must abort the
  entire report before normal output; partial reports are forbidden.
- Report tests must keep comments in `Progress`, include them only in their
  cursor-bounded add/edit period, and prove task completion does not repeat old
  comments in `Finished`.
- Comment-command tests must distinguish the no-text cached display form from
  the text-supplied mutation form and restrict both to parent tasks.
- Comment display tests must order comments chronologically from oldest to
  newest.
- Comment creation with multiple text arguments must create one comment per
  argument in command-line order.
- Explicit `todo add comment` must be behaviorally identical to the
  text-supplied `todo comment` creation form.
- A partial multi-comment creation failure must retain accepted comments, stop
  further creation, report the accepted and failed arguments, exit nonzero, and
  send no compensating deletion.
- Comment-editor tests must restrict editing to open parent tasks, synchronize
  before opening the editor, perform no mutation for an unchanged buffer, and
  support editing, deleting, and adding comments from a changed valid buffer.
- Comment-editor parsing tests must recognize existing
  `[id: COMMENT_ID posted: TIMESTAMP]` blocks and multiple `[new]` blocks while
  retaining stable IDs for existing comments.
- Comment-editor application must use the stable comment ID and ignore changes
  to the informational posted timestamp.
- Comment-editor deletion tests must require removal of the complete marked
  block and must never merge text left after a removed header into an adjacent
  comment.
- Malformed comment-editor buffers must fail validation before mutation,
  including orphan text, malformed or unknown headers, duplicate IDs, and IDs
  not present in the generated buffer.
- An empty or whitespace-only existing or `[new]` comment block must reject the
  complete edit before mutation.
- A partial comment-editor application failure must stop further operations,
  retain and report accepted operations, report the failure, exit nonzero, and
  send no compensating mutations.
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
- Authentication tests must prefer a nonempty `TODOIST_TOKEN` over the
  configured token and fall back to configuration when the variable is absent.
- Initialization must require an existing valid config containing the root,
  initial categories, and hidden categories. Missing, malformed, or incomplete
  configuration must fail before network access or provisioning, and init must
  not invent structural defaults.
- Init must reject a `--token` option and must never write authentication
  credentials.
- Configuration tests must parse INI syntax and produce clean distinct errors
  for a missing file, malformed INI, and absent or invalid required settings.
- Configuration compatibility tests must retain `[todoist] token` and `[main]`
  keys `project`, `default_sections`, and `hidden_from_now`, preserve category
  name case, and prove that `default_wait_due` has no effect.
- Root-project lookup must use exact case-sensitive equality during init,
  validation, and managed-scope resolution.
- Unknown configuration sections and keys must be ignored, while malformed or
  invalid recognized settings must still fail validation.
- An explicitly empty `hidden_from_now` must be valid and produce a successful
  empty `todo someday` view.
- Exact and case-only duplicates in a nonempty `hidden_from_now` value must fail
  configuration validation.
- An empty or whitespace-only `default_sections` value must fail configuration
  validation before network access or provisioning.
- Exact and case-only duplicates in `default_sections` must fail configuration
  validation before network access or provisioning.
- Configuration and init tests must allow hidden category names outside
  `default_sections` and must not provision categories from `hidden_from_now`.

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

- Global color tests must cover `auto`, `always`, and `never`; auto mode must
  disable color for non-terminals, `NO_COLOR`, and `TERM=dumb`.
- Color configuration tests must use Solarized Dark defaults, apply partial
  recognized `[colors]` overrides, retain defaults for omitted roles, reject
  invalid recognized values, and ignore unknown keys.
- Meaning and severity must never be conveyed by color alone.
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
- Priority-command tests must select open tasks and steps, reject completed
  items and invalid priorities, and recalculate the affected task's effective
  priority.
- Priority parsing tests must treat numeric and case-insensitive `P`-prefixed
  forms as equivalent.
- Priority mutation output must identify the item and print both its previous
  and resulting stored priority.
- Task-detail tests must display only the task's stored priority, not label the
  derived task-group sorting priority as another task property.
- Task-detail tests must display the parent's own attention value and each
  step's own value without presenting derived effective attention as another
  task property.
- Task-detail tests must interleave all current comments and all open/completed
  steps in one reverse-chronological history, using current comment posting
  timestamps and step creation timestamps. Step priority and attention must not
  affect this order, and completion must change the marker rather than create a
  second history record.
- Every task-history entry must display the timestamp used for its position.
- Task-history timestamps must be displayed in the executing machine's local
  timezone.

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
- `close`/`closed` and `unclose`/`undone` must be behaviorally identical to
  `done` and `reopen`, respectively.
- Retained `todo task --ACTION` and `todo step --ACTION` mutation forms must
  delegate to their canonical verb behavior and must not reintroduce removed
  features.
- The parser must not expose a `check` command; step completion remains covered
  by `done` and its documented aliases.
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
- Task creation must default to P2 when no priority is supplied. Step creation
  must copy the parent's effective priority at that moment, after which the
  priorities remain independently mutable.
- Task-creation priority tests must accept numeric and case-insensitive
  `P`-prefixed `--priority` values plus `-p1` through `-p4`, and reject
  conflicting priority options before mutation.
- Explicit `todo add task` must be behaviorally identical to short-form task
  creation and permit categories whose names collide with explicit add kinds.
- Task- and step-creation tests must support initial attention values and
  repeatable reminders, reuse normal parsing and validation, and reject a
  reminder without a timed attention value before mutation.
- Combined task-and-inline-step creation must apply scheduling options only to
  the parent and leave every inline step unscheduled.
- Multi-step creation with any scheduling option must fail before creating any
  step; multiple unscheduled steps remain supported.
- Task- and single-step creation must support `--hide REASON`, persist the
  waiting label and nonempty reason metadata, and enforce the normal hiding
  invariants before creation. Multi-step creation with `--hide` must fail before
  mutation.
- Creation-time `--hide` without an explicit `--due` must fail before mutation
  and must not consult or apply the configured default wait date.
- Every attention-change alias used with `--hide` must require an explicit date
  and reason before mutation; the design has no default wait-date setting.
- Successful `--hide` output must print previous and resulting attention values
  and hiding reasons, explicitly representing an absent previous reason.
- Category-list tests must verify lowercase alphabetical ordering independently
  of Todoist's manual project order.
- Category creation must reject case-insensitive name collisions before
  Todoist mutation while leaving ordinary category selection case-sensitive.
- `todo category --add NAME` and `todo add category NAME` must exercise the same
  category-creation operation and observable behavior.
- `categories` must be behaviorally identical to `category`; `show` must not be
  registered as a command or alias.
- Rename tests must enforce the same case-insensitive open-sibling uniqueness
  invariants as creation and reject collisions before mutation.
- Successful rename output must identify whether the item is a task or step and
  print both the previous and resulting title.
- Successful move output must identify the task and print both the previous and
  resulting category.
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
