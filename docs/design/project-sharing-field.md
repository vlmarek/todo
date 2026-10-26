# Project sharing field — revision 6 correction

Status: **Accepted**

The operator asked whether support for older `shared` could be omitted and then
instructed “do that” after disclosure of this exact is_shared-only correction,
matching Plan alignment, adapter/fixture correction and accurate initialization
discovery error labeling. Actual instruction, disclosed scope and confirmation:
`/home/neuron/Documents/cml/todo-3/runtime/operator/is-shared-only-authorization-20261026.md`.
The older dual-spelling recommendation in the diagnosis is superseded. No repeated
product confirmation is pending. Stop before any additional Design/Plan scope
change after this approved correction and alignment.

## Scope, evidence and precedence

This is a correction to the application's provider interpretation, not a new
privacy policy or a claim that the provider documentation is consistent. The
existing retained API v1 snapshot at
[external/todoist/upstream/api-v1.openapi.json](external/todoist/upstream/api-v1.openapi.json)
contains the conflicting evidence:

- `components.schemas.PersonalProjectSyncView` and
  `components.schemas.WorkspaceProjectSyncView` both define boolean `is_shared`
  and include it in `required`; neither defines a `shared` property.
- `tags[name="Sync"].description`, Projects / Properties, still describes
  `shared`. This prose conflicts with those typed schemas.

The operator selected the typed-schema spelling only. The retained upstream bytes,
source manifest and retrieval dates remain unchanged; this pass re-inspected them
offline on 2026-10-26. It neither refreshes provider evidence nor claims a live
account test or provider-wide removal of the older spelling. The field selection
is settled application support policy grounded in the retained typed schemas.

| Current definition | Earlier scope superseded or clarified |
| --- | --- |
| REQ-SYNC-028 | Supersedes only REQ-SYNC-021's instruction to read `shared` and prohibition on `is_shared`; all other mapping and eligibility obligations remain |
| REQ-INIT-010 | Clarifies REQ-INIT-003/008 failure-phase reporting when remote discovery runs inside the wizard; terminal requirements and preflight/provisioning behavior remain |
| REQ-VERIFY-026 | Adds evidence for this correction under the existing isolated verification contract; historical accepted evidence and assignments remain protected |

All earlier binding definitions remain byte-for-byte intact for the 19 accepted
run-001 assignments. Planning must apply these successor obligations through
supported follow-up work, not silently replace accepted assignments. The previous
publication/manual-recovery and subsecond limitations remain unchanged. No
init/recovery redesign, new compatibility branch, dependency or live-account
verification requirement is added. Task decomposition, implementation details,
test layers and normal supported adoption belong to Planning and the runner.

### REQ-SYNC-028 — Provider project sharing uses is_shared only

For every live Todoist project mapped from API v1 provider responses, require
`is_shared` to be a JSON boolean. Map `false` to unshared and `true` to shared.
The internal `Project.shared` property and persisted application representation
may keep their existing names; those are not provider wire fields.

A missing `is_shared`, explicit `null`, string, number (including `0`/`1`) or other
non-boolean value must fail validation. Never default unknown sharing state to
private or coerce by truthiness. Provider `shared` is not a supported alternate,
fallback or reconciliation source: even a boolean `shared` cannot rescue missing
or malformed `is_shared`. When `is_shared` is valid, an additional `shared` has no
authority over it and follows the existing unknown-response-field rule.

Apply this mapping consistently in wizard discovery, initialization preflight and
post-provision validation, full/incremental synchronization, refresh,
reconciliation and any diagnostic path consuming provider projects. Preserve
existing deletion-tombstone and unrelated-data discard rules; this requirement
does not invent live-project fields for a deletion tombstone. The same provider
interpretation must survive subsequent synchronization without treating internal
state naming as legacy provider compatibility.

An otherwise eligible active personal root/category with `is_shared: false` and no
`shared` must be accepted under the existing identity, hierarchy, ownership and
Inbox/workspace rules. `is_shared: true` must exclude it from eligible wizard
choices and reject it as a managed root/category before provisioning or task
mutation. `is_shared: true` plus `shared: false` remains shared. A sole
`shared: false` is missing required `is_shared`, not proof of privacy. Inbox and
workspace-owned projects remain ineligible even with `is_shared: false`.

Only the sharing-field rule changes. Keep REQ-SYNC-021's other mappings, including
the existing `inbox_project`/`workspace_id` rules and malformed supplied metadata
rejection. Preserve private/unshared management, stable bindings, repeat init,
remote-change detection, failure preservation and no automatic repair.

### REQ-INIT-010 — Accurate remote-discovery failure phase

When initialization performs remote project discovery inside the configuration
wizard, a network, authentication or provider-response/mapping failure must
identify remote discovery as the failed phase and exit nonzero. Do not label that
failure as terminal setup or tell the user to rerun in a terminal as its remedy.
Actual stdin/stdout or hidden-input capability failures retain their terminal
setup diagnostics and existing safety behavior.

For invalid project sharing data, identify `is_shared` and the expected boolean,
distinguishing absence, explicit null and wrong type under existing error and
privacy rules. A legitimate project using the supported `is_shared` shape must
not be diagnosed as malformed merely because it lacks `shared`.

Discovery failure must never become empty-account fallback or authorize remote
provisioning. Keep existing wizard cancellation, credential protection, local
permission handling, configuration-publication boundary, accepted remote outcome
reporting and preflight/post-provision failure phases. This diagnostic correction
adds no reset, rollback or recovery mechanism.

### REQ-VERIFY-026 — Evidence for project sharing correction

Use retained typed-schema-grounded synthetic provider responses and the existing
offline/isolation contract. Establish successful eligible-project discovery and
initialization without `shared`, valid repeat-init/refresh behavior, rejection of
missing or malformed `is_shared` even when legacy `shared` is present, and shared,
Inbox and workspace exclusion. Include a case where `is_shared: true` and
`shared: false` cannot enroll a shared project. Preserve still-required earlier
behavior; internal naming alone does not require a storage migration.

Establish through the public initialization path that remote discovery/mapping
failure is identified as discovery, performs no fallback provisioning, and
preserves the existing local/configuration boundary. An actual terminal capability
failure must retain its distinct terminal diagnostic. Planning chooses
representative cases and reuse of adequate evidence; separate exhaustive suites
or every combination at every layer are not required. No real credentials, real
`~/.todo`, authenticated provider requests or live mutations are needed.
