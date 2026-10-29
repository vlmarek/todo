# Remove routine limitation notices — revision 16

Status: **Accepted**

## Agreement and precedence

The operator requested removal of the older-completed-descendants deletion
warning, then selected messages 1, 2 and 4 from the assessed notice list: inspection
coverage, completed-search coverage and successful cache-clearing notices. They
approved the presented documentation scope by instructing: "I want you to update
the design and then implement the change directly". This selects direct delivery
after the completed installed final plan. The task/step unification discussion was
abandoned; the existing hierarchy and terminology remain unchanged.

These narrow successor requirements govern the removed output only. Earlier
definitions, accepted assignments and their evidence remain unchanged as history.

| Successor | Replaced scope |
| --- | --- |
| REQ-OUT-026 | REQ-OUT-020's TPL-DETAIL completed-step coverage disclosure and TPL-CACHE-COVERAGE, REQ-CLI-021/016's corresponding disclosure duties, and REQ-OUT-024's instruction to preserve these coverage warnings. |
| REQ-OUT-027 | REQ-MUT-003/007's older-completed-descendants warning and the matching warning-preservation clause in REQ-VERIFY-031. Preview, eligibility, confirmation and cancellation remain required. |
| REQ-OUT-028 | REQ-CLI-029's routine successful cache-clearing/history-preservation explanation. The explanation remains valid in help; failure diagnostics remain required. |
| REQ-VERIFY-034 | Adds distinguishing output evidence while preserving the existing offline isolation and proportional verification policy. |

### REQ-OUT-026 — Inspection and completed search without coverage notices

Successful task and step inspection must not print the routine
`todo: completed steps use retained history; coverage may be incomplete` notice.
Successful `search --all` must not print TPL-CACHE-COVERAGE, including its earliest
retained completion date, whether results are empty or nonempty and whether any
completed history is retained. Do not replace either message with another routine
notice or placeholder on stdout or stderr.

The known-descendant and retained-history populations, incomplete-history limits,
ordering, filtering, item dates, comments and normal result text remain unchanged.
This removes disclosures, not the underlying limits or genuine diagnostics.

### REQ-OUT-027 — Deletion preview without the historical-descendant warning

Deletion must not print `Older completed descendants are outside this bounded
preview and may also be cascade-deleted by Todoist.` or an equivalent routine
warning, including with `--yes` and before cancellation. Preserve the selected
scope preview, cached/bounded descendant population, recursive ancestor context,
affirmative confirmation, cancellation and non-interactive rules. `--yes` skips
only confirmation. Direct deletion and reconciliation remain unchanged.

The preview does not become complete: older completed or otherwise unobserved
descendants can remain absent. Existing accepted cascade effects and the exclusion
of full-history backfill remain in force.

### REQ-OUT-028 — Successful cache rebuilding without explanatory notices

Successful `--clear-cache --refresh` must not add a cache-clearing,
history-preservation or historical-coverage notice, whether the cache existed or
was already absent. In particular, omit both `Explicit cache clearing occurred;
unreported history was preserved. Clearing does not fill historical coverage
gaps.` and `Cache was already absent; unreported history was preserved.` with no
replacement receipt. Render the requested read result normally.

Preserve the actual clearing/rebuild behavior, separate unreported history,
configuration, binding, credentials, cursor and remote data. A failed rebuild
still reports actual clearing, publication state, failure and applicable recovery.

### REQ-VERIFY-034 — Removed notices and preserved operation outcomes

Establish representative offline evidence that task/step inspection and completed
search retain their results without coverage notices, including empty completed
search and absent retained history. Establish deletion without the warning for
interactive confirmation/cancellation and `--yes`, retaining preview bounds and
direct-operation behavior. Establish successful clearing/rebuild without a notice
for an existing or absent cache while retaining unreported data.

Keep meaningful existing failure/cancellation assertions. The limited-report-
history warning and its configuration, stale-snapshot warning, retrieval progress,
convention diagnostics, retry notices and actual failure/partial/unknown outcome
messages remain unchanged. No new verbosity setting, provider call, backfill,
storage migration or test dependency is introduced. Verification organization and
implementation details are delegated to the authorized direct-delivery work.

## Assessment and delivery boundary

This is one presentation change. The implementations emit these notices at known
renderer, deletion-preview and successful-refresh boundaries; no provider
investigation or unresolved product decision is required. Source inspection shows
that failed clearing has separate diagnostics and genuine convention warnings
can remain independently rendered. Direct implementation must preserve those
paths and update affected existing expectations proportionally. The approved
Design handoff is initially uncommitted; delivery recording identifies the actual
implementation subject and verification evidence separately.
