# Human-readable output contract

Status: **Accepted**

todo-3 specification, revision 2. See [README](README.md).

### REQ-OUT-019 — Streams, color, exit codes, and untruncated text

Normal results, previews, prompts, and accepted-change details must use stdout.
Warnings, errors, retry notices, retrieval progress, cache-coverage information,
and partial-failure summaries must use stderr. Prompting is permitted only under
`REQ-CLI-032`.

Color must follow `REQ-CLI-030` and must never carry the only indication of
meaning or severity. Color-stripped output must retain identical words, spaces,
markers, ordering, and meaning.

The application must not truncate or reflow output based on terminal dimensions.
Optional configured paging follows REQ-OUT-018 across read-only result views;
without a configured pager output is direct. `todo report --final` always bypasses
the pager. Pager-owned visual wrapping does not alter the rendered document.
Every line of multiline user text must retain its line boundaries and receive the
documented indentation. Exit status must follow `REQ-CLI-030`, including `130`
under `REQ-LOCAL-006`.

### REQ-OUT-015 — Common formatting, timestamps, empty values, and tie-breakers

Hierarchy indentation must be two spaces per level. Open and completed markers
must be `[ ]` and `[x]` where state markers apply. The open-only flat `now` queue
and compact waiting view omit these redundant markers under TPL-NOW/TPL-WAITING.
Priorities must render as `P1` through `P4`. An applicable absent scalar or empty list must render as `none`;
optional fields may be omitted
only where the field does not apply. A reasonless hiding policy has an enabled
state with no reason field; absence of that reason is not absence of the policy.
TPL-DETAIL and TPL-COMMENTS explicitly use
single-line `Waiting: none`, `Steps: none` and `Comments: none` where applicable,
and omit absent optional description and scheduling suffixes. TPL-NOW omits the
entire absent due field under NO DATE; other contexts retain their stated absence
representation.

Absolute instants must be converted to the authoritative Todoist account timezone
and rendered with seconds as `Fri 14 Aug 2026, 16:30:42`. The `now` header and
relative attention labels have the explicit forms in REQ-OUT-021 and TPL-NOW.
TPL-DETAIL and TPL-COMMENTS instead use account-local `YYYY-MM-DD HH:MM` for
comment and step-added timestamps, without seconds. A missing timestamp renders
`none`; never invent one. These compact displays still sort by full instants.
TPL-DETAIL renders actual timed attention as `YYYY-MM-DD HH:MM:SS IANA_TIMEZONE`
and date-only attention as `YYYY-MM-DD` without an invented time. TPL-WAITING
renders the account-local hiding day as `YYYY-MM-DD`, not a timed deadline.
Report headers must also render the IANA timezone name. Comparisons and ordering
use full instants.

After every documented semantic sort key, stable Todoist object ID must be the
unprinted final tie-breaker. Activity ties must use event instant, then non-null
event ID, then object ID and stable source order. IDs must remain unprinted unless
a corrupt-state diagnostic cannot otherwise identify the object.

A step's ANCESTOR_PATH is the complete current chain of ancestor titles, root
task first and immediate parent last, joined by the literal separator ` > `.
The selected item's title is excluded. At depth 1 this is exactly the existing
parent title. Preserve full Unicode titles; this human display is not a parsed
path selector or machine identity. Titles containing the separator remain literal
user text and matching continues to use only the item's own title.

Flat now rows, task/step ambiguity choices, step detail headers and owner-comment
headers/receipts use ` — ANCESTOR_PATH` wherever the existing template has a
parent-title suffix. Task headers have no such suffix. Full paths may exceed
terminal width and must not be truncated. Grouped lists retain actual recursive
indentation instead of flattening children. Intermediate context-only ancestors
are included once where needed and do not gain match, completion or hidden-item
eligibility from their context role.

### REQ-OUT-020 — Exact output templates and fragments

The following named templates are exact after placeholder substitution and the
edge-newline rule in `REQ-OUT-009`.

#### TPL-EMPTY — Successful empty views

Each applicable command prints exactly one of:

```text
No actionable items.
No waiting items.
No someday items.
No matches.
```

An empty `search --all` instead prints:

```text
No matches in open or retained completed items.
```

#### TPL-AMBIGUITY — Candidate choice

```text
Multiple items match "report":
  1. task: Report  due:today — Work
  2. task: Weekly report  due:3d overdue — Admin
Select 1-2, or q to cancel:
```

A step candidate has this line shape:

```text
  3. step: Write report  due:in 2d — Weekly review — Admin
```

A completed candidate appends:

```text
  4. task: Report  due:none — Work — completed Fri 14 Aug 2026, 10:00:00
```

A positional `move` destination choice may mix category, task and step
candidates under the same heading and numbering. A category candidate uses:

```text
  1. category: Release
```

Task and step candidates insert two spaces and their own `due:` block immediately
after the title, before the existing parent/category/completion context. Use
REQ-OUT-021 timing, recurrence/reminders and urgency colors: overdue is red,
other present dates blue. An absent attention renders uncolored `due:none` here
because no NO DATE section supplies that context. Completed timestamps remain
separate and never substitute for the object's attention. Category candidates
have no date block. This applies to the shared chooser, including task/step
move destinations and non-interactive candidate listings, with the normal color
policy and without extra network requests or changes to candidate ordering.
No candidate kind receives silent preference. A nested step candidate keeps
its step type and full ancestor path before category/completion context. The
existing prompt,
cancellation and non-interactive fragments apply to this mixed choice too.

Invalid interactive input prints:

```text
Enter a number from 1-2, or q.
```

Non-interactive ambiguity prints the same heading and numbered candidates to
stdout, omits the prompt, and prints this stderr fragment:

```text
todo: multiple items match; interactive selection is unavailable
```

The quoted query, numbering range, titles, types, category/parent context, and
timestamps are substituted without changing punctuation or field order.

#### TPL-LIST — Work-list records

This existing hierarchy template applies to list surfaces other than `now` and
`waiting`. Those views use TPL-NOW and TPL-WAITING respectively.

```text
Work
  [ ] P1 Deploy staging — Fri 14 Aug 2026, 16:30:42
    [ ] P2 Write migration — none
    [x] P2 Draft rollback plan — none
```

When applicable, hiding lines immediately follow their item:

```text
    Hidden until: Mon 17 Aug 2026, 00:00:00
    Reason: waiting for client approval
```

Retain complete multiline reasons under REQ-OUT-019 on these other list surfaces.
When a valid own hiding policy has no reason block, retain its Hidden until line
and omit the inapplicable Reason line. Do not skip the item or manufacture a reason.
The compact waiting-reason interpretation in REQ-OUT-017 applies to TPL-NOW,
TPL-DETAIL and TPL-WAITING; it does not change this fragment or report output.

Recursive list structure follows the same two-space increment, for example:

```text
Work
  [ ] P2 Launch — none
    [ ] P2 Prepare slides — none
      [ ] P2 Collect figures — none
        [ ] P2 Check sources — none
```

#### TPL-NOW — Urgency queue

A nonempty `now` view has this exact header shape:

```text
NOW · Mon 19 Oct 2026 · 08:00 Europe/Prague
9 actions · 2 overdue · 2 today
```

Substitute the account-local weekday/date, 24-hour hour/minute, IANA timezone,
total included task-and-step row count, and Overdue/Today row counts. Use the
literal labels `actions`, `overdue`, and `today` for all counts, including one.
The timestamp represents the same current-time reference as the classification.

Omit empty sections. Each rendered section is separated from the header or prior
section by one blank line. Its heading is one of `OVERDUE (N)`, `TODAY (N)`,
`NEXT 7 DAYS (N)`, `NO DATE (N)`, `LATER (N)`, in REQ-DOM-010's order. `N` counts
included task and step rows in that section, excluding annotation lines.
Use these row shapes, with two leading spaces and two spaces before a present
`due:` block:

```text
  P1 Submit client proposal  due:2h left reminders:at due, 1h before
  P1 Collect audit evidence  due:2d 7h left — Prepare for audit
  P2 Review budget  due:in 23d ↻ every 2nd monday
  P4 Deploy production
```

Substitute the item's own priority, complete title and REQ-OUT-021 timing block.
Under NO DATE, omit `due:none` and its two-space separator entirely because the
heading already establishes absence. Preserve any parent suffix, with one space
before its em dash. Do not omit absence fields from unrelated contexts merely
because this section does. Scheduling validation still rejects inconsistent
undated recurrence/reminders; hiding/metadata invariants are unchanged.
If an actual own waiting reason exists, append ` (REASON)` after the complete timing
block using REQ-OUT-017. A reasonless policy has no annotation/empty parentheses;
its visibility still follows its waiting label and attention day. Do not print separate `Hidden until:`, `Reason:` or
`Since:` metadata lines. For multiline reasons, keep the first line on the row,
indent each continuation four spaces, and close the parenthesis on the final
reason line; retain internal blank lines and all actual reason text. These are
continuations, not actions, and do not affect counts. This applies consistently
to included own-waiting rows in every now variant, including `--all`; inherited
waiting alone does not duplicate the parent's reason onto a step.
Only step rows append ` — ANCESTOR_PATH`, after the timing block and any waiting
annotation, on the final continuation line when necessary. Task rows have no
parent suffix. No category/project names, checkbox markers or nested child
rows are printed in this queue. Parent titles are context, not duplicate actions.
Do not pad or truncate based on terminal width. TPL-EMPTY takes precedence for
an empty view. Existing section-edge newline rules apply.

A deeper step uses the same flat row shape; for example, under NO DATE:

```text
  P2 Check sources — Launch > Prepare slides > Collect figures
```

#### TPL-DETAIL — Task and step details

Use the selected open item's own priority, category and title on one header,
with exactly two spaces between fields. A step appends ` — ANCESTOR_PATH` to
identify its full parent chain. Then print one `Due: ` line. With timed attention,
use
`Due: YYYY-MM-DD HH:MM:SS IANA_TIMEZONE · RELATIVE`; with date-only attention,
use `Due: YYYY-MM-DD · RELATIVE`; with no attention use `Due: none`.
`RELATIVE` is REQ-OUT-021's core text with its initial `due:` removed. Append any
recurrence and every reminder in that requirement's order and wording after the
relative text. Preserve the actual date/time as well as its countdown; date-only
attention never invents midnight or an exact time. Use one current-time reference
for the complete detail. Color the complete value after `Due: ` red when overdue
and blue otherwise under the same existing configured-slot/color policy.
No extra `due:`, separate absent recurrence/reminder fields or redundant open-state
field is printed. Priority is stored own priority, never a group-effective value.

Separate sections with one blank line, in this order: Waiting; optional
Description; Steps (tasks and steps); Comments. Waiting displays own metadata even
when its hide-until day has arrived. When a step has only inherited waiting,
show each ancestor with a stored own hiding policy in root-to-parent order using
`- Inherited from ANCESTOR_CONTEXT: REASON` with that ancestor's available age.
ANCESTOR_CONTEXT is the ancestor's root-to-self title path; for the root task it
is just the task title. When the selected step has own waiting, retain its own
reason display. These annotations do not redefine
whether the item is currently suppressed. For an own policy with no reason,
print the single line `Waiting: enabled`; it describes the stored policy, not a
claim that the item is currently suppressed. A step with only inherited waiting
and one reasonless ancestor policy prints `Waiting: inherited from ANCESTOR_CONTEXT`.
With several inherited policies, use a Waiting heading and one root-to-parent
bullet per ancestor, omitting the colon/reason for reasonless entries. Do not
invent an age/reason or lose inherited context. With no applicable waiting, print
the
single line `Waiting: none` instead of an empty heading/body pair.

```text
P4  Engineer  toupper
Due: 2026-10-19 14:31:32 Europe/Prague · 19h 53m overdue

Waiting
- Should I take it back? (99d)

Steps: none

Comments
- 2026-06-17 09:57  39092259 Difference between SPARC and Intel when it comes to output of toupper()
- 2026-07-13 17:28  D13713
- 2026-07-13 17:28  codex resume 019ed494-27e0-7041-b966-521590681e9e
```

Use REQ-OUT-017 for waiting text and age. A multiline waiting bullet retains
all lines, indents continuations two spaces and places an available age suffix
after the final reason line. Preserve ordinary description text outside the
canonical waiting block, with original line boundaries and two spaces of
indentation beneath a `Description` heading. Omit that section when no ordinary
text remains. Do not repeat the internal waiting block as description text.

The selected task or step's Steps section recursively includes all its current
open descendants and known completed descendants from REQ-CACHE-006. Each successful
task/step inspection prints this coverage disclosure to stderr, including when
no completed history is retained:

```text
todo: completed steps use retained history; coverage may be incomplete
```

This warns that older or unobserved completed steps may be absent. Retained unreported
history survives cache clearing until successful final-report cleanup; its values
are last-observed evidence unless
reconciled against current authoritative data. Steps: none means no known
descendants, not proof of lifetime childlessness. Category inspection does not
gain this task/step disclosure. At each immediate sibling level, use
REQ-CLI-021's known-newest-first order, then unknown creation times in ascending
stable-ID order. Each step uses this compact shape:

```text
- [x] P2 Draft rollback plan — added 2026-08-13 12:00
  Comments
  - 2026-08-14 15:00  Ready for review
```

Retain the completed/open marker, own priority, complete title and added timestamp.
For unknown creation time, the exact added fragment is `added unknown`, for example
`- [ ] P2 Collect figures — added unknown`. Do not omit the item, print a fabricated
date, or issue an invalid-state warning solely because its creation time is unknown.
Nest that step's own comments under it in chronological order using the comment
bullet shape; omit the nested Comments subsection when empty. Completed direct
steps retain their comments and descendants. Render child step bullets two
spaces deeper than their immediate parent's bullet, after that parent's own
Comments subsection when present. A nested Comments heading and comment bullets
remain two spaces deeper than their owning step bullet, as in the existing shape;
comment bullets have timestamps, while child-step bullets have [ ] or [x].
The selected owner's final Comments section contains only its own comments;
never duplicate descendant comments there. Empty Steps and owner Comments use
single lines Steps: none and Comments: none, including leaf step inspection.
Keep a blank line between logical sections, including one-line empty sections.

For example, this Steps section retains a child step's own comments before its
child's bullet; the selected owner's final Comments section remains separate:

```text
Steps
- [ ] P2 Collect figures — added 2026-10-24 10:00
  Comments
  - 2026-10-24 10:30  Use the current figures
  - [x] P2 Check sources — added 2026-10-24 10:15
    Comments
    - 2026-10-24 10:45  Verified
```

#### TPL-COMMENTS — Compact owner comment display

The no-text `todo comment SELECTOR` form uses this exact shape:

```text
Comments for: toupper
- 2026-06-17 09:57  39092259 Difference between SPARC and Intel when it comes to output of toupper()
- 2026-07-13 17:28  D13713
- 2026-07-13 17:28  codex resume 019ed494-27e0-7041-b966-521590681e9e
```

Substitute the selected title and only its own comments. A step appends
` — ANCESTOR_PATH` to `Comments for: TITLE` to retain its full ancestor context; an
ordinary task has no parent suffix. Do not add redundant category/type header
fields. With no comments print `Comments: none` on the next line beneath the
same owner heading. Both here and in TPL-DETAIL, sort comments oldest first by full
current `posted_at` with the existing deterministic tie rules; comments with
missing timestamps follow dated comments, tied by stable ID. Render each first
line as `- TIMESTAMP  TEXT`, preserving two spaces before text. Retain multiline
bodies and internal blank lines; each continuation receives two spaces beyond
the bullet's indentation. No timestamps or IDs are inferred from comment text.

#### TPL-WAITING — Compact current waiting snapshot

Retain category grouping and the existing alphabetical task/step order under
REQ-CLI-027. Use two spaces per actual hierarchy level; steps are indented one
level deeper than their parent. This open-only view omits checkbox markers:

```text
Work
  P1 Deploy  until:2026-10-23 (client approval)
    P2 Plan  until:2026-10-24 (prep)
  P3 Release notes  [context]
    P4 Get review  until:2026-10-25 (reviewer available Sunday)
```

For an own-hidden row, retain own priority and complete title, then exactly two
spaces and `until:YYYY-MM-DD`, then the parenthesized actual reason under
REQ-OUT-017 only when present. A reasonless row ends after its date, for example
`  P2 mailman  until:2026-10-23`; no empty parentheses or placeholder is printed.
The date is the item's account-local hiding day. For a context-only
ancestor of independently hidden steps, retain its priority/title and append
exactly `  [context]`; do not give it a misleading own-hiding date/reason or
count it as an independently hidden item. No `Hidden until:`/`Reason:` detail
lines or duplicate metadata fields follow these compact records. Preserve all
actual multiline reason text: first line on the row, continuations two spaces
deeper than that item's indentation, closing parenthesis on the last line.
TPL-EMPTY still governs an empty waiting view. Visibility and validation rules
are unchanged; this template introduces no new inclusion or scheduling rule.

#### TPL-COMMENT-EDIT — Editor success and partial-failure receipts

For a wholly successful editor save with actual accepted comment changes, print
one stdout line:

```text
Comments updated: toupper · 2 added, 1 edited, 1 deleted
```

Substitute the owner title and exact accepted addition/edit/deletion counts in
that order; keep all three fields, including zero. A step owner appends
` — ANCESTOR_PATH` immediately after its title. Exclude internal validation from
counts and suppress repetitive per-comment success receipts for this all-success
case. A no-change valid save is a successful no-op with no mutation receipt.
This summary is specific to editor reconciliation; ordinary comment creation,
completion and other mutation receipts retain their existing contracts.

A partial failure must retain specific outcomes instead of using a success
summary. A combined terminal example is:

```text
Comments for: toupper — partial failure
  Accepted: edited comment from 2026-07-13 17:28
  Accepted: added “Checked the SPARC result.”
  Failed: add “Sent the follow-up.” — request rejected
  Not attempted: delete comment from 2026-06-17 09:57
```

Print the partial-failure heading and failed/unknown/unattempted details to
stderr; actual accepted-change details remain stdout under REQ-OUT-019. Keep
operation order and enough original timestamp/body or operation-position context
to distinguish the actual affected comments without printing internal IDs.
Retain complete actual multiline text with required indentation where it is
used for identification, and the actual failure reason. Use `Unknown:` for an
unknown remote outcome; never relabel it accepted, failed or not attempted.
This illustrative combined stream does not promise ordering after external
stdout/stderr redirection. Existing cache-usability, read-only recovery,
external-correction and no-replay instructions remain mandatory when applicable;
they may add lines beyond this example. Preserve first-failure stop and no rollback.

#### TPL-MUTATION — Accepted changes

Changed scalar output uses these shapes:

```text
Updated task: Deploy staging
  Priority: P2 -> P1
```

```text
Moved task: Deploy staging
  Category: Work -> Client Work
```

Parent/type changes use the resulting type in `Moved task:` or `Moved step:` and
print a changed parent before a changed category. An absent parent is `none`:

```text
Moved step: Write tests
  Parent: none -> Implement authentication
  Category: Work -> Client Work
```

```text
Moved task: Write tests
  Parent: Implement authentication -> none
```

Only changed parent/category lines appear; a category-only move retains its
existing shape. Parent scalar values use the old/new parent's complete root-to-self
path when that parent is a step, or its title when it is a root task, and none
when absent. Descendants are not reported as separate direct move operations.
For a depth-2 or deeper selected step, append its applicable ancestor path to
ordinary mutation headers; completion receipts use the preserved pre-completion
path if
the owner or ancestors leave active Sync. Restored step ancestors in Also reopened
use their full ancestor path before category, retaining actual operation order.
No accepted-change header is printed before remote acceptance.

Reopened ancestors use:

```text
Reopened step: Run migration
Also reopened:
  task: Deploy staging — Work
```

Task/step/category creation prefixes are exactly `Created task:`, `Created step:`
and `Created category:`. Completion prefixes are exactly `Completed task:` and
`Completed step:`. One accepted object/occurrence is printed in operation order.
Previous-to-result scalar lines use ` -> `; prefixes have exactly one colon.

After a fully accepted task/step creation with requested attention, append
`  Due: VALUE` under its created-object line, using the actual authoritative
date-only `YYYY-MM-DD` or timed `YYYY-MM-DD HH:MM:SS IANA_TIMEZONE`. Reuse the
existing account-local representation; do not print only the unparsed request
string or invent a date when acceptance/reconciliation is uncertain. Creation
without attention retains its compact receipt. Partial/unknown creation still
reports the known accepted work and actual failure under REQ-CLI-032.

Direct accepted comment creation instead prints each actual created body:

```text
Comments for: 39884423 ucrypto_get_mechprop() is not thread-safe — ON test fail on nightly-on-nightly
-> Filed 40189034 Test multithreading access to ucrypto_get_mechprop
-> Resubmitted RTI
```

Show that destination at most once per selected owner, after the first accepted
comment, retaining parent context for a step. When an earlier accepted operation
already identifies that owner (for example completion), do not repeat the heading.
Each accepted body has `-> ` on its first line; preserve actual multiline content
and indent continuation lines two spaces, including internal blank lines. Do not
substitute the owner's title for body text or print a receipt before acceptance.
Completion comments show their actual stored Done: prefix. Preserve specific
failed/unknown/unattempted outcomes. The editor all-success count receipt remains
its separate TPL-COMMENT-EDIT shape.

Hiding state is independent of optional reason text. Changed policy state uses
`  Hiding: off -> on` or `  Hiding: on -> off` beneath the actual Updated task/step
header. A changed reason uses `  Reason: PREVIOUS -> RESULT`, with `none` for
absence and normal multiline indentation. Print only changed fields, alongside
actual attention/reminder changes; enabling a reasonless policy must show the
state change even though both reasons are absent. Ordinary date-only changes of
an already-enabled policy need not repeat unchanged hiding metadata.

#### TPL-REPORT — Complete report framing

```text
Report
From (exclusive): Fri 07 Aug 2026, 16:30:42
Until (inclusive): Fri 14 Aug 2026, 16:30:42
Timezone: Europe/Prague

Finished
  Work
    Fri 14 Aug 2026, 10:00:00 — Deploy staging

Progress
  Work
    Deploy staging
      Fri 14 Aug 2026, 09:00:00 — Completed step: Run migration
      Fri 14 Aug 2026, 09:30:00 — Comment: Ready for review
      Fri 14 Aug 2026, 09:45:00 — Comment on step: Run migration — Checks passed

Hidden
  Work
    Deploy production
      Until: Mon 17 Aug 2026, 00:00:00
      Reason: waiting for approval
```

A reasonless hidden item retains its Until line and has no Reason line; it remains
in the same hidden snapshot population. Finished still contains root-task
occurrences only. Progress remains chronological within its root-task group:
for a depth-2 or deeper step, replace the step-title placeholder in Completed step:
or Comment on step: with TITLE — ANCESTOR_PATH. Preserve the event's existing
indent and its comment-body separator. This retains ancestry without reordering
events by branch. A depth-1 step keeps the existing compact event shape because
the root-task heading already supplies its full ancestor context.

Hidden uses two spaces per actual item level beneath its category, with the
existing Until/Reason fields beneath each own-hidden item. Include necessary
context-only ancestors with `  [context]` after their title and no own Until/Reason
fields; include each ancestor only once. An ancestor with an eligible own policy
keeps its ordinary entry rather than an additional context row. Other report
framing, interval eligibility and event order remain unchanged.

Each empty section must contain:

```text
  None.
```

#### TPL-HISTORY-WARNING — Limited activity retention

For an account reporting seven retained days with history access available, the
stderr line is exactly:

```text
todo: warning: Your Todoist account keeps 7 days of report history; set [report] warn_limited_history=false to hide this warning.
```

Substitute the current positive day count in the same sentence. No plan name is
used. Unavailable or zero-history failures follow REQ-REPORT-009 rather than this
informational warning template.

#### TPL-CACHE-COVERAGE — Completed-search coverage

Every `search --all` prints to stderr:

```text
todo: completed search uses retained history; earliest retained completion: Fri 01 May 2026, 09:00:00; coverage may be incomplete
```

When none is retained, substitute `earliest retained completion: none`.
Retained unreported objects and coverage survive current-cache clearing under
REQ-CACHE-006. Successful final reporting may release them; the exact template
wording does not promise a permanent completed-history archive.

#### TPL-PAGINATION-PROGRESS — Retrieval progress

After pages 10, 20, and every later tenth completed page of one endpoint, print:

```text
todo: loading report activity: 10 pages
```

Substitute the domain resource name and completed page count without changing the
line shape. The line does not assert completion.

### REQ-OUT-009 — Exact-template boundary and section-edge newline normalization

Only fragments explicitly named `TPL-*` in `REQ-OUT-020` are exact prose and
punctuation templates. Other output requirements fix required facts, semantic
order, stream, status, and consistency; their wording is implementation-chosen
and must remain consistent across commands. Examples outside named templates are
illustrative syntax, not additional golden prose.

For each logical template, report section, editor block, or multiline field,
leading and trailing blank lines are ignored when determining equivalence and
content. Internal blank lines, line ordering, indentation, and all nonblank text
remain significant. Output uses LF and may end immediately after its last content
line or with one terminating LF; neither form changes conformance. This rule does
not permit blank lines to split or merge records, move content between sections,
or alter the internal blank-line positions shown by a named template.

### REQ-OUT-021 — `now` and shared attention timing, recurrence, reminders, and color

All `now` variants must use TPL-NOW and each row's own existing attention,
recurrence and reminder data. Use the same view-time reference and authoritative
account timezone as REQ-DOM-010. TPL-DETAIL reuses this timing content and color
with an actual date/time prefix and `Due: ` replacing the initial `due:`.
TPL-AMBIGUITY reuses its `due:` content/colors with an explicit uncolored
`due:none` for absent attention. Waiting
uses TPL-WAITING. Someday, search and report retain their existing formats.

The time block starts with exactly `due:` followed immediately by:

- No attention: omit the timing block on NO DATE rows under TPL-NOW. Where the
  timing content is reused in detail, render the explicit absence `none`.
- Date-only attention: `today` for the current account-local date, `in Nd` for
  a future date, or `Nd overdue` for a past date. `N` is the absolute calendar-date
  difference, not elapsed 24-hour periods. Tomorrow is `in 1d`.
- Timed attention: an elapsed-duration magnitude followed by ` left` or
  ` overdue`, determined by the full signed instant difference. At exact equality
  use `now`. A positive magnitude below one minute is `<1m`; it must not become
  `0m`, change direction, or change section because of display precision.

For timed magnitudes at least 24 hours, display whole elapsed days and remaining
whole hours (`2d 7h`); below 24 hours, whole hours and remaining whole minutes
(`3h 20m`). Truncate the lower unit, omit zero components, and retain the higher
nonzero unit: exactly 48 hours is `2d`, exactly 3 hours is `3h`, and 20 minutes is
`20m`. No seconds appear. An elapsed day here is 24 hours; date-only labels and
section membership still use account-local calendar dates across DST.

If recurring, append ` ↻ ` followed by the authoritative recurrence wording
without translation, case rewriting or local interpretation. User text such as
`kazde utery 15:00` remains unchanged. If recurrence is known but no nonempty
wording exists, append ` ↻ recurring`; never fabricate a schedule. Non-recurring
rows omit this suffix.

If reminders exist, append ` reminders:` followed by every relative reminder,
ordered by offset ascending and separated by `, `. Zero renders `at due`;
positive offsets render `OFFSET before`, using the largest exactly divisible
existing unit among weeks, days, hours, minutes (`1h before`, `90m before`).
An empty reminder list omits this suffix. Recurrence precedes reminders, and both
precede the trailing parent title on a step. Existing reminder validity,
normalization and capability rules remain binding; rendering performs no mutation.

When color is enabled under REQ-CLI-030, the entire time block, including any
recurrence and reminder suffix, uses the configured `red` slot for overdue rows
and configured `blue` for every other present time block. NO DATE rows have no
time block to color. Task titles and parent context are outside this colored block. Use bold emphasis for `P1` and
muted parent context; section-heading styling may use
existing color slots. No new color configuration is required. Color-stripped
output must exactly match the uncolored text, spacing and ordering, with `overdue`,
`left`, `today`, and section labels retaining meaning independently of color.

### REQ-OUT-018 — Opt-in configured paging of read-only views

There is no pager by default. Missing or empty `[main] pager` means complete direct
stdout output, regardless of terminal height. A configured command under
REQ-CONFIG-003 enables external paging when both stdin and stdout are interactive
terminals and TERM is not `dumb`. Pipes/redirection and non-interactive input or
output always receive the complete ordinary output directly.

Configured paging applies to all read-only result views: default `todo`/every
`todo now` variant; task, step and category inspection; no-text owner-comment
display; waiting, someday and search; non-final reports, including explicit
preview boundaries; and `report --show-cursor`. `todo report --final` is an
explicit exception and always writes directly, with REQ-REPORT-003's unchanged
complete-write/flush-before-cursor rule. Help, diagnostics, prompts, ambiguity
candidate choices, mutation previews and mutation receipts remain direct; the
pager must not capture an interactive decision or a partial-failure diagnostic.

For an eligible configured view, deliver the complete rendered document to the
configured external command, including short and empty-result documents. Do not
measure terminal height or bypass the pager because content fits: the pager's
options own fit handling, scrolling, wrapping and navigation. For example,
`pager = less -FR` lets GNU less exit automatically when the view fits and display
ANSI colors. The application must not implement a less-like terminal UI, choose
another pager, append less-specific flags, or introduce a `--pager`/`--limit` flag.
Honor the configured command and arguments; ordering, text, hierarchy, counts,
view filters and eligibility remain the same as for direct output. Paging must
not trigger additional Todoist requests or truncate/filter the document.

Choose application colors under REQ-CLI-030 using the original stdout terminal,
not the child-input pipe. Pass the same colored or uncolored rendered content to
the pager: `auto` must not lose colors solely because the child reads from a pipe,
and explicit `always`/`never`, NO_COLOR and TERM=dumb retain their existing
meanings. The operator chooses a pager/options able to display that ANSI output;
GNU less needs `-R`, as in `less -FR`. Do not force color when it is disabled or
change arbitrary pager arguments to compensate for its display capabilities.

A normal pager exit, including quitting GNU less with q before viewing every
line, completes the read successfully. Non-final reports still leave the cursor
unchanged. A normal early quit must not be diagnosed as a broken-pipe failure or
cause the application to dump the view again. An unavailable executable, launch
failure or actual pager failure must warn on stderr and fall back to the complete
original direct output without refetching it; successful fallback completes the
read, while direct-output failure follows REQ-CLI-030. Handled SIGINT retains
REQ-LOCAL-006's exit 130 and cleanup semantics rather than triggering fallback.
Restore the terminal and clean any temporary delivery state on every exit path.
Exact process/input delivery and failure detection are delegated to Planning.

### REQ-OUT-017 — Compact waiting reason and optional age

For TPL-NOW, TPL-DETAIL and TPL-WAITING, interpret an item's existing canonical trailing
`[todo waiting]` block for presentation without modifying stored description,
labels, attention, hiding policy or cache schema. Remove at most one initial
`Reason: ` label from its body. A single final `Since: YYYY-MM-DD` line is age
metadata only when it is a valid ISO calendar date no later than the current
account-local date. Remove that line from displayed reason text and derive whole
calendar days since that date; same-day waiting is `0d`. On 2026-10-20,
`Since: 2026-07-13` yields `99d`, independent of attention and DST.

TPL-NOW and TPL-WAITING display an actual reason in parentheses and omit age
metadata. With no reason block, omit the annotation/parentheses entirely; do not
mistake that absence for a disabled waiting policy or infer a start date.
TPL-DETAIL uses its explicit reasonless own/inherited state lines.
TPL-DETAIL displays the reason as a Waiting bullet and appends ` (Nd)` when the
recognized date exists. Without a recognized date, omit the age suffix; do not
invent a start date, infer it from attention, or mutate remote content. Invalid,
future, duplicated or non-final Since lines remain literal reason text. If
removing recognized labels/metadata would leave no nonblank reason, display the
original body without an inferred age rather than erase content or fail a valid
read. Ordinary reasons without these conventional labels remain valid. Preserve
all other reason text and line boundaries with the template's indentation.

This is a display interpretation of canonical metadata. It does not require
adding Since dates to new hiding mutations, fetching history or extra network
reads. Existing malformed canonical-block validation
still applies; arbitrary reason prose is not malformed structured metadata.
