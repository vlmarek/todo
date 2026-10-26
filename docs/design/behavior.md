# Behavioral contract

Status: **Accepted**

todo-3 specification, revision 2. See [README](README.md).

### REQ-COMMENT-008 — Comment display, creation, aliases, and partial creation

The supported comment forms are:

```console
todo comment [--refresh] SELECTOR
todo comment SELECTOR COMMENT...
todo comment SELECTOR... --comment COMMENT... [--comment COMMENT...]...
todo add comment SELECTOR... --comment COMMENT... [--comment COMMENT...]...
```

Comment operations must select one open task or step. Comments belong to that
item's stable ID, independently of its parent or children. The no-text form is a
cache-first read displaying that owner's comments oldest first and accepts
`--refresh`. In shorthand creation only the first argument is the selector; the
remaining unmarked arguments produce comment bodies under REQ-CLI-012. A
multi-term creation selector requires explicit `--comment`; quote a multiword
selector when using shorthand or a no-text read.

Each explicit marker group is split independently under REQ-CLI-012. Create
all resulting comments sequentially in group and argument order. `todo add comment`
must be an exact alias for creation, including its shorthand. Validate every
resulting body before the first mutation. A later failure must
retain accepted comments, stop before later comments, report accepted, failed, and
unattempted operations, perform no deletion, and exit nonzero. Render each accepted
comment's actual body using the arrow receipt in TPL-MUTATION rather than repeating
the destination title as though it were comment text. Identify the destination at
most once, preserving step-parent context. Canonical/alias creation and supported
completion comments share that body receipt; the editor's all-success count summary
and its detailed partial-failure rules remain unchanged.

### REQ-COMMENT-007 — Editor launch, locking, temporary file, and concurrent changes

`todo comment --edit SELECTOR` must synchronize before selecting one open task or
step, acquire and retain the exclusive local lock, then invoke `$VISUAL`, else
`$EDITOR`, else `vi`. The editor value must be parsed as a shell-like argument
string but executed directly without a shell.

The UTF-8 temporary file must be created under `~/.todo` with mode `0600`. Launch
failure, interruption, or nonzero editor exit must make no comment mutation and
must clean temporary state. An unchanged valid buffer is a successful inspection
with no mutation.

The complete saved buffer must validate before mutation. Valid changes must be
applied sequentially as edits, additions, then deletions. An externally added
comment absent from the generated buffer must remain untouched. Saving changed
text for a known stable ID intentionally overwrites a concurrent edit to that ID;
a concurrently deleted target must fail at its ordered operation. Informational
timestamp edits do not change identity.

An empty buffer requests deletion of every comment shown in the generated buffer
and requires a second interactive confirmation; non-interactive use must fail
unchanged. A saved buffer containing only the ignored empty trailing `[new]`
starter under REQ-COMMENT-006 is equally an all-shown-comments deletion request
when any comments were originally shown; require the same confirmation. With no
original comments, the unused starter is a successful no-op. The first API failure
stops processing without rollback and reports
accepted, failed, outcome-unknown when applicable, and unattempted work. Use
TPL-COMMENT-EDIT for the one-line all-success receipt and operation-specific
partial-failure presentation; this changes no reconciliation order or outcome
classification and does not suppress required cache-recovery diagnostics.

### REQ-COMMENT-006 — Editor block escaping and edge-blank normalization

The editor buffer must consist only of these block types:

```text
[id: COMMENT_ID posted: TIMESTAMP]
existing comment text

[new]
new comment text
```

Stable comment ID is authoritative and displayed timestamp is informational.
Each header starts a section extending to the next header or end of file. Leading
and trailing blank lines in each section body are ignored for comparison,
validation, and saved content; internal blank lines and line breaks are preserved.
Generate all existing comment blocks oldest first and always append one empty
trailing `[new]` section, including when the item has no comments. Ignore that
section if its body remains empty or whitespace-only after normalization; saving
the generated file unchanged must succeed without mutation. Filling it creates
a new comment. Additional nonempty `[new]` blocks create comments in saved order.
The exception applies only to one empty new section that is the final block;
other empty new sections and all empty retained existing sections remain invalid.
A removed empty starter is also harmless when other blocks are unchanged.
To delete an existing comment without changing another block's content, remove
its complete header and body, not merely empty its body. Preserve delete-all
confirmation under REQ-COMMENT-007 when only the unused starter remains.

When content is rendered into the buffer, prefix one backslash to a line that
would otherwise be parsed as `[new]`, as an `[id: ...]` header, or that already
begins with a backslash. Parsing removes exactly that protective prefix. Backslash
has no other escape meaning. This selective escaping must allow literal header-like
content and round-trip it without changing other backslashes.

Text before the first header, malformed or unknown headers, duplicate IDs and
foreign IDs must reject the entire edit before mutation. Parse the saved buffer
according to its observable block structure; do not try to infer whether a header
was removed accidentally. If an interior header is removed but its body remains,
that text becomes part of the preceding block. The missing existing ID requests
deletion of its original comment, while the preceding block's resulting body
determines its edit or addition under the ordinary rules. For example, removing
comment B's header after comment A while leaving B's text edits A to include that
text and deletes B; this is valid when the resulting buffer otherwise validates.
The existing empty-buffer and unused-starter delete-all confirmation rules remain
unchanged. This adds no heuristic missing-header detection or new confirmation.

### REQ-COMP-005 — Normal completion and optional `Done:` comment

```console
todo done SELECTOR... [--comment TEXT...]
```

`done` must select an open task or step. In one-selector shorthand the unmarked
remaining arguments form the completion-text group; canonical multi-term selection
uses `--comment`. Completion text is valid for a task or step and must use
REQ-CLI-012 grouping. The explicit form accepts one `--comment` group, which may
produce several bodies; repeated `--comment` groups remain invalid for `done`.
Validate all requested bodies before the first completion mutation. After the
requested completion succeeds, create each comment sequentially on the completed
item's own stable ID, with content exactly `Done: TEXT` for its normalized body.
No-text completion creates no comment. Recurring completion comments belong to
the same item even though its next occurrence remains open.

Ordinary completion must use Todoist's completion operation and print one accepted
completion occurrence at a time. Failure to create a later comment leaves the
completed tree intact, reports a partial failure, and must not fabricate an earlier
comment, roll completion back, or attempt later requested comments. Retain any
earlier accepted comments and distinguish failed/unknown and unattempted results.

### REQ-COMP-006 — Recursive subtree confirmation, ordering, and partial completion

Before completing a selected task or step, synchronize and validate its complete
current open subtree. If it has open descendants, list the affected descendants
with recursive indentation in their normal display order and require one explicit
interactive y or yes confirmation. Show the selected root as context. Any other
answer, blank, EOF, or non-interactive input exits 1 without mutation; this command
gains no --yes bypass. A leaf with no open descendants needs no subtree confirmation.

An open recurring descendant must reject the entire selected-root operation before
prompting or mutation. List every such descendant with its ancestor context and
explain that recurrence must be removed, the step deleted, or that recurring work
separated. This restriction does not forbid completion of a recurring selected
root with only ordinary descendants.

After confirmation, traverse direct children in REQ-CLI-021's inspection display
order, including known creation times before unknown times and stable-ID ties.
The same ordering applies to the preview; unknown creation time does not block
completion. Visit each child's open descendants recursively, then complete that
child exactly once; complete the selected root last. This deterministic postorder ensures a
parent is never
completed while an ordinary open descendant remains. Skip already completed
descendants. Create any requested Done: comments only on the selected root,
after its successful completion under REQ-COMP-005; do not copy them to descendants.

The first failure or unknown outcome stops later operations. Accepted completions
remain accepted and must be distinguished from failed/unknown and unattempted
operations; there is no rollback. Completing a child never automatically completes
its parent. Reopen remains bounded under REQ-COMP-008 and does not recursively
reopen completed descendants.

### REQ-COMP-007 — Recurring completion and post-mutation reconciliation

Completing a recurring task or step must record one occurrence and use Todoist's
forward recurring-completion operation to advance it. It remains open. A retained
hiding policy applies to the next occurrence, and recurring parent completion must
not reset already completed ordinary steps.

Before a locally predictable recurring completion or undo, validate its resulting
next occurrence against configured hidden-category, hidden-parent and reminder
invariants. Category hiding must use REQ-DOM-013's configuration authority in both
preflight and reconciliation. A valid own hiding policy on this or another item
in a visible category must not reject recurring completion or undo, and must not
cause a post-acceptance hidden-category error. A locally known violation in an
actually configured hidden category must fail before mutation.

After every accepted recurring mutation, synchronize and reconcile authoritative
recurrence, due, reminder, and hierarchy state. An unexpected invalid normalization
is a nonzero partial failure that identifies the accepted mutation and prevents synchronized success
until external repair and successful read-only synchronization; it must not be
rolled back or described as unchanged. Preserve genuinely invalid-state rejection;
do not suppress validation to avoid the reported failure.

If the mutation was accepted but reconciliation or cache publication subsequently
fails, preserve that acceptance, stop later operations, and make the read-only
recovery path explicit under REQ-CLI-032 and REQ-CACHE-008. Recovering the cache
must not issue another completion or undo. A cache-only failure does not itself
mean Todoist data needs external repair.

### REQ-COMP-008 — Recent reopen, restored ancestors, and recurring undo

```console
todo reopen SELECTOR...
```

Reopen exists only to correct recent mistaken completion. It accepts no comment/text creation, but accepts REQ-CLI-031 literal selector
escaping, and must select only eligible completion occurrences in
`(report cursor, now]`. A non-recurring candidate must currently be completed.
An already-open ordinary object, an older occurrence, or an occurrence at or
before the cursor must fail unchanged.

Reopening a parent leaves completed steps completed. Reopening a step may cause
Todoist to reopen its completed ancestor chain; the complete predicted chain must
be checked for active sibling-title conflicts before mutation and every actually
reopened ancestor must be printed afterward.

Only the latest completion occurrence of a recurring object is eligible. Undo
must use Todoist's recurring completion operation in the backward direction and
move recurrence backward exactly one occurrence, not use ordinary REST reopen.

### REQ-CREATE-007 — Task and step creation grammar, defaults, and ordering

Canonical forms are:

```console
todo add task [--done|--close|--closed]
              [--priority P|-p1|--p1|-p2|--p2|-p3|--p3|-p4|--p4]
              [--at WHEN|--due WHEN|--schedule WHEN] [--hide] [--reason REASON]
              [--reminder OFFSET]...
              --category CATEGORY --title TITLE... [--step STEP...]...
todo add step [--done|--close|--closed]
              [--at WHEN|--due WHEN|--schedule WHEN] [--hide] [--reason REASON]
              [--reminder OFFSET]...
              SELECTOR... --step STEP... [--step STEP...]...
```

Scalar options accept separated/equals forms under REQ-CLI-031. Creation extracts
recognized options and their values before interpreting remaining positional
category/title or parent/step operands, whether the options precede or follow them.
Short forms `todo add [OPTIONS] CATEGORY TITLE...`, `todo add task [OPTIONS]
CATEGORY TITLE...`, and `todo add step [OPTIONS] TASK STEP...` keep one category
or parent-selector argument and apply REQ-CLI-012 to the remaining original text
arguments. Quote multiword scalar option values and positional category/parent
arguments. Scheduling/hiding/reminder options must not require explicit category/
title markers. Explicit title/step groups retain the same independent batching.
For example, `todo task --add --p1 --at tomorrow gatekeeper "Discuss OCA security
issues"` creates one task without requiring --category or --title.

A request may create several tasks in one category or steps under one selected
open parent, which may be a task or a step. Each receives its supported request
options. Several new tasks with
any inline --step remain invalid before synchronization/mutation; do not guess or
copy inline steps across parents. Inline steps of one new parent remain valid.

Task priority defaults to P2; explicit values accept 1..4, case-insensitive P1..P4,
-p1..-p4 and --p1..--p4. Conflicting forms are rejected. Step creation has no
priority option and copies the parent's effective priority. Existing steps may
still be reprioritized through their supported mutation/alias.

Before the first create, validate every title, option, active sibling-title set,
capability and affected invariant, including collisions within a batch. Completed
same-title siblings remain ignored under REQ-DOM-007. Create in group/argument
order, finish one object's options/completion before the next, and retain the
existing parent/inline-step order. A failure/unknown stops later work, preserves
accepted creations and reports accepted, failed/unknown and unattempted outcomes;
no transactional rollback is introduced. Shared relative inputs use one validated
command-time/account-timezone basis. Parent options apply only to the parent;
inline steps remain unscheduled.

The selected parent in todo add step may be any open managed task or step with
room for another level. Use REQ-CLI-035 over both types and the existing ambiguity
chooser; do not treat a matching step as an invalid parent. Every --step group
adds direct children of that one selected parent, not children of the previously
created step. Repeated groups create siblings. A parent at depth 4 is rejected
before any create request. Existing inline steps on one newly created task are
still depth-1 siblings. There is no nested-batch or path-selector syntax.

```console
todo add step "Prepare slides" --step "Collect figures"
todo add step "Collect figures" --step "Check sources"
```

### REQ-CREATE-008 — Creation-time scheduling, hiding, reminders, and completion

Task and step creation support initial attention through --at or aliases
--due/--schedule, repeatable reminders, boolean --hide and optional scalar --reason, following
REQ-CLI-031 and REQ-SCHED-012, REQ-SCHED-013, REQ-SCHED-010, REQ-SCHED-014. Repeated or mixed date aliases are invalid.
Creation with --hide requires an explicit future account-local attention day;
a reason is optional and no default reason/date is generated. --reason is valid
only with explicit --hide in creation/schedule; todo hide implies that context.
An explicit empty reason produces no reason block/comment. Preserve normal text
validation and reject malformed marker lines.

For several new steps, requested attention/reminders/hiding/completion apply to
each. Validate the complete batch and parent/step invariants before any creation.
Later failure preserves earlier accepted objects. Inline steps on a new task do
not inherit its scheduling/hiding options.

Creation-time --done/--close/--closed remain equivalent and cannot be combined
with attention, recurrence, reminders or hiding or target a recurring item.
Complete inline steps before their new parent; retain normal occurrence and
partial-failure rules.

### REQ-MUT-001 — State-transition and complete no-op rejection

Every ordinary mutation must operate only on an item in the documented source
state. Completion of completed state, reopen of ineligible state, and editing a
completed item must fail without workaround reopen/recomplete mutations.

After selection and synchronization, compare the complete proposed observable
result with current state. A proposal changing nothing must fail before a Todoist
mutation and identify the unchanged property/value. Examples include setting the
current priority, renaming to the current title, moving to the current category,
clearing an empty reminder set, and setting the cursor to its current instant.

Preserving one field while changing another is a real mutation. Creating another
comment with identical text is also real because identity differs. Repeatable init
and an unchanged valid comment-editor buffer are successful maintenance/inspection,
not state transitions.

All locally decidable validation must precede the first remote mutation. The only
allowed post-acceptance validation path is documented Todoist normalization and
reconciliation; its accepted state must be reported as a partial failure when invalid.

### REQ-MUT-005 — Priority, rename, and category operations

Supported forms are:

```console
todo priority SELECTOR... P
todo rename SELECTOR... --to NEW_NAME...
todo category --add NAME...
todo add category NAME...
```

Priority must select an open task or step and accept numeric or case-insensitive
`P`-prefixed values `1` through `4`. Output must show the stored previous and new
priority; task-group effective priority is recalculated but not another editable
property.

Rename must support open tasks and steps. Active sibling-title uniqueness must be
validated before mutation, while completed same-title objects are ignored silently.
Rename to the current title is a no-op error. No merge or implicit rename is
allowed. Successful output must identify object type and previous/new title.
Moves are defined by REQ-MUT-004.

Category listing is defined by `REQ-CLI-021`. Category creation joins its name as
one value, rejects a case-insensitive current-name collision before mutation, and
supports the aliases in `REQ-CLI-033`.

### REQ-MUT-004 — Category moves and task/step conversion

```console
todo move SELECTOR TARGET...
todo move SELECTOR ''
todo move SELECTOR... --category CATEGORY...
todo move SELECTOR... --to CATEGORY...
todo move SELECTOR... --task PARENT_SELECTOR...
todo move SELECTOR... --task [--category CATEGORY...]
todo move SELECTOR... --task '' [--category CATEGORY...]
```

Move selects one open task or step after synchronization. The positional form is
the primary shorthand; the existing destination-marker forms remain supported.
When `--task`, `--category`, or `--to` is present, retain the existing marker-form
operand boundaries and selection rules below. Otherwise, the first positional
shell argument is the source selector, and all remaining arguments form one
space-joined destination. Quote a multiword source to preserve it as one selector
phrase. Destination quoting is optional; both `release preparation` and
`"release preparation"` form the same contiguous destination phrase. Creation
splitting under REQ-CLI-012 never applies to this destination.

For a nonempty positional destination, combine matching current categories and
matching open tasks and steps in one candidate set. Categories retain
the existing case-insensitive full-name lookup; item destinations use REQ-CLI-035 on
the joined destination phrase. No candidate kind takes precedence, including
when one kind has an exact match. One match selects that destination; no match is
an operational error. Several matches require the existing numbered choice,
cancellation, and non-interactive ambiguity behavior under REQ-CLI-035 and
TPL-AMBIGUITY, with candidate kinds and task/category context visible. Resolve
source selection before destination selection and both before mutation.

Selecting a category moves a standalone task and its surviving steps there.
Selecting a category for a source step must fail unchanged with status `1`, even
if it is the step's current category; it never implies promotion. Selecting a
task or step destination attaches or reparents the complete source subtree as
a direct child of that item and inherits its category throughout the subtree,
subject to the resulting depth and ancestor invariants below.

A sole exactly empty positional destination, `''` or `""`, explicitly promotes
a source step and its complete subtree to a standalone task in its current
category. Preserve the empty
shell argument through parsing. A missing destination is a syntax error, not
promotion. An empty source, a whitespace-only destination, or any mixture of
empty and nonempty destination arguments is also a syntax error with status `2`
before synchronization or mutation. An already standalone source with an empty
destination is the existing complete no-op error with status `1`.

```console
todo move my project release preparation
# selector: my; destination: project release preparation
todo move "my project" release preparation
# selector: my project; destination: release preparation
todo move "write tests" ""
# explicitly promote the selected step in its current category
```

The retained `--category` form selects one current category case-insensitively
and joins its words as a name. Existing
`--to` is an exact alias for `--category` on this command. Supplying both aliases,
repeating either destination marker, or supplying no destination is a usage error.

`--task` with nonempty arguments selects one open task or step using
REQ-CLI-035, preserving its selector-term/phrase boundaries. The retained marker
name denotes the destination parent and does not restrict it to depth 0. Attach
the complete source subtree as a direct child of that item and inherit its
category. Resolve source and destination ambiguities independently
before mutation; cancellation or unavailable interactive selection changes nothing.

Bare `--task` and `--task ''` mean the same explicit promotion to a standalone
task. Keep the current category unless `--category`/`--to` supplies another one.
A sole exactly empty argument or no arguments is promotion; whitespace-only
parent text or a mixture of empty and nonempty parent arguments is invalid, not
promotion. A nonempty parent name such as `none` is an ordinary selector.

In a destination-marker form, omitting `--task` must preserve the parent
relationship. Therefore a category-only move of a standalone task moves that
task and all its surviving descendants; a step
cannot change category without explicit promotion or reparenting. A category-only
request for the step's existing category is a no-op error. If a nonempty parent
and an explicit category are both supplied, the category must equal that parent's
actual category; otherwise reject before mutation, without moving the parent.

Reject a completed destination, self-parenting, or a destination anywhere in
the source subtree. Carry all surviving descendants, including known completed
ones, with their existing relative parent relationships. Before mutation, compute
the new source depth (destination depth + 1, or 0 for promotion/category-root
placement), then add the deepest known descendant's relative depth. Reject if
any resulting item would exceed depth 4; do not flatten, split or drop descendants.
A task or step with children may be reparented when its complete known resulting
subtree fits. Promotion resets the selected root to depth 0, not just one level up.

Use the synchronized managed tree and available surviving-descendant evidence
from supported retrieval and compatible retained history. No exhaustive archive
scan or authoritative proof of childlessness is required. Missing proof alone
does not reject an otherwise valid move, and no known surviving child is itself
a reason to reject. If an undiscovered archived descendant is later retrieved,
validate its actual resulting depth; only a real invariant violation triggers
REQ-DOM-009. Do not silently flatten or repair it. Existing transport, malformed
response and required-pagination failures remain failures.

Validate affected source/destination sibling-title sets, all ancestor/descendant
hiding and attention constraints, and the complete subtree's hidden-category
restrictions before the first mutation. Never clear scheduling or rename an item
to make a move valid. An unchanged parent and category is a complete no-op error,
even with explicit promotion syntax.

Preserve the same source ID, own comments and their IDs, title, description,
stored priority, attention/recurrence, reminders, own hiding metadata, completion
history, and creation timestamp for every moved item. A conversion is a move of existing data, not
deletion and recreation. Recompute inherited visibility and task-group effective
ordering from the new hierarchy. Report/search presentation uses the current role,
parent and category under the existing current-truth policy; moving does not
fabricate a completion or a comment event or advance the report cursor.

Use direct Todoist moves, reconcile the authoritative result, and report resulting
type and changed parent/category under REQ-OUT-020. Existing lock, safe replay,
no-rollback, partial/unknown and cache-validation rules apply. A task with children
may change category as a complete tree or be demoted if the resulting subtree fits.
An incomplete archive does not turn a failed required request into success.

### REQ-MUT-003 — Direct deletion bounds and bounded parent preview

```console
todo delete [--yes] SELECTOR...
```

Deletion must synchronize, resolve open candidates normally, and add only currently
completed non-recurring candidates completed in `(report cursor, now]`. Older
completed objects cannot be selected even if retained for search. A recurring
object must appear once as an open candidate; deletion removes the active recurrence.

Before every deletion, including `--yes`, print the selected scope. Treat a selected
task or step as a subtree root: the preview must include every current open
descendant and every completed
descendant retrievable in `(report cursor, now]`. It must also explicitly warn that
older completed descendants are outside the bounded preview and may nevertheless
be cascade-deleted by Todoist. Do not infer complete childlessness from an empty
bounded preview. No full-history backfill is performed.

Interactive deletion requires affirmative `y` or `yes`; cancellation, EOF, or
non-interactive use without `--yes` exits `1` unchanged. `--yes` skips only the
prompt, never preview or warning. Deletion must call Todoist's direct operation,
never temporarily reopen, and retain no undelete data. API rejection must be
reconciled with Todoist before local state is considered current.

### REQ-SCHED-012 — Attention aliases, expression grammar, recurrence preservation, and clearing

Schedule is canonical; wait/due remain command aliases. --due and --schedule are
exact aliases of --at wherever the date option is accepted, under REQ-CLI-033.

```console
todo schedule SELECTOR... --at WHEN [--hide] [--reason REASON] [--reminder OFFSET]...
todo schedule SELECTOR... --due WHEN [--hide] [--reason REASON] [--reminder OFFSET]...
todo schedule SELECTOR... --schedule WHEN [--hide] [--reason REASON] [--reminder OFFSET]...
todo schedule SELECTOR... clear
todo schedule SELECTOR... --reminder clear
```

WHEN is one nonempty English expression, passed as one shell argument. Scalar
separated/equals spellings are equivalent. The local grammar recognizes:

- ISO dates and date-times, retaining the existing explicit-offset/Z rule for
  attention date-times;
- today, tomorrow or an English weekday with optional H/HH/H:MM/HH:MM;
  a bare weekday is its strict next occurrence;
- next week, meaning date-only attention on the strict next Monday, including
  a week later when today itself is Monday;
- a nonnegative integer (positive for calendar months) with a case-insensitive
  suffix in the table below,
  optionally separated from it by spaces. Singular/plural suffixes are aliases
  regardless of the count, so 14day and 14days both mean 14d.

| Unit | Suffixes |
| --- | --- |
| Minutes | m, min, mins, minute, minutes |
| Hours | h, hr, hrs, hour, hours |
| Calendar days | d, day, days |
| Calendar weeks | w, wk, wks, week, weeks |
| Calendar months (positive integer) | month, months |
| Business days | bd, business day, business days |

Month singular/plural forms are independent of agreement with the positive count:
"1 month", "1 months", "5 month" and "5 months" are all locally understood.
Case and optional spaces follow the shared suffix rule; m remains minutes, not
months. No new month-based reminder unit or local recurrence grammar is added.
These expressions work in creation, ordinary scheduling and hiding, including
parent/step comparisons; they must not be routed to the unknown-expression path
merely because --hide is present. Arithmetic is defined by REQ-SCHED-013.

Other nonempty expressions, including recurring expressions and `next Friday
10:00`, pass unchanged to Todoist's English parser when no locally resolved day
is needed for preflight; they are then reconciled. Unknown expressions must still
fail before mutation when a required parent/hiding/reminder comparison cannot be
performed. A required local comparison must distinguish an absent date from an
unresolved supplied expression, quote the expression, and show a locally supported
example or ISO alternative. For example --at "banana" with hiding must not claim
that no date option was supplied. Known invalid input causes no remote mutation
and leaves the existing cache unchanged under REQ-CACHE-008.
ask, none and '-' remain invalid attention values. Any repeated or mixed
--at/--due/--schedule aliases are invalid. No separate report weekday grammar is added.

When moving the current occurrence of an existing recurring item using a locally
resolved date/time, retain its existing recurring expression, is_recurring flag,
language and applicable recurrence timezone. Do not construct a nonrecurring due
value merely because the requested new occurrence date is nonrecurring text such
as tomorrow or 14days. Todoist remains authoritative for normalized state and
advancement; validate the retained rule and occurrence after acceptance. A newly
supplied recurring expression may intentionally replace the pattern through the
existing Todoist-parser path. A new recurrence-off switch is not introduced.
Preserve current exact-time/reminder eligibility: choosing a date-only occurrence
cannot silently discard existing reminders. Recurrence preservation does not keep
a second original date or guarantee a backlog of missed occurrences.

Scheduling without --hide preserves existing hiding and its optional reason.
Its new attention day becomes that policy's visibility day. Non-hidden items
remain non-hidden. Use unhide for removal. Supplying --hide still requires an
explicit attention expression in schedule; use todo hide to reuse an existing
one. Literal trailing clear retains its existing syntax and removes attention,
recurrence, reminders, waiting label and reason. --reminder clear removes only
reminders. All obey complete no-op rejection; no --clear aliases are added.

### REQ-SCHED-013 — Account timezone, DST, and local-relative attention semantics

Offset-free attention uses the last authoritative Todoist account timezone,
never the host timezone. Nm and Nh add elapsed minutes/hours. Nd adds N local
calendar dates while retaining command-time local wall-clock time. Nw does the
same for 7*N calendar dates, rather than forcing 168 elapsed hours across DST.
Nbd/business-day aliases advance Monday-Friday without a holiday calendar and
retain local wall time. Every alias of a unit has identical arithmetic.

N month/months adds N calendar months directly to the command-time account-local
year/month, retaining the local day and wall-clock time. If that day does not
exist in the target month, clamp to that month's last valid day. Do not substitute
30*N days or repeatedly add one month with cumulative clamping: 2026-01-31 plus
one month is 2026-02-28, plus two months is 2026-03-31; 2028-01-31 plus one month is
2028-02-29. From 2026-10-23, "1 month" selects 2026-11-23 at the retained local
time. Use the existing ambiguous/nonexistent-wall-time rejection below. Recurrence
preservation and date/reminder/hiding eligibility remain unchanged.

Today/tomorrow/weekdays/next week, due buckets, visibility days and parent/step
comparisons use that timezone. If local parsing produces an ambiguous or
nonexistent DST wall time, fail before mutation and request an explicit ISO
instant with offset. Explicit-offset values retain their instant independently
of account/host timezone. When sync reports a changed account timezone, it becomes
authoritative for the synchronized workflow and future offline reads under
REQ-LOCAL-005. Aliases do not weaken these rules or add locale/holiday handling.

### REQ-SCHED-010 — Reminder grammar, replacement, preservation, and capability

Each --reminder consumes one shell argument, with the equivalent scalar equals
spelling, and accepts a positive integer followed by the scheduling aliases for
minutes, hours, days or weeks, case-insensitively and with optional separating
spaces. Quote forms such as "30 minutes". Business-day offsets, months, compound
forms, signed or fractional counts and unsupported units remain invalid. Normalize
to whole minutes and reject minute-equivalent duplicates before mutation.

Zero is accepted only with a minute suffix: 0m, 0min, 0mins, 0minute, 0minutes and
their space/case variants mean a reminder at the exact attention instant. Keep the
existing lexical rejection of leading-zero zero forms such as 00m. Zero-hour/day/
week forms remain invalid. Imported integer zero is independent of CLI spelling.
The zero exception does not bypass capability, exact-time, duplication, replacement,
preservation or no-op rules.

Canonical CLI/scalar offset notation for zero is `0m`, including changed or
retained reminder sets in scalar mutation receipts. Shared readable timing blocks
under REQ-OUT-021 instead render it as `at due`, including now, detail and ambiguity
output. Keep positive-offset formatting and marker order. Zero is never absence,
`0d` or `0w`.

One or more reminder markers replace the complete reminder set in marker order.
`--reminder clear` removes all reminders while retaining attention, recurrence,
and hiding. Changing attention without a reminder marker preserves the complete
existing set and successful output must print a nonempty retained set.
These rules include zero reminders: absence of a reminder marker preserves them,
replacement replaces them, and `--reminder clear` removes them. Zero does not
bypass complete no-op rejection.

Relative reminders require a supported Todoist account capability and a timed
attention occurrence. A locally known date-only proposal with preserved reminders
must fail before mutation and tell the user to clear or replace them. For a locally
unknown Todoist expression, snapshot reminders, permit submission only when no
local day comparison is required, synchronize afterward, and compare the due value,
reminders, and invariants. Todoist removal/change or a date-only/reminder conflict
must report accepted attention state as a nonzero partial failure without rollback.

### REQ-SCHED-011 — Waiting label, optional reason metadata, and parent-step invariants

Setting attention without --hide preserves the item's existing own hiding label
and optional reason; it no longer clears them implicitly. Boolean --hide enables
own hiding. A supplied nonempty --reason replaces only the canonical optional
block from REQ-DOM-013; omission preserves it and explicit empty removes the block
without disabling hiding. Preserve ordinary description. Reasonless label-plus-
attention state is valid. Full schedule clear and explicit unhide remove both
own waiting label and reason, with their distinct scheduling effects.

The waiting label resource is required only when adding hiding. Its absence
rejects that operation before mutation and suggests todo init. Unrelated commands
and removing an existing policy do not fail solely because that resource is absent.
No reason is a Todoist comment and no Since date or placeholder is generated.

Before hiding any task or step or moving its own visibility day, validate every
affected open dated descendant at every depth. Before changing a step, validate
its complete ancestor chain. Its attention day may equal/follow but never precede
any own-hiding ancestor's visibility day; exact times on one day are compatible.
An undated descendant may inherit suppression without an own date or label.
Validate the proposed resulting policy rather than an old
policy which an explicit unhide/clear removes. Unknown expressions preventing a
required comparison fail before mutation with a locally understood/ISO hint.
A new explicit hiding request with today/past resulting day fails unchanged under
REQ-DOM-013/REQ-SCHED-014. An ordinary reschedule of an existing expired policy is
not a request to enable hiding and retains normal due-day visibility semantics.

Successful output identifies policy enablement independently from optional reason
presence, alongside actual changed attention/reminders. Do not report none -> none
as the only indication that a reasonless policy was enabled. Apply TPL-MUTATION;
unchanged retained values need not be repeated.

### REQ-SCHED-014 — Explicit hide and unhide commands

```console
todo hide SELECTOR... [--at WHEN|--due WHEN|--schedule WHEN] [--reason REASON]
todo unhide SELECTOR...
```

Hide selects one eligible open task or step using the normal synchronized mutation
and ambiguity rules. With no date option, preserve the exact existing attention,
recurring rule and reminders; a missing attention value fails unchanged with an
example supplying --due. With --at/--due/--schedule, move its one attention value
under REQ-SCHED-012, REQ-SCHED-013, REQ-SCHED-010 and retain existing recurrence. Do not add an independent
unhide date or infer a trailing positional duration/reason; every unmarked argument
belongs to the selector after scalar extraction. Repeated or mixed date aliases
are invalid. Options may precede or follow the selector under REQ-CLI-031. An
unresolved supplied date must use the specific diagnostic in REQ-SCHED-012 rather
than claiming an attention option is missing.

The resulting own attention day must be strictly future in the account timezone.
If today/past, reject the entire request before mutation, including a supplied new
reason/date, and explain that hiding ends at the start of that day. Add the waiting
label, preserve the existing optional reason when --reason is omitted, replace it
when nonempty, or remove only the block when explicitly empty. Empty/missing scalar
rules and --hide boolean behavior follow REQ-CLI-031. Apply whole-tree invariants,
capability, no-op, ordered failure and cache reconciliation; do not bypass them.

Unhide removes only the selected item's own waiting label and optional canonical
reason block. Preserve its exact attention, recurring rule, reminders and ordinary
description. It does not remove parent-inherited hiding or change its siblings;
identify a remaining inherited suppression rather than claiming visibility.
No own policy to remove is a complete no-op error. Full schedule clear remains a
different operation that also removes scheduling. Neither command adds a special
confirmation bypass, new structure provisioning, background work or cache-only
mutation; both use the existing normal mutation protocol.

### REQ-SCHED-005 — Hidden-category moves and invalid external state

Before moving a parent task into a currently configured hidden category, validate
the task and all its steps. Any attention value, recurrence, reminder, waiting label,
or hiding reason must reject the whole move before mutation; the command must never
clear scheduling implicitly.

Hidden policy names match current category names exactly and case-sensitively. A
configured name matching no category has no effect. If an external rename makes a
category hidden while scheduled state exists, reads must still treat it as hidden,
identify the blocking violation, print no partial synchronized normal view, and never change or ignore
the Todoist data. Moving or renaming it back externally is the recovery.

### REQ-REPORT-013 — Cursor boundary syntax and `Nd ago` wall-clock semantics

The report cursor is the locally authoritative UTC instant immediately through
which the last successful final report claimed activity. Default and recent-object
intervals are start-exclusive and end-inclusive.

Report boundaries and cursor values must accept RFC 3339/ISO 8601 date-times and
past-relative `Nd ago` or `N days ago`, with positive integer N and the multiword
value passed as one argument. Relative input means the same local wall-clock time
on the account-local calendar date N dates earlier, not N multiplied by 24 elapsed
hours. Ambiguous or nonexistent resulting wall time must require an explicit offset.
Offset-free absolute values use the account timezone; storage is UTC.

Start after end, a future end, and a future cursor are invalid. Equal report
boundaries are valid and produce an empty interval. Setting the cursor to its
current instant is a no-op error.

`report --show-cursor` reads local state without synchronization.
`report --set-cursor TIMESTAMP [--yes]` sets the explicitly supplied valid value
without Todoist access. Show the previous valid timestamp, `none` if missing, or
`corrupted` if the contents cannot be parsed, plus the proposed resolved timestamp.
A missing/corrupt old cursor is not a prerequisite failure for this setter; use
the valid binding timezone and ordinary configuration/path/permission safeguards.
Do not follow symlinks or bypass unsafe/unreadable-file checks. No task cache or
valid previous cursor is required solely to set the supplied boundary.

Keep the existing interactive confirmation or non-interactive `--yes`. With a valid
old value, warn once that moving backward can repeat work and forward can skip it.
With `none`/`corrupted`, use one warning that the chosen boundary may repeat or skip
work because the old boundary is unknown. Save atomically and print the resulting
cursor without repeating the warning. Never infer a replacement timestamp. Setting
the cursor alone does not prune unreported history or reconstruct previously
reported history that was already discarded.

Absolute boundary input also accepts an ISO date interpreted at account-local
midnight, for example 2026-10-19; an ISO date-time can carry its explicit offset.
Invalid values show absolute examples (2026-10-19 and
2026-10-19T09:00:00+02:00) and relative examples ("2d ago" and "2 days ago"),
explaining that offset-free input uses account timezone and relative days retain
current local time of day. Do not silently add monday/next week/attention-parser
semantics to report boundaries. Other syntax errors follow REQ-CLI-024.

### REQ-REPORT-014 — Fixed-end complete report retrieval

After local syntax validation, a report must acquire the exclusive lock and reload
configuration, binding, timezone authority, and cursor. When `--until` is absent,
capture one end instant immediately before the first Todoist request. Every current
state resource and required current comment must be retrieved completely for
current-truth presentation. Sync/current-comment endpoints are not historical
snapshots bounded by the report interval. Activity and completed-object eligibility
must use `(start, fixed end]`; later activity belongs to the next interval.
Translate endpoint wire boundaries under REQ-SYNC-025 without losing fractional
seconds or window-edge events. Query overlap used to establish complete retrieval
does not change eligibility, fixed-end capture, or cursor advancement.

Retrieval must exhaust each endpoint's actual continuation mechanism and
completed-object windows under REQ-SYNC-025, distinguish missing required state
from valid cursorless completed responses, detect malformed/repeated pagination,
and emit only the progress fragments in
`REQ-OUT-020`. Missing current state, history, object, comment, or page must abort
before intentional normal report output. The implementation must not impose a
local result limit, emit a truncated report, claim an atomic cross-endpoint
snapshot, or perform a second comparison sync.

The unresolved archived-owner failure in REQ-REPORT-011 is an accepted reporting
availability limitation, not permission to omit a qualifying comment. A cold-cache
report need not successfully reconstruct arbitrary old archived owner/parent
metadata. It must fail explicitly when that required metadata cannot be established.

### REQ-REPORT-003 — Preview, finalization, output completeness, and cursor advancement

Supported forms are:

```console
todo report
todo report --final
todo report [--since TIMESTAMP] [--until TIMESTAMP]
todo report --show-cursor
todo report --set-cursor TIMESTAMP [--yes]
```

`--since` and `--until` override boundaries for preview/recovery and never change
the cursor. `--final` cannot combine with either and invalid combinations fail
before external requests.

Non-final reports use the optional configured pager under REQ-OUT-018 and always
leave the cursor unchanged, including a normal early pager quit. A final report
must always bypass the configured pager and write directly to stdout; it must
never launch that command or depend on its availability or exit status.
It must build the complete three-section document in memory, write and flush it
completely, and only then
atomically advance the cursor to the captured end. Only after that succeeds
may it release covered reporting history under REQ-CACHE-006. A successful empty
final report advances it. Retrieval, validation, rendering, write, flush, broken pipe,
interruption before completed finalization, or cursor failure must exit nonzero
and retain the old cursor and needed unreported history. A later history-cleanup
failure does not undo output/cursor success; extra retained records are safe. A
crash after complete output but before replacement may repeat the interval; it must
never silently skip an interval whose output was not completed.

### REQ-REPORT-009 — Activity retention capability, warnings, and hard failure

The required synchronization must provide the current activity-history access,
activity-retention limit, and reminder capability under REQ-SYNC-021. Reporting
must not make a separate plan/capability request or depend on a plan name.

If `activity_log=false` or `activity_log_limit=0`, every report must fail clearly
with a nonzero exit before normal report output or cursor advancement. The failure
must explain that activity history is unavailable or that no history is retained,
as applicable. It must not render an empty successful report or treat zero as
unlimited history. These valid capability values must not block initialization,
synchronization, or unrelated task/reminder operations.

When history is available and the limit is positive, every report must emit the
exact warning form in `REQ-OUT-020` unless `warn_limited_history=false`. A limit of
`-1` is unlimited and emits no limited-history warning. History access must still
be checked: `activity_log=false` fails even when the limit is positive or `-1`.

If the requested start is earlier than retained activity history, the report must
fail before normal output and cursor advancement. A start exactly equal to the
retention boundary is valid. Warning suppression must never suppress or weaken this
hard failure or the unavailable-history failures above. Reminder capability is
independent and affects only operations that request reminders. Existing preview,
final-report, fixed-end, boundary, output-completeness, and cursor safeguards remain
in force. A changed retention/access value after synchronization must affect the
next report even when Todoist returns the same plan name.

### REQ-REPORT-005 — Report framing, ordering, and current-state presentation

Every report must use the exact framing from `REQ-OUT-020` and always include
`Finished`, `Progress`, and `Hidden` in that order, with explicit `None.` in an
empty section. It is an operational current-truth summary, not an immutable ledger.

Use current surviving object text, complete current ancestor chain, current
category, and current managed-scope membership. An object currently outside scope
contributes nothing;
one currently inside may contribute qualifying events from before it entered.
Deleted objects contribute nothing. Concurrent post-boundary edits may affect text
returned by later authoritative requests, while their activity events remain in
the next interval.

Categories sort case-insensitively alphabetically. Within event-based categories,
task groups sort by oldest qualifying event and events sort oldest first. Hidden
task groups and independently hidden steps sort by lowercase title. Every equal-key
case uses the stable tie-breakers in `REQ-OUT-015`.

For recursive Hidden trees, apply that alphabetical ordering within every
immediate sibling set, including necessary context-only ancestors, rather than
flattening or repeating branches. Progress keeps chronological event order with
the ancestor context defined by REQ-REPORT-011 and TPL-REPORT.

### REQ-REPORT-006 — Finished-section occurrence semantics

Finished must contain task completion occurrences only. A non-recurring completion
is included only while the task is currently completed, so ordinary reopened tasks
are omitted. Each still-effective recurring completion in the interval is one line
even though the task remains open at its next occurrence.

For one recurring object, an uncompleted activity event must cancel the latest
unmatched preceding completion. The pair is omitted without storing a local report
tombstone. Comments never move to Finished; `Done:` text remains a normal comment
eligible for Progress by its own event.

### REQ-REPORT-011 — Progress-section step and comment semantics

Progress must contain qualifying completed step occurrences and surviving comments
owned by tasks or steps added or edited in the interval. Group a step comment
under its current root task and identify the owning step; for a deeper owner,
include its ancestor path under REQ-OUT-015. Every depth-1 through depth-4 step
completion belongs to Progress, never Finished solely because that step has
children. Preserve chronological event ordering rather than reorganizing events
into separate branch groups. Never silently attach a step comment to an ancestor.
Include eligible comments on surviving completed steps
as well as open steps, even when the step has no completion event in this interval.
A non-recurring step occurrence is included only while the step is currently
completed. Recurring step occurrences
use the pairing rule from `REQ-REPORT-006`.

If a potentially qualifying surviving comment refers to an archived owner whose
current owner/parent metadata cannot be established through supported evidence,
the report must exit nonzero before normal report output and retain the report
cursor. Diagnose the unresolved owner or parent without exposing unrelated data.
Never silently omit the comment, fabricate current role/parent/category or managed
scope, or turn missing metadata into a deletion claim. Owner-scoped comment text
alone does not establish that metadata. This is an accepted limitation on successful
reporting, including a cold cache with no owner completion in the report interval;
it is not an unconditional requirement to retrieve arbitrarily old archived owners.

Repeated attempts at the same interval may remain blocked. Preserve existing
preview/recovery boundaries and the explicit, confirmed `report --set-cursor`
workflow in REQ-REPORT-013, REQ-REPORT-003, including its warning that moving forward may skip
work. No automatic skip, cursor adjustment, or new recovery command is introduced.
Archived owners that can be resolved still require their eligible current comments;
the limitation does not weaken pagination, time boundaries, or successful known-owner
post-completion comments.

Comment eligibility and ordering must use `note:added` and `note:updated` activity
times, never original `posted_at` alone. Several qualifying add/edit events for one
surviving comment in one interval collapse to one entry with current text and the
latest qualifying event time. A later-period edit makes it eligible in that later
period. Deleted comments are omitted.

### REQ-REPORT-015 — Hidden-section snapshot semantics

Hidden must be a current-state snapshot independent of the report interval. It
must contain every task currently suppressed by its own temporary hiding policy,
including one with no interval activity, and must exclude work hidden only by a
configured hidden category.

Include independently own-hidden steps at every supported depth, even when none
of their ancestors has an eligible own policy. Preserve all necessary context
ancestors once; context alone does not make an ancestor independently hidden.

Each task must show its current attention boundary and optional actual reason.
An independently own-hidden step must be nested at its actual depth with its
optional reason and all necessary context-only ancestors. A step hidden only by
inheritance must not be counted or repeated as an own-hidden item; it may appear
once as structural context for an independently own-hidden descendant. Reasonless
policies remain in the
snapshot; omit the inapplicable Reason line instead of inventing text or removing
the item. Membership ends at the beginning of the account-local
attention day even though the stored waiting label remains.
