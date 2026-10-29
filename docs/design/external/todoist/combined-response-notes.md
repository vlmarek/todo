# Combined mutation response consumption

Status: **Accepted**

Technical planning navigation for TODO3-PLAN-017, inspected 2026-10-29.
Design revision 18 owns product behavior. This note chooses a compatible extension
of existing APIs and records evidence limits; it adds no requirement or guarantee.

Use the unchanged adjacent manifest and `upstream/api-v1.openapi.json`, original
retrieval 2026-10-24. `tags[name=Sync].description`, Overview / Read resources and
Write resources, together with the Sync introductory feature list (reading and
writing multiple resources in one HTTP request), defines the same POST `/api/v1/sync` endpoint, JSON-valued
`commands` and `resource_types` form parameters and `sync_token`. Read Response /
Incremental sync defines full/delta resources and new token; Command UUID and
Temporary resource ID / Response / Error define independent command proof. Full
sync data delay requires freshness after full candidates. Write-only examples
show receipt/token without resource collections; their token cannot be attached
to an old resource baseline as though all intervening changes were incorporated.

Current implementation navigation: `adapter/commands.py:Gateway.execute` builds
commands-only form, then `current.retrieve` issues `_read`; `current.py` already
owns `_merge`, metadata, `_map`, entrant hydration, created_ids, tombstones and
full freshness. `Result.after/before_token/evidence` and workflow
`reconcile_accepted_locked(result)` already reuse compatible complete operation
state. Extend this shared path to consume an actual supplied mutation response;
avoid a second mapper, synthetic transport replay or result-derived local patch.
Retain positional/default compatibility and document concrete chosen signatures
in existing adapter/workflows API.md. Gateway callers include capture, scheduling,
moves, lifecycle and comments/editor; injected retrieve/history doubles and copied
strict HTTP fixtures need coordinated migration.

Request all existing Current.RESOURCE_TYPES: user, user_plan_limits, projects,
items, labels, notes and reminders. Consume every returned relevant change with
its actual full/delta/baseline contract. Sufficient combined response evidence may
satisfy current publication, active-owner comment result checks or an ordinary
completed lifecycle check; it never proves arbitrary archived-owner comments,
recurring occurrences or interval-history completeness. Keep those reads where
necessary. Provisioning/category mutation is outside this amendment.

The retained provider contract establishes combined read/write and incremental
capability, not a universal transactional read-after-own-write guarantee or a
complete response for every operation. The diagnostic full_sync=true observations
did not retain collections or establish normalized own effects. Test source-cited
response semantics through real transport and actual production mapping, and
require operation-specific authoritative actual state before success. Retrieve
supported additional evidence when insufficient. Fixtures must check actual request
parameters and may not fill required resources/own effects from request predictions.
Report contrary evidence rather than weakening verification or inventing a provider
promise. No live probe, universal one-request count or latency gate is required.
