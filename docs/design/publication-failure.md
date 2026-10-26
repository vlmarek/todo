# Publication failure limitation — current revision 3

Status: **Accepted**

This scoped amendment is the current product agreement for unfinished and successor
work. Original definitions remain byte-for-byte historical inputs for accepted
assignments; their intact-snapshot promises do not govern the changed boundary.
Read this with the unchanged definitions, using the precedence below. No original
identifier is recycled. The operator confirmed the precise limitation and instructed
“implement that and continue the work”; actual excerpts and the separate
interpretation are retained in the durable Design handoff.

## Scope and precedence

| Current definition | Earlier definitions it supersedes only for this scope |
| --- | --- |
| REQ-CACHE-009 | REQ-CACHE-008: preserving a usable previous snapshot after multi-file publication has begun |
| REQ-LOCAL-007 | REQ-LOCAL-006: cache retention after interrupted publication; REQ-LOCAL-005: publication across cache/history/binding is per-file atomic |
| REQ-CACHE-010 | REQ-CACHE-006 and REQ-VERIFY-022: history preservation does not promise an immediately loadable consistent set after partial publication |
| REQ-CLI-036 | REQ-CLI-032: publication-failure recovery diagnostics; REQ-CLI-029: failed clear-and-refresh may have replaced some files |
| REQ-VERIFY-023 | REQ-VERIFY-020/021: intact-cache expectations after publication begins; related boundary evidence |
| OUT-LOCAL-001 | Explicit accepted limit, consistent with OUT-OPS-003 and OUT-NFR-003 |

REQ-SYNC-013/026, REQ-COMP-007 and all other consumers of REQ-CACHE-008 use
REQ-CACHE-009 at this boundary. Their retrieval, remote outcome and no-replay rules
remain. REQ-INIT-002's existing binding-last per-file boundary remains; it is no
longer an exception limited to initialization. REQ-LOCAL-002/003 and REQ-SEC-005/007
remain unchanged. REQ-REPORT-003/013 retain their independent output/cursor and
history-cleanup ordering; this amendment does not permit cursor advancement on
failed reporting or early history cleanup. No other behavior is superseded.

### REQ-CACHE-009 — Current cache after synchronization and publication failure

The cache remains disposable, schema-versioned, reconstructable current managed
state under REQ-CACHE-008, with no HTTP for cache-backed reads unless explicitly
refreshed. Missing, malformed, incompatible, unsafe or identity/publication-mixed
state fails clearly without a partial normal view or an empty-account default.

Build and validate the complete candidate set before its first destination
replacement. Failure in input validation, retrieval, remote reconciliation,
candidate preparation, or before any replacement succeeds preserves the previous
files, except a cache explicitly deleted by --clear-cache. Do not delete cache as
automatic error or interruption cleanup. Every destination replacement remains
atomic under REQ-LOCAL-003.

Publication of cache, separate history and binding is a sequence of atomic file
replacements, not an atomic transaction of the set. Once any replacement succeeds,
a later replacement failure or interruption can leave some new files alongside
old files, or a missing file on first initialization. Report failure and require
explicit recovery. There is no guarantee that the previous usable snapshot can
still be loaded after that boundary. Files must remain individually complete;
readers must reject a mixed account/root/publication set rather than combine it,
show a partial normal result, or silently accept it as current.

Ordinary synchronization and post-mutation reconciliation/publication use the
same rule. If a consistent binding-compatible saved snapshot remains, later
offline reads may display it even when older than remote truth, including the
ordinary age warning. A mixed or otherwise invalid set must fail without HTTP on
an offline read. No persistent clean/outdated/blocked state or stale-cache mode
is introduced. Preserve the originating remote operation's accepted, failed,
unknown and unattempted classification; local publication failure changes none
of those remote outcomes.

### REQ-LOCAL-007 — Per-file publication and interruption boundary

Binding remains the final publication point for a coordinated snapshot. Cache,
history and an initial cursor where applicable precede binding, with complete
validated restrictive candidates and per-file atomic replacement. A successful
publication has consistent account/root/publication associations and the one
binding timezone authority. A cache's sync token and corresponding cached state
remain together in their atomic replacement under REQ-SYNC-013. No token-only
advance or competing timezone authority is permitted.

SIGINT stops further remote mutations as soon as control returns from an in-flight
request. Report accepted operations, any outcome-unknown in-flight mutation, and
unattempted operations without rollback or replay. Preserve the prior complete
set when no destination has yet been replaced; after a replacement succeeds the
partial-publication limitation of REQ-CACHE-009 applies. Never promise a usable old
cache merely because reconciliation/publication did not finish. Do not delete
cache as interruption cleanup without explicit --clear-cache.

Clean unpublished temporary files, restore terminal state where applicable,
release the lock and exit 130 for handled SIGINT. Other operational publication
failures exit 1 under REQ-CLI-030. No incomplete result is successful. The report
cursor remains unchanged unless complete final output and cursor replacement both
succeeded; pending-history cleanup still follows that finalization boundary.
Lock-free readers may observe a coherent published set or reject a concurrently
mixed set; per-file atomicity never authorizes accepting a mixed view.

### REQ-CACHE-010 — Pending-history protection at the per-file boundary

All retained history obligations in REQ-CACHE-006 remain: store pending observations
separately from disposable cache, retain required identity/ancestry/fields/own
comments, respect authoritative deletion/scope/privacy rules, and release covered
history only after successful final output and cursor publication. Refresh,
cache clearing, preview, ordinary failures and interruption do not authorize
emptying, deleting, silently resetting or prematurely pruning needed history.

Candidate history must preserve still-required pending observations. Its destination
has the same per-file atomic replacement guarantee: failure before its replacement
leaves the prior complete history file; a successful replacement leaves the complete
validated candidate. Failure elsewhere can make its publication association differ
from cache or binding, so immediate usability of the whole set is not guaranteed.
Preserve available history bytes and refuse incompatible/mixed sets. Do not silently
reset history to recover consistency, bypass its association, or claim all newly
retrieved in-memory observations were saved after a failed publication. Explicit
recovery retains recoverable pending history using existing supported workflows;
this amendment adds no automatic repair or new recovery command.

### REQ-CLI-036 — Truthful failure diagnostics and existing explicit recovery

An ordinary refresh or a post-mutation publication failure reports the actual failed
phase and exits nonzero without synchronized normal output. Distinguish the remote
operation's accepted/failed/unknown/unattempted outcomes from the subsequent local
failure. A failed local write is not proof that Todoist rejected an operation or
needs remote data repair. Never replay completion, undo, creation or another
mutation to repair local state.

When no replacement succeeded, explain that the previous snapshot remains if it
was not explicitly cleared. After publication has begun, say that local files may
be partially published and the saved snapshot may be unusable; do not claim that
the old snapshot was preserved. A failed --clear-cache --refresh must disclose the
explicit deletion and actual publication failure; it must not assert that no new
cache file was written when an earlier replacement succeeded.

Give existing read-only `todo --refresh now` recovery where applicable. It is not
a promise that every mixed set can be refreshed without manual restoration.
If local consistency/path/permission validation prevents refresh, identify that
condition and the applicable existing manual consistent-set restoration under
REQ-OPS-001 or init-rerun path under REQ-INIT-002, as appropriate. Do not bypass
validation or suggest that cache clearing repairs binding/history/cursor errors.
Existing explicit cache clearing remains optional where safe; full-directory fresh
start retains its disclosed loss of pending local history and report boundary.
No silent restoration, guessed cursor/account, rollback or mutation replay is added.

### REQ-VERIFY-023 — Publication failure and recovery evidence

Distinguish failure before the first successful replacement from failure after a
replacement, including a later binding replacement, and handled interruption where
it affects that boundary. Before publication, the prior files remain unchanged
unless explicitly cleared. After partial publication, each existing destination
is a complete old or candidate file, the error is reported, and a new-process
offline read either loads a consistent saved snapshot or refuses a mixed set with
zero HTTP. A usable previous snapshot is not an acceptance condition at that point.
Successful publication still loads coherently with exact timestamps, paired cached
state/token and one binding timezone authority.

Use representative ordinary refresh and accepted-mutation failure evidence to
establish the shared boundary. Remote acceptance/unknown outcome remains truthful,
later operations stop as required, and read-only recovery does not complete or undo
another recurring occurrence. Establish preservation of needed pending-history
content through its per-file replacement and refusal rather than silent reset on
inconsistent association. Retain the unchanged report output-before-cursor and
cleanup-after-finalization requirements. Planning chooses the smallest meaningful
boundary cases, test layers and consumer coverage; no exhaustive cross-product,
transactional publisher or repeated broad suite is required by this amendment.

### OUT-LOCAL-001 — No intact snapshot guarantee after partial publication

Preserving or automatically restoring the previous usable multi-file snapshot
after the first successful file replacement is excluded. A later-file failure or
interruption may require explicit recovery from an individually complete but mixed
set. Transaction journals, automatic rollback, transactional storage redesign and
new recovery commands are outside this amendment. Per-file atomicity, complete
candidate validation, mixed-set refusal, pending-history content protection and
existing explicit recovery remain required.
