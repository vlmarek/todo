# Quality requirements

Status: Accepted

## Safety

- Every locally decidable validation must complete before any Todoist mutation.
  The only post-acceptance validation path is the documented unknown English
  attention-expression reconciliation, and it must report accepted remote state
  as a partial failure when reconciliation finds a problem.
- Completing a parent with open steps must obtain explicit confirmation before
  completing any item; cancellation must leave the whole task tree unchanged.
- A parent with any open recurring step must be rejected before confirmation
  or mutation; advancing that step cannot satisfy the closed-tree invariant.
- Once Todoist accepts an operation in a confirmed multi-item completion, a
  later failure must not trigger compensating reopens. The partial failure must
  be reported clearly with a nonzero exit status.
- An ambiguous mutation must not guess which task or step to change.
- An ambiguous non-interactive read lookup must print its numbered candidates,
  exit nonzero, and display no candidate detail view.
- Interactive ambiguity must accept only a displayed number or `q`, re-prompt
  invalid numbers, and treat blank/EOF as cancellation without mutation.
  Non-interactive ambiguity must print the identical candidate set and never
  prompt.
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
- Parser tests must never infer batch structure from spaces or tabs inside an
  argument. Unmarked prose is one value; multiple comments/steps require
  repeated markers; marker values may be multiword; `--literal` escapes a
  marker-looking token.
- Comment shorthand tests must treat only the first argument as selector and
  join the remainder into one comment. Multi-term selectors must use an
  explicit `--comment` marker.
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
- Search visibility tests must exclude completed items and their comments by
  default and include open plus retained completed items and surviving cached
  comments with `--all`.
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
- Report tests must consume plan limits from the required sync without an
  extra plan request, warn on every limited-history report unless configured
  off, use the exact Free warning, and hard-fail before normal output when the
  cursor predates retained history. Warning suppression must not suppress the
  hard error.
- Report tests must keep comments in `Progress`, include them only in their
  cursor-bounded add/edit period, and prove task completion does not repeat old
  comments in `Finished`.
- Comment-command tests must distinguish the no-text cached display form from
  the text-supplied mutation form and restrict both to parent tasks.
- Comment display tests must order comments chronologically from oldest to
  newest.
- Unmarked comment prose must create one joined comment regardless of shell
  argument count. Multiple comments require repeated `--comment` markers and
  are created in marker order.
- Explicit `todo add comment` must be behaviorally identical to the
  text-supplied `todo comment` creation form.
- A partial multi-comment creation failure must retain accepted comments, stop
  further creation, report the accepted and failed arguments, exit nonzero, and
  send no compensating deletion.
- Comment-editor tests must restrict editing to open parent tasks, synchronize
  before opening the editor, perform no mutation for an unchanged buffer, and
  support editing, deleting, and adding comments from a changed valid buffer.
- Comment-editor process tests must hold the local lock, use a UTF-8 mode-0600
  file, treat launch/signal/nonzero exit as no mutation, leave concurrently
  added comments untouched, and apply saved text by stable ID even when it
  overwrites a concurrent edit to that same comment.
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
- Invalid-model tests must block normal views, reports, and mutations without
  automatic repair. `todo doctor` must synchronize, enumerate all violations
  with repair guidance, remain read-only, and work when normal validation fails.
- Model validation must reject any project deeper than a direct category child
  beneath the configured root and abort normal read output.
- Model validation must reject parent tasks directly in the configured root
  rather than ignoring or implicitly categorizing them.
- Model validation must reject any step that has a child, preserving the
  two-level parent-task/direct-step hierarchy.
- Initial root lookup must create a root on zero exact active top-level matches,
  reuse one only when it is unshared and personally owned, and reject multiple,
  shared, or team-owned matches. Configured categories must reuse a unique
  case-insensitive direct-child match or be created and must reject collisions.
  After binding, normal commands must use the stable root ID and reject a
  missing, shared, workspace-owned, archived, or wrongly nested root without
  selecting or creating a replacement.
- Initialization tests must provision only missing root/category/label objects
  and verify that ordinary commands perform no implicit provisioning.
- A missing `waiting` label must fail `--hide` before item mutation but must not
  make unrelated commands fail. The error must direct the user to `todo init`.
- Secrets must not appear in logs, errors, caches committed to source control,
  or test fixtures.
- Authentication tests must prefer a nonempty `TODOIST_TOKEN` over the
  configured token and fall back to configuration when the variable is absent.
- First init must bind account, unshared-personal root, and category IDs.
  Synchronizing with a different account must abort before provisioning or
  mutation. Confirmed `init --rebind` must leave the old account untouched,
  establish new state, replace cache, and create a new cursor only on success.
- Token rotation within the bound account must succeed. Offline reads must use
  the bound cache without making a token-account network check.
- Shared roots and team-workspace roots must be rejected and diagnosed.
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
- Root-project name lookup must use exact case-sensitive equality during first
  init and explicit rebind. Subsequent validation and scope resolution must use
  the bound account/root IDs and tolerate root renaming.
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
- Runtime-lock tests must cover acquisition, release, a 30-second timeout, and
  lock-free reads during atomic cache replacement.
- Two concurrent final-report tests must prove that each process acquires the
  lock before reading the cursor and that the second process reloads the cursor
  after the first advances it; neither may reuse a stale pre-lock interval.
- Cache fixtures carry a schema version. Incompatible versions fail cleanly and
  are rebuilt rather than migrated when `--refresh` is supplied.
- Reports and completed-object workflows must accumulate completed tasks,
  steps, and comments in the disposable cache. Cursor advancement and ordinary
  refresh must retain them; deletion removes them. `search --all` must search
  all retained objects and always state earliest cached completion plus
  incomplete-coverage semantics. No search `--since` option exists.
- Cache deletion or incompatible rebuild may lose accumulated completed search
  history, but a cached empty result must never claim complete Todoist history.
- A failed cache replacement retains the preceding usable cache. A Todoist
  mutation followed by cache-write failure is a partial failure and suggests
  global `--refresh`.
- Cache-backed reads older than 24 hours warn and suggest `--refresh`.
- Cursor persistence tests cover atomic replacement plus file and directory
  synchronization. Cache persistence requires atomicity but not `fsync`.
- Local-state permissions are `0700` for the application directory and `0600`
  for sensitive files and editor buffers.

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

- The primary workflow must be discoverable from `todo help` without reading
  source code or Todoist API documentation.
- Command help must teach canonical forms before compatibility aliases.
- Commands operating on the same concepts must share parsing, matching,
  validation, and output conventions.
- User-facing output must use domain vocabulary and avoid raw Todoist API field
  names except in explicitly diagnostic detail.
- Errors with a known safe recovery must identify the failure, its cause, and
  the applicable next command or option.
- Errors must not suggest a recovery that would violate current domain state.
- Ambiguity output must include enough parent and category context to
  distinguish candidates with similar titles.
- Partial-failure output must distinguish accepted, failed, and unattempted
  operations.
- Successful mutations must identify the affected item and resulting state.
- Automated acceptance tests must cover complete common workflows, not only
  individual parser and domain functions.
- Global color tests must cover `auto`, `always`, and `never`; auto mode must
  disable color for non-terminals, `NO_COLOR`, and `TERM=dumb`.
- Color configuration tests must use Solarized Dark defaults, apply partial
  recognized `[colors]` palette-slot overrides, retain defaults for omitted slots, reject
  invalid recognized values, and ignore unknown keys.
- Recognized color values must accept case-insensitive six-digit `#RRGGBB` and
  reject shorthand, named, alpha, or unprefixed formats.
- Meaning and severity must never be conveyed by color alone.
- Success exits `0`, command-line usage errors exit `2`, and operational or
  partial failures exit `1`.
- Golden-output fixtures cover every command and major failure with fixed time,
  timezone, terminal width, color, and backend data. They make presentation
  changes explicit without creating a permanent scripting interface.
- Golden fixtures must implement every literal heading, indentation level,
  marker, empty message, ambiguity prompt, mutation label, report header, and
  cache-coverage line in `output-contract.md`. Machine-readable output and
  identity-safe selectors must remain absent.
- Displayed instants use friendly English timestamps with seconds in the
  Todoist account timezone; report headers print the IANA timezone name.
- `todo help COMMAND` and `todo COMMAND --help` must produce equivalent help,
  and all help forms must work without configuration, cache, or network access.
- A no-argument invocation must be behaviorally identical to `todo now`, while
  `todo help` and `todo --help` remain explicit configuration-free help paths.
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
- Task-history timestamps must be displayed in the Todoist account timezone.

### Workflow acceptance scenarios

At minimum, tests must exercise these workflows through the public CLI:

1. Find current work, inspect a task, add progress, and complete a step.
2. Capture a task, refine it into steps, and change a step's priority.
3. Add an attention time and reminders, then inspect the resulting state.
4. Temporarily hide work with a reason and later make it visible.
5. Resolve an ambiguous selector without modifying the wrong item.
6. Encounter an unusable cache and recover through `--refresh`.
7. Preview and finalize a report.
8. Encounter a partial Todoist mutation and understand which changes remain.

The expected stdout, stderr, exit status, and state change are asserted for
every scenario.

Because “intuitive” cannot be proven entirely through automated tests, a
release review should also walk through these scenarios using only public help.
Any point at which the user must consult implementation details is a usability
defect or a missing help requirement.

## Testability

- Domain rules and ordering must be testable without Todoist or network access.
- Acceptance tests must cover stdout, stderr, exit status, Todoist requests,
  and absence of mutation after failure.
- Selector tests cover Unicode normalization and case folding, preserve accent
  distinctions, and verify substring matching.
- Time parsing treats offset-free input as local to the Todoist account
  timezone and rejects nonexistent or ambiguous daylight-saving times unless an
  explicit offset is supplied. Explicit offsets retain their instant. This
  applies to cursor, report boundaries, and locally parsed attention input.
- Attention parser tests must cover ISO values, today/tomorrow, strict-next
  English weekdays, optional clock times, elapsed `Nh`, account-calendar `Nd`,
  Monday-Friday `Nbd`/business-day values, and unknown English Todoist strings.
  Unknown values must fail before mutation when a hidden-parent/step day
  comparison depends on them and otherwise undergo post-mutation reconciliation.
- Reminder parsing accepts only a positive integer plus lowercase `m`, `h`,
  `d`, or `w`; rejects zero, signs, decimals, whitespace, compound/unsupported
  units; and rejects minute-equivalent duplicates before mutation.
- First-binding init tests create a cursor only after provisioning and binding
  persistence succeed. Once binding exists, missing/corrupt cursor tests must
  fail init and require explicit `report --set-cursor` rather than silently
  creating a current-time cursor.
- Cursor tests cover display, confirmation, `--yes`, direction warnings, UTC
  persistence, and `Nd ago`/`N days ago` input.
- Reports fail before synchronization when no valid cursor exists. Tests prove
  complete output and flush precede cursor advancement; broken pipes, write
  errors, and interruption leave the cursor unchanged so repetition is favored
  over omission.
- Paginated report tests retrieve every activity and comment page and never
  present a truncated report as complete.
- Pagination progress tests must print the fixed stderr line after every tenth
  completed page of one endpoint and must not treat progress as completion.
- Comment-editor tests parse `$VISUAL`/`$EDITOR` arguments without a shell,
  apply edits then additions then deletions, allow the saved buffer to overwrite
  concurrent remote changes, and require confirmation before an empty buffer
  deletes all comments.
- Adapter tests ignore unknown response fields but reject unsupported values or
  shapes in recognized behavior-affecting fields.
- Adapter tests must prove the Todoist `4..1` to domain `P1..P4` mapping in both
  directions, English due-language submission, atomic sync-token/state
  persistence, reference-order independence, tombstone precedence, and
  retention of a compatible completed-search index across full replacement.
- Packaging tests target Python 3.11+ on Linux and macOS through the installed
  `todo` console entry point. Windows is unsupported.
- Tests must cover account-local calendar-day boundaries, account-timezone
  changes after synchronization, cached offline timezone use, and explicit
  offsets independent of the executing machine timezone.
- Report tests must cover cursor boundaries, failed finalization, comments,
  completed steps, completed tasks, and current-category grouping.
- Report tests must verify case-insensitive alphabetical category ordering,
  independently of Todoist's manual project order.
- Report tests must order categories alphabetically, then task groups by their
  oldest qualifying event within each category, then grouped events oldest to
  newest, with stable ID/event tie-breakers.
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
- Successful empty waiting and someday views must print `No waiting items.` and
  `No someday items.`, respectively, and exit zero.
- Someday-view tests must order tasks by priority/category/title and nested
  steps by priority/title without date-related sorting.
- Completion-text tests must complete ordinary open steps, then the parent,
  then create the `Done: TEXT` progress comment. Comment failure must leave the
  completed tree intact and report a partial failure; no false pre-completion
  `Done:` comment may remain.
- Report tests must verify that deleting a task before generation removes all
  of that task tree's Finished, Progress, and Hidden entries.
- Report tests must verify the same erasure semantics when only a step or
  comment is deleted while its parent remains.
- Report tests must verify that renames and category moves are reflected using
  current Todoist titles and category names rather than event-time values.
- Current-scope tests must omit objects currently outside the managed root
  and include qualifying events for objects currently inside even when they
  crossed the boundary during the interval.
- Comment-report tests must derive add/edit time from activity rather than
  `posted_at`, collapse several same-period events for one surviving comment to
  current text at the latest event, show it again after a later-period edit,
  and omit deleted comments.
- Recurring report tests must print one entry per qualifying task/step
  completion occurrence with its event time.
- Report tests must ignore regular completion events for currently open items,
  retain one line per effective recurring occurrence, and cancel the latest
  unmatched recurring completion when a corresponding uncompleted event exists.
- Reopen tests must reject explanatory text, create no audit/progress comment,
  search only `(report cursor, now]`, list Todoist-reopened ancestors, preflight
  duplicate-title conflicts across that chain, and permit only the latest
  recurring occurrence to move backward once.
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
- Canonical creation must delimit unquoted multiword category/title values
  with `--category` and `--title`; repeated `--step` creates several steps.
  Positional aliases join their unmarked tail into one title and never use
  shell quoting as a batch boundary.
- Creation tests must treat `--done`, `--close`, and `--closed` as equivalent,
  generate normal completion events, and complete all inline steps before a
  newly created parent.
- Creation must reject completion-at-creation combined with `--hide`, `--at`,
  `--due`, or `--reminder` before any mutation.
- Completion-at-creation must use the same duplicate-title errors and
  completed-title reuse warnings as ordinary creation.
- Task- and step-creation tests must support initial attention values and
  repeatable reminders, reuse normal parsing and validation, and reject a
  reminder without a timed attention value before mutation.
- Combined task-and-`--step` creation must apply scheduling options only to the
  parent and leave every marked inline step unscheduled.
- Repeated-`--step` creation with any step-level scheduling option must fail
  before creating any step; several explicitly marked unscheduled steps remain
  supported and preserve marker order.
- Task- and single-step creation must support `--hide REASON`, persist the
  waiting label and nonempty reason metadata, and enforce the normal hiding
  invariants before creation. Multi-step creation with `--hide` must fail before
  mutation.
- Creation-time `--hide` without explicit `--at` or its `--due` alias must fail
  before mutation and must not consult or apply a default wait date. Supplying
  both `--at` and `--due` is an option conflict.
- Every attention-change alias used with `--hide` must require an explicit date
  and reason before mutation; the design has no default wait-date setting.
- Successful `--hide` output must print previous and resulting attention values
  and hiding reasons, explicitly representing an absent previous reason.
- Category-list tests must verify lowercase alphabetical ordering independently
  of Todoist's manual project order.
- Category creation must reject case-insensitive name collisions before
  Todoist mutation. User-entered category lookup for now-filtering, task
  creation, and moves must be case-insensitive.
- `todo now --category` must retain normal actionable visibility and urgency
  ordering while limiting results to the case-insensitively selected category.
- A missing `now --category` target must fail nonzero with no normal list,
  while an existing category with no actionable items must succeed.
- `todo now --all --category` must include all open visibility states within
  only the selected category.
- Every successful empty `todo now` variant must print `No actionable items.`
  and exit zero.
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
- Move tests must reject a same-title open task in the destination before
  mutation, allow only completed same-title conflicts with a warning, and never
  merge or rename implicitly.
- Every ordinary editing workflow must reject completed targets before Todoist
  mutation. Only reopen and delete intentionally resolve completed parent
  items; normal task inspection remains open-only.
- Reopen selection must retrieve only eligible occurrences in `(report cursor,
  now]`. Completed-delete selection must retrieve only currently completed
  non-recurring objects completed in that interval; open deletion remains
  unrestricted. Older completed objects are not mutation candidates even when
  retained for cached search.
- Recurring items must appear only once as open delete candidates. Deleting one
  removes the active recurring object; a historical completion occurrence must
  never appear as a second delete target.
- Report tests must verify that all three section headings remain present for
  empty and partially empty reports.
- Cursor-boundary tests must verify start-exclusive, end-inclusive periods,
  capture the automatic end before the first Todoist request, and prove that an
  event cannot appear in two consecutive finalized reports.
- Report interval tests must cover independent `--since` and `--until`
  overrides and a single captured end time when `--until` is absent.
- Report/cursor time tests must reject start-after-end and future end/cursor
  values, accept equal report boundaries as empty, and require explicit offsets
  for ambiguous or nonexistent account-local times.
- Report option validation must reject `--final` combined with either interval
  override before external requests and leave the cursor unchanged.

### Accepted edge-case matrix

The acceptance suite must additionally prove:

- all retained aliases (`close`, `closed`, `unclose`, `undone`, `wait`, `due`,
  `schedule`, `categories`, both category/task/comment creation families,
  creation close flags, noun-action forms, help aliases, and priority spellings)
  delegate to one canonical workflow with identical state and output
- `--at` and `--due` are equivalent value markers and conflict when combined;
  `--hide` is final and consumes one joined reason
- exact selector equality never hides broader substring candidates
- reopening a step may reopen ancestors and prints each one, but a duplicate
  open title anywhere in the affected chain rejects before mutation
- only the latest recurring occurrence can be undone through
  `item_update_date_complete` with backward direction; ordinary REST reopen is
  not used for an active recurring item
- a matching recurring uncompleted event removes the corresponding upcoming
  report occurrence without a local tombstone
- deletion remains terminal and contributes no report or cached-search entry;
  no undelete command or snapshot is created
- root/category renames retain stable binding identity, while unsafe moves,
  archives, sharing, workspace transfer, and forbidden hierarchy are diagnosed
- a report interval whose start equals the retention boundary is accepted,
  while one earlier than it is rejected without partial output
- a final report with completely written stdout and failed cursor persistence
  repeats on the next run; a failed/broken stdout write never advances
- reports use current scope and current names rather than reconstructing an
  event-time ledger
- category order, task-group event order, recurring occurrence order, and every
  equal-key tie are deterministic across repeated runs
- all local files use required modes, tokens never enter cache/output/fixtures,
  and personal-token-only help exposes no OAuth flow
- Linux and macOS packaging pass; Windows, localization, JSON, exact ID/title
  selectors, OAuth, shared roots, and undelete remain outside scope
