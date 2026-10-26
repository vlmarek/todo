# Syntax API

`parse(argv)` accepts shell arguments after the executable name and returns a
frozen `CommandRequest` or `HelpRequest`. It performs no I/O and imports only the
public domain API for text and reminder validation. Parse before loading config,
synchronizing, or dispatching a workflow. `UsageError` has `status = 2`, `command`,
`problem`, `offending`, `synopsis`, and `example`; its string contains a short
usage diagnostic. Domain/state/timezone-dependent checks still belong to workflows.

A command request exposes:

- `command`: canonical workflow (`lookup` for all unrecognized top-level words).
- `target`: `task`, `step`, or `category` for creation/inspection; `item` for
  general operations. Retained step actions use `step` and an explicit `parent`.
- `selector`, `parent`: tuples retaining each original phrase/term. Parent in a
  retained step action identifies the immediate parent, not a path. Resolve it
  before resolving the direct child in `selector`.
- `groups`: ordered `TextGroup(kind, arguments, values, literal_indices)` records.
  `arguments` retains original shell boundaries and edge spaces; `values` holds
  independently split, domain-validated creation values. Kinds are `title`, `step`,
  and `comment`. Inline steps apply to the sole new task. Completion comment
  values are unprefixed; the completion workflow adds `Done: ` after acceptance.
- `options`: sorted `(name, value)` pairs; `option(name, default)` reads a value.
  Names omit `--`. Booleans are `True`, scalar values retain their contents
  (priority normalizes to `P1`…`P4`), repeated reminders are a tuple in marker order.
  Absent options stay absent; in particular absent `reason` differs from `''`.
  Category creation uses the joined `name` option. No temporal reference is sampled.
- `destination`, `destination_kind`: `None` when absent. Positional move joins
  destination words into one phrase and uses `positional`, or `promotion` with
  `('',)` for exactly empty promotion. Marker forms use `parent` and preserve
  phrases, `promotion` for bare/empty `--task`, or `category` with the category in
  options. Both parent/promotion and category can coexist. Rename uses `name`
  with the joined destination. Parent/category state checks belong to consumers.
- `selector_literals`, `parent_literals`, `destination_literals`: positions of
  explicit literal insertions in their respective phrase tuples. Text groups
  retain their own literal positions. Scalars retain the escaped value itself.

`render_help(command=None)` is independent of state. `HelpRequest.command` is
canonical, or `None` for top-level help. T16 can extend help content and public
wiring without changing the parser or depending on configuration.

All interactive workflows must call `prompt`, including setup values, hidden
tokens, confirmations and destructive second confirmations. It checks both TTYs,
writes and flushes stdout before every blocking read, and supports defaults,
validation/conversion, cancellation, and hidden input. A validator returns the
accepted value or raises `ValueError` to retry. Blank uses a supplied non-`None`
default; otherwise validators decide blank policy. EOF and `q` cancel by default.
`Cancelled` and noninteractive `InputError` have status 1; handled SIGINT raises
`Interrupted` with status 130. Exceptions do not include the entered secret.
No confirmation bypass policy is built into this function.

Questions and candidates use stdout; validation errors and retry notices use
stderr, including redacted hidden-input diagnostics. Both output streams are
flushed after writing. Only stdin and stdout must be terminals.

For offline consumers, `stdin`/`stdout`/`stderr`, `reader(stream)`, and
`hidden_reader(stream)` can be supplied. The hidden reader is an explicitly
trusted boundary that must suppress echo and restore it on all exits; otherwise
the shared termios guard surrounds reading and restores terminal attributes in
`finally`. Failure to disable echo raises `InputError` without an echoed fallback.

`select([(number, stable_object), ...], render=callback, ...)` prints the supplied
numbered candidates. The callback owns candidate presentation/context. Selection
accepts only displayed numbers, `q`, blank or EOF and returns the original object.
It prints the identical candidates in noninteractive mode but fails before any
question or detail. Callers retain their documented confirmation and `--yes`
policies; this API grants no bypass for selection, setup, or delete-all.
