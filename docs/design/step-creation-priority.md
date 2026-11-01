# Explicit priority when creating steps — revision 21

Status: **Accepted**

## Agreement, scope and precedence

The operator's step-creation command with --p1 failed because the design prohibited
an explicit creation priority for steps. They requested examination of the design
and history, then a cml-design discussion and updated documentation. They answered
yes to accepting task-style priority options for step creation, retaining the
parent-based default when omitted, applying the supplied priority to every step
in a batch, and preserving inline-step behavior for a newly created task. Actual
instructions, question context, evidence and documentation approval are retained
separately in the external Design report.

The purpose is to create a step with its intended own priority in one command.
Copying the parent's effective priority remains a default, not a restriction on
which own priority a new step may have. Steps retain independent stored priorities
and later priority changes do not propagate.

Earlier definitions and accepted effective assignments remain historical inputs.
These narrow successors govern changed and follow-up work:

| Successor | Earlier scope qualified or superseded |
| --- | --- |
| REQ-CREATE-009 | REQ-CREATE-007's task-only creation-priority grammar and prohibition for steps; REQ-DOM-010's unconditional copying becomes the omitted-option default. Qualifies REQ-CLI-033 and OUT-USABILITY-001 only where they exclude creation-time step priority. All other restrictions and creation behavior remain. |
| REQ-CLI-041 | Extends REQ-CLI-024's creation help and applicable usage guidance to teach explicit step priority and the retained default. |
| REQ-VERIFY-039 | Adds distinguishing creation-priority evidence and supersedes old assertions that a valid step creation priority must be rejected. Existing offline isolation and still-required behavior remain. |

### REQ-CREATE-009 — Explicit step priority with the existing omitted default

Step creation accepts the same priority options and value normalization as task
creation: --priority P with 1 through 4 or case-insensitive P1 through P4,
including --priority=VALUE, and fixed -p1 through -p4 or --p1 through --p4.
P1 is the highest product priority. Fixed flags consume no value; the scalar
form consumes exactly one argument. Preserve existing duplicate/conflicting-option,
missing/invalid-value and assignment validation; do not introduce new priority
spellings or change task creation validation.

This applies to canonical todo add step and the retained creation aliases
todo step --add/--new/--create and todo task --step PARENT TEXT.... Accept
supported options before or after the positional parent/text operands, preserving
REQ-CLI-031's extraction, original shell boundaries and literal handling,
REQ-CLI-012's independent creation groups, and existing parent selection. It does
not change the operand grammar of an existing-step priority mutation.

If an explicit priority is supplied, each requested new step receives that stored
priority, whether higher or lower than the parent's effective priority. A single
request-level value applies to every new sibling across its supported text groups;
option position does not make it local to one group. The selected parent may be
a task or step with room for children under the existing depth limit. The request
does not change stored priority on the parent or existing siblings; derived
effective priorities follow the existing subtree rules.

If no priority option is supplied, preserve REQ-DOM-010's synchronized
pre-creation-parent effective-priority default, including elevation from open
descendants. Every sibling created by the request receives the same copied
default. Explicit and defaulted priorities belong to the new steps thereafter;
later parent or sibling changes do not propagate to them.

Include the chosen priority in each step's creation operation. Successful
creation must not require a separate priority-update operation to establish the
requested initial value. Validate the complete batch before its first create,
then preserve existing ordered execution, authoritative result reconciliation,
publication, actual-result receipts and partial-failure classification. A valid
priority equal to the default is valid creation input, not a mutation no-op.

Other supported creation options remain composable under REQ-CREATE-008 and its
existing incompatibilities. In particular, an explicit priority can accompany
initial attention. Task defaults and inline steps of one newly created task
retain their existing behavior; this adds no per-inline-step priority syntax,
priority propagation, nested-batch grammar or new scheduling capability.

Examples:

```console
todo step --add ca-virt-t72-220 --p1 instal sru build machine in oci --at monday
todo add step --priority=P4 "Release plan" --step "Write summary" --step "Check links"
todo task --step "Release plan" "Review results" -p1
```

The first creates one P1 step with Monday attention. The second creates two
direct sibling steps, each P4 regardless of the parent's effective priority.
The third is a step-creation alias with an explicit P1. Omitting the priority
option from any supported form keeps the parent-based default.

### REQ-CLI-041 — Explain explicit and defaulted step creation priority

Creation help and applicable usage examples must advertise the supported priority
options for both task and step creation. Explain that new tasks default to P2,
new steps copy their parent's effective priority when the option is omitted,
and an explicit step-creation priority applies to all steps in that request.
Include a concrete step-creation example combining priority and initial attention.
Do not advertise the superseded prohibition or suggest creating and then
reprioritizing as the required workflow. Preserve independent help without state
or network access, existing status codes and useful syntax diagnostics.

### REQ-VERIFY-039 — Distinguishing step creation priority evidence

Use proportionate offline evidence to establish:

- Explicit priority reaches the actual step creation request and accepted stored
  result, including a value higher and a value lower than the parent-based default.
  Existing parent/sibling stored priorities remain unchanged. No subsequent
  priority update is required to obtain the requested initial value.
- Omitting the option still copies synchronized pre-creation effective priority,
  including elevation from an existing open descendant; a sibling batch receives
  the same default. An explicit batch receives its supplied value throughout.
- Canonical and retained alias creation forms normalize consistently with task
  priority options and option ordering, preserving parent selection and creation
  grouping. The reported command combining --p1 and --at monday is accepted;
  existing date semantics remain unchanged.
- Malformed, missing, duplicate or conflicting priority options retain existing
  rejection before mutation. Valid creation input equal to the default succeeds.
  Help teaches the added support and the omitted default without loading state.

Reuse adequate evidence for unchanged depth/sibling validation, inline steps,
scheduling, outcome handling and publication. Planning chooses representative
cases, test layers and decomposition; no separate suite per flag, alias or depth,
new live-account gate or provider refresh is required. Earlier accepted tests
that enforce the superseded prohibition are historical evidence, not an oracle
for the new behavior.

## Provider evidence and delegated work

The unchanged retained API v1 specification at
external/todoist/upstream/api-v1.openapi.json, tags[name="Sync"].description,
Tasks / Add a task, documents priority and parent_id in the same item_add
operation. Product P1 maps to wire priority 4 under the existing adapter contract.
The application already sends both when creating a step with its copied default.
This is an application restriction change using established provider capability,
not an upstream contract update or evidence from a new live-account probe.

Planning owns implementation decomposition, follow-up assignments, actual request
and result verification and existing-run adoption. Preserve earlier accepted
assignments and their referenced definitions; this amendment does not rewrite
them. No new unresolved provider investigation or product choice remains in this
scope. Documentation approval alone authorizes no commit, Planning, production
implementation or runner execution.
