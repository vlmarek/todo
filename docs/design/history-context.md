# Unreported-history provider evidence and responsibility boundaries

This is authored evidence/navigation, not another requirement definition or a
concrete Python API. REQ-CACHE-006 and REQ-SYNC-005/025/026 define behavior.
Source retrieval details are unchanged; no old task graph, code or host-only
research artifact is required to understand the todo-3 implementation input.

## Retained source and exact navigation

Use the retained complete `docs/design/external/todoist/upstream/api-v1.openapi.json`
and its adjacent `../manifest.json`. Retrieved from
https://developer.todoist.com/api/v1/ at 2026-10-24T14:36:15.204899+00:00;
API version 1, no immutable provider release supplied. The unchanged extracted
JSON SHA-256 is `9a7c4816042e5c1b66935f2be1cf83da953dc459649ee606ac364d1acbc4764c`.
The following JSON pointers/section names identify the consumed source:

- `/tags/3/description`, Sync / Overview / Read resources and Incremental sync:
  `sync_token=*` supplies active data; delta updates use the returned token.
  Full-plus-incremental current retrieval does not promise archived children.
- The same pointer, Sync / Tasks / Complete task and Close task: ordinary
  completion archives the object/subtasks; Close task advances recurring items.
  Uncomplete item restores the item/ancestors and resets their checked values.
  Move a task accepts exactly one destination; this establishes selected-item
  movement, not an undocumented guarantee about every archived descendant.
- `/paths/~1api~1v1~1tasks~1{task_id}/get/description`: single-task GET is active
  only. A 404 cannot distinguish archive, deletion or unavailable identity.
- `/paths/~1api~1v1~1tasks~1completed~1by_completion_date/get`: GET with UTC
  `since` inclusive / `until` exclusive, at most three months per window;
  optional project/parent filters and cursor/limit. Exhaust returned continuation.
  `/components/schemas/TasksCompletedDateResponse/properties/items` contains
  ItemSyncView records; `next_cursor/description` explicitly permits terminal
  omission. Never use Sync completed_info counts as completed-object records.
- `/components/schemas/ItemSyncView/properties`: stable id, parent_id,
  project_id, user_id, checked, is_deleted, completed_at, updated_at and item fields.
  The completed endpoint establishes completion occurrences; recurring occurrences
  do not override a currently active item's lifecycle. Do not impose current-only
  completion assumptions on every completed-endpoint example.
- `/paths/~1api~1v1~1activities/get`: separate paginated GET; use documented
  `date_from`/`date_to`, scope and object/event filters, never invented Sync activity.
  `/components/schemas/ActivityEvents/properties`: object_type/object_id,
  event_type/event_date are required; id/parent_project_id/parent_item_id/extra_data
  are optional. Item completed/uncompleted/deleted/moved and note added/updated/
  deleted are explicit events. Parent_item_id describes a note's owner, not a
  general item-parent guarantee. extra_data documents source_project_id and
  destination_project_id for moved items but remains optional.
  `/components/schemas/PaginatedList_ActivityEvents_` requires results and
  next_cursor (null terminal). Supplied event IDs support simple deduplication; anonymous entries
  remain in source order and may duplicate; content-free deleted events remain valid evidence.
- `/paths/~1api~1v1~1comments/get` and NoteSyncView: the known owner's scoped
  paginated request supplies ownership if item_id is omitted. Required report
  current-comment resolution remains separate from last-observed retained comments.
  Sync / Task Comments / Delete a task comment defines note_delete acceptance.
- `/paths/~1api~1v1~1tasks~1{task_id}/delete` states task/subtask deletion; Sync
  command UUID status supplies acceptance for application-issued operations.


## Current application responsibilities

The adapter supplies current state and supported lifecycle/ownership evidence.
Workflows reconcile by stable identity and retain observations still needed for
unreported work. Persistence owns protected separate storage and consistent reads;
the report workflow owns complete retrieval, output/cursor publication and subsequent
cleanup eligibility. Names, Python types and module boundaries belong to Planning.

For known open B beneath A disappearing from active data, use supported completed
or activity evidence to establish completion, deletion, reopen or departure. Keep
the necessary known parent/fields/own comments for pending reporting. Required
unresolved evidence fails the online operation; absence is not a terminal state.
Current authoritative data wins over observations. Unknown archived metadata still
follows the explicit report-owner failure limitation.

Refreshing, cache clearing or previewing does not discard unreported history.
After complete successful final output and cursor publication, records covered by
the reporting boundary and no longer needed for newer pending work may be removed.
Keep sufficient context for those newer records. Cleanup can safely leave extra
already-reported records after failure; it cannot precede finalization or become a
permanent archive guarantee. Setting a cursor is not itself a cleanup operation.

No serialized mutation journal, mandatory event ledger, invented archive endpoint,
time-based pruning schedule or anonymous-event identity reconstruction is required.
Use independent endpoint-shaped examples and representative integration evidence
where they expose real failure mechanisms; test decomposition belongs to Planning.
