# Architecture

Status: Initial outline

## System context

The user invokes `todo` from a shell. `todo` communicates with:

- Todoist, the authoritative task store and notification provider
- local files under `~/.todo`, used for configuration, cache, cursor, and lock
- the terminal, used for output and ambiguous-match selection
- the user's phone indirectly through Todoist synchronization and reminders

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

## Report flow

1. Load the report cursor without changing it.
2. Synchronize current Todoist data and relevant activity.
3. Generate Finished, Progress, and Hidden sections.
4. Print the report.
5. If and only if `--final` was requested and all previous steps succeeded,
   advance the cursor.
