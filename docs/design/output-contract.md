# Human-readable output contract

Status: Accepted

This document defines the stable human-facing structure of command output. It
is intentionally not a machine API. A future structured format requires a new
Accepted design and is listed in `out-of-scope.md`.

## Streams, color, and exits

Normal results, prompts, previews, and accepted-change details use stdout.
Warnings, errors, retries, and partial-failure summaries use stderr. Prompting
is permitted only when both stdin and stdout are interactive terminals.

Color follows the global color policy but never changes wording, spacing,
markers, ordering, or meaning. Golden fixtures compare color-stripped output.
Output is never truncated, reflowed, or sent through a pager based on terminal
width. Multiline user text keeps its line boundaries and receives the required
indentation on every line.

Exit statuses are:

- `0` for a completed successful request, including defined empty views
- `1` for operational, domain, ambiguity, cancellation, API, output-write, or
  partial-mutation failure
- `2` for invalid command-line syntax or option combinations
- `130` when interrupted by SIGINT before the program handles completion

## Common formatting

Indentation is two spaces per hierarchy level. Open and completed state use
`[ ]` and `[x]`. Priorities use `P1` through `P4`. An absent scalar value is
printed as `none`; an empty list is printed as `none` rather than as a blank
field.

Instants are converted to the Todoist account timezone and displayed with
seconds as `Fri 14 Aug 2026, 16:30:42`. Report headers also print the IANA
account-timezone name. Internally, ordering uses the complete instant.

After every documented semantic sort key, stable Todoist object IDs provide an
invisible final tie-breaker. Activity events sort by event instant, then
non-null event ID, then object ID and stable source order. IDs are not printed
unless a diagnostic cannot otherwise identify corrupted external state.

The fixed successful empty messages are:

```text
No actionable items.
No waiting items.
No someday items.
No matches.
```

`todo search --all` instead uses this line when no open or cached-completed
object matches, followed by the cache-coverage line defined below:

```text
No matches in open or cached completed items.
```

## Ambiguous selection

Interactive ambiguity uses this shape:

```text
Multiple items match "report":
  1. task: Report — Work
  2. task: Weekly report — Admin
Select 1-2, or q to cancel:
```

A step candidate adds parent context:

```text
  3. step: Write report — Weekly review — Admin
```

A completed candidate also adds its account-local completion time:

```text
  4. task: Report — Work — completed Fri 14 Aug 2026, 10:00:00
```

A valid number selects that candidate. `q`, a blank line, or EOF cancels with
no mutation and exit `1`; an invalid number prints `Enter a number from 1-2, or
q.` and prompts again. Non-interactive ambiguity prints the same numbered list,
then `todo: multiple items match; interactive selection is unavailable` to
stderr, performs no mutation or detail rendering, and exits `1`.

## Work-list shape

List views group by category and task. Optional fields are omitted only where
the field does not apply; applicable absent fields use `none` in detail views.

```text
Work
  [ ] P1 Deploy staging — Fri 14 Aug 2026, 16:30:42
    [ ] P2 Write migration — none
    [x] P2 Draft rollback plan — none
```

`todo now` omits completed steps, while task details may show them. Hidden
reasons appear on the line immediately below the affected item:

```text
    Hidden until: Mon 17 Aug 2026, 00:00:00
    Reason: waiting for client approval
```

## Detail shape

Task detail uses fixed labels in this order:

```text
Task: Deploy staging
Category: Work
State: open
Priority: P1
Attention: Fri 14 Aug 2026, 16:30:42
Recurrence: none
Reminders: 1d, 1h
Hidden: no
Description: none
History:
  Comment — Fri 14 Aug 2026, 15:00:00
    Ready for review
  [x] P2 Draft rollback plan — added Thu 13 Aug 2026, 12:00:00
```

Step detail replaces `Task:` with `Step:` and adds `Parent:` before `Category:`.
Comment-only display prints the task/category heading and comments oldest first.
Multiline user text is indented without reflow or interpretation.

## Mutation output

A successful single mutation names the object, then prints changed state. The
arrow templates are:

```text
Updated task: Deploy staging
  Priority: P2 -> P1
```

```text
Moved task: Deploy staging
  Category: Work -> Client Work
```

```text
Reopened step: Run migration
Also reopened:
  task: Deploy staging — Work
```

Creation prints `Created task:`, `Created step:`, `Created comment:`, or
`Created category:` once per accepted object in command-line order. Completion
prints `Completed task:` or `Completed step:` once per accepted completion
occurrence. Reopen never prints or creates an audit comment.

A pre-mutation warning is printed before any corresponding accepted-change
output. A partial failure prints accepted stdout lines as they occur, then one
stderr summary naming the failed operation and every unattempted operation. It
never prints a whole-command success summary.

## Report shape

Every report uses this framing and always prints all three headings:

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

Hidden
  Work
    Deploy production
      Until: Mon 17 Aug 2026, 00:00:00
      Reason: waiting for approval
```

Empty sections contain an indented `None.` line. Categories are alphabetical.
Within an event-based category, task groups are ordered by their oldest
qualifying event and each group's events are oldest first. One recurring
completion line is printed per qualifying occurrence. Hidden task groups are
alphabetical.

The limited-history warning is exactly:

```text
todo: warning: Todoist Free keeps 7 days of report history; set [report] warn_limited_history=false to hide this warning.
```

The plan name and day count come from Todoist. The word `Free` is used only when
Todoist identifies that plan; other limited plans use the same sentence with
the reported plan name and limit.

## Cached completed-search coverage

`todo search --all` always appends a stderr informational line, including when
no completed object is cached:

```text
todo: completed search uses cached history; earliest cached completion: Fri 01 May 2026, 09:00:00; coverage may be incomplete
```

If no completed object is cached, `earliest cached completion: none` is used.
The line prevents a best-effort cached search from claiming complete Todoist
history. It is informational and does not change a successful exit status.

## Retrieval progress

After page 10, 20, and every further tenth page of one paginated endpoint, the
adapter prints this stderr line with the domain resource name and completed
page count substituted:

```text
todo: loading report activity: 10 pages
```

Progress lines do not alter stdout, ordering, or exit status and do not imply
that retrieval is complete.
