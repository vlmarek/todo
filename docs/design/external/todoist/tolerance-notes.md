# Tolerance amendment: retained evidence and interpretation

Informative source navigation for revision 8, inspected offline 2026-10-27.
Binding application choices are in ../../todoist-tolerance.md. This document
does not amend provider bytes or claim an authenticated observation in this pass.

## Source baseline

Use the original API JSON and manifest in this directory. Its SHA-256 remains
`9a7c4816042e5c1b66935f2be1cf83da953dc459649ee606ac364d1acbc4764c`;
the retained retrieval date remains 2026-10-24. The prior research's unauthenticated
2026-10-27 HTML observation reported the same source hash as the retained manifest.
That report is provenance, not a fresh retrieval performed during this Design pass.
Official source: https://developer.todoist.com/api/v1/.

The supplied research is `/home/neuron/Documents/cml/brittle.txt`, with detailed
findings under the project's external
`runtime/operator/todoist-tolerance-research-20261027/`. Its saved proposals
expressly did not approve Design/Plan changes. The present operator discussion
selected the revised behavior. The application repository retains the original
upstream source, this focused interpretation and the complete product agreement;
workers do not need host-only research files to understand the requirements.

## Exact useful source locations

- `components.schemas.ItemSyncView.properties.due.examples[0]`: an original
  provider due example includes `date`, `is_recurring`, `lang` and `string` but
  omits timezone. The accepted application interpretation treats that omission
  as null while keeping supplied values and required scheduling semantics strict.
- `components.schemas.NoteSyncView`: `content` has an empty-string default and is
  not required. This supports incoming blank/default content, not arbitrary null
  or wrong-type coercion. Inspect each consumed endpoint's response contract;
  scoped REST ownership still comes from the request where documented.
- The Sync tag's Task comments/Notes sections and the comments REST paths:
  `file_attachment` is separate from text. Choosing not to consume it does not
  establish server behavior when text is updated. Actual update requests must
  omit attachment fields and retain the existing stable comment ID.
- `paths["/api/v1/activities"].get`, `ActivityEvents` and associated pagination:
  annotations are separate from event identity/type/time/ownership. The current
  application retrieves surviving report comment text separately; annotation
  content has no required product consumer. Other consumed scope/lifecycle
  metadata remains relevant and must not be indiscriminately stripped.
- `tags[name="Sync"].description`, Reminders / Properties, Add a reminder,
  Update a reminder and Delete a reminder: stable IDs, type, item ownership,
  optional reminder due, offsets, notify_uid and is_urgent. Reminder due values
  require time. The minute_offset description specifically requires a timed
  task due value; the absolute due description does not impose that prerequisite.
- `components.schemas.NotificationSyncView`: reminder `due` is an open object,
  `minute_offset` is nullable, and the type determines consumed scheduling meaning.
  Do not require an absolute reminder's offset to describe its schedule.
- `components.schemas.ReminderDueAttribute`: due input can carry date or natural
  language string, language, timezone and recurrence. REST reminder create/update
  paths supply an additional independent contract description, even if the
  implementation continues using Sync operations. Do not substitute REST request
  property names such as task_id/reminder_type into Sync arguments.
- The Due dates tag and inherited floating-time evidence distinguish floating
  wall times, fixed instants, account timezone and recurrence metadata. An English
  parser language is suitable for new English input, not for replaying a retained
  non-English recurring rule.

## Evidence limits and source conflicts

The research reports one reproduced website-preview rejection and an in-memory
counterfactual that mapped 57 tasks/107 comments after removing that metadata. It
does not report a completed initialization, publication or live attachment update.
Its selected-root profile contained relative reminders, not a demonstrated
absolute-reminder failure in that account. Other rejection cases used documented
examples or synthetic fault-isolation inputs. Counts of rejected probes are not
counts of bugs or claims about live malformed unrelated data.

The original Sync reminder documentation is internally inconsistent: its example
labelled relative sends type absolute with minute_offset, while the offset
description and separate REST create contract distinguish an offset before task
due from an absolute due schedule. The generic type prose also says relative
means minutes from now, conflicting with that offset description. Preserve the
upstream bytes; do not copy the erroneous example uncritically or change the
settled relative-reminder meaning. Absolute examples contain incidental placeholder
inconsistencies too. Planning must ground actual requests in the consumed contract
and record how it resolves contradictions rather than treating examples as proof.

The reminder due response's open object is not an exhaustive schema for every
recurring/floating variant. Keep necessary metadata and establish the specific
mapping/request/reconciliation cases used. An SDK, synthetic response or successful
request construction alone does not prove live notification delivery, recurrence
advancement or attachment preservation. No live account access is authorized here.

## Planning handoff

Revision 8 delegates unresolved expression parsing/normalization to Todoist.
The retained REST reminder create description accepts `due.string`; Sync Add a
reminder refers to the Due dates contract. Individual create/update/delete
operations do not establish an automatic semantic deduplication or whole-set
replacement guarantee. The application owns its replacement preview and consent:
show the unresolved expression as entered before writes, preserve explicit `keep`
and locally established matches, then reconcile actual provider results. Equivalent
wording resolved only by Todoist may recreate an existing schedule with a new ID.
No new read-only parse endpoint, local recurrence/equivalence engine or live probe
is required by this decision. This is operator-selected application behavior;
upstream evidence and manifests are unchanged.

Use a few independently grounded fixtures, including the unchanged due example,
blank/default comments, non-null/absent attachment metadata and absolute schedules.
Retain negative required-data and complete-pagination cases. Resolve exact reminder
arguments, optional/nullable due fields, preserved recipient/urgent metadata,
local recurrence/timezone matching within the stated identity boundary and
authoritative mutation outcomes before claiming
the affected assignments ready. Provider details are technical investigations;
changed product promises return to the operator through Design.
