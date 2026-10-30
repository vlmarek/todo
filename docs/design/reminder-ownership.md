# Reminder ownership tolerance and useful failures — revision 19

Status: **Accepted**

## Agreement, scope and precedence

The operator observed an accepted move followed by an unresolved-reminder-owner
failure; ordinary refresh failed on the same owner. They pointed out that todo
manages only part of the Todoist account and requested a cml-design discussion.
They answered yes to silently ignoring reminders whose owners remain unknown
after normal managed-state reconciliation, accepting that reminders alone will
not discover never-seen managed tasks. They also answered yes to managed-reminder
failures including available task/category, reminder identity, type and schedule
without extra diagnostic requests. The final yes approves the concrete update to
this file and README.md. Actual instructions, question context, observations and
separate interpretation are retained in the external Design report.

Earlier definitions and accepted effective assignments remain historical inputs.
The following narrow successors govern changed and follow-up work:

| Successor | Earlier scope qualified or superseded |
| --- | --- |
| REQ-SYNC-039 | REQ-SYNC-021/030/031 and REQ-VERIFY-027 only where unresolved ownership alone requires failure or additional discovery for a live reminder with usable identity/owner context whose owner remains never-known after the normal workflow. Previously known or operation-required managed owners, other resource kinds and all other required reconciliation remain strict. |
| REQ-OUT-029 | Supplements REQ-SYNC-030's owner/record diagnostics and narrowly qualifies REQ-OUT-015's unprinted-ID rule for managed-reminder failures. Existing privacy, stream, exit-status and mutation-outcome rules remain. |
| REQ-VERIFY-037 | Adds distinguishing tolerance and diagnostic evidence; all still-required lifecycle, report, publication and isolation obligations remain. |

REQ-SYNC-013/036/037/038 retain their full/delta, matching-baseline, necessary
hydration, freshness, affected-state and evidence-reuse obligations. This amendment
does not introduce generic-error recovery, automatic cache clearing or mutation
replay. Report coverage and cursor rules, account/root binding, known managed
state, per-file publication, accepted-assignment protection and privacy remain.

### REQ-SYNC-039 — Reminders with unknown owners

Use the workflow's normal current-state, retained managed-history and applicable
lifecycle reconciliation to establish reminder ownership. After that reconciliation,
silently discard a live reminder whose usable stable reminder ID and owning item ID
identify an owner that remains unknown to reconstructed managed state, has not been
established in retained managed data, and is not required to verify the current
operation. The reminder must not block successful reconciliation or publication,
trigger additional ownership searches or full-refresh recovery, produce a warning,
or be persisted as an orphan or unrelated payload. Do not apply managed reminder
type/schedule restrictions to the discarded reminder's unused fields.

Apply this rule consistently during initialization, synchronization, mutation
reconciliation, explicit refresh and reporting. Where an ordinary workflow must
perform historical retrieval, perform it before deciding the owner's remaining
unknown status. This exception neither adds such retrieval nor waives an existing
retrieval obligation. Retain enough transient context within the command to attach
and validate the reminder if normal reconciliation establishes a managed owner.

Previously known managed owners and owners needed to establish the current
operation's actual result retain their existing validation and lifecycle rules.
A known owner's absence from active Sync is not permission to discard its reminder
instead of required reconciliation. Existing authoritative deletion, departure,
update, full-omission and historical retention rules still govern known managed
objects. Missing or unusable reminder identity/owner context remains an error under
the existing consumed-contract rules. Other resource kinds, including comments and
activity events, retain their current ownership and completeness rules.

Ignoring a reminder does not establish that its owner belongs outside managed
projects, is completed or is deleted. The accepted limitation is that reminders
alone do not cause discovery of never-seen managed tasks. For example, a task may
be created and completed in a managed project between synchronizations; if normal
required reconciliation does not discover it, its reminder is ignored too. Normal
task/history discovery, later scope-entry hydration and report obligations remain.

An accepted move accompanied by an unknown, never-managed owner's reminder may
therefore complete its normal verification and publication without replaying the
move. A known managed owner's unresolved required lifecycle transition still
fails under the existing outcome and saved-state preservation rules.

### REQ-OUT-029 — Useful managed-reminder failure context

When a failure concerns a managed reminder, report the actual reason alongside
the reminder ID and available owner task title/category, reminder type and
schedule or relative offset. Use only information already retrieved or retained
for the command; make no additional diagnostic API requests and invent no missing
values. Identify owner information taken only from a previous saved observation
as cached, rather than implying it is fresh authoritative state. Usable owner ID
may also identify the affected managed object when its title is unavailable.

Use safe available summaries when malformed fields prevent ordinary formatting;
do not dump raw responses, credentials, arbitrary malformed values or unrelated
payloads. Preserve existing text escaping and credential redaction. Reminders
ignored under REQ-SYNC-039 produce no routine output or warning and must not expose
unrelated task details. Diagnostic layout and shared implementation placement are
delegated; no new exact template, debug option, persistent log or telemetry is added.

Existing stderr and exit-status rules, accepted/rejected/unknown remote outcomes,
publication-state diagnostics and no-replay guidance remain. Formatting context
must not convert a failure to success, mask the original reason or claim a remote
correction. Do not recommend repeated ordinary refresh as a repair for a condition
it cannot resolve, or local cache clearing as a cure for malformed managed data.

### REQ-VERIFY-037 — Unknown-owner tolerance and managed failure evidence

Use proportionate offline controlled-boundary evidence distinguishing:

- An incremental reminder update with a usable but never-known owner no longer
  blocks successful managed synchronization, causes extra ownership/recovery
  requests, emits a warning or persists the ignored payload.
- Normal required reconciliation can establish an owner and retain its reminder;
  previously known managed owners and relevant malformed reminders retain strict
  lifecycle/validation behavior rather than being silently discarded.
- An accepted ordinary mutation accompanied by an ignored reminder verifies and
  publishes the actual managed result, submitting the mutation exactly once.
- A managed-reminder failure includes available contextual fields and identifies
  cached owner information, without additional diagnostic requests, credential
  leakage or unrelated-data disclosure.

Assess shared initialization, refresh, mutation and reporting consumers and reuse
adequate existing evidence; no duplicate full matrix at every layer is required.
Preserve meaningful required-data failure, saved-history, report-cursor and
accepted/unknown-outcome checks. Tests use synthetic provider-shaped records and
credentials against retained upstream evidence, with no live-account dependency.

## Evidence, exclusions and handoff

The inspected deployed implementation is commit
6d1f5c67da96c16ada615c88892b9b7397701b90. Disposable synthetic probes reproduced a
full read filtering an unrelated owner, a later reminder-only delta losing that
ownership context and failing reconciliation, and explicit full rebuilding
succeeding. These probes establish the local implementation mechanism; they do
not establish the live owner's current project/scope or a provider guarantee.
No production code or test was changed during this Design pass.

The existing pinned API-v1 evidence remains the external contract. This revision
selects application behavior for unresolved references; it makes no claim that
Todoist always returns the owner with a reminder update. No new provider snapshot,
ownership index, background recovery, general record-skipping policy, command,
option, storage migration or performance guarantee is introduced. Reminder-only
discovery is expressly excluded within the accepted limitation above.

Planning owns follow-up assignments, necessary consumer/test adaptations and
proportional verification, preserving earlier accepted assignments and useful code.
No substantive product decision or new feasibility investigation remains in this
scope. The operator separately requested fresh Planning and delegated operational
continuation, with a stop for serious persistent failures or any further needed
design/plan change. Documentation agreement itself is not runner adoption.
