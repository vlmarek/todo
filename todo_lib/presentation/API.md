# Rendered documents and delivery

All exports are in `todo_lib.presentation`. Renderers are pure: they return an
immutable `Document(stdout, stderr)` with LF text and no terminating LF. They
never make requests, mutate snapshots, advance cursors, or write streams. The
caller supplies a reconciled shared `Snapshot` (including known retained
children/comments), its authoritative account timezone, and one aware `now` for
the whole view. Domain validation and refresh-failure handling precede rendering.
A failed refresh must never invoke normal rendering/delivery.

- `render_now(snapshot, now, *, items=None, hidden_names=(), all_items=False,
  category_id=None, color=Color())`: default domain actionable population, or
  every open item for `all_items`. An optional supplied `items` population is
  already selected by the caller. Classification/order/counts always use own
  values and this same `now`. `category_id` is already resolved by the caller.
- `render_detail(snapshot, item_or_id, now, *, color=Color())` includes every
  known recursive descendant, each owner's own comments, and the stderr coverage
  disclosure. `render_comments(snapshot, item_or_id)` renders only own comments.
- `render_categories(snapshot)` lists current categories alphabetically.
- `render_waiting(snapshot, now, *, items=None, hidden_names=())` derives the
  current own-hidden population unless the caller supplies it. Intermediate
  ancestors are structural context only.
- `render_someday(snapshot, *, hidden_names=(), items=None)` defaults to open
  items in the configured hidden categories. `render_search(snapshot, items, *,
  all_items=False, earliest_completion=None)` consumes matched owners selected by
  the search component. Both preserve hierarchy, including context ancestors,
  and sort groups/children by their specified own values. They do not perform
  matching. Search-all coverage is always emitted, including for an empty result.
- `render_ambiguity(snapshot, query, candidates, now, *, interactive=True,
  color=Color())` consumes an ordered sequence of shared Item/Category records,
  including mixed destination candidates. It never reorders candidates or reads
  input. `invalid_selection(count)` supplies the retry text; cancellation and
  actual prompting remain with the caller. Deliver choices as `ambiguity`.
- `render_report(snapshot, start, until, *, finished=(), progress=(), hidden=())`
  consumes **already eligible** report view data. `ReportEvent(item_id, instant,
  kind='completed', body=None, event_id=None, source_order=0)` represents an
  occurrence/comment. Finished must contain root-task occurrences; Progress
  contains step completions and comments. Events sort by exact instant, non-null
  event ID, object ID, stable source order and original sequence order. Category
  groups sort alphabetically; task groups sort by oldest event then stable ID.
  Hidden receives selected own-hidden Items and gains only necessary structural
  ancestors. No interval, completion, visibility, or finalization eligibility is
  calculated here: even supplied events outside start/until remain rendered.
- `render_report_cursor(cursor, zone)` renders a supplied nullable cursor and
  its authoritative timezone for the `report-show-cursor` view.
- `history_warning(days)` and `pagination_progress(resource, pages)` return
  stderr-only named fragments. Callers determine whether/when each applies.

`absolute`, `compact`, and `actual_due` use `instant_datetime` only for local
calendar/display conversion. Sibling and comment order use `ordered_siblings`
and `instant_key`, retaining arbitrary fractional precision and stable ID ties,
with null timestamps last. No datetime projection is an ordering key. Waiting
Since interpretation is display-only; list/report reason text remains literal.
`edge` removes blank edge lines, preserving indentation and internal blank lines.
Date-only due values remain dates; no display-only exact instant is invented.

## Accepted receipts

Call receipt functions only for known accepted operations. `render_mutation`
accepts snapshot, Item, action (`Updated`, `Created`, `Completed`, `Reopened`),
ordered `(field, previous, result)` changes, optional accepted creation
`attention`, and ordered `also_reopened` Items. Scalar values are display-ready
(e.g. `P2`, `P1` for priorities); None/empty values become `none`, booleans become
`off`/`on`, and unchanged fields disappear. Updated/moved receipts with no
changed fields are empty. For completed objects that departed
active Sync, pass the preserved pre-completion snapshot and Items so ancestor
context remains available. Creation attention must be authoritative, never the
unreconciled request string.

`render_move(before_snapshot, before_item, after_snapshot, after_item)` derives
parent/category changes by ID, formats their snapshot-specific paths/names, and
uses the resulting type. Distinct identities with identical display text still
produce changed-field lines. Call once per direct
move, not for descendants. `render_created_category(category)` supplies its exact
prefix. `render_comment_bodies(snapshot, owner, accepted_bodies, *,
owner_identified=False)` groups actual accepted bodies under at most one owner
heading; use `owner_identified=True` after an earlier completion identifies the
owner. An empty body sequence has no receipt.

`render_comment_edit(snapshot, owner, *, added=0, edited=0, deleted=0,
outcomes=None)` produces the editor success summary (or no text for no changes).
For partial failure supply ordered `CommentOutcome(status, operation, body=None,
timestamp=None, position=None, reason=None)` records. Status is `Accepted`,
`Failed`, `Unknown`, or `Not attempted`; use past-tense operation wording for
accepted details and infinitive for others. Each record requires an identifying
body, timestamp, or operation position. The function keeps accepted details on
stdout and all other outcomes plus the heading on stderr. The caller owns
first-failure stopping and any required cache/recovery diagnostics.
`render_receipts(documents)` joins receipt documents in operation order per
stream without changing their outcomes.

## Color and terminal delivery

Create `Color.for_stdout(original_stdout, mode='auto', environ=None,
slots=settings.colors)` **before rendering**. Pass the same Color to every
renderer for that view. Auto uses the original output terminal, NO_COLOR and
TERM; always/never override auto. Renderers never measure terminal dimensions.
Color changes only ANSI sequences, never visible bytes.

`deliver(document, settings, original_streams=None, view_kind='now', *,
environ=None)` returns 0 after complete write/flush or a successful pager exit.
`settings` is the local Configuration API, whose `pager` is already parsed argv.
`OriginalStreams(stdin, stdout, stderr)` captures the original streams; omitted
streams use the current standard streams. Document stderr is direct. Eligible
view kinds are `default`, `now`, `task`, `step`, `category`, `comment`/`comments`
(no-text only), `waiting`, `someday`, `search`, `report`, `report-preview`, and
`report-show-cursor`. Use `report-final` for final reports, `ambiguity` for
choices, `prompt`, `help`, `receipt`, `diagnostic`, or `mutation-preview` for
direct output. Unknown kinds are also direct. Never deliver an interactive
decision or mutation as an eligible read view.

Paging additionally requires configured argv, interactive original stdin/stdout,
and TERM other than dumb. Every eligible complete document, even empty or short,
is written to an unlinked mode-0600 TemporaryFile before launching exact argv
without a shell. Child output/error inherit the original terminal; the child
can use its inherited controlling terminal for navigation. No producer pipe or
write/quit race is involved. Exit zero succeeds even without reading the file.
Launch/input-preparation failure or nonzero exit warns and writes/flushes the
complete original stdout text, without refetching. Temporary input closes and
original terminal attributes restore on success/failure/interruption.

`OutputError` propagates on incomplete direct write/flush (including fallback):
map it to exit 1 and do not finalize a report. `KeyboardInterrupt` propagates
after child termination/reaping and terminal/file cleanup; the command's SIGINT
handler must map it to exit 130, with no fallback or cursor advancement. A child
terminated by SIGINT follows the same interruption path. Final reports always
write/flush directly; cursor/history cleanup belongs after successful delivery.
The application supplies no default pager and requires no external executable.

`render_reminder_replacement(snapshot, item, removals, additions)` returns a pure
proposed-change document, using safe owner paths, complete reminder scheduling
fragments and type-specific retention hints. Unresolved additions are labelled
`expression (Todoist): ...`; no timestamp is inferred. The workflow delivers it
directly and invokes the shared default-cancel prompt before any mutation.
Accepted reminder receipts use reconciled values with scalar `0m`/offsets and
the shared `at ...` absolute fragment. Creation shows `  Reminders: RESULT`.
