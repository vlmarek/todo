# Behavioral specification

Status: Accepted

## Helpful interaction

Helpfulness is part of observable behavior.

For a failure whose cause is known, diagnostics should answer:

1. What operation failed?
2. Which item, category, setting, or external resource was involved?
3. Which rule or condition prevented the operation?
4. What can the user do next, when a safe applicable action is known?

Diagnostics should not dump internal identifiers or API payloads unless they
are needed for debugging. Todoist failures are translated into domain
vocabulary while retaining enough technical detail to diagnose an external
failure.

Recovery suggestions are operation-specific. Examples include:

- An unusable cache suggests the same read command with `--refresh`.
- A missing `waiting` label suggests `todo init`.
- Editing a completed item explains that it must be reopened first.
- Scheduling work in a hidden category explains that hidden-category items
  cannot have attention values or reminders.
- An invalid parent/step attention relationship identifies both items and both
  relevant dates.
- Ambiguous selection presents candidates with enough parent/category context
  to distinguish them.

A command must not print a success message before Todoist has accepted the
operation. After a partial failure, it must not summarize the whole command as
either wholly successful or wholly unchanged.

## `todo now`

`todo now` shows all actionable tasks and every actionable open step belonging
to them. Step presentation makes its parent task clear.

It excludes:

- completed tasks and steps
- tasks in configured hidden categories
- future-hidden tasks and their steps
- future-hidden steps

`todo now --all` shows all open managed tasks and their open steps, including
future-hidden work and configured hidden categories. It still excludes
completed work.

Completed steps are visible in `todo task SELECTOR` with a checked square.

## `todo waiting`

`todo waiting` shows the same current temporary-hiding snapshot used by the
report's `Hidden` section, including independently hidden steps nested under
their parents. It does not include configured hidden categories or items whose
attention day has arrived. Tasks and nested steps use the same alphabetical
ordering established for the report snapshot.

## `todo someday`

`todo someday` shows all open tasks in every configured hidden category and
their open steps. It does not show completed tasks or steps. The view is based
on current category membership and is not limited to a category literally named
`Someday`.

When `hidden_from_now` is explicitly empty, `todo someday` prints an empty view
as `No someday items.` and exits successfully.

Someday task groups are sorted by priority (P1 through P4), then lowercase
category name, then lowercase task title. Open steps within a task are sorted by
their own priority and then lowercase step title. No attention-date ordering is
needed because hidden-category items cannot have attention values.

`todo search` searches only open tasks, their steps, and their surviving task
comments by default. Its `--all` option also includes retained completed tasks,
steps, and their surviving cached comments. Search remains a read-only
discovery operation in either mode.

Search visibility is independent of work-queue visibility. Open items hidden by
temporary waiting and open items in configured hidden categories remain in the
default search population.

Search task groups are ordered by priority, lowercase category, and lowercase
task title. Matching steps within a group are ordered by their own priority and
lowercase title. Search ordering does not use attention dates.

### Urgency ordering

Task groups are sorted using these keys in order:

1. Due bucket:
   1. overdue
   2. due today
   3. everything else
2. Effective priority: P1, P2, P3, P4
3. Effective attention value: earlier first
4. Category name, compared lowercase
5. Task title, compared lowercase

The effective attention value and priority include the parent task and all its
open steps as defined in `domain-model.md`.

Priority is independently mutable on an open parent task or open step through
`todo priority ITEM P`. P may be `1`/`P1`, `2`/`P2`, `3`/`P3`, or `4`/`P4`,
with either case accepted for the letter. The displayed effective task priority
is recalculated from the current open task tree after the change.

For the effective-attention sort key, an absent attention value is treated as
infinitely far in the past. Consequently, among items in the same due bucket
and with the same effective priority, an undated item sorts before every dated
item.

Open steps displayed within a task group use the same urgency keys: due bucket,
step priority, step attention value, and lowercase title. A step has no separate
category key because it inherits its parent task's category. This ordering
replaces Todoist's manual step order in `todo now`.

Priority precedes the exact attention value within a bucket. For example, when
both items are due today, a P1 item due at 17:00 sorts before a P2 item due at
09:00. The same rule applies in the overdue bucket: a P1 item overdue by one
day sorts before a P2 item overdue by one month.

## Attention values and hiding

`wait`, `due`, and `schedule` are intended to be equivalent aliases.

Setting an attention value without `--hide` makes the item's own hiding policy
false. Setting it with `--hide` makes the policy true.

The own hiding policy is persisted as the Todoist `waiting` label. Setting an
attention value without `--hide` removes that label; setting it with `--hide`
adds it. Clearing the attention state also removes it. The label remains after
the attention day arrives and is removed only by an explicit later mutation.

The `waiting` label is required only by operations that add a hiding policy.
If it is missing, `--hide` fails before item mutation and directs the user to
run `todo init`. Unrelated commands do not perform or fail this label-existence
check. Removing an existing hiding policy does not require the label resource
to still exist.

A hidden task or step must store a non-empty hiding reason in a marked metadata
block in its Todoist description. Setting or changing temporary hiding updates
that block without replacing ordinary description text. Removing the hiding
policy also removes the metadata block while preserving the ordinary
description.

The existing unversioned `[todo waiting]` and `[/todo waiting]` markers remain
the storage format. A canonical block is appended at the end of the ordinary
description, separated by one blank line when ordinary text exists; both
markers occupy exact lines, line endings are LF, and the intervening reason is
preserved as Unicode text. A reason containing either exact marker line is
invalid. Marker collisions with user-authored text are an accepted risk. A
duplicate, incomplete, non-trailing, or otherwise malformed block is invalid
model state: commands report it and do not guess which text is metadata or
modify the description.

For a hidden item, list visibility begins at the start of its account-local
attention day, not at an exact attention time. Exact time remains relevant to
display, ordering within the day, and reminders.

Changing a value prints any previous attention value and the resulting value.
Changing reminders prints previous reminders, when present, and resulting
reminders. Output is printed only after successful mutation.

### Parent and step validation

If a task is hidden until Friday, a step attention value before Friday is
invalid, whether or not the step uses `--hide`.

| Hidden parent day | Step attention | Valid |
|---|---|---:|
| Friday | Thursday | No |
| Friday | Friday 10:30 | Yes |
| Friday | Saturday | Yes |
| Friday | none | Yes |

When hiding a task or moving its hidden attention day later, all open dated
steps are validated before any mutation. When adding or changing a step date,
the parent is validated before any mutation.

Date-time validation compares Todoist account calendar days. A parent hidden until
Friday 15:00 and a step due Friday 10:30 are compatible because both are
eligible for display from Friday morning.

## Recurrence

Completing a recurring task or step through `todo done` records one completion
occurrence and advances the item to its next occurrence. The item remains open;
the report nevertheless includes one entry for every qualifying occurrence. A
retained hiding policy applies to the next occurrence. Completing a recurring
parent uses Todoist's normal non-resetting behavior: already completed ordinary
steps are not implicitly reopened for its next occurrence.

A parent cannot be completed while any open step is recurring. Completing such
a step advances it and leaves it open, so the parent completion could not
satisfy the tree invariant. The command identifies all open recurring steps and
rejects the entire operation before confirmation, comment creation, or any
completion.

A recurring completion can be undone only when it is the latest completion
occurrence for that object. Undo uses Todoist's recurring-completion command in
the backward direction and moves the recurrence back exactly one occurrence.
Older occurrences are ineligible while a later occurrence exists.

Before a locally predictable recurring completion or undo, the resulting next
occurrence is checked against hidden-parent and reminder invariants. If Todoist
normalizes an occurrence in an unpredicted way, the mandatory reconciliation
detects any resulting violation, reports a partial failure, and blocks normal
workflows until the user repairs it; the CLI never claims the invalid result is
safe.

## Completing a task with open steps

Before mutation, `todo done TASK` validates the complete task tree. If any open
step is recurring, it applies the rejection above. Otherwise it lists every
open step in normal displayed order and asks whether all should be completed
with the parent. Only explicit `y` or `yes` authorizes the operation. Any other
answer, blank input, EOF, or non-interactive invocation leaves the complete tree
unchanged and exits `1`. A parent with no open steps needs no confirmation.

After confirmation, ordinary open steps are completed sequentially in displayed
order, then the parent. Only after every requested completion succeeds does the
command add optional task completion text as one `Done: TEXT` comment. Steps do
not accept completion text because they cannot own comments.

The first Todoist failure stops later operations. Already accepted completions
or a completed parent are never rolled back. In particular, failure while
creating the final `Done:` comment leaves the tree completed and reports the
missing comment as a partial failure. This is safer than writing a false
`Done:` comment before a completion that might fail.

## Reopening

`todo reopen` corrects a recent mistaken completion. Its candidate set is
completion occurrences in `(report cursor, now]`; it does not search arbitrary
history. It accepts no explanatory text and never creates a progress or audit
comment.

Reopening a parent restores only that parent; its completed steps remain
completed. Reopening a completed step may make Todoist restore its completed
ancestor chain. Before sending any request, the command determines that complete
chain and checks whether reopening any member would collide with a currently
open case-insensitive sibling title. A collision rejects the whole operation
and identifies the open conflict. A success prints the selected item and every
ancestor Todoist reopened.

A recurring item follows the latest-occurrence rule above, and only that latest
eligible occurrence appears in its candidate population. A regular item must
currently be completed. An already-open item, an occurrence at or before the
cursor, or an older recurring occurrence fails without mutation. Reopen never
changes reporting state locally; regular current-state filtering and recurring
completed/uncompleted activity pairing determine the next report.

## No-op mutations

Every mutation compares its complete proposed result with current state after
selection and validation. If the operation would make no observable state
change, it fails before contacting Todoist. Examples include setting P1 on an
already-P1 item, moving a task to its current category, renaming to the current
title, and clearing an already-empty reminder set.

The error identifies the unchanged property and current value so the user can
distinguish an accidental repeated command from a selection mistake.

The comparison covers the complete operation. Keeping an attention date while
changing reminders or the own hiding policy is a real mutation and is allowed.
Creating another comment with identical text is also a real mutation because it
creates a distinct comment.

An unchanged comment-editor buffer and a repeatable already-provisioned
`todo init` are successful inspections/maintenance operations, not requested
state transitions, so the no-op failure rule does not apply to them. Setting
the report cursor to its current instant is a no-op error.

## Moving to a hidden category

Before moving a task into a configured hidden category, validate the task and
all of its steps. If any has an attention value, reminder, or own hiding policy,
reject the complete move without mutation. The command never clears scheduling
information implicitly to make the move valid.

Configured hidden categories are resolved by their current case-sensitive
Todoist names. If a configured name no longer exists because its project was
renamed or deleted in Todoist, it matches no category and produces no warning.
A renamed project is treated as an ordinary visible category unless its new
name is also configured as hidden. Todoist remains authoritative for the
project and for the disposition of its tasks.

The reverse rename takes effect immediately as well. If a Todoist project is
renamed to a configured hidden-category name, it is hidden even when it already
contains tasks or steps with attention values, reminders, or hiding policies.
Read operations diagnose each resulting invariant violation. They must not
ignore the scheduling data, treat the category as visible, or silently modify
Todoist to repair it.

Model validation precedes normal read output. If any such invariant violation
is found, the command prints diagnostic errors to stderr, exits nonzero, and
does not print a partial actionable list or other normal result.


Before moving a task, the destination is checked under the same title rules as
creation. A same-title open task rejects the move before mutation; a same-title
completed task permits it after a warning. The command never merges tasks or
renames one implicitly.

## Clearing

`ITEM clear` removes the item's attention value, recurrence, reminders, and own
hiding policy. It is the supported way to return an item to an undated state.

`--reminder clear ITEM` removes reminders while preserving the attention value,
recurrence, and hiding policy.

## Reminders

An item may have multiple relative reminders. Reminder offsets are relative to
the exact occurrence time and are handled by Todoist so notifications appear
on the phone.

When one or more `--reminder OFFSET` arguments are supplied, they replace the
item's complete existing reminder set. They are not added to the previous set.
Repeating `--reminder` within one invocation defines multiple values in the new
set.

Each offset is one positive integer followed immediately by lowercase `m`,
`h`, `d`, or `w`. Zero, signs, decimals, spaces, compound units, and other units
are rejected before mutation. Values normalize to minutes. Equivalent duplicate
offsets in one proposal, such as `1h` and `60m`, are rejected before mutation
as a likely input error.

When an attention value is changed without any `--reminder` option, the
existing reminder set is preserved. Successful output explicitly prints the
retained reminders when the set is nonempty, even though they were not changed,
so the user can see that they now apply relative to the new attention time.

The local attention parser implements exactly the forms and account-timezone
semantics in `command-interface.md` and classifies them as known date-only or
known timed. Every other nonempty English expression is unknown locally. When
an item has relative
reminders, changing it to a known date-only value is rejected before mutation
and instructs the user to clear or replace the reminders explicitly.

When resolving the proposed day is necessary to validate a hidden parent or an
open dated step before mutation, an unknown expression is rejected with a
request for a locally understood or ISO value. Otherwise the command lets
Todoist parse it. Before mutation it snapshots the complete reminder set. After
Todoist accepts the update, it synchronizes and compares the authoritative due
value, reminders, and all affected domain invariants with that snapshot. It
prints a warning to stderr if Todoist changed or removed any reminder, if the
resulting item is date-only while relative reminders still exist, or if an
unexpected normalization created an invalid relationship. It does not attempt
to roll back an accepted Todoist update.

Such a reconciliation warning makes the command exit nonzero even though
Todoist accepted the attention-value change. The output must state that the
date mutation succeeded and identify the resulting reminder discrepancy so the
user does not mistake the operation for an unchanged failure.

## Reporting

`todo report` is an operational summary of current managed work plus qualifying
activity; it is not an immutable audit ledger.

### Boundary and retrieval algorithm

A report performs these steps in order:

1. Validate local option syntax, acquire the exclusive runtime lock, then load
   and validate the binding, configuration, and cursor without changing them.
2. Resolve explicit interval overrides and capture one end instant immediately
   before the first Todoist request when `--until` is absent.
3. Synchronize current state, account timezone, and `user_plan_limits`.
4. Verify that the start is within available activity history.
5. Retrieve every activity page in `(start, end]`, every required completed
   object page, and every comment page needed for eligibility or rendering.
6. Apply current managed-scope, survival, reopen, and recurrence rules.
7. Build all sections in memory, render, write, and flush the complete report.
8. Only for `--final`, atomically replace the cursor with the captured end.

The interval is start-exclusive and end-inclusive. An event exactly at the old
cursor is not repeated; one exactly at the captured end belongs to this report.
An event after the boundary belongs to a later report even if it occurs while
requests are running.

Any missing page, malformed pagination, unavailable required comment, output
write or flush error, broken pipe, synchronization error, model error, or cursor
write error returns nonzero. No partial normal report is intentionally printed,
and the old cursor remains. A successful empty final report advances the cursor.
A crash after a complete write but before cursor replacement may repeat output;
it must never skip output that was not completely written.

The report does not claim an atomic Todoist snapshot and performs no second
comparison sync. Concurrent post-boundary edits may affect current text or
state returned by authoritative later requests, but their activity events remain
for the next interval.

### Account history capability

The synchronization already returns the plan name and activity-history limit;
reporting performs no extra plan request. Every report warns when history is
limited unless `[report] warn_limited_history = false`. The exact Free warning
is defined in `output-contract.md`. Suppression never converts insufficient
history into success.

If the requested start predates retained activity history, generation stops
before normal output and cursor advancement. It never substitutes a shorter or
partial interval. Reminder capability is independent: basic commands and
reports continue on an account without arbitrary reminders, while a reminder
mutation fails only when it needs an unavailable capability.

### Structure and ordering

`Finished`, `Progress`, and `Hidden` are always printed in that order. Category
groups are ordered by lowercase current category name. Within each event-based
category, task groups sort by their oldest qualifying event, and events within a
task group sort oldest first. Hidden tasks sort by lowercase current title.
Stable object/event tie-breakers are defined in `output-contract.md`.

All timestamps, date-only boundaries, and displayed attention days use the
Todoist account timezone. Explicit-offset input retains its instant; persistence
uses UTC.

### Finished

`Finished` contains task completion occurrences. A non-recurring completion is
included only while the task is currently completed. A regular reopened task is
therefore omitted naturally. Every still-effective recurring completion event
is a separate entry even though the task is open at its next occurrence.

For recurring objects, an `uncompleted` activity event cancels the latest
unmatched preceding completion of the same object. The paired completion and
undo are omitted. This event pairing is required because recurring items are
open both before and after undo; it stores no local tombstone.

Task comments never move into Finished. Completion text remains a normal
`Done: TEXT` comment in Progress when its own add event qualifies.

### Progress

`Progress` contains completed step occurrences and surviving task comments
added or edited during the interval. A completed step is nested under its
current parent. A non-recurring step completion is included only while the step
is currently completed; recurring steps use the occurrence and undo rules
above.

Comment eligibility comes from `note:added` and `note:updated` activity event
timestamps, never from the immutable original `posted_at` alone. When one
surviving comment has several qualifying add/edit events in one interval, it is
shown once using current text and the latest qualifying event for ordering. A
later-period edit makes it eligible once in that later report. A deleted comment
is omitted.

### Hidden

`Hidden` is a current-state snapshot, not a cursor-bounded event list. It
contains every task currently suppressed by its own temporary hiding policy,
including tasks with no interval activity. Configured hidden categories are not
included merely because of category policy.

Each task displays its current reason. A step with its own effective hiding
policy is nested beneath the parent with its own reason. A step hidden only by
inheritance is not repeated. Independently hidden steps sort by lowercase title.
The snapshot uses the account-local attention day, so an item leaves Hidden at
the beginning of that day even though its stored waiting label remains.

### Current-state scope and deletion

Every entry uses current title, current parent, and current category. Current
managed-scope membership controls inclusion: a task currently outside the bound
root is omitted with all its events; a task currently inside may contribute all
qualifying interval events even if it entered scope during the interval.

A deleted task, step, or comment contributes no entries. Deleting a parent also
removes its step and comment contributions. Deletion is terminal and behaves as
though the object never existed for report rendering. Reports neither cache a
private undelete snapshot nor reconstruct event-time names, categories, or
scope.

## Synchronization, cache, and local state

All managed current task data is cached so read-only commands can operate
without Todoist. Mutations, initialization, doctor, explicit refresh, and
reports synchronize first. A failed synchronization prevents mutation and
normal synchronized output.

Without `--refresh`, a cached read fails cleanly on a missing, unreadable,
malformed, or incompatible cache and suggests the same command with global
`--refresh`. It never treats an unusable cache as an empty account. Cache-backed
data older than 24 hours warns on stderr.

`~/.todo/cache.json` is disposable, schema-versioned, and atomically replaced.
An incompatible cache is rebuilt on refresh rather than migrated. A failed
replacement retains the previous usable cache. If Todoist accepted a mutation
but cache update fails, the command reports remote success as a partial failure
and suggests refresh.

The cache also accumulates completed tasks, steps, and surviving comments
fetched by reports and completed-object workflows. Cursor advancement and
ordinary refresh do not purge them; Todoist deletion does. The cache records
the earliest cached completion and known coverage metadata. `todo search --all`
searches every retained object and always states that coverage may be
incomplete. Cache loss or incompatible rebuild may therefore reduce completed
search results without losing authoritative data.

Completed-search objects are keyed by stable object ID. Several recurring
completion occurrences enrich one cached object and never create duplicate
search rows; the coverage line uses the earliest retained completion occurrence.

The authoritative local files are:

- `~/.todo/config`
- `~/.todo/binding.json`
- `~/.todo/report-cursor`

The binding stores schema version, Todoist account ID, bound root-project ID,
and managed category identities. It is migrated deliberately rather than
discarded. `~/.todo/lock` is runtime coordination state. The cache and binding
also retain the Todoist account timezone required for offline rendering; after
a sync, Todoist's current timezone wins.

Cached reads remain offline even if the process environment now contains a
token for another account; they display the explicitly bound account's cached
data. The next synchronizing command detects the mismatch before provisioning
or mutation.

Displayed instants use friendly English account-local time with seconds, for
example `Fri 14 Aug 2026, 16:30:42`. Ordering and comparisons use full instants.
Report headers print the account timezone name.

## Category identity, listing, and invalid-state recovery

`todo category` lists current direct children of the bound root alphabetically
by lowercase name; Todoist manual order is ignored. A newly discovered direct
child is enrolled by stable ID as a managed category. A rename updates its
current/last-known name without changing identity. Hidden-category policy still
matches current names exactly as configured.

During first binding or explicit rebind, the configured root name follows the
exact create/reuse/reject rules in `command-interface.md`. After binding,
stable account and root IDs are authoritative; renaming the root does not make
the CLI bind a different same-name project.

A missing, deleted, archived, shared, workspace-owned, or wrongly nested bound
root is invalid. A managed category moved or archived outside the root while it
still owns managed tasks is also invalid and must be restored. An empty removed
category may be retired from the binding because no managed work would be
silently lost. Ordinary commands never create a replacement or move structure
back automatically.

Projects below a category, parent tasks directly in the root, and steps deeper
than one direct level are invalid. Duplicate open sibling titles, malformed
waiting metadata, and scheduling data forbidden inside a configured hidden
category are likewise invalid when introduced outside the CLI.

The same invalid-state policy covers an orphan step, a step whose parent is
outside managed scope, an open step below a completed parent, a task comment
attached to a step, and either half of a waiting-label/reason mismatch. Doctor
identifies the exact external repair; normal commands never discard or
reinterpret these objects.

Normal views, reports, and mutations validate the complete managed model in the
loaded snapshot, even when a selector or category filter would touch only one
part of it. Capability checks and existence checks for operation-specific
resources remain scoped to the requested operation. Any model violation prints
diagnostics and no partial normal result. `todo doctor` remains available,
synchronizes, lists all violations rather than stopping at the first, and gives
concrete repair instructions. It never modifies Todoist. After external repair,
doctor or a
normal command with `--refresh` confirms recovery.

There is no built-in interactive root/category configurator. The user creates a
complete config before initialization; init consumes it rather than choosing
settings.
