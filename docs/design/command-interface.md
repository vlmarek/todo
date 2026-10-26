# Command interface

Status: **Accepted**

todo-3 specification, revision 2. See [README](README.md).

### REQ-CLI-030 — Global options, default invocation, and exit statuses

The public invocation shape must be:

```console
todo [--color=auto|always|never] [--refresh] [--clear-cache] COMMAND ...
# --color VALUE is equivalent to --color=VALUE under REQ-CLI-031.
```

Running `todo` with no arguments must be exactly equivalent to `todo now`.
`--refresh` is global for cache-backed reads and may appear before the command or
in that command's documented option position. Repeating a singleton global option
is a usage error. A command that already synchronizes, or that does not read task
state, must reject `--refresh` as inapplicable.

Color defaults to `auto`: enable it only when stdout is a terminal, except that
`NO_COLOR` or `TERM=dumb` disables it. `always` forces color and `never` disables
it. Color must not change text, spacing, markers, ordering, or meaning.

Exit statuses must be `0` for a completed successful request including defined
empty views, `2` for command-line syntax or option-combination errors, `1` for
operational/domain/ambiguity/cancellation/API/output/partial failures, and `130`
for handled SIGINT as defined by `REQ-LOCAL-006`.

### REQ-CLI-031 — Option arity, text groups, shorthands, and literal values

The shell removes quoting syntax but preserves argument boundaries and contents.
Selectors retain REQ-CLI-035 matching and text creation retains REQ-CLI-012 grouping.
Recognized options must have explicit arity; never infer a value from prose after
a boolean flag. In the affected creation/scheduling/hiding grammar, `--at`,
`--due`, `--schedule`, `--reason`, `--category` and each `--reminder` take exactly
one following shell argument. Quote a multiword scalar, for example `--at "next week"`,
`--reason "no time"` or `--category "Client Work"`. All supported scalar options
also accept `--option=VALUE` with identical contents and semantics, including
report/filter/global scalar settings. This does not make boolean flags take
values or introduce assignment syntax for batch text-group markers.

`--hide` is boolean and consumes no value. Reasons require the scalar `--reason`.
An omitted reason preserves existing text, a nonempty reason replaces it, and
an explicit empty value (`--reason ""` or `--reason=`) removes only that reason.
A bare `--reason` with no value is invalid. The old `--hide REASON` interpretation
is not retained or guessed at: remaining text follows the new selector/positional/
group grammar. Help and applicable errors teach `--hide --reason VALUE`, but an
old-looking invocation valid under the new grammar cannot reliably be detected
and follows that grammar. This compatibility limitation is accepted.

`--title`, `--step` and `--comment` remain multiple-argument text-group markers,
ending at the next text-group marker after extraction of supported scalar/boolean
options. Preserve the original arguments and group identity through extraction;
intervening scalar/boolean options do not split a group or create another object.
Apply REQ-CLI-012 independently to each resulting group. Repeated supported
`--step`/`--comment` groups retain order; `--title` remains a singleton group.

Creation must parse recognized options and their values whether before or after
positional operands, then use the remaining fixed shorthand boundary: one category
argument followed by the task-title group, or one parent-selector argument followed
by the step-title group. Scheduling, hiding and reminders do not force the use of
explicit `--category`/`--title` forms. Explicit forms remain supported. For example:

```console
todo task --add --p1 --at tomorrow gatekeeper "Discuss OCA security issues"
todo add task Work "Write code" --at tomorrow "Write tests"
todo add task --category "Client Work" --title "Write code" "Write tests" --at tomorrow
todo schedule mailman --hide --at tomorrow --reason="no time"
```

For selector-taking scheduling/hiding commands, extract supported scalar/boolean
options independently of the selector's position too: `todo hide --at "1 month"
40153280` and `todo hide 40153280 --at "1 month"` select the same item and date.
Remaining unmarked selector arguments retain their original phrase boundaries.
The scalar's one-argument value must not absorb later selectors. Preserve explicit
text-group, literal and noun-action boundaries rather than globally reinterpreting
creation text as selectors. Leading scalar noun-action aliases consume their
adjacent values as explicitly defined by REQ-CLI-033; selecting a workflow does
not move its scalar value behind the selector.

The two-task title examples retain their original two quoted title arguments.
In one-selector comment/completion shorthand, only the first unmarked argument
is the selector and the remaining creation text follows REQ-CLI-012. Explicit
multi-term selection uses the existing text-marker boundary. Positional `move`
retains one source argument followed by one joined destination, independently of
creation grouping. Existing `--to`/`--task` destination/rename boundaries and the
bare/empty promotion exception remain governed by REQ-MUT-004, REQ-MUT-005, rather than
being silently changed by creation option extraction.

`--literal ARG` inserts exactly the next original argument into the current
selector or supported text value without marker interpretation. Every
selector-taking command, including `reopen`, supports literal selector insertion;
this is escaping, not content creation. Alias, global/scalar extraction and equals
handling must preserve it. Several literal insertions are valid where several
terms are valid. They do not alter candidate scopes or lifecycle validation.

Missing, unknown, duplicated singleton or conflicting options fail with usage
status 2 before synchronization/mutation. Documented repeatable groups and literal
insertions retain their exceptions. An empty value is allowed only where explicitly
documented, including reason removal and the existing move promotion forms.

### REQ-CLI-012 — Space-sensitive creation groups

Task titles, step titles, and comment bodies must use this rule, independently
for each positional creation-text group and each explicit `--title`, `--step`,
or `--comment` group:

1. Examine the original argument contents, including `--literal` insertions,
   before trimming. If none contains the ordinary space character U+0020, join
   the arguments with one ordinary space to produce one value.
2. If any argument contains U+0020, each argument is one separate value, in
   argument order. Leading or trailing spaces count as a trigger.
3. Trim leading and trailing U+0020 from each resulting value, then apply its
   existing domain text normalization and validation. Preserve internal spaces,
   line breaks, tabs, and other valid content. An empty or invalid resulting value
   rejects the complete request before its first mutation; never silently drop it.

Grouping uses argument content, not the presence of shell quote characters.
`'a'` and `a` are identical arguments; `'a '` contains a significant trigger
before trimming. Tabs and line breaks alone are not U+0020 triggers. Existing
title/control-character validation still applies. This command-line edge-space
normalization does not rewrite existing remote text or editor-buffer content.

```console
todo comment task a b c d
# one comment: a b c d
todo comment task "decide algo" implement "test results"
# three comments: decide algo; implement; test results
todo comment task 'a ' b c
# three comments: a; b; c
todo add task Work "decide algo" implement "test results"
# three tasks in Work
todo add task --category Work --title "decide algo" implement "test results"
# the same three tasks
todo add step project --step "write code" "write tests"
# two steps under project
todo comment task --comment a b --comment "c d" e
# three comments: a b; c d; e
```

Repeated `--comment` and `--step` groups remain supported where documented.
Each group is evaluated independently; a space in one group cannot change another
group's interpretation. `--title` remains a singleton marker whose one group may
create several tasks. Selectors, category names, rename/move destinations, date
expressions, hiding reasons, and reminder offsets do not use creation splitting.
Aliases must retain the original creation argument boundaries until grouping.
No `--each`, `--no-parent`, `promote`, or `demote` syntax is introduced.

### REQ-CLI-024 — Discoverable help and canonical vocabulary

`todo help` and `todo --help` must display top-level help. `todo help COMMAND`
and `todo COMMAND --help` must produce equivalent command help and succeed without
loading configuration, cache, binding, or network state.

Top-level help must explain the primary sequence: view work, inspect an item,
record progress, maintain state, and produce a report. Each command's help must
contain its canonical synopsis, a short explanation using the product vocabulary,
the common example, important destructive or state-dependent constraints, and
supported aliases after the canonical form. Every command syntax error must identify
the command/problem and offending input where applicable, then show short valid
usage and one concrete applicable example. Date-boundary errors additionally show
the accepted absolute/relative forms. Do not replace API/domain/recovery diagnostics
with generic usage text, expose secrets in examples or guess an intended command.
Keep help synchronized with supported behavior: `reopen` accepts no comment creation,
`someday` shows configured hidden-category work rather than all undated items,
and quoted scalar values, boolean hiding and aliases follow this specification.
Init help must explain terminal-only
first-time setup from no directory or missing/empty config, Todoist-derived choices
and the Work/category/hidden suggestions in REQ-INIT-003, hidden token input versus
TODOIST_TOKEN, final confirmation, and the preservation of populated configuration.

Creation/comment/completion help must explain REQ-CLI-012 with one joined example,
one split example and the trailing-space single-word batch spelling. Move help
must show positional category change, parent attachment and an empty positional
destination for promotion, plus the retained `--category`/`--to` and both `--task`
promotion spellings. Explain the first-argument source boundary, joined target,
typed ambiguous-target choices, and unchanged rejection of a step-to-category
move.

Help for scalar noun-action aliases must show the adjacent option-value pair
before the task selector or parent/step selector pair under REQ-CLI-033. Explain
that a multiword date, new name or move destination is one quoted shell argument;
do not teach a selector between the option and its value. Comment-editor help
must instruct deletion of the entire comment block and explain that removing an
interior header alone makes its remaining body part of the preceding block under
REQ-COMMENT-006.

Ordinary user output must say `task`, `step`, `category`, `attention`, `reminder`,
and `hidden`; it must not expose Todoist field names such as `item`, `project_id`,
`parent_id`, `checked`, or `sync_token` except where technical diagnostic context
is necessary and explained.

### REQ-CLI-032 — Prompting, recovery, and partial-failure interaction

Prompting is allowed only when both stdin and stdout are interactive terminals.
A non-interactive operation needing a choice or confirmation must fail unchanged
unless an explicit documented non-interactive confirmation option applies.
All questions must use one shared prompt/input function which writes the prompt
and flushes stdout before blocking for input. Apply to selections, confirmations,
setup values and hidden credential prompts, preserving secret input, terminal
checks, cancellation/defaults, input validation and command-specific `--yes`
policies. Sharing input must not grant new bypasses for selections, wizard steps
or destructive confirmations. Do not repeat the same warning before and after
one answer; cursor confirmation shows the old timestamp (or none/corrupted),
the proposed resolved timestamp and the one applicable boundary warning under
REQ-REPORT-013.

Every successful mutation must identify the selected item and resulting state.
When a previous value helps explain the change, output must include previous and
resulting values. No accepted-change line may appear before Todoist accepts the
corresponding operation.

A known rejection must identify the operation, affected item/category/setting or
resource, violated condition, and the one concrete recovery command or option when
exactly one safe applicable recovery is known. It must not guess an ambiguous
target, recommend an invalid operation, dump secrets, silently repair state, or
claim success for an unchanged or partially failed command.

For an ordered partial mutation, accepted operations must remain accepted; the
first failure stops later operations. Output must distinguish accepted, failed or
outcome-unknown, and unattempted operations, exit nonzero, and perform no
compensating rollback. The same classification applies after interruption under
`REQ-LOCAL-006`.

Creation must never return silently on failure or an unknown outcome, including
when no created ID can be established and the saved cache is older or
unusable. Always identify the attempted operation/title, what is known about its
remote outcome, the failure and applicable read-only recovery. A matching
pre-existing title or issue number is not proof of creation. When creation succeeds
with attention, identify the accepted item and actual resolved attention so an
accepted date is observable; never silently claim requested scheduling succeeded
when the authoritative object has no corresponding attention.

When accepted or outcome-unknown remote work is followed by reconciliation or
local publication failure, distinguish that remote outcome from the later failure.
State that the last successfully saved cache may still show older data and give
`todo --refresh now` as read-only recovery. Preserve needed unreported observations.
For recurring completion/undo, warn against repeating the mutation as recovery,
because it can change another occurrence. Report actual invalid retrieved state
and the needed external correction when known; a local cache error is not proof
that Todoist data needs repair. Do not persist a special cache-warning/block mode.

Accepted-change output describes actual remote changes or occurrences. Internal
preflight/validation steps must not appear as completed tasks or generic
`Completed: validate completion tree` records.

### REQ-CLI-033 — Supported compatibility aliases and rejected legacy commands

All aliases must delegate to the canonical workflow with identical selection,
validation, confirmation, ordering, state, output, and status. A retained leading
noun-action flag selects the workflow before ordinary option parsing. For the
scalar actions listed below, consume the adjacent option-value pair before their
item operands as defined below, using the ordinary scalar-option arity and
validation rules. Boolean actions and creation text-group markers retain their
own arities; they must not consume a selector as an invented scalar value.


- `close` and `closed` alias `done`; `unclose` and `undone` alias `reopen`;
- `wait` and `due` alias `schedule`, while `--due` aliases canonical `--at`;
- `--schedule` also aliases `--at` everywhere that date option is accepted,
  including creation, scheduling and hiding for tasks and steps; all three take
  one scalar value and share equals syntax and singleton/conflict checks;
- `comments` aliases `comment`, including its no-text read, creation and retained
  noun-action/editor forms, help, arguments, output and statuses;
- `categories` aliases `category`;
- `--close` and `--closed` alias creation-time `--done`;
- `--new` and `--create` alias `--add` in retained noun-action forms;
- `todo category --create NAME` aliases category creation;
- `todo add comment` aliases comment creation.

For `move`, retain `--category`, its `--to` alias, and `--task` (including bare
and empty-value promotion) alongside the positional destination form. Their
operand boundaries and behavior remain as defined in REQ-MUT-004.

The retained noun-action actions are exhaustive:

| Noun | Retained actions |
|---|---|
| `task` | `--add`/`--new`/`--create`, `--done`/`--close`/`--closed`, `--undone`/`--unclose`, `--delete`, `--wait`/`--waiting`, `--at`/`--due`/`--schedule`, `--reminder`, `--priority`/`-p1`…`-p4`/`--p1`…`--p4`, `--move`, `--rename`, `--comment`, `--step` |
| `step` | `--add`/`--new`/`--create`, `--done`/`--close`/`--closed`, `--undone`/`--unclose`, `--delete`, `--wait`/`--waiting`, `--at`/`--due`/`--schedule`, `--reminder`, `--priority`/`-p1`…`-p4`/`--p1`…`--p4`, `--move`, `--rename`, `--comment` |
| `comment` | `--add`/`--create`, `--edit` |
| `category` | `--add`/`--create` |

For these scalar noun-action aliases, VALUE must be exactly one shell argument
immediately following the action option, or the same value in `--option=VALUE`
form. A multiword value must be quoted. The selected workflow receives that scalar
value and the remaining item operands; it must never put a selector between the
option and its value or join later selectors into the value.

| Scalar action | VALUE | Task form | Step form |
|---|---|---|---|
| `--at` / `--due` / `--schedule` | attention expression | `todo task --due VALUE SELECTOR` | `todo step --due VALUE PARENT_SELECTOR STEP_SELECTOR` |
| `--priority` | priority | `todo task --priority VALUE SELECTOR` | `todo step --priority VALUE PARENT_SELECTOR STEP_SELECTOR` |
| `--reminder` | reminder offset or `clear` | `todo task --reminder VALUE SELECTOR` | `todo step --reminder VALUE PARENT_SELECTOR STEP_SELECTOR` |
| `--rename` | new name | `todo task --rename VALUE SELECTOR` | `todo step --rename VALUE PARENT_SELECTOR STEP_SELECTOR` |
| `--move` | positional move destination | `todo task --move VALUE SELECTOR` | `todo step --move VALUE PARENT_SELECTOR STEP_SELECTOR` |

For example:

```console
todo task --due tomorrow "Release plan"
todo task --due "tomorrow 10:00" "Release plan"
todo step --due tomorrow "Release plan" "Write summary"
todo task --priority P1 "Release plan"
todo task --reminder 1h "Release plan"
todo task --rename "New release plan" "Release plan"
todo task --move "Client Work" "Release plan"
```

The leading `--at`/`--schedule` actions are exact synonyms of `--due` and consume
their values identically. Reminder repetition, date-alias conflicts, priority
validation and no-op rules remain those of the canonical workflow. The fixed
priority spellings `-p1` through `-p4` and `--p1` through `--p4` already encode the
value and consume no additional priority argument. Rename supplies one new-name
value to the canonical rename workflow. Move supplies one destination value to
REQ-MUT-004's positional-destination workflow, including its typed ambiguity and
the exactly empty destination for explicit step promotion; it adds no implicit
promotion or new move operation. Empty values remain invalid for other listed
actions. A missing value or missing item operand is a usage error before
synchronization or mutation.

These forms retain their leading noun-action position. Once creation or another
workflow is selected, ordinary options follow REQ-CLI-031. Canonical `rename`
and `move` retain their existing marker and positional grammars; the adjacent
single-value rule above defines the listed noun-action aliases only.

Those compatibility forms retain one shell argument for a task operand and one
parent plus one step argument for a step target. Later creation text uses
REQ-CLI-012; creation groups are not scalar action values. Other retained
action-specific text groups keep their joined-value rules. Their
`--wait`/`--waiting` compatibility form retains its reason operand and explicit
`--at`/`--due` requirement, translating that operand to `--hide --reason VALUE`;
it never invents a default date. These retained value-taking aliases are distinct
from the new boolean `--hide` flag. Applicable task action aliases must have step
counterparts using the identical canonical workflow, arguments, validation,
selection, output and partial-failure behavior at every supported depth. A
retained step-target form takes one immediate-parent selector argument (task or
step) and one direct-child selector argument; it does not gain one positional
argument per ancestor or a path grammar. Resolve parent ambiguity before child
selection. Canonical todo add step selects its parent across open tasks/steps;
the retained task --step action likewise accepts a step parent. Applicable step
noun-action counterparts delegate to the same workflows. This adds no creation-
time step priority option or unsupported lifecycle operation. Canonical `hide`
and `unhide` work on eligible tasks and steps under REQ-SCHED-014.

The public parser must not register `check`, `show`, `resume`, or `ask` as
commands or compatibility aliases. `report --show-cursor` remains a documented
option and is not a `show` command.

### REQ-CLI-034 — `now` views, category filters, and actionable ordering

The supported forms are:

```console
todo now
todo now --all
todo now --refresh
todo now --category CATEGORY
```

Normal `todo now` must display every actionable task and actionable open step as
an independent row, in the urgency sections and order defined by REQ-DOM-010.
Use REQ-OUT-021 and TPL-NOW rather than category headings or nested task groups.
Every included item retains its own row; each step row ends with its complete
ancestor path under REQ-OUT-015, root task first and immediate parent last.
It must omit completed objects, configured hidden categories, future-hidden tasks
and their trees, and future-hidden steps and their subtrees.

`--all` must include every open managed task and open step regardless of
temporary or category hiding, while still excluding completed objects.
`--category` must resolve one current category case-insensitively, restrict the
scope first, and retain the chosen view's normal visibility and urgency rules.
It may be combined with `--all`. A missing category is an operational error with
no normal list; a valid empty scope is successful. All variants use the same
flat-row presentation, own-priority/date ranking and timing format. `--all` changes
inclusion only: it must not classify rows against a simulated future date or
bypass existing invalid-state validation. Retain applicable inline own-hiding
reason annotations under TPL-NOW and REQ-OUT-017. Do not add TPL-LIST's separate
Hidden until or Reason lines: `--all` uses the normal NOW presentation and adds
the otherwise hidden tasks and steps to its population.

Without `--refresh`, the view must use the local cache. With it, the view must
synchronize before validation and output; refresh failure must produce no normal
view. Recompute time-derived sections and countdowns using the view's current-time
reference even when reading an unchanged cache; this does not require network
access. After refresh, use the returned authoritative account timezone. Every
successful empty variant must print only `No actionable items.` under TPL-EMPTY
in REQ-OUT-020, without a NOW header or empty sections. The no-argument `todo`
invocation remains exactly equivalent under REQ-CLI-030. Optional configured paging
follows REQ-OUT-018 regardless of view height; all rows and urgency order remain
intact. Without a configured pager the view is direct.

### REQ-CLI-027 — `waiting` and `someday` views

The supported forms are:

```console
todo waiting [--refresh]
todo someday [--refresh]
```

`waiting` must show the current temporary-hiding snapshot: currently suppressed
own-hidden tasks and independently own-hidden steps nested under their parents.
It must exclude configured hidden categories, items hidden only by inheritance
as independent entries, and policies whose account-local attention day has arrived.
Retain the complete ancestor chain to every independent entry as context; render
an ancestor only once, marking context-only rows without an own-hiding date/reason.
At each sibling level, use the same alphabetical ordering as the report Hidden
snapshot. Render
the snapshot with TPL-WAITING: compact priority/title, hiding day and actual
optional reason; omit absent reason parentheses, indent steps beneath parents and
explicitly mark context-only parents. Reason presence must not determine inclusion.
The report's own output format is unchanged.

`someday` must show every open task and open step in all configured hidden
categories, not only one literally named `Someday`. It must exclude completed
objects. Task groups sort by priority, lowercase category, lowercase task title,
and stable ID; at each child level, steps sort by their own priority, lowercase
title, and stable ID. Render every included descendant at its actual depth.

Both are cache-first and follow the refresh failure rules of `REQ-CLI-034`.
An empty view, including an explicitly empty `hidden_from_now`, must print its
exact `REQ-OUT-020` message and exit successfully.

### REQ-CLI-021 — Task, step, and category inspection

The supported forms are:

```console
todo task [--refresh] SELECTOR
todo step [--refresh] SELECTOR
todo category [--refresh]
```

Task inspection must select open parent tasks only and use compact TPL-DETAIL:
its own stored priority, category and title; actual due date/time plus relative
Due with actual recurrence
and reminders; Waiting with optional age; nonempty ordinary Description;
recursive Steps; and owner Comments. Do not present derived effective priority as
editable state or repeat redundant open/absent scalar fields. Include all current
open descendant steps and all known completed descendants retained under
REQ-CACHE-006, recursively preserving immediate-parent relationships. Completed
history survives cache clearing until successful final reporting permits
cleanup; it does not promise recovery of descendants never retrieved or already
released after reporting. Disclose incomplete historical coverage under TPL-DETAIL,
including with no retained completed descendants. Within
each immediate sibling set, place known creation timestamps first, newest full
instant first, with ascending stable-ID ties. Place unknown creation timestamps
after all known timestamps, ordered by the same ascending stable-ID comparator.
Apply this order independently at every depth, with each item's own state and
timestamps. A valid unknown creation time does not suppress an item or its subtree.
Owner comments and each descendant's nested own comments are separately oldest first
by full current `posted_at`, retaining ownership and deterministic ties.

Step inspection must select open steps across all managed parents and use the
same compact detail format with parent context and inherited category, its own
fields and own Comments, and the same recursive Steps section for its own
descendants. When no descendants are known, inspection prints Steps: none; this
does not prove that no unobserved completed descendants exist. Show the full ancestor path and
preserve inherited waiting context under TPL-DETAIL. A task's Comments must never
include or duplicate step-owned comments. Account-local display timestamps use the compact template
format while sorting retains full instants.
Category inspection must list every current direct child of the bound root case-insensitively
alphabetically, ignoring Todoist manual project order.

All three commands are cache-first and accept `--refresh`. Historical parents or
steps are not inspectable through these ordinary forms; only bounded reopen and
delete resolve completed objects.

### REQ-CLI-016 — Search population, matching, ordering, and coverage

The supported form is:

```console
todo search [--all] [--refresh] TEXT
```

Search is read-only discovery and can never select or mutate. It must search task
and step titles, ordinary descriptions, temporary-hiding reasons, and comments
owned by either tasks or steps.
One individual field must satisfy the complete query; terms cannot combine across
fields, comments, or objects.

By default, include all open managed tasks/steps and their surviving own comments,
including temporarily hidden work and work in configured hidden categories.
`--all` must additionally search every completed task, step, and surviving comment
retained as unreported history under REQ-CACHE-006. It must not promise complete
or permanently retained history, perform full-history backfill, or accept `--since`.
Every `--all` result, including
empty results, must print the coverage line from `REQ-OUT-020`.

One argument containing spaces is a contiguous phrase. Several terms must all
match the same field case-insensitively in any order and need not be contiguous.
An object matching several fields appears once. Output displays titles, not match
excerpts or field names. A step-only match includes its complete ancestor chain
as context, sharing ancestors once, and omits unmatched siblings and descendants.
An ancestor-only match does not include unmatched descendants. Context does not
itself count as a match. A step-comment match belongs to its owning step with
the same full ancestor context;
it must not become a match on the parent's own fields or comments.

Task groups sort by priority, lowercase category, lowercase task title, and stable
ID. At each child level, retained matching or context-only steps sort by their
own priority, lowercase title, and stable ID; retain the actual hierarchy.
Attention does not affect search ordering. Empty search is a successful explicit
message under `REQ-OUT-020`.

### REQ-CLI-035 — Selector scopes, ambiguity, and implicit lookup

Selectors must match titles only among types allowed by the command. Normalize
each term and candidate to NFC, compare with Unicode case folding, preserve accent
distinctions, and require every nonempty term to occur in the same title in any
order. One argument containing spaces is one contiguous phrase. Exact title equality
has no precedence over broader substring matches.

Candidate scopes are:

- task inspection: open parent tasks;
- step inspection: all open steps at depths 1–4 across managed parents;
- step-creation parent and nonempty item-move destination: open tasks and steps;
- implicit top-level lookup: open tasks and steps independently;
- ordinary mutation: open types allowed by that operation;
- reopen: eligible occurrences in `(report cursor, now]`;
- completed delete: currently completed non-recurring objects completed in that
  interval, in addition to ordinary open deletion candidates.

For a recurring object, only its latest undo-eligible occurrence may participate
in reopen selection. Completed candidates must show their completion time. Steps
must show the complete ancestor path and category context under REQ-OUT-015.
Ancestor paths are display context, never an extra selector syntax or title-match field.

When several candidates match interactively, print the exact numbered structure
from `REQ-OUT-020`; accept only a displayed number, `q`, blank, or EOF, re-prompting
invalid numbers. Cancellation exits `1` unchanged. Non-interactive ambiguity must
print the identical candidates, never prompt or render a candidate detail, and
exit `1` unchanged.

Unrecognized top-level arguments must be treated as intentional implicit lookup,
not accompanied by an unknown-command warning or typo-command suggestion. A task
and step may compete in the same ambiguity set. No match is an operational error,
unlike an empty explicit search, and must include the complete selector actually
searched, with phrase/term boundaries represented sufficiently to explain the
query. For `todo schedle`, for example, identify `schedle` as the lookup term;
when the actual query contains further arguments, do not falsely report only its
first word. All selector-taking commands support REQ-CLI-031 literal escaping.

Only a successfully searched applicable population with no match may produce a
no-match diagnostic. Propagate cache, binding, synchronization and mapping errors
with their actual reason and safe recovery advice, including implicit lookup;
never replace a cache-read failure with `no matching item`.

Task and step ambiguity candidates show their own attention timing using
REQ-OUT-021 wording and urgency colors, alongside the retained title/type,
category/parent context, numbering and completion timestamp. TPL-AMBIGUITY fixes
the placement. Use one command-time reference and the authoritative account
timezone; do not perform an extra network read just to decorate the chooser.

### REQ-CLI-029 — Explicit cache clearing and refresh recovery

`--clear-cache` is a singleton boolean global option for an applicable cache-backed
read combined with `--refresh`, in either documented global option position.
`todo --clear-cache --refresh now` explicitly deletes the local published cache
and its saved sync token/timestamp, then rebuilds from authoritative state.
It is not inferred from an error and is never needed for an ordinary successful
refresh, which replaces the cache atomically. Without --refresh, or with a command
that does not accept refresh, reject the combination with usage status 2 before
changing files. Missing cache is harmless to this explicit clearing step.

Validate syntax, configuration, binding, applicable path safety and lock ownership
before clearing. Delete only the selected local current-cache state; preserve
configuration, credentials, binding, report cursor, separate unreported history,
and remote Todoist data. Never
follow an unsafe symlink or bypass existing permission/path protections. No new
confirmation is needed beyond the explicit switch. Explain that unreported
history is preserved. Clearing does not fill historical coverage gaps; reported
history may already have been released.
If the subsequent refresh fails, report that explicit clearing occurred and that
no new cache was published, with the actual failure and recovery advice. Never
claim to have retained a file the operator explicitly cleared.

Help and corrupt-cache diagnostics show ordinary read-only refresh first and
explicit clear-and-refresh as an optional local recovery, not automatic repair.
For an incremental failure with no evidenced sync-token discriminator, explain
that automatic token recovery could not be established and offer this existing
explicit path where applicable under REQ-SYNC-013. Do not suggest that clearing
repairs invalid credentials, configuration or authoritative managed data.
No backup, restore, rollback, implicit retry or mutation replay is introduced.

### REQ-CONFIG-002 — INI schema, validation, and compatible unknown settings

Configuration must be read from `~/.todo/config` as INI with this recognized
schema:

```ini
[todoist]
token = ...

[main]
project = Oracle
default_sections = ai, gatekeeper, engineer, Someday
hidden_from_now = Someday

[report]
warn_limited_history = true

[colors]
# optional base01, base1, red, green, yellow, blue, magenta, cyan overrides
```

`project`, `default_sections`, and `hidden_from_now` are required recognized
settings. Names are trimmed and preserve case. `default_sections` must contain
one or more nonempty comma-free values; `hidden_from_now` may be explicitly empty.
Empty list elements and exact or case-only duplicates within either independent
list are errors. Hidden names need not occur in `default_sections` and must not be
provisioned merely because they are hidden policy names.

`warn_limited_history` defaults to true and accepts only true/false. It suppresses
only an informational limited-history warning, never insufficient-history failure.
The legacy `default_wait_due` has no effect.

Color slots use Solarized Dark defaults. A recognized override must be a
case-insensitive six-digit `#RRGGBB`; shorthand, named, alpha, or unprefixed values
are invalid. Omitted slots retain defaults.

Unknown sections and keys must be ignored for compatibility, but malformed INI,
missing required settings, or invalid recognized values must fail distinctly.
Initialization must validate the complete configuration before network access
when a populated config is present, and before any Todoist mutation in every path.
The missing/empty-config wizard in REQ-INIT-003 may first make read-only discovery
requests after local safety and credential validation, then construct and validate
the complete INI. The schema's Oracle/category example is illustrative, not the
wizard fallback or an implicit default. Ordinary commands must not invent
structural defaults. Credential precedence and
file safety are defined by `REQ-SEC-004` and `REQ-SEC-005`.

### REQ-CONFIG-003 — Optional configured pager extension

This extends REQ-CONFIG-002 for the recognized `[main] pager` key; all other
configuration, credential, validation and local-file safeguards remain applicable.

`[main] pager` is optional and defaults to disabled. An omitted, empty or
whitespace-only value disables paging. A nonempty value is a shell-like command
argument string, parsed with quoting and escaping and executed directly without
a shell, matching the editor-command convention in REQ-COMMENT-007. The first
argument names the executable (looked up on PATH when not an explicit path);
remaining arguments are passed unchanged. Shell substitutions, variable expansion,
redirections and pipelines are not interpreted. Malformed quoting, NUL, or an empty
executable after parsing are invalid recognized configuration values; fail before
network access under the ordinary configuration-validation rules. Executable
availability is checked only when launching an eligible pager; absence follows
REQ-OUT-018's complete-output fallback and does not prevent direct operation.
There is no implicit pager or PAGER-environment fallback. For example:

```ini
[main]
pager = less -FR
```

This example enables the optional pager; it is not a default or a requirement to
use GNU less. The command's fit/navigation options remain the operator's choice.
REQ-OUT-018 defines the paged views, color delivery, failure behavior and final-report
exception. First-time setup may omit this optional key or leave it empty; it must
not enable a pager by default or add a required pager-setup step.
