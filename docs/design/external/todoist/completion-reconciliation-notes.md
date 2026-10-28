# Completion reconciliation: Planning choices and evidence limits

This is technical interpretation for revision 12, not new product requirements.
REQ-REPORT-017/018 and REQ-VERIFY-030 control the behavior. Earlier definitions
and accepted assignments remain intact. No provider evidence bytes are replaced.

## Retained contract and observed starting point

Read the original `upstream/api-v1.openapi.json` and adjacent manifest, retrieved
2026-10-24; inspected offline for this plan on 2026-10-28. Relevant pointers are
`paths["/api/v1/tasks/completed/by_completion_date"].get`,
`paths["/api/v1/activities"].get`, `components.schemas.ItemSyncView`,
`components.schemas.ActivityEvents`, and `components.schemas.PaginatedList_ActivityEvents_`.
The completed endpoint supplies task context and completed_at; activity supplies
object identity, event type and event_date. Activity id is optional integer/null.
Its extra_data is optional object/null, with permissive additional properties;
neither a shared occurrence ID nor timestamp equality is specified. The observed
completed_due_date/completed_due_date_local fields are not required by that schema.
Do not make them a required discriminator, parse arbitrary metadata, or download
new provider snapshots to implement this correction. Existing activity filter
encoding, scoped completed windows, page exhaustion and protocol validation stay.

At accepted integration `97e29189449f73a4f5457f24b55987e9b28955d8`:

- `adapter.history.HistoryAdapter.completed/activities` returns
  `Retrieval(records, pages, start, end)`. CompletedRecord has item, occurrence,
  deleted; Activity has id, object_type, object_id, event_type, event_date,
  owner_id, project_id and an unused annotation slot. IDs/times are mapped and
  required data is validated there. Completed-record occurrence IDs currently
  use item ID plus exact completed_at; activity has no mandatory shared ID.
- `workflows.report._select` combines activity and completed records, suppressing
  the latter only on exact owner/instant equality. Its chronological stack
  pairs recurring undo, but unequal cross-source representations survive twice.
  `Reporter._prepare` fetches complete scoped records/activity, uses `_Evidence`
  for command-local reuse, reconciles, resolves required owner/comments, then
  publishes candidates. `ReportResult` and public command shapes stay unchanged.
- `workflows.sync._reconcile(current, known, history, adapter, start, end, cursor,
  hidden_names)` returns `(snapshot, pending_history)`. It seeds recurring
  occurrences only from completed records; it reads scoped activity only when
  occurrences already exist, and currently consumes only uncompleted events.
  Its undo candidate list includes already-undone occurrences. Those are concrete
  evidence-consumer gaps against existing recurring requirements, not a changed
  mutation policy. `_known` combines current/pending context.
- `workflows.lifecycle._recent_snapshot` performs bounded completed discovery and
  can supplement occurrence IDs before `domain.recent_reopen_candidates`, which
  chooses the latest recurring completion and refuses it if undone. Preserve that
  eligibility rule; a latest undone completion does not license an older reopen.
  `adapter.commands.Gateway` has separate UUID/status and before/after evidence
  logic; report preference cannot turn its unknown operation into accepted.
- `domain.Occurrence(id, item_id, completed_at, recurring, undone=False)` already
  carries exact time and undo state. `local.History`/StateStore keep protected
  pending observations. `local.history.prune_history` acts only after complete
  output and cursor publication and keeps owners/ancestors of newer occurrences.
  Preserve serialized compatibility and available observations; no state reset.

## Bounded association strategy

Use one small shared pure reconciliation helper, with module and return type left
to the implementer. It consumes already validated, successfully exhausted evidence
and known/current owner context. It must be usable by report selection and shared
recurring-history consumers without HTTP, storage side effects or a second engine.

Activity is the chronological backbone. Keep each completion activity after the
existing supplied-ID deduplication, including every anonymous entry. Associate
completed records as supplemental representations one-to-one within the same owner,
using chronological occurrence position and nearest exact timestamps to align
partially overlapping sequences. Prefer exact matches, then nearest remaining
chronological counterparts, preserving source order as the deterministic tie break.
Each completed record and activity completion can participate at most once; do not
consume an activity undo as a completion counterpart. Owner identity is necessary
but does not identify an entire recurring series as one occurrence. Keep unmatched
completed occurrences as fallback; never suppress all completed records simply
because any activity for that owner exists. This is bounded evidence association,
not provider-certified identity, a fixed tolerance window, or an elaborate matching
service. Do not collapse activity events against each other.

Perform association across the fetched evidence before effective-undo filtering
and requested report interval filtering. The matched activity time governs report
eligibility, order and display. Process undo chronologically once against the
latest unmatched preceding completion, preserving existing equal-time stable-ID
and anonymous source-order rules. A matched completed representation cannot be
reintroduced after that occurrence is undone. Activity-only occurrences use fresh
active context; completed-only fallback does not trigger a counterpart lookup or
absence error. An unresolved required archived owner remains the existing failure.

For shared stored history, preserve existing still-needed observations, map
re-observed supplied IDs idempotently and avoid re-seeding a matched completed
representation in sync or recent discovery. Recomputing effective undo from the
same bounded evidence must be idempotent across reload/refresh. Use current context
and existing protected occurrence/history representation with the smallest compatible
extension if needed; no new persistent event ledger or command-spanning cache.
Anonymous cross-observation identity cannot be proved and retains its existing
tolerance. Keep older observations when needed and never reinterpret endpoint
absence as deletion or a successful mutation. Bounded discovery still obtains
archived object context where required; it must not undo the reconciled state.

There is no universal proof for disjoint or changing endpoint observations. The
accepted design expressly declines a stronger cross-report cutoff guarantee;
the association does not silently introduce one. If implementation discovers a
case requiring a new user-visible error, dropped obligation or general undercounting
policy, stop that scope and report it for Design rather than guessing a waiver.

## Distinguishing evidence and verification reuse

Reuse real-adapter fixtures in `tests/adapter/history/test_history.py`,
`tests/workflows/report/test_report.py`, `tests/workflows/sync/test_sync.py`,
`tests/workflows/lifecycle/test_lifecycle.py`, `tests/local/`, and
`tests/delivery/final/copy_probe.py`. Relevant existing tests cover same-time
activity multiplicity/anonymous source ordering, deep recurring pairing, latest
recurring undo, current-null preservation, pending-state reload and output/cursor
failure. They currently use equal source timestamps or completed-backed recurring
evidence and do not establish the new unequal-time/activity-only correction.

T29/T30 specify the representative additional cases. In particular, two distinct
activity completions plus one completed representation must remain two, while
two separate completed occurrences plus one matching activity must retain the
unmatched fallback. One completion in both sources plus one undo must leave zero.
Repeated undo/reload and recent discovery must not resurrect a matched occurrence.
Use omitted extra_data as a valid activity-only recurring case; optional observed
due metadata is unnecessary for the minimum strategy. A source-pair cutoff case
tests selection when both records were fetched, not future endpoint completeness.

Existing named checks t15/t08/t18/t06/t02-focused cover the changed consumer and
storage slice. T30 reuses t15/t18/t25-focused and the unchanged final-delivery gate.
`scripts/verify_clean.py` calls `scripts/check` once, then copy_probe.py and
less_probe.py as distinct delivered-copy observations. Its miniature self-tests
must not invoke complete suites. Do not duplicate the broad gate for each role
or claim earlier accepted test runs validate a changed subject. All acceptance
is synthetic/offline; no production account or new framework is needed.
