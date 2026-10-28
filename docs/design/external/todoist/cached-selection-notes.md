# Cached task/step workflows: Planning contracts and compatibility

Status: **Accepted**

This is technical interpretation for Design revision 13, not a new product
requirement. Read `../../cached-selection.md` for the exact scoped precedence.
All earlier definitions, original evidence and accepted assignments stay intact.
The inspected source and accepted execution integration are
`35ac02cf7fb6dc1ba8cc82b71400c02be7d91c35`; the prior prepared-plan commit is
`8275862260fbbedd7b0e1aa9cfd09fd7b127213b`.
No provider call or application implementation/test edit was made in Planning.

## Concrete starting APIs and required adaptations

- `Synchronizer.read_local()` loads `StateStore.load_consistent_state()`, returns
  `SyncResult` with `_known(state)` and one current clock observation, and performs
  zero HTTP. `_known` combines compatible pending context with current snapshot.
  `refresh_locked()` performs current/lifecycle retrieval and publication;
  `reconcile_accepted_locked()` calls it with the accepted remote classification.
  Keep those fresh consumers. A small shared lock-held local-context entry can
  reuse the existing loader/result rather than create a second synchronization
  engine. ReadWorkflow already selects locally unless explicit refresh is set.
- `reads.title_candidates`, `select_child`, `move_destination_candidates`,
  `recent_candidates`, `deletion_candidates`, `combined_snapshot` and `choose`
  provide existing matching, eligibility and prompt semantics. Current mutation
  workflows call these only after refresh; switch their supplied population to
  validated saved data without a remote retry. NoMatch must retain full query
  boundaries and explicit saved-data/refresh guidance. Invalid local state must
  remain its actual error, never NoMatch.
- `CaptureWorkflow.execute` refreshes before `_plan`, then `_require_waiting_label`
  performs a separate full-plus-delta labels read when adding hiding. Replace both
  reads for ordinary task/step requests, including task creation and add-step
  parents. Keep category-only creation on its existing fresh path. `_plan`
  validates the entire cached proposal/batch and builds ordered `_Action`s;
  `_run` already receives saved IDs and reconciles each accepted operation.
- `MoveWorkflow.execute` refreshes and combines pending context before resolving
  source and mixed destination. Keep those identities and all cached known
  subtree/depth/cycle/sibling checks. Its `_publish` and move gateway observer
  still reconcile actual resulting state. A fresh remote title/untouched field
  differing from last-saved values is accepted stale context, not a new conflict
  gate; requested destination/field and actual invariant checks still apply.
- `LifecycleWorkflow.execute` refreshes before selection, and `_recent_snapshot`
  additionally retrieves per-category completed records and owner comments for
  reopen/delete. Those preflight reads are removed for revision-13 selection:
  use saved compatible ordinary/recurring occurrence evidence with existing
  cursor bounds and latest-eligible semantics. Retain report/shared history and
  post-operation retrieval. Known-tree recursive completion, recurring-descendant
  refusal, postorder and direct deletion semantics remain.
- `CommentWorkflow.execute` refreshes before choosing an owner and refreshes again
  after a changed editor buffer. Both become saved-context preflight. Its buffer
  codec, stable-ID edit/add/delete plan, all-shown confirmation, lock/temp cleanup
  and sequential accepted-operation reconciliation remain. Never refresh comments
  simply to populate the editor or check a target before its first write.
- `Gateway.execute(Operation, before=Current, ...)` locally checks known IDs,
  then submits POST `/sync` with `commands` before read reconciliation. It does
  not require a new pre-submission HTTP request. Its error text/docstrings saying
  "synchronized preflight" need compatible cached-context wording. Use the saved
  account/scope/model and token. `current_snapshot=None` can trigger full
  hydration in the existing post-submission reconciliation, which is permitted;
  do not move hydration before the operation to satisfy legacy provenance.
  UUID/status/temp-ID proof, unknown outcomes and no unsafe replay remain.

All public workflow results/requests stay usable. Existing test doubles that only
supply `refresh_locked` must provide real saved context, and request fixtures that
expect a preflight read must migrate explicitly. Do not weaken request-order fakes
so they accidentally accept either policy. Concrete code APIs are available in
these modules and their focused tests; names may be adjusted within the task's
scope without changing the public behavior.

## Minimal saved context and compatible publication

`Snapshot.account` already contains account ID and capabilities. Root/category
records carry personal/shared/workspace/nesting flags; binding supplies stable
identity and the single timezone authority. Codec/state validation already checks
association, complete model, safety and precision. No fresh account request is
needed to use those saved facts, and the design explicitly accepts that remote
metadata can have changed. Credentials still resolve through the existing path.

The gap is the `waiting` label resource's existence: item label names do not prove
that resource is available. `Current` retrieval requests labels, but discards the
minimal resource context needed by the next command. Extend current retrieval and
existing protected cache/LocalState plumbing with a validated optional availability
fact plus only the identity/provenance needed to merge relevant full/delta label
updates correctly. For example, retain relevant exact-name waiting-label IDs and
an explicit known/unknown distinction; full response establishes absence/presence,
renames/tombstones remove a formerly matching ID, new exact-name matches add one,
and omitted unchanged delta fields preserve established facts. Do not serialize
unrelated account label names/raw resource payloads. A boolean default inferred
from an item's labels, a guessed absent label or a partial delta does not prove
availability. The exact internal field/type remains delegated.

Acquire that context only during already-authorized init, explicit refresh,
report current-state retrieval or post-operation reconciliation. Publish it with
its matching current baseline/token in the existing JSON replacement, validate
it on reload, and carry/invalidate it correctly through every producer of
`Current`, `LocalState`, `Candidates` and `prepare_candidates`. Inspect callers in
init/sync/report/move/lifecycle and `adapter.commands`; do not let a successor
field disappear because one publisher reconstructs an older result shape.
Incremental merge needs a genuine compatible baseline, not combined archived
history; the existing current-resource provenance remains separate.

Compatible legacy cache lacking the new optional fact remains readable for
operations not needing it. A task/step request needing the fact fails before any
network operation and recommends existing explicit refresh. That explicit
workflow establishes it while retaining pending history/cursor. A required fact
with malformed type or inconsistent provenance is invalid local state; it is
never a default false or permission for automatic hydration. Normal cache schema
rebuilding remains explicit. Do not change supported binding/history schemas or
reset irreplaceable observations merely to add disposable command context.
Preserve existing missing/corrupt/foreign-history refusal, full/delta timestamp
behavior and mixed-publication safety.

## Retained direct-command evidence

Source: original `upstream/api-v1.openapi.json`, authenticated by adjacent
`manifest.json`, retrieved 2026-10-24 and inspected offline for this plan on
2026-10-28. No snapshot refresh or stronger live-provider assurance is claimed.
`tags[name="Sync"].description` (`/tags/3/description`) contains the consumed
Command UUID/Response, Tasks, Task comments, Reminders and Labels tables:

- `item_add` uses project/optional parent stable IDs; `item_update` uses stable
  item ID and supplied changed fields; item `labels` contains names.
- Move a task uses `item_move` with ID and exactly one destination; Delete task
  uses `item_delete.id` and explicitly deletes the task and its subtasks. An ID
  does not freeze remote title, parent or descendants. No version precondition
  or read-first requirement is supplied by these commands.
- Complete task/Close task, Uncomplete item and Complete a recurring task use
  the selected stable ID. Uncomplete restores ancestors; recurring forward/back
  direction and `reset_subtasks=0` remain the existing application contract.
- Task comment `note_add.item_id`, `note_update.id`, `note_delete.id`, and the
  reminder add/update/delete tables support direct existing stable-ID writes.
  Creates still require temp IDs and every command requires UUID attribution.
- Read resources/Incremental sync and personal Labels define full/delta resource
  evidence and tombstones. Saved availability is application context, not a new
  remote label endpoint or permission to create missing structure implicitly.

POST `/sync` authentication/form encoding, exact command args/status, due/reminder
interpretation and existing request retry/replay remain the accepted gateway
contract. A post-write read is not preflight. Definitive provider rejection cannot
retarget to a title match; ambiguous connection outcome cannot become rejection.
Existing scoped completed/activity/comments retrieval remains necessary after
operations where required and in reports. Scope it to its existing contracts;
active GET 404 is still not proof of deletion/archive.

## Shared consumers, evidence and limits

Reports continue fresh incremental current retrieval, complete required historical
and owner-comment evidence, command-local reuse, revision-12 completion association
and activity timestamps, exact interval eligibility, and output/flush then cursor
then cleanup. Pending observations cannot become fresh report-owner metadata.
Init/provisioning and category-only creation retain their own fresh contracts.
Normal cached views and explicit refreshed reads keep their existing boundaries.
No extra label read belongs in a task/step workflow before its mutation.

T31 owns code, all affected callers/fakes and a focused composed suite at
`tests/workflows/test_cached_selection.py`, plus compatible local/current/sync
checks. T32 audits distinguishing public behavior, adds one unchanged-copy
cached-selected-ID mutation in `tests/delivery/final/copy_probe.py` and appends
subject-bound acceptance evidence. Report and existing delivery tests retain the
unaffected guarantees. Full product verification uses the existing final-delivery
on the settled integrated subject: verify-clean calls scripts/check once, then
performs distinct copy/PATH/real-less probes. Miniature harness tests must not
recursively run the application suite.

Offline request traces establish ordering and conformance to retained contracts,
not guaranteed speed or provider availability. Use synthetic fixtures with a
saved state differing from subsequent remote state to distinguish cached ID
acceptance, rejection and unseen cascade effects. Observe metadata acquisition
through legitimate full/delta retrieval rather than preseed a success that avoids
that path. Existing current/result validation must still reject real invalid
post-operation state. No database, freshness conflict protocol, identity ledger,
background refresh, new command/flag/prompt or cached report mode is introduced.
