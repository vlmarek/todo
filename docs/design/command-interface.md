# Command interface

Status: Accepted

This document defines the binding first-release public CLI. Canonical forms
are taught first, but every documented compatibility alias is intentional
public syntax and must behave identically to its canonical operation.

## Global options

```console
todo [--color=auto|always|never] [--refresh] COMMAND ...
```

`--refresh` is global for cache-backed reads, including implicit lookup.
`todo --refresh` is equivalent to `todo now --refresh`. Commands that already
synchronize and help commands reject it as redundant or inapplicable.

Color defaults to `auto`: it is enabled only when normal output is a terminal
and is disabled for redirected output, `NO_COLOR`, or `TERM=dumb`. `always`
forces color and `never` disables it. Diagnostics sent to stderr must remain
understandable without relying on color.

The built-in palette is Solarized Dark. An optional `[colors]` section in
`~/.todo/config` may override the existing palette slots `base01`, `base1`,
`red`, `green`, `yellow`, `blue`, `magenta`, and `cyan`. Omitted slots keep
their Solarized defaults. An invalid value for a recognized slot is a
configuration error; unknown keys remain ignored under the general
configuration compatibility rule. Values are case-insensitive six-digit
`#RRGGBB`; shorthand, named, alpha-channel, and unprefixed forms are invalid.

`todo help` displays top-level help. `todo help COMMAND` is equivalent to
`todo COMMAND --help`; both forms display the same command-specific help and
exit successfully without loading configuration, cache, or Todoist state.

Running `todo` with no arguments is exactly equivalent to `todo now`. It loads
the cached work queue and follows the same validation, ordering, output, and
exit behavior. Top-level help remains available explicitly through `todo help`
or `todo --help`.

Global options are accepted either before the command or in the command's
documented option position. Repeating a singleton global option is a usage
error. `--refresh` remains invalid for commands that already synchronize or do
not read cached state.

Successful commands exit `0`, command-line usage errors exit `2`, and every
operational or partial failure exits `1`.

## Interaction contract

The public interface follows these rules across all commands:

- Help teaches canonical verb commands first. Compatibility aliases are listed
  afterward and do not appear as separate concepts.
- Commands accepting the same kind of selector, category, priority, attention
  value, reminder, or refresh option use the same parsing and matching rules.
- Successful mutations identify the selected item and resulting state.
- When a previous value exists and is relevant to understanding the change,
  mutation output displays both the previous and resulting values.
- A successful empty view prints a short explicit message rather than producing
  ambiguous blank output.
- A rejected command identifies what could not be done and why.
- When exactly one safe and applicable recovery is known, the error suggests
  the concrete command or option that performs it.
- Suggestions must not assume an ambiguous item selection or propose an
  operation that would violate another domain rule.
- Partial failures distinguish operations already accepted by Todoist from
  operations that were not attempted or failed.

Examples of actionable recovery include:

```text
todo: local cache is missing; rerun with --refresh
todo: item is completed; reopen it before changing its priority
todo: waiting label is missing; run `todo init`
```

The exact wording may vary, but the error must preserve the same facts and
recovery action.

## Argument and value grammar

The shell removes quote syntax before `todo` receives its argument vector.
`todo` therefore never infers a batch boundary from whether an argument happens
to contain a space or tab.

The canonical grammar uses value markers:

- selector terms precede the first value marker
- `--category`, `--title`, `--to`, `--at`, `--due`, `--comment`, `--step`, and
  `--hide` begin values
- a multiword value continues until the next recognized marker
- `--reminder` is a marker that consumes exactly one following offset argument
- `--comment` and `--step` are repeatable and create one object per occurrence
- `--hide` consumes the remaining words as one reason and must therefore be the
  last marker
- `--literal ARG` inserts its next argument into the current selector or value
  block without interpreting it as a marker

Unmarked trailing prose in a documented shorthand is one logical value. It is
never split into one value per shell argument. Quoting may preserve a
contiguous phrase for selector matching, but quoting does not create multiple
steps or comments.

For example:

```console
todo add task --category Client Work --title prepare quarterly proposal \
  --step draft outline --step request figures
todo rename deploy staging --to deploy production
todo move deploy staging --to Client Work
todo done deploy staging --comment finished rollout
todo schedule deploy staging --at next Friday 10:00
todo add comment weekly report --comment added note about future
```

Legacy positional and noun-action forms remain accepted, but they normalize to
this model. Their unmarked prose is a single value; positional batching is not
retained. Invalid or conflicting markers fail with exit `2` before
synchronization or mutation.

## Help content

Top-level help explains the primary workflow: view work, inspect an item,
record progress, update state, and generate a report.

Each command's help contains:

- its canonical synopsis
- a short explanation in domain vocabulary
- the most common example
- important destructive or state-dependent constraints
- supported aliases, listed after the canonical form

## Work views

```console
todo now
todo now --all
todo now --refresh
todo now --category CATEGORY
todo waiting [--refresh]
todo someday [--refresh]
todo task [--refresh] SELECTOR
todo step [--refresh] SELECTOR
todo category [--refresh]
todo search [--all] [--refresh] TEXT
```

`todo waiting` is the focused view of currently suppressed temporary-hidden
tasks and independently hidden steps. It excludes configured hidden categories
such as `Someday` and excludes items whose stored `waiting` label remains but
whose attention day has arrived.

`todo someday` is the focused view of every open task and open step in all
configured hidden categories. Completed items remain excluded.

An empty `todo waiting` prints `No waiting items.`; an empty `todo someday`
prints `No someday items.`. Both cases exit successfully.

Every read view (`now`, `waiting`, `someday`, `task`, `step`, `category`, and
`search`) accepts `--refresh`. Without it the command reads the local cache.
With it the command synchronizes from Todoist before validating and displaying
the result. A failed refresh exits nonzero and prints no normal view output.

`todo now --category CATEGORY` limits the normal actionable view to one current
category. The supplied category name is matched case-insensitively. It does not
change the normal visibility or urgency-ordering rules.

If no current category matches the supplied name, the command reports the
missing category and exits nonzero without normal list output. A matching
category that simply contains no actionable items produces a successful empty
view.

`--all` and `--category` may be combined. The category lookup first limits the
scope, then `--all` includes every open task and open step in that category,
including temporarily hidden items and items hidden by category policy.

Any successful `todo now` variant with no items prints `No actionable items.`
and exits zero.

## Discovery

`todo search TEXT` searches broadly across task titles, step titles, ordinary
descriptions, temporary-waiting reasons, and task comments. It only displays
matches and never selects an item or changes state. Its searchable fields do
not affect the title-only selector rules used by other commands.

Search examines open tasks and steps by default. `todo search --all TEXT` adds
every completed task, step, and surviving comment currently retained in the
disposable cache. Completed objects fetched by reports, completed-item
operations, and prior refreshes remain searchable after the report cursor
advances. Cache deletion or incompatible replacement may remove that historical
population; `--all` does not claim complete Todoist history.

Every `--all` search prints the completed-cache coverage line defined in
`output-contract.md`, including when it finds no match. Ordinary `--refresh`
updates current state and merges newly obtained completed objects without
purging older retained objects. There is no search `--since` option and no
first-release full-history backfill.

Search visibility is independent of work-queue visibility. Open items hidden by
temporary waiting and open items in configured hidden categories remain in the
default search population.

Search task groups are ordered by priority, lowercase category, and lowercase
task title. Matching steps within a group are ordered by their own priority and
lowercase title. Search ordering does not use attention dates.

Search uses the same term matching as selectors: one shell argument containing
spaces is a contiguous phrase, while multiple arguments are independent terms
that must all match one field in any order and need not be contiguous. Matching
is case-insensitive.

One individual searchable field must satisfy the complete query. Terms cannot
be combined across a title, description, hiding reason, and comment, or across
multiple comments. Each comment is a separate searchable field.

Search output shows only the matching task or step title within its task group;
it does not print the matching description, reason, comment excerpt, or field
name. An item matching through multiple fields is displayed once. A matching
step includes its nonmatching parent as context and omits nonmatching siblings.
A matching parent does not pull in nonmatching steps.

An empty default search prints `No matches.` and exits successfully. An empty
`--all` search uses the cached-history message and coverage line from
`output-contract.md` and also exits successfully.

## Initialization and diagnosis

```console
todo init
todo init --rebind [--yes]
todo doctor
```

Before first initialization, the user creates `~/.todo/config` and specifies
the root project, initial categories, and hidden categories. Init validates that
configuration, then provisions only a missing root project, configured initial
category projects, and Todoist `waiting` label. It does not invent structural
defaults or prompt for them. Ordinary commands never provision structure.

Authentication must already be available from `[todoist] token` or
`TODOIST_TOKEN`; the nonempty environment value wins. Init has no token option,
does not write credentials, and supports personal API-token authentication only.
OAuth is outside scope.

First successful initialization requires an unshared personal root project.
Root discovery examines active top-level projects with exact case-sensitive
name equality. No match creates one personal root; one match is reused only if
it is unshared and personally owned; multiple matches, or a sole shared/team
match, fail without provisioning a competing root. Configured initial
categories reuse a unique case-insensitive direct-child match or are created;
case-colliding or structurally invalid matches fail. Init stores the Todoist
account ID, root-project ID, and managed category IDs in
`~/.todo/binding.json`. Subsequent commands use stable IDs, so renames retain
identity.

Init is repeatable within the bound account and provisions only missing
configured structures. A token for a different account aborts before
provisioning or mutation. Deliberately switching accounts requires
`todo init --rebind`, displays both account identities, and requires interactive
confirmation or `--yes`. Rebind leaves the old account untouched, establishes a
new binding, replaces the disposable cache, and creates a new report cursor at
the new binding time only after provisioning and local binding persistence
succeed.

The first successful binding creates the report cursor if it does not yet
exist. Once a binding exists, a missing, unreadable, or corrupt cursor is an
error; ordinary init never recreates it. Recovery requires an explicit
`todo report --set-cursor` operation.

`todo doctor` is a read-only synchronizing diagnostic. It remains available
when normal model validation fails and prints every detected violation with the
affected task, step, category, or binding plus the concrete Todoist-side or
local repair. It never repairs, moves, renames, deletes, or normalizes data.
Normal views, reports, and mutations remain blocked until a later refresh or
doctor run confirms the repairs. Help and report-cursor inspection also remain
available without a valid model.

## Progress and completion

```console
todo comment [--refresh] SELECTOR...
todo comment SELECTOR COMMENT...
todo comment SELECTOR... --comment COMMENT... [--comment COMMENT...]...
todo add comment SELECTOR... --comment COMMENT... [--comment COMMENT...]...
todo comment --edit SELECTOR...
todo done SELECTOR... [--comment TEXT...]
todo reopen SELECTOR...
```

`todo close` and `todo closed` are aliases for `todo done`. `todo unclose` and
`todo undone` are aliases for `todo reopen`. Every alias preserves selection,
confirmation, ordering, failure, output, and exit behavior.

`todo comment TASK` displays the selected open parent task's comments oldest
first and accepts cache-backed `--refresh`. The shorthand
`todo comment report added note about future` treats only the first argument as
the selector and joins the remaining words into one comment. To use a
multi-term selector, use an explicit marker:

```console
todo comment weekly report --comment added note about future
```

Each repeated `--comment` creates one distinct comment sequentially in
command-line order. `todo add comment` is an exact alias for creation. A later
failure retains accepted comments, stops before unattempted comments, reports
all three sets, and performs no compensating deletion. Steps cannot own
comments, so comment commands select open parent tasks only.

`todo comment --edit TASK` synchronizes first and opens current comments using
`$VISUAL`, then `$EDITOR`, then `vi`. The editor command is parsed as a
shell-like argument string but executed directly without a shell. An unchanged
valid buffer succeeds without mutation.

The UTF-8 temporary file remains under `~/.todo` with mode `0600`, and the
runtime lock is held while the editor is open. Launch failure, signal, or a
nonzero editor exit performs no comment mutation. A comment concurrently added
outside this CLI is not present in the generated buffer and is left untouched.
Saving a changed block intentionally overwrites a concurrent edit to that same
comment ID; a target deleted concurrently causes the ordered application to
fail at that operation.

The editor buffer uses blocks:

```text
[id: COMMENT_ID posted: TIMESTAMP]
existing comment text

[new]
new comment text
```

Stable comment ID is authoritative; the displayed timestamp is informational.
Deleting an existing comment requires removing its complete block. The whole
buffer is validated before mutation: orphan text, malformed or unknown headers,
duplicate or foreign IDs, and whitespace-only blocks reject the entire edit.
An empty buffer requests deletion of every comment shown in that generated
buffer and requires a second interactive confirmation; non-interactive use
fails. Comments added concurrently remain untouched. Valid operations run
sequentially as edits, additions, then deletions. The first API failure stops
processing without rollback and reports accepted, failed, and unattempted work.

`todo done` selects an open task or step. The one-selector shorthand may place
unmarked completion text after its first selector argument; canonical multi-term
selection uses `--comment`. Completion text is valid only for a parent task and
becomes one `Done: TEXT` comment.

Completing a parent with ordinary open steps first prints them and requires an
explicit `y` or `yes`; non-interactive use fails without mutation. After
confirmation, steps are completed sequentially, then the parent is completed,
and only then is the optional `Done: TEXT` comment created. A comment failure
leaves the completed tree intact and is reported as a partial failure.

An open recurring step cannot be cleared by completing the parent: completing
it would merely advance it and leave it open. The entire parent completion is
therefore rejected before confirmation or mutation, identifies every recurring
open step, and tells the user to remove recurrence, delete the step, or move the
recurring work to a separate task.

`todo reopen` exists only to correct a recent mistaken completion. Candidates
are completion occurrences in `(report cursor, now]`; older history is not
searched. It accepts no text and creates no comment.

Reopening a parent leaves its completed steps completed. Reopening a step may
cause Todoist to reopen its completed ancestor chain; output lists every
reopened ancestor. Before mutation, the complete affected chain is checked for
case-insensitive open-sibling title conflicts. Any conflict rejects the whole
operation and identifies the current open item that must be renamed or moved.

For a recurring task or step, only its latest completion occurrence may be
undone. A later occurrence makes an older occurrence ineligible. Undo moves the
recurrence backward exactly one occurrence through Todoist's recurring-undo
operation. Reopening an already-open ordinary item or any otherwise ineligible
occurrence fails without mutation.

## Creation and maintenance

Canonical forms are:

```console
todo add task [--done|--close|--closed]
              [--priority P|-p1|-p2|-p3|-p4]
              [--at WHEN...|--due WHEN...]
              [--reminder OFFSET]...
              --category CATEGORY... --title TITLE...
              [--step STEP...]... [--hide REASON...]
todo add step [--done|--close|--closed]
              [--at WHEN...|--due WHEN...]
              [--reminder OFFSET]...
              SELECTOR... --step STEP... [--step STEP...]...
              [--hide REASON...]
todo rename SELECTOR... --to NEW_NAME...
todo move SELECTOR... --to CATEGORY...
todo priority SELECTOR... P
todo delete [--yes] SELECTOR...
todo category [--refresh]
todo category --add NAME...
todo add category NAME...
```

The short task-creation forms remain aliases:

```console
todo add [OPTIONS] CATEGORY TITLE... [--step STEP...]...
todo add task [OPTIONS] CATEGORY TITLE... [--step STEP...]...
```

In those positional forms the first argument is the category selector and every
remaining unmarked word is one task title; a multiword category must be quoted.
Inline positional step batching is not supported. `todo add step TASK STEP...`
likewise uses its first argument as the task selector and joins the rest into
one step; repeated `--step` is required for several steps.

A new parent task defaults to P2 unless explicitly overridden. A new step copies
its parent's effective priority at creation and thereafter owns that value
independently. Step creation has no priority override; `todo priority` changes
it afterward.

Task and step creation retain equivalent `--done`, `--close`, and `--closed`
options. All proposed titles and duplicate-title warnings are validated before
the first creation. Created steps are completed before their newly created
parent. Completion-at-creation cannot be combined with attention, recurrence,
reminders, or hiding and cannot be used for a recurring item.

Task priority accepts `1` through `4`, case-insensitive `P1` through `P4`, and
`-p1` through `-p4`. `todo priority` accepts the numeric and P-prefixed forms
for an open task or step. Multiple priority forms conflict. Successful output
prints the stored previous and resulting priority; derived effective priority
is recalculated but is not another editable field.

`--at` is canonical for an initial attention value; `--due` is an equivalent
alias and the two cannot appear together. Repeatable reminders and `--hide`
reuse the scheduling grammar. `--hide` requires a nonempty final reason and an
explicit attention value. Parent creation options apply only to the parent;
inline steps remain unscheduled. Scheduling or hiding options on `add step`
require exactly one `--step` value.

`todo category` lists categories alphabetically. `todo categories` is an exact
alias, including `--refresh`, `--add`, and the legacy `--create` spelling.
`todo category --add NAME`, `todo category --create NAME`, and
`todo add category NAME` are equivalent. Category names are one joined value
and fail on a case-insensitive collision.

Creating a task fails before mutation if the target category contains an open
same-title task under case-insensitive comparison. Creating a step applies the
same rule among open siblings. A same-title completed sibling does not block
creation but produces a warning before mutation. The same open/completed rules
apply to rename and move.

`todo rename` supports open tasks and steps. `todo move` supports open parent
tasks only; steps inherit category. Moving to the current category is a no-op
error. Before moving, an open same-title task in the destination rejects the
move; only completed same-title tasks allow it with a warning. No merge or
implicit rename is ever performed. Success prints previous and resulting title
or category.

Ordinary edits operate on open items only. Completed items are never reopened
and re-completed as an implementation shortcut. Normal `todo task SELECTOR`
selects open parents but includes their completed steps in detail. Historical
parents are resolved only by `reopen` and `delete` within `(report cursor,
now]`.

Legacy noun-action forms such as `todo task --done`, `todo task --rename`, and
`todo step --delete` delegate to the same canonical workflows. Compatibility
syntax does not restore unsupported `check`, `show`, `resume`, or `ask` forms.

The retained noun-action spellings are exhaustive:

| Noun | Retained actions |
|---|---|
| `task` | `--add`/`--new`/`--create`, `--done`/`--close`/`--closed`, `--undone`/`--unclose`, `--delete`, `--wait`/`--waiting`, `--due`, `--reminder`, `--priority`/`-p1`…`-p4`, `--move`, `--rename`, `--comment`, `--step` |
| `step` | `--add`/`--new`/`--create`, `--done`/`--close`/`--closed`, `--undone`/`--unclose`, `--delete`, `--rename`, `--reminder` |
| `comment` | `--add`/`--create`, `--edit` |
| `category` | `--add`/`--create` |

Compatibility forms preserve their historical positional boundary: a task
operand is one shell argument; a step target is one parent argument followed by
one step argument; later operands form the one action value. Quoting can keep a
multiword selector in that one operand but never creates a batch. Unmarked
creation tails now form one title, comment, or step; several comments or steps
still require the canonical repeated markers. New code and help examples use
the marker-based canonical forms because they support multi-term selectors
without positional ambiguity.

The retained `todo task --wait`/`--waiting` form maps to `schedule --hide` and
therefore requires an explicit `--at` or `--due` value plus a nonempty reason;
it never consults a default date. Compatibility `--new`/`--create` actions map
to `--add`, and `comment --create` maps to comment creation.

Task detail displays the parent's stored priority and own attention value, not
the derived group values. It interleaves all current comments and open/completed
steps newest first. Steps use `added_at`; comments use current `posted_at` for
this detail timeline. Each entry prints its ordering timestamp in the Todoist
account timezone. A step completion changes its marker rather than creating a
second detail-history record.

`todo delete` requires interactive affirmative confirmation or `--yes`.
Cancellation, EOF, or non-interactive use without `--yes` exits `1` unchanged.
A parent preview lists the complete open/completed step tree before the prompt;
`--yes` skips only the prompt, not that preview.

Open items are normal delete candidates. A recurring object remains open after
each completion and therefore appears once as an open candidate; deleting it
deletes the active recurrence, not one historical occurrence. Non-recurring
completed task and step candidates are limited to objects completed in
`(report cursor, now]`, matching reopen's time horizon. Deletion uses Todoist's
direct operation without temporary reopen and is terminal: no local undelete
snapshot is retained. Deleting a parent deletes its whole displayed tree. API
rejection leaves local state consistent with Todoist.

## Attention and reminders

`wait`, `due`, and `schedule` are equivalent command aliases. `schedule` and
`--at` are canonical:

```console
todo schedule SELECTOR... --at WHEN... [--reminder OFFSET]... [--hide REASON...]
todo schedule SELECTOR... --due WHEN... [--reminder OFFSET]... [--hide REASON...]
todo schedule SELECTOR... clear
todo schedule SELECTOR... --reminder clear
```

The older item/date positional forms for `wait`, `due`, and `schedule` remain
accepted. `--at` and `--due` name the same attention value and conflict if both
are supplied. Their multiword value ends at the next recognized marker.
`--hide` must be last and consumes the remaining words as one nonempty reason.
There is no implicit or configured hiding date.

`WHEN` is one nonempty English attention expression. The local forms are:

- ISO 8601 date or date-time, including an explicit offset or `Z`
- `today`, `tomorrow`, or an English weekday name, optionally followed by
  `H`, `HH`, `H:MM`, or `HH:MM`; a bare weekday means its next occurrence
- a nonnegative integer followed by `h`, `d`, `bd`, `business day`, or
  `business days`

`Nh` adds elapsed hours. `Nd` adds account-local calendar days and `Nbd` counts
Monday through Friday without a holiday calendar; both retain the current
account-local wall-clock time. A generated ambiguous or nonexistent wall time
fails and asks for an explicit date-time with offset. Other nonempty English
expressions, including recurrence and `next Friday 10:00`, are sent unchanged
to Todoist's English date parser and then reconciled. `ask`, `none`, and `-` are
not attention values. Clearing uses the separate literal `clear` form.

Each `--reminder` accepts exactly one positive integer followed immediately by
`m`, `h`, `d`, or `w`, for example `30m`, `2h`, `3d`, or `1w`. Units are
case-sensitive lowercase. Zero, signs, decimals, whitespace, compound forms
such as `1h30m`, and units such as months are invalid. Values normalize to
minutes; equivalent duplicates such as `1h` and `60m` reject the complete
proposal before mutation.

One or more reminder markers replace the complete existing reminder set in
marker order. `--reminder clear` removes all reminders while preserving
attention, recurrence, and hiding. Changing attention without a reminder marker
preserves reminders and prints the retained set. Relative reminders require an
exact attention time and the Todoist account capability.

Supplying attention without `--hide` removes the item's own hiding policy.
Supplying `--hide` adds it and stores its reason. Clearing the item removes
attention, recurrence, reminders, and its own hiding policy. Successful output
shows previous and resulting values, including retained reminders and an
explicitly absent prior reason.

## Reporting

```console
todo report
todo report --final
todo report [--since TIMESTAMP] [--until TIMESTAMP]
todo report --show-cursor
todo report --set-cursor TIMESTAMP [--yes]
```

After local syntax validation, a report acquires the exclusive runtime lock and
then reloads its binding and cursor. Without `--until`, it captures one end
instant immediately before its first Todoist request. The period is
`(cursor, captured end]`. Synchronization and every activity,
completed-object, and comment page are then retrieved against that fixed
boundary. Activity after it belongs to the next report.

`--since` and `--until` override boundaries for preview/recovery and never
change the stored cursor. `--final` cannot be combined with either override.
Invalid combinations fail before external requests.

Report boundaries and cursor values accept RFC 3339/ISO 8601 date-times or the
past-relative forms `Nd ago` and `N days ago`, where `N` is a positive integer.
A multiword relative value must be one shell argument. Offset-free values use
the cached Todoist account timezone; ambiguous or nonexistent local times
require an explicit offset. Start after end, a future end, and a future cursor
are rejected. Equal report boundaries are a valid empty preview.

`todo report` previews without changing the cursor. `--final` writes and
flushes the complete report first, then atomically advances the cursor to the
captured end. Broken pipe, output error, interruption, retrieval failure, or
local persistence failure leaves the previous cursor unchanged. A successful
empty final report still advances it.

The report sync reads Todoist `user_plan_limits` without an extra request. If
Todoist reports limited activity retention, every report prints a warning. For
the Free plan and seven-day limit, the wording is defined in
`output-contract.md`. Configuration may suppress only that warning:

```ini
[report]
warn_limited_history = false
```

If the requested start is older than the available activity history, report
generation fails before normal report output and cursor advancement. It never
emits a partial report. Reminder commands independently fail only when the
account lacks the required reminder capability.

`--show-cursor` displays local state without synchronizing. `--set-cursor`
changes it without synchronization and accepts ISO timestamps or past-relative
forms such as `7d ago` and `7 days ago`. Offset-free input uses the Todoist
account timezone cached in the binding/cache; nonexistent or ambiguous local
times require an explicit offset. Storage is UTC.

Cursor changes display the resolved instant and require confirmation, explaining
that moving backward may duplicate work and moving forward may skip it.
Non-interactive use requires `--yes`. If a binding exists but the cursor is
missing or corrupt, reports and ordinary init fail until this explicit command
repairs it.

## Selection

Selectors match titles only among the item types allowed by the command.
Descriptions, reasons, and comments affect `search` but never targeting. Each
selector term and candidate title is normalized to NFC and compared with
Unicode case folding for substring matching; accent distinctions are
preserved. Stored text is not rewritten. Empty terms are usage errors. All
terms must match the same title, in any order and not necessarily contiguously.
One shell argument with spaces is one contiguous phrase.

For marker-based commands, every argument before the first value marker is a
selector term. The comment and done one-selector shorthands intentionally use
only their first argument as selector and join the remaining unmarked words as
one value. Use explicit `--comment` for a multi-term selector. `--literal ARG`
escapes a marker-looking selector or value token.

An exact title match receives no precedence. If both `Report` and
`Weekly report` match `report`, both are candidates.

Interactive ambiguity prints the numbered candidates with item type, title,
category, and parent context as defined in `output-contract.md`. A valid number
selects; `q`, blank input, or EOF cancels unchanged with exit `1`; invalid
numbers re-prompt. Non-interactive ambiguity prints the same candidates, never
prompts or mutates, and exits `1`.

Completed candidates append their completion timestamp so reused titles can be
distinguished. For a recurring object, only its latest undo-eligible occurrence
participates in reopen selection; older occurrences are not displayed as
candidates.

Task, step, and user-supplied category selectors are case-insensitive.
Configured hidden-category names remain exact case-sensitive policy names,
while the configured root name is used only to establish or re-establish its
stable binding.

Candidate type depends on the command:

- `todo task` searches open parent tasks only.
- `todo step` searches open steps across all managed parents and displays parent
  and category context.
- implicit top-level lookup searches open tasks and steps independently.
- ordinary mutations search open types permitted by that mutation.
- `reopen` searches eligible completion occurrences only in `(report cursor,
  now]`; completed-item `delete` searches currently completed non-recurring
  objects whose completion is in that interval.

Implicit lookup is intentional syntax and emits no unknown-command warning. No
match is an operational error, unlike an empty discovery search. When a step
and task both match an implicit selector, both participate in normal ambiguity
handling.

## Mutation output

After a successful attention, reminder, hiding-reason, priority, title, or
category change, print previous values when present and print the resulting
values. Do not print successful-change output until Todoist has accepted the
mutation.

Warnings and errors go to stderr. Normal results and successful change details
go to stdout. Exact structural templates, empty messages, ambiguity prompts,
report framing, timestamp rendering, and tie-breakers are defined in
`output-contract.md`.
