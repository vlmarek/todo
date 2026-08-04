# Architecture

Status: Initial outline

## System context

The user invokes `todo` from a shell. `todo` communicates with:

- Todoist, the authoritative task store and notification provider
- local files under `~/.todo`, used for configuration, cache, cursor, and lock
- the terminal, used for output and ambiguous-match selection
- the user's phone indirectly through Todoist synchronization and reminders

Capabilities delegated to Todoist and the implications of replacing it are
catalogued in `todoist-dependencies.md`.

## Responsibility boundaries

```text
CLI parsing and presentation
        ↓
Application command workflows
        ↓
Domain rules and validation
        ↓
Todoist adapter       Local persistence
```

### CLI parsing and presentation

Parses commands, aliases, flags, selectors, dates, and reminder offsets.
Formats normal output, previous-value feedback, warnings, and errors.

### Application workflows

Coordinate refresh, matching, validation, mutation, cache update, and output.
Ensure that validation and synchronization precede mutation.

### Domain rules

Define actionability, visibility, task/step constraints, effective urgency,
Someday restrictions, report membership, and sorting. These rules must not
depend on network access.

### Todoist adapter

Maps Todoist projects and items to domain values, synchronizes task data,
performs mutations, handles idempotency and retries, and manages reminders.

### Local persistence

Stores configuration, cache, report cursor, and runtime lock safely.

Todoist authentication resolves the token at command start. A nonempty
`TODOIST_TOKEN` environment variable takes precedence over the token stored in
`~/.todo/config`; the configured token is the fallback when the environment
variable is absent.

`todo init` consumes these existing credentials and never accepts or persists a
token argument.

## Initialization flow

The user creates local configuration before initialization. `todo init`
validates it, synchronizes Todoist, and provisions a missing configured root
project, configured initial categories, and the `waiting` label. It does not
choose structural settings or create a default config. Ordinary command flows
only validate these structures and never provision them implicitly.

`~/.todo/config` uses INI syntax. Configuration loading distinguishes a missing
file, malformed INI, and missing or invalid required settings and reports each
as a concise user-facing error rather than exposing parser exceptions.

The schema retains these keys:

```ini
[todoist]
token = ...

[main]
project = Oracle
default_sections = ai, gatekeeper, engineer, Someday
hidden_from_now = Someday

[colors]
# optional palette overrides
# base01 = #586e75
# base1 = #93a1a1
# red = #dc322f
# green = #859900
# yellow = #b58900
# blue = #268bd2
# magenta = #d33682
# cyan = #2aa198
```

`token` may be omitted when `TODOIST_TOKEN` supplies authentication. `project`,
`default_sections`, and `hidden_from_now` are the structural settings consumed
by init and ordinary commands. Comma-separated names are trimmed but preserve
their case. `default_wait_due` is not a supported setting because hiding always
requires an explicit date.

The configured `project` name is matched against Todoist project names by exact,
case-sensitive equality during initialization, synchronization validation, and
managed-scope resolution.

Unknown INI sections and keys are ignored for compatibility. This includes an
old `default_wait_due` entry: it has no effect and does not make the config
invalid. Recognized settings are still validated strictly.

The optional `[colors]` section recognizes exactly the palette slots `base01`,
`base1`, `red`, `green`, `yellow`, `blue`, `magenta`, and `cyan`. Solarized Dark
supplies the defaults shown above. Omitted slots retain their defaults; invalid
values for recognized slots fail configuration validation. Other keys are
ignored.

Each recognized color value uses exactly six hexadecimal RGB digits prefixed by
`#`, for example `#dc322f`. Hexadecimal digits are case-insensitive; shorthand,
named colors, alpha values, and other formats are invalid.

`hidden_from_now` is required as a recognized setting but may have an empty
value, meaning that no category is hidden from `todo now` by category policy.
Its nonempty names must be unique under case-insensitive comparison.
`default_sections` must contain at least one nonempty category name.
Names in `default_sections` must be unique under case-insensitive comparison;
exact or case-only duplicates make the configuration invalid.

The two lists are independent. `default_sections` only names category projects
that `todo init` creates when absent. `hidden_from_now` classifies current
matching categories for visibility and may contain names not present in
`default_sections`; init does not create categories merely because they are
listed as hidden.

## Read-only flow

Read-only commands load configuration and cached task data, validate the
complete relevant model, apply domain rules, and format results. Explicit
`--refresh` synchronizes Todoist before reading. Validation failure produces
diagnostics and no normal result output.

## Mutation flow

1. Load configuration and acquire the runtime lock.
2. Synchronize from Todoist.
3. Resolve the selected task or step.
4. Validate the complete proposed change.
5. Send the mutation to Todoist.
6. Update or refresh the cache.
7. Print previous and resulting values.

If synchronization, selection, or validation fails, no mutation is sent.

Validation is operation-scoped. Workflows check Todoist projects, labels, and
capabilities only when they depend on them rather than running a global
external-object preflight for every command.

When Todoist must interpret a due expression that the local parser cannot
classify, the workflow snapshots reminder state, performs the update,
synchronizes, and compares the resulting authoritative due/reminder state. Any
unexpected reminder change or invalid date-only/reminder combination is
reported without compensating rollback.

Workflows requiring multiple Todoist mutations are not assumed to be
transactional. Once a mutation is accepted, a later failure is reported rather
than automatically reversed. A subsequent synchronization reconciles the
cache with the authoritative partial result.

Deleting an open or completed item uses Todoist's direct delete operation.
Deletion must not be emulated by removing only cached data, and completed items
must not be reopened merely to make them deletable.

## Report flow

1. Load the report cursor without changing it.
2. Synchronize current Todoist data and relevant activity.
3. Retrieve every comment set required to evaluate and render the report.
4. Generate Finished, Progress, and Hidden sections entirely in memory.
5. Print the report.
6. If and only if `--final` was requested and all previous steps succeeded,
   advance the cursor.

Any required synchronization, activity, or comment failure aborts before
normal report output and leaves the cursor unchanged.
