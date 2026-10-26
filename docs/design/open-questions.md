# Technical evidence and delegated choices

todo-3 design revision 2. The operator confirmed the scoped product agreement;
the choices are recorded in README.md. The questions below are
technical investigations within those choices, not additional product features,
mandatory new research stages, or permission to recover an old execution run.

## Unreported history through reporting and cache rebuilding

Dependent definitions: REQ-CACHE-006/008, REQ-SYNC-005/013/025, REQ-REPORT-003/014,
REQ-LOCAL-002/003/005 and REQ-VERIFY-022.

Choose minimal separate storage for reporting observations and necessary ancestry,
stable-ID merging, source-associated lifecycle evidence and consistent publication.
Demonstrate observed open-to-completed web/mobile transitions using supported
completed/activity/current evidence, not absence alone. Cache clearing preserves
pending history and a rebuild makes it usable again. Retention is reporting-bounded,
not an all-history scanner, permanent search index or mutation journal.

Establish finalization ordering: complete output/flush, successful cursor publication,
then cleanup of data no longer needed for unreported activity. Preserve shared
context for newer work. Failure before finalization retains the old cursor and
needed observations; interruption during later cleanup may leave extra data.
Choose representation/idempotent cleanup within ordinary atomic-file guarantees;
do not introduce a transaction log, automatic rollback or quota/expiry system.
No persisted clean/outdated/blocked cache-state machinery is needed.

## Completed retrieval, interval precision and archived metadata

Dependent definitions: REQ-SYNC-025, REQ-REPORT-014/011, bounded reopen/deletion.

Read the retained endpoint-specific response/continuation schema. Completed
next_cursor omission is terminal where documented; other endpoints keep their
required continuation rules. Translate inclusive-start/exclusive-end wire filters
to exact product (start, end], including subsecond and split-window boundaries.
Exhaust required pages/windows and use suitable controlled endpoint-shaped cases.

Resolve current archived owners/ancestors only through supported evidence. A 404
from active lookup is not deletion/archive proof. Required unavailable metadata
still fails reports with unchanged cursor, even when local observations exist.
Retention of unreported evidence is not a guarantee of reconstructing every old
owner or refresh of all archived fields. Anonymous event IDs need no elaborate
identity proof; possible duplicate entries are an accepted application choice.

## Recursive provider operation outcomes

Dependent definitions: REQ-DOM-009, REQ-MUT-004, REQ-COMP-006/007/008, REQ-SYNC-026.

The retained Help article establishes the chosen four descendant levels. The API
does not specify a numerical backend maximum. Check consumed subtree move/category
propagation, preservation of known completed descendants, recurring completion
without resetting children and ancestor restoration against retained source.
Independent controlled after-states establish application handling, not live
provider behavior. If no supported evidence establishes an indispensable outcome,
return that specific contradiction to Design rather than declaring a fake proof.
There is no all-history childlessness proof or live-account release gate.

## Remote time and operation-specific proof

Dependent definitions: REQ-SYNC-021/026/027/013, REQ-SCHED-012/013, REQ-DOM-014.

Preserve nullable added_at and known/unknown sibling ordering. No pinned invalid-
sync-token discriminator is established; implement the agreed explicit failure/
clear-and-refresh fallback rather than a guessed classifier. Server full replacement
plus one freshness delta remains supported and bounded.

Use the selected remote floating overlap/gap interpretation and local-input DST
refusal in all consumers. Verify recurrence-preserving date-only/timed/floating/
fixed occurrence updates and reminder interactions; source examples do not prove
all future recurrence/notification behavior. See floating-time-context.md.

Missing UUID/create-ID/occurrence proof remains an unknown remote outcome. Reconcile
read-only without blindly repeating the mutation. Keep origin-command diagnostics,
old-cache retention and pending-history protection, without a persistent cache
validity-state system.

## Pager/runtime and verification

Dependent definitions: REQ-OUT-018, REQ-CONFIG-003, REQ-PLAT-001/003, REQ-BUILD-002.

Choose direct process/input delivery, original-stdout colors, normal early quit,
complete fallback and SIGINT/terminal cleanup. Retained less documentation and
inherited local probes establish limited example-command feasibility only. Planning
must supply an environment where bounded real-less evidence can be obtained;
the source project's former image is not a required or assumed todo-3 image.

Planning chooses the pinned Linux/amd64 Python 3.11 Docker environment invoking
Codex directly, resource configuration and test organization. No provider/model,
credential, paid call, plan, readiness or code deliverable is established by Design.
Ordinary errors may stop at the first relevant issue; no doctor is needed.
