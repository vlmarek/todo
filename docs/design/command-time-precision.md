# Command-time precision — current revision 4 amendment

Status: **Accepted**

The operator accepted ordinary timezone-aware Python datetime precision for
urgency, countdowns, relative scheduling and relative report-boundary parsing,
then instructed “do that and continue the work. Stop before any future update to
plan or design.” The actual excerpts and intervening confirmed understanding are
retained in the durable Design handoff, separately from the author interpretation.
No product question remains open in this scope.

## Scope and precedence

For unfinished and successor work, the definitions below supersede only demands
for exact subsecond command-time calculations in the stated scope. Original
definitions remain byte-for-byte protected inputs for accepted assignments.

| Current definition | Earlier definitions affected only in this scope |
| --- | --- |
| REQ-TIME-001 | REQ-DOM-010, REQ-CLI-034/035, REQ-OUT-015/020/021: command-time urgency/countdown comparisons; REQ-SCHED-012/013 and REQ-REPORT-013: relative calculation precision |
| REQ-VERIFY-024 | REQ-VERIFY-016/017/018: exact command-time subsecond distinctions are no longer acceptance obligations |
| OUT-TIME-002 | Excludes exact subsecond guarantees for these calculations and unnecessary precision redesign |

Other consumers of these calculations use the same scoped rule, including cached
views, detail, ambiguity timing and scheduling aliases. References to full/exact
instants or preserving fractions elsewhere do not reintroduce a stricter
command-time comparison obligation here. They retain their storage, ordering,
provider mapping and report-interval meaning. The revision-3 per-file publication
agreement in publication-failure.md remains unchanged. No unrelated requirement
is superseded.

### REQ-TIME-001 — Ordinary datetime precision for command-time calculations

Urgency classification, countdowns, locally relative attention scheduling and
relative report/cursor-boundary parsing may calculate with ordinary timezone-aware
Python datetime precision, including projection from the existing precise instant
representation. Subsecond imperfections caused by those calculations are accepted
and are not defects or acceptance failures. No exact-clock interface or new
rounding model is required. Do not force whole-second normalization.

For example, a due instant and command time that differ only beyond datetime
precision need not distinguish overdue, now and left perfectly. The same allowance
applies to the subsecond component of a calculated relative schedule or `Nd ago`
boundary. Use the existing one command-time reference for each applicable view or
workflow; this allowance does not authorize inconsistent clocks within it.

One-second-or-larger timing errors remain defects. Retain the correct account-local
date and authoritative timezone, elapsed minute/hour versus calendar day/week/month
arithmetic, month clamping, weekday/business-day behavior and local DST refusal.
Date-only attention, hiding/visibility days, recurrence and reminder eligibility
keep their existing semantics. This tolerance does not excuse a wrong calendar
date, timezone, lifecycle decision or unrelated report behavior.

Preserve the existing precise timestamp representation, supplied fractional data,
serialization/reload and full-instant ordering. In particular, item/comment/event
ordering must not use a lossy command-time projection as its sort key. Explicit
absolute input and stored cursor values retain their precision and existing exact
no-op semantics; this is not permission to round stored values or collapse an
explicit small requested time change. Once a relative report boundary is resolved,
the existing exact `(start, fixed end]` eligibility, wire-window coverage, fixed-end
capture, output-before-cursor publication and pending-history cleanup safeguards
remain. Remote reconciliation retains its separately agreed tolerance and strict
date/recurrence/timezone checks.

### REQ-VERIFY-024 — Time evidence within the accepted precision scope

Establish urgency and countdown behavior before, at and after due time using
ordinary datetime precision, with meaningful full-second distinctions. Preserve
the existing calendar/date-only, timezone/DST, cached-clock recomputation, relative
arithmetic and exact output-template evidence. Do not require successful exact
before/equal/after distinctions that depend on subsecond command-time precision,
or treat a permitted calculation projection as a failure by itself.

Retain evidence for precise timestamp storage/reload, full-instant ordering,
absolute boundaries and exact report event eligibility. The relative-boundary
calculation tolerance does not waive fractional event/window-edge coverage after
the boundary is resolved. Existing nested-parent alias selection and other
unrelated acceptance obligations remain. Planning selects the smallest meaningful
affected cases and test layers; no shared exact-clock repair is required.

### OUT-TIME-002 — No exact subsecond command-time guarantee or precision redesign

Exact subsecond agreement for urgency, countdowns, relative scheduling and relative
report-boundary parsing is excluded. A shared exact-command-clock repair, a new
rounding architecture, forced whole-second normalization and a precision-storage
migration are outside this amendment. Existing precise storage and ordering remain
required; the tolerance does not create a general waiver for timestamps, reports,
calendar/timezone errors or unrelated lifecycle behavior.
