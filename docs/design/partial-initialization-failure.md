# Partial first-initialization failure — current revision 5 amendment

Status: **Accepted**

The operator asked “failing write to a file is not a concern. How to continue
without making todo unnecessarily complex?” and confirmed “I agree with that”
after the manual-recovery boundary and its pending-history/report-cursor loss were
disclosed. The actual statement, proposed understanding and confirmation are at
`/home/neuron/Documents/cml/todo-3/runtime/operator/partial-init-write-failure-authorization.md`.
This approves this scoped Design amendment and matching Plan alignment; the
instruction to stop before every subsequent Design or Plan change remains.

## Scope and precedence

For unfinished and successor work, apply this amendment only to local first-init
publication that fails before establishing a coherent initialized state. Earlier
definitions remain byte-for-byte protected inputs for accepted assignments.

| Current definition | Earlier definitions affected only at this boundary |
| --- | --- |
| REQ-INIT-009 | REQ-INIT-002/003/005/008: applicable init-rerun recovery language; REQ-CACHE-010 and REQ-CLI-036: recoverable-history and explicit-recovery language does not require every partial first-init state to be recoverable by rerun |
| REQ-VERIFY-025 | REQ-VERIFY-004/007/018/022/023: no comprehensive partial-first-init rerun-recovery acceptance obligation |
| OUT-INIT-001 | Excludes guaranteed recovery of every partial first-init publication, including a timezone change between attempts |

Normal successful initialization, repeat initialization of a valid binding,
remote provisioning reuse, synchronization and timezone behavior retain their
existing requirements. The revision-3 per-file publication contract and revision-4
command-time precision agreement remain. No unrelated behavior is superseded.

### REQ-INIT-009 — Manual-recovery boundary after failed first-init publication

If local first-init publication fails, report the failed phase and a nonzero
outcome; do not present initialization as successful. A failure before any
destination replacement retains the existing pre-publication guarantees. After a
replacement, the existing per-file boundary permits individually complete files
that do not form a usable initialized set. Reject mixed or inconsistent local
files as current state. Preserve available bytes until the user explicitly takes
a recovery action; do not bypass association, path, permission or identity checks,
guess history/account/cursor values, or silently discard pending history.

The existing explicit manual fresh start in REQ-INIT-002 and REQ-OPS-001 is
sufficient recovery: stop `todo` processes, optionally back up wanted local data,
delete the entire `~/.todo` directory and run `todo init`. Disclose that this
discards local configuration, binding, cache, pending history and report cursor,
can lose unreported local observations, and creates a new initial report boundary
on successful init; remote Todoist data is unchanged. Deletion remains an explicit
user action. This amendment authorizes no automatic deletion or new repair/reset
command. Existing safe restoration or init reruns may remain available where they
work; rerunning init is not guaranteed to recover every partially published state.

In particular, first init may publish complete cache/history/cursor candidates and
then fail to replace binding. If the account timezone changes before a rerun and
saved unbound floating history cannot be validated with the new candidate binding,
clear failure and rejection with the existing manual fresh-start option satisfy
this boundary. Recovery through that rerun is not required. This exception does
not weaken normal floating/fixed-time interpretation, current account-timezone
authority, ordinary synchronization or successful/repeat initialization.

Keep complete restrictive candidates, per-file atomic replacement, binding-last
publication and safe identity/path/mode validation. Remote accepted, failed,
unknown and unattempted outcomes remain truthful, without rollback or mutation
replay. Preserve the normal valid-binding cursor and pending-history guarantees;
the disclosed loss above applies only to the user's deliberate manual fresh start.

### REQ-VERIFY-025 — Evidence for the scoped first-init failure boundary

Establish that a representative failed first-init publication reports failure,
keeps each existing destination individually complete, and refuses mixed or
inconsistent files as a usable snapshot. Retain the pre-publication preservation
boundary and the documented explicit fresh start with pending-history/cursor loss.
Do not make successful recovery of every partial state by rerunning init an
acceptance condition, including the changed-account-timezone/unbound-floating-
history case in REQ-INIT-009. Existing working rerun behavior need not be removed.

Retain successful first initialization, normal repeat initialization preserving
valid binding/cursor/pending history, safe remote provisioning reuse, ordinary
synchronization/timezone semantics, per-file safety and truthful remote outcomes.
Planning chooses representative cases and appropriate test layers and may reuse
existing evidence; no storage repair or new recovery mechanism is required to
establish this accepted limitation.

### OUT-INIT-001 — No guaranteed rerun recovery of every partial first init

Guaranteed idempotent recovery of every failed local first-init publication by
rerunning init is excluded, including when the account timezone changes between
attempts. The existing explicit manual fresh start with disclosed local
pending-history and report-cursor loss is sufficient at this boundary. No shared
storage redesign, journal, rollback, automatic deletion or new repair/reset command
is included. Normal successful/repeat initialization and unrelated safety, history,
synchronization and timezone obligations remain required.
