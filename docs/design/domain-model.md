# Domain model

Status: **Accepted**

todo-3 specification, revision 2. See [README](README.md).

### REQ-DOM-001 — Stable account, root, and category identity

One local binding must identify exactly one Todoist account, one unshared
personally owned root-project ID, and the managed direct-child category IDs.
During first initialization, the configured root name is
matched exactly and case-sensitively. After binding, stable IDs are authoritative:
renames do not rebind scope and a same-named replacement is not adopted.

Current category names and direct-child membership come from Todoist. User-entered
category lookup is case-insensitive, and open category names must be unique under
case-insensitive comparison. A newly discovered valid direct child is enrolled by
stable ID. An empty removed category may be retired, but a moved, archived, deleted,
shared, workspace-owned, or wrongly nested root/category that could discard managed
work is invalid and is never silently replaced or repaired.

### REQ-DOM-009 — Recursive task, step, comment, and text model

A managed task is a top-level Todoist item in one managed category, at depth 0.
Every descendant is called a step, whether its immediate parent is a task or
another step. Steps may occur at depths 1 through 4; there are at most five item
levels including the task. Each item has a stable ID and at most one immediate
parent. All descendants belong to the same category as their root task. A task
or step may have zero or more direct children within this limit.

"Parent" means the immediate parent, which may be a task or step. "Root task"
means the depth-0 ancestor. "Descendants" and "subtree" include every nested level;
a subtree includes its selected root unless explicitly limited to descendants.
Unqualified "steps" in a task tree includes all descendant steps; "direct steps"
means only immediate children. An item's role depends on its current hierarchy,
not a permanent separate identity or implementation type.

An orphan, cycle, cross-category parent link, out-of-scope ancestor, open item
under any completed ancestor, task directly in the project root, or descendant
at depth 5 or greater is invalid managed state. Valid nested steps must be
accepted by init, refresh, incremental merge and cache reload. Resolve
parent references after the complete candidate merge; response order does not
establish depth or ownership. Never flatten, drop or recreate nested items.

Creation and move preflight enforce the resulting depth of the complete known
subtree under REQ-CREATE-007 and REQ-MUT-004. Unknown archived descendants do not
require exhaustive discovery or proof of childlessness. If later discovered,
any actual over-depth descendant remains invalid; valid nested descendants are
not a violation. The supported product boundary follows Todoist's documented
four indent levels. Its API accepts parent_id but publishes no numerical depth
maximum; this is not a claim that API rejection at depth 5 was live-tested.
See external/todoist/README.md for retained provider evidence.

Tasks and steps at every depth retain their own description, comments, priority,
attention/recurrence, reminders, own hiding metadata and lifecycle. Existing
operation-specific restrictions remain in force; nesting adds no new scalar
option or unsupported lifecycle operation. A comment belongs to its owning
item's stable ID; reparenting or promotion does not transfer or recreate it.
Inspection displays recursive children and their own comments under REQ-CLI-021.
Completion changes an item's marker rather than creating another identity.

Single-line task, step, and category titles must be nonempty after trimming and
must reject line breaks, tabs, NUL, ESC, and every other C0/C1 control character.
Multiline descriptions, comments, and hiding reasons may contain LF and tab but
must be nonempty after the applicable edge normalization and reject NUL, ESC, CR,
and all other C0/C1 controls. Todoist's length limits remain authoritative and
must be translated into domain errors. Matching normalization never rewrites
stored Unicode text.

### REQ-DOM-014 — Known and unknown item creation timestamps

A task or step's creation timestamp may be unknown. Preserve a documented null
creation timestamp as unknown through mapping, domain validation, current-cache
and unreported-history serialization/reload, inspection, and hierarchy/lifecycle
operations. A known timestamp remains an aware instant at full supplied precision.
Do not fabricate an epoch, command time, completion time or ID-derived timestamp,
or reject otherwise valid managed state merely because creation time is unknown.
An authoritative null remains unknown rather than being filled from an older known
observation. This does not relax required completion, activity, due or report times;
creation time is not a substitute for any of them. Unknown creation time changes
only its truthful presentation and the creation-time sibling ordering defined in
REQ-CLI-021; urgency, selection and lifecycle eligibility keep their existing rules.

### REQ-DOM-010 — Priority, actionability, and urgency

Priorities are `P1` through `P4`, with `P1` highest. A new parent task defaults
to `P2`. A new step copies its immediate parent's effective priority at creation,
including elevation from any open descendant in that parent's subtree; the copied
value then belongs to the step and does not propagate later. Compute the default
from the synchronized pre-creation subtree; repeated new sibling steps receive
the same copied default. Creating a step never copies dates, reminders or hiding
metadata implicitly.

For a task or step subtree, effective priority is the highest priority among its
open root and all open descendants. Effective attention is the earliest attention
value among them. Completed descendants contribute to neither. These remain
internal derived values
where required, including the step-creation default above; they are not additional
editable or displayed properties and must not rank parent rows in `todo now`.

An actionable item is open and eligible after category and temporary-hiding rules.
`todo now` must place every included task and step in one independent queue row,
using that item's own stored priority and own attention value. A parent's row
must remain present even when its steps occupy other positions or sections; steps
must not transfer their priority or date to the parent row. No category/project
priority or separate deadline field is introduced.

Classify rows into these sections, in exactly this order, using the authoritative
Todoist account timezone and one current-time reference for the complete view:

1. **Overdue**: an exact attention instant is strictly before now, or a date-only
   attention date is before today's account-local date.
2. **Today**: a remaining dated row has today's account-local attention date.
   A timed item exactly at now belongs here and is due now, not overdue.
3. **Next 7 days**: a remaining dated row has an attention date from tomorrow
   through account-local date today + 7, inclusive. These are calendar dates,
   not a rolling 168-hour interval.
4. **No date**: the item has no attention value.
5. **Later**: the attention date is today + 8 or later.

Within each section, sort by own priority `P1` through `P4`, then own attention
earlier first, then lowercase item title, then stable Todoist ID. Date-only
attention uses the start of its account-local date for this ordering; timed
attention uses its full instant. No-date rows skip the date key. Category names,
parent titles, item type and group-effective values are not earlier sort keys.
Stable IDs remain unprinted. A step can precede its parent without implying a
hierarchy change, and an overdue P4 precedes an undated P1.

Exact time never delays visibility past the beginning of its account-local day.
The new instant-based overdue boundary does not change REQ-DOM-013's hiding rules.
Date-only rows retain their full local day before becoming overdue; calendar
classification and elapsed countdown formatting must remain distinct across DST.

### REQ-DOM-012 — Attention, recurrence, reminders, and occurrences

An attention value is one Todoist due specification identifying a date or exact
date/time when an item requires attention; the product does not classify why.
It may recur. The current occurrence's date/time and the recurring expression are
separate fields of that one due specification; moving the occurrence need not
replace its recurring rule. Preserve recurrence under REQ-SCHED-012. Postponing
replaces the current occurrence's old date, so its original lateness is no longer
represented by the active due date. A completion occurrence is one completion
event; a recurring object can contribute multiple occurrences while remaining
open at its next occurrence. Passing a recurrence boundary does not create a
separate accumulating backlog of missed tasks.

An item may have multiple relative reminder offsets before or at an exact
attention time. Each offset is a whole number of minutes greater than or equal to
zero, excluding booleans. Zero means at the exact attention instant; a positive
offset means that many minutes before it. Zero is a present reminder, not absence
or a request to clear reminders. Reminders require an exact time and an account
capability supporting the request. Todoist is authoritative for normalized
due/recurrence data, occurrence advancement, recurring undo, reminders, and
notification delivery.

Offset-free dates, attention days, overdue buckets, and displayed instants must
use the Todoist account timezone. Explicit offsets identify an instant; persisted
instants use UTC.

### REQ-DOM-013 — Own hiding, optional reasons, and effective visibility

The Todoist `waiting` label is the authoritative switch for an item's own hiding
policy. An enabled policy requires the existing attention value. A reason is
optional: the label and attention with no reason block are valid. A reason block
without the label, or the label without attention, remains invalid. No second
hide-until date, generated reason, comment or separate timer is introduced.

A supplied nonempty reason is stored in a trailing description block whose marker
lines are exactly `[todo waiting]` and `[/todo waiting]`, separated from ordinary
text by one blank line when that text exists. Lines use LF. Either exact marker
line inside a reason is invalid. Duplicate, incomplete, empty, non-trailing or
otherwise malformed blocks remain invalid and must not be guessed at or repaired.
Removing the optional reason removes the entire block and preserves ordinary text.
Cache readers, full/incremental mapping, inspection, search, `now`,
waiting/report snapshots, mutations and reconciliation must all determine
own-policy presence from the label rather than reason presence.

An own hiding policy suppresses the item before the start of its attention day
in the Todoist account timezone. The label remains after that day, but the item
is visible. An own-hidden task or step suppresses its complete open subtree before
its own visibility day. Effective suppression is the union of own and ancestor policies.
Hiding a step does not hide its ancestors or siblings. A descendant's attention
day, when present, cannot precede the attention day of any ancestor with an own
hiding policy; exact times on the same day are compatible. Undated descendants
may inherit suppression without acquiring their own date or label. Validate all
affected ancestors and open descendants before mutation. Unhiding removes only
the selected item's own policy and cannot override an ancestor's policy.
Explicit enabling/updating of hiding must reject a resulting own attention day of
today or earlier without mutation and explain that a future day is required.
Existing policies whose day arrives remain valid and visible; ordinary
rescheduling and recurring completion do not silently remove their label.

The `hidden_from_now` configuration remains the sole authority for category hiding.
Names match exactly and case-sensitively; a missing configured name has no effect.
A task in a currently configured hidden category and all its steps must have no
attention, reminder or own hiding policy. An external rename creating forbidden
state must hide the category and diagnose it, never reinterpret or repair it.
An item's waiting label/reason and parent-to-step inheritance must never make its
category or unrelated items hidden. An empty configured list means no hidden
categories, even when individual items retain waiting metadata. Apply the same
category policy before and after remote mutation.

### REQ-DOM-006 — Completion, reopen, immutable-completed, and deletion lifecycle

Completion requires an open item. Ordinary reopen requires an eligible completed
item. A completed item is immutable through ordinary editing and may be selected
only by the bounded reopen or deletion workflows. Any task or step remains open
after its last child completes; there is no automatic upward completion. Completing
a selected item with open descendants uses REQ-COMP-006 recursively: complete all
ordinary open descendants before their parents, including the selected root last.
An open recurring descendant blocks completion of the containing subtree. A
recurring selected root still uses its own occurrence-completion operation after
its ordinary descendants are completed.

Completing a recurring object records an occurrence and advances it while leaving
the object open. Only its latest completion occurrence can be undone, moving the
recurrence backward one occurrence. Reopening a step may reopen its completed
ancestor chain and must preserve active sibling-title uniqueness throughout.

Recent reopen candidates are eligible occurrences in `(report cursor, now]`.
Completed deletion candidates are currently completed non-recurring objects in
that interval. Recurring objects remain one ordinary open deletion candidate and
must not also appear as historical candidates.

Deletion is terminal and uses Todoist's direct operation. Deleted tasks, steps,
comments, and their report/search contributions disappear; no local undelete
snapshot is retained. Current managed scope, current names and parents, and
survival determine report inclusion and presentation.

### REQ-DOM-007 — Active-only sibling-title uniqueness

Open task titles must be unique within a category under Unicode-normalized,
case-insensitive comparison. Open step titles must be unique within their immediate parent
under the same comparison at every depth. Equal titles in different branches
are allowed and remain subject to the shared ambiguity chooser. Creation, rename,
move, and reopen must validate every affected active sibling set before the first
mutation and must never merge or
implicitly rename objects.

Completed objects do not participate in uniqueness checks. Reusing a title held
only by completed siblings is allowed silently: it produces no duplicate lookup,
warning, confirmation, or other behavior. The same rule applies when more than
one completed sibling has that title.
