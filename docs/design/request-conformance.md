# Activity filters and waiting-label requests — revision 10

Status: **Accepted**

## Instruction, scope and protected history

After the report failure diagnosis and related request audit, the operator asked:
"$cml-design I want to update the design documentation to cover that change".
The disclosed corrections were a single JSON-array activity filter and the
missing required local `operation` argument in the waiting-label lookup. This
revision documents that scope under the existing intended behavior. It does not
introduce a new hiding policy, report policy or product limitation.

The instruction is recorded separately from this interpretation in native
operator decision `TX-b901b1681400469c91fb75d7c92fa6dc:0` and the external
Design session. Code and tests identify implementation gaps; they do not define
product intent. The earlier report implementation/test edits remain uncommitted
work to assess in Planning. This Design pass changes no production code or tests,
does not fix the waiting-label call, and does not establish runner acceptance.

| Clarification | Existing obligations clarified |
| --- | --- |
| REQ-SYNC-032 | REQ-SYNC-021/025: endpoint-specific request encoding and complete activity retrieval |
| REQ-SYNC-033 | REQ-SCHED-011/014 and REQ-CREATE-008: usable waiting-label preflight before adding hiding; REQ-NET-001: shared HTTP boundary |
| REQ-VERIFY-028 | REQ-VERIFY-003/004/013/027: actual request conformance and representative composed-workflow evidence |

Earlier requirement definitions and all 25 accepted effective assignments remain
unchanged. These clarifications add precision within their stated scopes; all
unrelated obligations, exclusions and accepted limitations retain authority.
Planning owns impact assessment, follow-up assignments, evidence reuse and
supported revision adoption. No commit or execution is authorized by this pass.

## Evidence and limits

The unchanged retained [API v1 specification](external/todoist/upstream/api-v1.openapi.json),
`paths["/api/v1/activities"].get.parameters[name="object_event_types"]`, describes
an array of `object_type:event_type` strings. The operation's `x-codeSamples`,
especially "Multiple event types", send a JSON-encoded array as one query value.
The schema does not specify an explicit serialization style; its array type alone
does not establish that repeated scalar query values work. The Sync tag's
Read resources and Write resources separately establish JSON-encoded
`resource_types` and `commands` form values.

During the preceding diagnosis on 2026-10-27, two authenticated read-only GETs
using the operator's reported interval were compared: repeated activity-filter
parameters returned HTTP 400 / `INVALID_ARGUMENT_VALUE`; a single JSON-array
parameter returned HTTP 200 with an empty terminal page. This is a scoped
observation, not a recorded upstream response fixture, a successful nonempty
report, or a guarantee of all future provider behavior. No raw authenticated
response or credentials are retained in these documents. This Design pass makes
no additional account request and does not refresh the upstream snapshot or
manifest. The retained snapshot and examples are sufficient for offline follow-up.

The waiting-label defect is local: calling `_require_waiting_label` with the real
`Transport` and a network-forbidden opener raises `TypeError` for missing
`operation` before HTTP. The existing capture fake's permissive `**kwargs`
signature does not enforce that real interface. This is not a Todoist API failure.

### REQ-SYNC-032 — Activity event filters use one JSON-array query value

When retrieving the completion, undo and comment activity required by the report
and reconciliation rules, serialize all selected `object_event_types` into one
JSON array of strings and send it as a single query parameter on
`GET /api/v1/activities`. Do not send one scalar parameter per selected event.
For the existing event set the decoded query value is:

```json
["item:completed", "item:uncompleted", "note:added", "note:updated", "note:deleted"]
```

JSON whitespace is not significant. `note:deleted` is valid; do not remove it to
avoid the rejection. Preserve the existing date bounds, applicable scalar scope
filters, page limit and cursor traversal. Every page keeps the same filter value;
only continuation changes. Any consumer of this shared activity retrieval uses
the same encoding, including bounded lifecycle reconciliation.

Keep exact local interval eligibility, stable-ID deduplication, accepted anonymous
events, current surviving comment content and complete-or-error reporting. A
required history failure remains nonzero with no report-cursor advancement or
pre-publication file replacement. Refresh guidance is existing recovery advice,
not a claim that refreshing state repairs malformed request construction.

This rule is specific to the consumed activity filter. Preserve the separate
documented JSON-in-form encoding for Sync reads/writes and scalar parameters for
completed-task and comment retrieval. No generic repeated-key conversion or new
HTTP compatibility layer is required.

### REQ-SYNC-033 — Waiting-label checks use a valid shared transport call

Before adding an item's own hiding policy, obtain the required current waiting
label evidence through the existing read-only Sync path. Every such call must
satisfy the production HTTP boundary's required arguments, including its local
nonempty `operation` metadata for safe diagnostics. That metadata is not a
Todoist query/form field. Retain JSON-encoded `resource_types: ["labels"]`, the
full read and required freshness delta, and the normal authentication/retry rules.

With valid label evidence and an otherwise valid proposed change, `hide`, creation
with hiding and scheduling that newly enables hiding must reach their existing
mutation and authoritative-result paths. They must not fail before HTTP because
a required local transport argument was omitted. If `waiting` is absent, preserve
the existing pre-mutation refusal and `todo init` guidance. A failed or malformed
label read must not authorize mutation or automatic label provisioning. Unrelated
commands and removal of an existing policy retain REQ-SCHED-011's behavior.

### REQ-VERIFY-028 — Distinguishing request-conformance evidence

Under the existing isolated offline verification contract, establish the activity
request's single query value through the real adapter and HTTP encoding boundary.
Its JSON array must retain the required event set, with invariant filters across
pagination. A fake that accepts the old repeated scalar encoding does not prove
conformance. Use the retained operation examples independently of implementation
output. Existing report and retrieval evidence may be reused to establish current
content and failure/cursor protection; no live-account gate is added.

Establish a representative valid hiding workflow through the production transport
interface with controlled HTTP responses, so omission of required local arguments
cannot be hidden by a permissive fake. Include missing-label refusal before any
mutation and preserve the existing label-read failure protections. Shared evidence
may cover creation, scheduling and direct hiding where they use the same lookup;
separate exhaustive suites or every alias at every layer are not required.

Planning chooses concrete cases, fixture structure and commands. Reuse adequate
existing verification, retain earlier required behavior and keep real credentials,
real local state and uncontrolled network out of automated checks. No SDK,
dependency, generic signature-enforcement framework or repeated full-suite gate
is introduced.

## Handoff

There is no unresolved product decision or new provider investigation within this
scope. Technical task decomposition and acceptance of the existing report edits
and remaining waiting-label repair belong to Planning and normal execution.
Historical successful offline checks do not prove live provider compatibility or
close the locally reproduced waiting-label defect. The revision-10
Design handoff was uncommitted; subsequent Planning must bind the complete tree
to committed inputs. An implementation diff alone is not an adopted plan.
