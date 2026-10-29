# Named-zone scheduling: consumed contract and code navigation

Status: **Accepted**

Planning interpretation for TODO3-PLAN-015, inspected 2026-10-29. Product authority
is Design revision 15 in `../../named-timezone-scheduling.md`; its narrow precedence
governs new work. Historical accepted assignments and upstream evidence stay intact.
This note supplies technical choices and source navigation, not provider guarantees.

## Retained provider evidence

Use the original `upstream/api-v1.openapi.json` and its adjacent `manifest.json`.
These are already-retained inputs, with unchanged bytes. Original retrieval: 2026-10-24;
source: https://developer.todoist.com/api/v1/ . No new snapshot or live probe is
required. The JSON `tags[name="Due dates"].description` describes full-day, floating
and fixed named-zone due values for tasks and reminders, plus create/update examples:

- `due.string` with an explicit `due.timezone` asks the provider to parse in that
  named zone. Use `lang: en` for new English expressions; retained rules preserve
  original language. Do not rewrite English recurrence into a guessed date/offset.
- Full-day results use `YYYY-MM-DD`, null timezone and no invented clock. Fixed
  results use a UTC instant plus the named zone used for subsequent recurrence
  iterations. Floating results have local wall text and null timezone. Preserve
  original recurring wording/flag/language/zone separately from current occurrence.
- Exact fixed input uses UTC `due.date`; the explicit optional timezone overrides
  the provider's default account zone. A date alone does not create a recurring
  pattern: moving an existing recurring occurrence must retain its existing rule.

The Sync tag's Tasks Add/Update commands and Reminders Add/Update commands consume
that due object. Keep POST `/api/v1/sync` form encoding, command UUID, temporary-ID
mapping for creates and exact UUID status attribution. Relative reminders continue
using Sync `item_id/type/minute_offset`; absolute reminders use `item_id/type/due`.
Do not substitute REST `task_id` or invent a parser endpoint. The dedicated reminder
due contract, `ReminderDueAttribute` and `NotificationSyncView` still apply; see
`planning-contracts.md` for the retained named-wall-time reminder example and known
prose/example contradictions. Do not import a task-only required-field predicate
into the reminder open due object or weaken task mapping.

No inspected retained source establishes a CET/CEST/CST/EST mapping. Those tokens
stay in the original English expression and the provider owns acceptance and
normalization. Synthetic fixtures can establish forwarding and actual result
handling; they cannot establish live code interpretation, notification delivery or
future recurrence advancement.

## Compatible implementation boundaries

The integrated revision-14 baseline is
`26e4851ab89b3fa9b3125e66b3cb753198bb25e1`. Existing concrete APIs are:

- `domain/time.py`: `parse_attention(expression, now, account_zone) -> Attention`
  or `DomainError`; `Attention` contains kind/date/instant/expression and retained
  recurrence/language/zone/raw_due/epoch precision. `resolve_wall` refuses locally
  ambiguous/nonexistent times; remote interpretation uses the existing policy.
  `retain_recurrence` copies rule/language/zone after local instant resolution.
  `same_attention` is exact; `reconciles_attention` permits at most two seconds
  while keeping kind, account day and applicable recurrence/zone semantics strict.
  `parse_boundary` is a distinct report/cursor grammar and stays unchanged.
- `workflows/scheduling.py`: `propose` and `equivalent` build a complete `Proposal`
  with desired/retained/addition/removal reminders; `validate_proposals` validates
  the complete resulting tree before writes. `CaptureWorkflow._plan/_run` performs
  saved-ID selection, all local validation/removal consent, ordered Gateway calls,
  reconciliation/publication and actual `CaptureResult/OperationOutcome` receipts.
- `adapter/commands.py`: `due_arguments`, `Operation(expected_attention=...)`,
  `Gateway.create_task/update_task/create_reminder/update_reminder` and `execute`
  own request construction and attributed `Result` outcomes. The current serializer
  only emits explicit timezone inside its recurring branch. Its fallback and both
  Gateway/workflow comparison branches need inspection for new named input; do not
  let a new explicit zone become the account default or silently bypass applicable
  strict semantics just because an expression was delegated.
- `adapter/current.py`: `_seed/_signature/_merge/_map` preserve consumed fields,
  omitted deltas and raw due data. `local/codec.py` serializes `Attention` via the
  shared dataclass path and restores exact `epoch_seconds`; saved state/history
  round-trips, fixed/floating re-resolution and all direct constructors must remain
  compatible. Persisted schedule zones are per-value data; binding stays the one
  account/default timezone authority. No last-input-zone field is needed.
- `syntax/help.py` and the existing normalized `CommandRequest` supply one scalar
  per option, including equals and leading task/step action aliases. Preserve these
  boundaries and creation grouping. Shared workflow parsing extends the supported
  surfaces; do not add an alternate alias implementation.

T34 owns those coupled changes, necessary existing caller/fake/codec adaptations
and concrete compatible API documentation. It may leave an inspected consumer
unchanged when its existing representation and tests establish compatibility.

Recognize a final slash-containing valid IANA location token or `UTC`; invalid
location names fail clearly before writes. Do not interpret legacy short-code
ZoneInfo keys locally. Retain the original scalar for unresolved previews and the
remaining wording for the provider. No suffix means the binding-account default
for that value, regardless of preceding attention/reminder options or host zone.
An aware numeric-offset/Z input combined with a validated name keeps its supplied
instant/precision; the name supplies schedule metadata rather than reinterpreting
the clock. A supported local wall datetime without an offset becomes permissible
when an explicit name supplies its zone. Date-only input/result stays date-only.

Resolve a locally supported one-occurrence move first, then retain the previous
recurring expression/language/zone, including fixed/floating semantics. The input
zone and recurrence zone can differ. New delegated recurring expressions use their
new English wording and supplied zone; stale raw due/date/rule metadata must not
override that request. Todoist owns arbitrary expression normalization; no local
general recurrence classifier or parse-only request is introduced.

Use existing `equivalent/preserves_reminder` semantics over complete supported
kind/instant/recurrence/language/zone metadata. Equal first instants do not justify
matching distinct recurring zones or fixed/floating schedules. Omitted reminder
options and explicit keep preserve independent schedules/IDs. Account-local
visibility, hierarchy days, urgency and reports consume the resolved value under
their existing account rules; they do not adopt the input zone globally.

## Presentation consumers and verification

T35 consumes T34's actual completed APIs. `formatting.actual_due/reminders_text`
serve several surfaces; `timing/time_block`, `render_detail` and its separate
revision-14 row helper share them. `receipts.render_mutation` formats created due,
while `capture.reminder_values/_document` currently turn prior/result/retained
schedules into scalar strings. Add scoped opt-in formatting/caller adaptation for
selected-item scheduling detail and existing scheduling/creation receipts. Keep
defaults for now, waiting, Steps/search/someday/candidates and removal previews;
report/cursor/comment/completion dates retain their own formats. Preserve the
existing explicit fractional-change fallback in `_document`.

Start with existing `tests/domain/test_time.py`, `test_reminders.py`,
`tests/adapter/commands/test_reminders.py`, current/local reminder tests,
`tests/workflows/capture/test_reminders.py`, `tests/workflows/test_cached_selection.py`,
`tests/presentation/test_reminder_receipts.py`, `test_item_dates.py` and
`tests/cli/test_reminders.py`. Reuse the strict `tests/support/reminders.py`
boundary and existing `tests/delivery/final/copy_probe.py`; cite the retained Due
dates/Sync source in new independent request/response fixtures.

Distinguishing independent facts include New York 2026-11-12 09:00 = 14:00Z =
Prague 15:00, and at 2026-10-29T00:30Z tomorrow is Oct 29 in New York versus Oct 30
in Prague. For recurring Monday 09:00 New York, Oct 26 2026 is 13:00Z and Nov 2
2026 is 14:00Z: request/returned rule and zone must survive, without a local
advancement engine. New York 2026-11-01 01:30 and 2027-03-14 02:30 are locally
ambiguous/nonexistent and fail before writes. Use one date-crossing dual display,
independent reminder zones, exact-equivalence versus same-first-instant schedules,
and representative keep/consent/partial/unknown outcomes. Detailed pure cases and
one composed/copied path establish different boundaries; no full cross-product or
new harness is needed.

The existing `final-delivery` gate calls `scripts/verify-clean`: exactly one
complete `scripts/check` offline suite, then distinct unchanged-copy/PATH/real-less
probes. Its self-tests use tiny synthetic suites and do not recursively run the
application suite. Preserve all gates. Workers use focused feedback; the runner
owns broad acceptance on each settled integrated subject. Append observations to
the existing acceptance evidence file; do not rewrite historical evidence or the
protected prepared contract-map ledger.
