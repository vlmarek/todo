# Attention and completion dates in item rows — revision 14

Status: **Accepted**

## Agreement and precedence

The operator wants actionable scheduling information in Steps instead of creation
dates. They agreed to actual attention dates plus countdowns, said "no, do not
show anything (including the dash between text and due date)" for undated steps,
and chose "completion date" for completed steps. They agreed to extend this rule
to search, someday and task/step selection menus, then confirmed the complete
scope and request to document it with "yes". The external Design report retains
the exact choices and confirmation context separately from interpretation.

REQ-OUT-023/024 are narrow successor definitions for future and follow-up work.
They override only date-field choice, formatting and absence in REQ-OUT-015 and
REQ-OUT-020's TPL-DETAIL Steps rows, TPL-LIST rows used by search/someday, and
TPL-AMBIGUITY task/step candidates. They also override REQ-OUT-021's relative-only
candidate timing and explicit due:none rule on that selection surface. Earlier
definitions and accepted effective assignments remain unchanged as history.
Named templates remain exact except for the replaced fragments defined here.

### REQ-OUT-023 — State-appropriate dates on Steps, search, someday and candidates

Apply one date-selection policy to every descendant row in the selected task or
step's Steps section, every task/step row in search (including --all) and someday,
and every task/step candidate in interactive or non-interactive selection menus.
The candidate rule applies wherever selection is used, including mutations and
mixed task/step/category choices; category candidates retain their existing shape.

For an open item with its own attention, show `due:ACTUAL · RELATIVE`.
ACTUAL uses the existing detail attention representation: YYYY-MM-DD for date-only
values, or YYYY-MM-DD HH:MM:SS IANA_TIMEZONE for timed values in the authoritative
account timezone. RELATIVE uses existing REQ-OUT-021 countdown wording and
calendar/elapsed-time semantics. Use one view-time reference throughout each
rendered document. Never inherit a parent's attention or invent midnight for a
date-only value. Preserve applicable open-item recurrence and reminder wording,
order and authoritative values under the existing scheduling-output contracts.

For an open item without attention, omit the date field entirely: no due:none,
none, added unknown, placeholder date, date separator or empty date-field spacing.
This does not remove independently applicable non-date metadata or ancestor and
category context. A parent with attention does not give its undated child a date.

For a completed row or candidate, show `completed YYYY-MM-DD HH:MM` using its
retained completion timestamp in the account timezone. Do not show an attention
date/countdown or creation date in place of, or in addition to, that completion
field. In selection menus this replaces the previous due block plus separate
completion timestamp with a single completion field. A missing completion timestamp
has no date suffix: do not fabricate one or fall back to added/attention dates.
This presentation fallback does not relax existing domain/provider validation or
require accepting an otherwise invalid completed record. Recurring objects that
remain open use their active attention; an eligible completed-occurrence candidate
uses the selected occurrence's existing completion timestamp.

### REQ-OUT-024 — Exact date fragments and preserved surrounding structure

Steps retain `- [ ] Pn TITLE` or `- [x] Pn TITLE` with existing nesting. Search
and someday retain their existing `[ ] Pn TITLE` or `[x] Pn TITLE` rows. Append
` — due:ACTUAL · RELATIVE` for an open dated row, or
` — completed YYYY-MM-DD HH:MM` for a completed row with a timestamp. Otherwise
the row ends at its title unless independently applicable metadata follows.

Task/step candidate rows retain numbering, role and title, then append exactly
two spaces followed by the same applicable `due:ACTUAL · RELATIVE` or
`completed YYYY-MM-DD HH:MM` field. If absent, omit that field and its two-space
separator. Existing ancestor/category context follows in its existing order with
its own separators. Do not leave the old extra completion suffix at the end.

For a view on account-local 2026-10-28, these date-only examples are exact shapes:

```text
Steps
- [ ] P4 Broken rpool disk — due:2026-10-29 · in 1d
  - [ ] P4 Tell Jakub Jirsa about it
- [x] P2 Investigate outage — completed 2026-10-28 19:30
```

```text
Work
  [ ] P2 Prepare report — due:2026-10-29 · in 1d
  [ ] P4 Collect ideas
  [x] P2 File report — completed 2026-10-28 19:30
```

```text
Multiple items match "hardware":
  1. task: Ask for new hardware  due:2026-10-29 · in 1d — Gatekeeper
  2. task: Broken failed hardware — Gatekeeper
  3. step: Replace hardware  completed 2026-10-28 19:30 — Broken failed hardware — Gatekeeper
Select 1-3, or q to cancel:
```

Existing prompt/input/cancellation and non-interactive error templates still apply.
The complete open attention block uses existing urgency colors (red overdue,
blue otherwise) where the existing view color policy enables color. Completion
fields carry no overdue/countdown styling. Color-stripped text has the exact same
fragments and spacing. Preserve priorities, state markers, full titles, nested
comments, ancestor/category context, grouping, filters, counts and coverage warnings.
Do not change ordering: Steps remain newest-added-first per sibling level under
REQ-CLI-021; the other surfaces retain their existing sort and tie-breakers.

### REQ-VERIFY-032 — Date choice, omission and shared display outcomes

Establish representative offline evidence that an open dated row shows its actual
attention plus the correct countdown, while an undated row has neither a date
placeholder nor a dangling separator. Include nested Steps with different own
dates or an undated child, and a completed row whose added, attention and
completion values differ, so selecting the wrong timestamp is observable.
Establish the corresponding shared behavior in search/someday and candidates,
including search --all, a completed candidate and preserved candidate context.
Include a timed attention example in the account timezone; use existing date-only,
calendar, countdown and color behavior rather than a new timing model.

Preserve unrelated ordering and the unchanged view formats below. Planning owns
test organization, representative shared coverage and exact verification commands;
do not multiply every case across commands or test layers. No live-account or new
provider-research gate is introduced.

## Boundaries, implementation choices and evidence

This revision excludes changes to now, waiting, the selected task/step's top-level
Due line, comment timestamps, report/cursor dates, mutation receipts and previews
other than candidate selection menus. It adds no command, sorting mode, storage
migration, history retention, remote retrieval, synchronization or completion
reconciliation policy. Creation timestamps remain stored and keep their existing
ordering role. Existing report/history limitations and cached-selection policy
remain in force.

Existing code stores attention, added and completion values separately. Its Steps
renderer currently prints added; search/someday print attention or none; candidate
rendering combines relative attention with a separate completion timestamp. These
are implementation observations, not authority for the changed product agreement.
Current validation requires completion timestamps for completed stored objects;
the absent-completion display rule adds no new acceptance of malformed data.

No unresolved product decision or new external investigation remains for this
scope. Planning must assess affected presentation/workflow interfaces (including
the shared current-time reference), preserve accepted assignments through supported
successor work, and choose implementation and verification details. The change is
a single presentation capability, with no need for a new architecture or staged
integration experiment. This Design handoff is uncommitted and has no production
implementation or execution evidence.
