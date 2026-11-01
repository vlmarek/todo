# Positional rename, scheduling and hiding — revision 20

Status: **Accepted**

## Agreement, scope and precedence

The operator's attempted `todo rename jklu "Add to nightly jenkins build jkuliks
script to find security bugs in python. So that it is executed periodically"`
failed because rename required `--to`. They requested assessment of similar
switches and then a cml-design discussion. They approved positional rename,
scheduling and hiding, retained explicit forms and multi-term matching, and
declined both multiple-category and positional-category changes to `now`.

After clarification of existing phrase/term boundaries, they selected consistent
first-argument selection even when reminder options are present, rejecting the
proposed reminder exception. Their final yes approved the concrete update to
this file and README.md, including the full-clear boundary described below.
Actual operator excerpts, question context and interpretation are retained
separately in the external Design report.

Earlier definitions and accepted effective assignments remain historical inputs.
These narrow successors govern changed and follow-up work:

| Successor | Earlier scope qualified or superseded |
| --- | --- |
| REQ-CLI-039 | REQ-CLI-031/033/035, REQ-MUT-005 and REQ-SCHED-012/014 only for positional rename/scheduling/hiding operands, the corresponding command aliases, and schedule's positional clear boundary. Existing explicit forms, matching, scalar/literal handling and unrelated command shapes remain. |
| REQ-CLI-040 | REQ-CLI-024 and REQ-CLI-037 only where help/errors must teach the added forms, retained explicit forms and compatibility consequences. Existing vocabulary, independent help and applicable usage diagnostics remain. |
| REQ-VERIFY-038 | Adds distinguishing grammar/help evidence and qualifies older assertions that rename always requires `--to`, attention changes always require a date option, or all unmarked scheduling/hiding words necessarily belong to the selector. All still-required behavior and isolation obligations remain. |

REQ-CLI-038 continues to govern cached selection and explicit-refresh recovery.
Scheduling, hiding, recurrence, reminders, sibling-title validation, no-op rules,
confirmation, outcomes, reconciliation, publication and reporting retain their
existing contracts. This amendment adds syntax, not additional accepted date
expressions, reminder capabilities, mutation bypasses or automatic recovery.

### REQ-CLI-039 — Positional value boundaries with retained explicit forms

Add these canonical shorthand forms for open tasks and steps:

```console
todo rename SELECTOR NEW_NAME...
todo schedule SELECTOR WHEN... [--hide] [--reason VALUE] [--reminder OFFSET|keep]... [--reminder-at WHEN|keep]...
todo hide SELECTOR [WHEN...] [--reason VALUE]
```

Command aliases `due` and `wait` use the same grammar as `schedule`; `wait` does
not independently enable hiding. Retain supported options and their existing
applicability, repeatability and scalar/boolean arities. Extract supported
scalar/boolean options regardless of their position before assigning the
remaining positional operands. Preserve original argument contents and literal
identity through extraction; an option's scalar value is never a positional
operand. Existing literal and option-error rules remain.

In shorthand mode, the first remaining positional shell argument is the complete
source selector. Join all subsequent positional arguments, in order and separated
by one U+0020 space, into one new name or attention expression. Preserve internal
argument contents and apply existing domain normalization and validation; do not
use REQ-CLI-012 creation splitting for these values. A quoted multiword selector
is one contiguous phrase under REQ-CLI-035, not several independent terms.
Parsing must not depend on the saved matching population or on whether an
attention expression resolves. Never retry with a different selector/value split.

For `rename`, require both a nonempty selector and a nonempty valid new name.
Its retained `--to NEW_NAME...` marker selects explicit mode: preserve the
existing selector-term/phrase boundaries before the marker and joined new name
after it. Existing marker arity, assignment, duplicate and literal rules remain.

For `schedule` and `hide`, an explicit `--at`, `--due` or `--schedule` option
selects explicit mode instead: every remaining unmarked positional argument
belongs to the selector, with the existing term/phrase boundaries. Each explicit
date option still consumes exactly one scalar shell argument, including equivalent
equals syntax. Supported option positions remain valid; the date option need not
follow the selector. Repeated/mixed date aliases remain usage errors.

Reminder options are not a selector/value boundary. Without an explicit attention
option, `schedule A B --reminder 10m` selects A and uses B as the attention
expression, while `schedule A --reminder 10m` changes reminders without supplying
new attention. Apply the same rule to `--reminder-at`, repeat/mixed reminder sets,
`keep` and reminder-only clear. Existing complete-set, exact-time, preservation,
replacement-confirmation and incompatibility rules remain. In particular,
`schedule A tomorrow --reminder clear` changes attention and clears reminders;
it does not request full scheduling clear.

With one selector and no positional or explicit date, `hide` preserves existing
attention, recurrence and reminders; absent/nonfuture attention still fails as
before. `schedule` with one selector and no date still requires a supported
reminder operation or full clear. `--hide` in schedule still requires a supplied
attention expression, which may now be positional. `--reason` remains explicit
and retains omission/preservation, nonempty replacement and empty removal rules.

Retain full scheduling clear as `schedule SELECTOR clear`: in shorthand mode,
the entire value tail must be exactly one unescaped argument `clear`. It removes
attention, recurrence, reminders and own hiding/reason as before. Extra words
must not turn part of the value into a selector or trigger full clear. Thus
`schedule A B clear` has selector A and attention expression `B clear`, not a
two-term selector and a clear action. Literal escaping prevents control-word
interpretation. Full clear cannot combine with another requested scheduling,
reminder or hiding/reason change; incompatible requests fail as usage errors.
An explicit attention option still selects explicit mode, so positional `clear`
there is a selector term, not a full-clear action.

Examples distinguish the supported boundaries:

```console
todo rename jklu New task title
# selector: jklu; new name: New task title
todo rename nightly python --to New task title
# selector terms: nightly, python; new name: New task title
todo schedule jklu next week
# selector: jklu; attention expression: next week
todo schedule jklu tomorrow 10:00 --reminder 10m
# selector: jklu; timed attention: tomorrow 10:00; reminder: 10m
todo schedule nightly python --at "tomorrow 10:00" --reminder 10m
# selector terms: nightly, python; explicit timed attention and reminder
todo hide "Release plan" next week --reason "no time"
# one selector phrase; attention: next week; explicit reason
todo hide nightly python --at tomorrow
# selector terms: nightly, python; explicit attention: tomorrow
todo schedule "Release plan" clear
# one selector phrase; full scheduling clear
```

The accepted compatibility cost is that bare extra words in schedule/hide,
including reminder commands, no longer necessarily extend the selector. An old
command such as `schedule nightly python --reminder 10m` now supplies attention
expression `python` for selector `nightly`. A rejected/unresolvable value must
follow existing date diagnostics, never fall back to multi-term selection.
Use an explicit date option when both multi-term selection and attention change
are needed. Reminder-only and full-clear shorthand selection use one argument;
quoting supplies a contiguous phrase, not equivalent independent-term matching.
No new selector marker or full-clear switch is introduced to restore those old
multi-term spellings.

Existing positional `move`, `comment` and `done` behavior remains unchanged,
including explicit markers, destination typing/promotion and REQ-CLI-012 comment
grouping. This is not a universal grammar replacement: selector-only inspection,
implicit lookup, reopen, deletion, unhide and search retain their existing
multi-argument matching; priority retains its final priority argument; creation
retains its category/parent and text-group boundaries. Leading noun-action
aliases retain their existing adjacent scalar and task/parent-step operand
rules. `now` retains its explicit single-category filter; do not add positional
or multiple-category filtering.

### REQ-CLI-040 — Teach shorthand boundaries and explicit alternatives

Help and applicable syntax diagnostics must present the short rename, scheduling
and hiding forms first, while documenting the retained explicit forms and the
same behavior for command aliases. Show a joined multiword value, a quoted
multiword selector and a multi-term explicit selector. Explain that independent
selector terms and quoted contiguous phrases are different, and that reminders
do not change shorthand parsing. Preserve quoted scalar examples in explicit
forms, existing noun-action examples, comment grouping guidance, important
destructive/state-dependent constraints and literal escaping guidance.

Teach both `schedule SELECTOR clear` and the single-selector/full-value-tail rule;
do not describe every trailing `clear` as full clear. Explain reminder-only
commands and the compatibility cost for former unmarked multi-term scheduling/
hiding selectors. The `now` synopsis and filtering behavior remain unchanged.

Help remains state-independent. Syntax failures still identify the command and
problem, show valid usage and a concrete applicable example, and fail with status
2 before loading state or attempting a mutation. Existing operational/date,
ambiguity, cancellation and partial-failure statuses remain distinct. Do not
replace a domain rejection with speculative parsing advice or promise that
every nonempty date expression is valid.

### REQ-VERIFY-038 — Distinguishing shorthand and compatibility evidence

Use proportionate offline evidence distinguishing:

- Positional rename, schedule/due/wait and hide use the first argument as the
  selector and all remaining value arguments, including three/four-operand cases,
  as one name/date. Quoted selectors and literal insertion preserve their meaning.
- Supported option extraction retains values and original positional boundaries;
  reminders do not change shorthand parsing. Reminder-only operations, positional
  timed attention plus reminders, explicit multi-term date forms and missing-date
  hide behavior retain their applicable validation and preservation duties.
- Full clear recognizes only the sole unescaped value `clear`; `A B clear` has
  selector A and value `B clear`. Reminder clear, explicit-date selector terms,
  literal escaping and incompatible clear requests stay distinguishable.
- Explicit rename/date boundaries preserve selector terms and scalar arity;
  missing/invalid operands and duplicate/conflicting options fail before state
  access or mutation. No data-dependent split or invalid-date selector fallback
  occurs. Domain failures retain their original classification.
- Help teaches both forms and the compatibility changes without configuration or
  network access. Existing move/comment/completion grouping, selector-only,
  priority, creation and noun-action behavior remain; `now` has no added category
  shorthand or multi-category filter.

Planning owns test layers, shared coverage and necessary adaptations; a separate
matrix at every layer or new live-account test is not required. Reuse adequate
existing evidence and preserve all still-required isolated copied-installation,
mutation-result, history, report and publication verification.

## Evidence, exclusions and handoff

The inspected clean baseline was commit
`12426b92fdcd0d12fdd46c8770e8c404845e8524`. Read-only parser probes confirmed
mandatory `--to` for rename, required scheduling options, bare hide terms all
belonging to the selector, and existing positional move/comment/completion and
creation forms. Matching probes distinguished independent terms from a contiguous
phrase. These observations establish the existing local mechanism, not completed
implementation of the new grammar. No live Todoist access was needed.

Only this file and README.md change in this Design amendment. No production or
test change, commit, Planning pass, runner adoption or execution is authorized by
its documentation approval. There are no unresolved product choices or new
external-provider investigations. Parser/help implementation, proportional
verification and follow-up assignments belong to a separately requested Planning
or otherwise authorized delivery pass. Preserve accepted effective assignments
and their historical definitions; do not rewrite them to install this revision.
