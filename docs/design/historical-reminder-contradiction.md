# Superseded historical reminder contradictions — revision 9

Status: **Accepted**

## Actual decision, confirmation and scope

The operator said: “Agreed. Can you tell cml that this is not a concern a the
check itself does not make sense?” The agreement followed the explanation that
the latest T23 finding concerned contradictory synthetic provider reminder
records; no evidence established that ordinary single-user Todoist responses
produce that contradiction. This is a product-value decision, not a new provider
guarantee or a claim that all duplicate checks are unnecessary.

The exact operator instruction and separate interpretation are retained natively
at `TX-1ad3c948fe854798b23c9131a686a71b:1` and in
`/home/neuron/Documents/cml/todo-3/runtime/operator/accept-reminder-contradiction-limitation-20261027/operator-decision.md`.
The later instruction, “run this throught cml-design and cml-plan and continue
the work”, authorizes this specific amendment, matching Planning and supported
continuation under existing limits; its actual scope is retained in
`/home/neuron/Documents/cml/todo-3/runtime/operator/design-plan-continuation-20261027/authorization.md`.
The same understanding is confirmed; no repeated interview is needed.

## Precedence and protected history

REQ-SYNC-031 supersedes only the historical reminder-contradiction duty in
REQ-SYNC-013 for the replacement-before-owner-resolution case below. Its scoped
precedence also governs consumers of REQ-SYNC-013, including REQ-SYNC-030's
relevance-first processing and REQ-VERIFY-027's evidence expectations. All earlier
definitions remain byte-for-byte intact. All other revision-8 and earlier
requirements, exclusions and accepted limitations remain binding.

Accepted effective assignments are historical and must not be reopened or
rewritten. Planning owns the minimal agreement-preserving alignment for affected
unfinished/successor work and supported run adoption. Preserve useful T23 code.
The historical rejection of candidate
`a3d2bf2f76991913feb35ebb59dad84c9e9bd8a5` at ATT-a388aac9816a4c7f /
INC-3a1b52cb4a5f4704 remains accurate against its historical assignment; acceptance
of this limitation does not relabel it a verified fix or close its runtime incident.

### REQ-SYNC-031 — Historical reminder contradiction after authoritative replacement

When earlier same-response live reminder representations contradict one another,
and a later authoritative hydration/full response replaces that reminder's live
record before history establishes the owner's relevance to managed scope, the
application need not retain the superseded contradiction as separate historical
validation evidence. A consistent later authoritative record may be published
once normal ownership/scope and final-record validation succeed. Delivery must not
be blocked solely because this superseded synthetic inconsistency is no longer
remembered; no additional historical contradiction tracker is required for this
case.

For example, an earlier response contains the same reminder ID at two different
reminder times while the owning item's relevance is unresolved. Later authoritative
hydration supplies a single consistent replacement for that ID, then required
history/ownership resolution establishes a managed owner. That final record may
contribute to the published snapshot if all other requirements pass. This accepts
the consequence that the earlier inconsistent reminder times may go undetected.

The exception applies only to superseded historical reminder evidence in this
replacement-before-owner-resolution sequence. Meaningful final-record validation
and contradictions still present in the final relevant data remain required.
Outside this exception, REQ-SYNC-013's contradiction and synchronization rules
remain in force. Do not reinterpret a delta or incremental omission as a full
replacement, preserve an authoritatively deleted/omitted old reminder, or discard
a later valid update to enforce an obsolete representation.

Preserve account/root identity, managed scope and privacy, required fields,
completeness/pagination, command attribution and actual deletion/update/omission
semantics. Unknown owner relevance must still be resolved or fail under the
existing rules. Preserve pending-history protection, timezone/schedule correctness,
truthful mutation outcomes and all other prior fixes. This is no blanket waiver
of duplicate validation, metadata retention, ownership or safety checks.

## Acceptance interpretation and Planning handoff

Representative evidence may demonstrate the permitted sequence above without
requiring the superseded contradiction to survive. Preserve meaningful negative
cases for invalid final relevant reminder records, unresolved/unsafe scope and
other still-required synchronization failures. Reuse adequate existing evidence;
this amendment does not add an exhaustive test matrix or require a new suite.
Planning chooses concrete assignments, evidence reuse, commands and task changes.

No application/test/plan/configuration or runtime change belongs to this Design
pass. No new provider research, live request or observed feasibility claim is
needed for this accepted behavioral boundary. Existing pinned-contract evidence
and its documented limits remain unchanged. No unresolved product decision remains
within this scope; an additional changed promise must return to the operator.
