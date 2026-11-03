# Accepted operation publication

Under the existing command lock, ordinary callers pass the exact adapter `Result`
to `Synchronizer.reconcile_accepted_locked(result=None)` after each accepted write
and before the next submission. Complete `after` evidence is reusable only with
its matching `before_token`, account/root and proven current snapshot. A missing
usable result requires current retrieval. All returned active state is validated,
including unrelated active changes. Acceptance survives reconciliation, local
publication failure, and interruption; callers stop without replay.

`OperationEvidence(adapter, result)` shares exhausted `Retrieval` values only for
their explicit endpoint/filter/owner and covering interval. Uncovered required
reads use the adapter. `_reconcile(..., affected=None)` keeps full refresh/report
policy by default; ordinary callers supply affected identities derived from the
exact target, owners, known/returned descendants and ancestors. Missing open
owners still require lifecycle evidence. Unrelated retained archived context and
comments keep their last established observations; unrelated recurring activity
is deferred. Moves pass their inherited completed-descendant context through the
same scoped policy and still validate actual returned source/destination state.

No persistent field or historical freshness inference is added. Current tokens,
`LocalState.current_snapshot`, resource membership and `synced_at` continue to be
published together. Ordinary writes preserve `History.coverage`, existing pending
observations, and the report cursor. Refresh and report retain complete required
historical retrieval with lower bounds including the cursor (and any earlier
required window); advancing current synchronization cannot skip deferred pending
intervals. Report output/flush, cursor publication and cleanup retain their order.

The no-argument accepted boundary preserves legacy/full policy, including category
provisioning. Unknown/rejected paths retain their existing required read-only
reconciliation and classifications. Public request/result/receipt shapes remain
unchanged.

Combined mutation responses reach this same boundary through `Result.after`;
there is no new workflow operation API. Gateway uses
`current.retrieve(..., supplied_response=response, supplied_token=before.sync_token)`
with the matching proven current baseline. Sufficient resources avoid the initial
equivalent current read, while legacy hydration/full freshness and required scoped
reads retain their existing policy. Current active notes need no equivalent REST
comment query. `OperationEvidence.lifecycle_records` retains command-local
`CompletedRecord` values separately from exhausted `Retrieval` interval evidence;
`_reconcile` incorporates those occurrences without claiming historical coverage.
Missing related owners still trigger supported retrieval. Each complete candidate
is validated and published before the next command receives its saved token.

`_reconcile` also accepts optional command-local `deletion_events=()` and
`discover_deletions=False`. Reports pass their exhausted shared activity records;
explicit refresh enables bounded item-scoped activity coverage for missing known
owners, including saved completed owners. Ordinary accepted operations reuse
supplied `OperationEvidence` activity facts without enabling these extra reads.
A proved deleted root makes its known subtree directly affected; supplied fresh
completed descendants can then replace saved parentage using the same scoped
evidence reuse.
Deletion roots and established descendants are removed before required owner or
comment resolution. Available completed parentage supersedes saved relationships,
and current parentage supersedes both. No deletion ledger or public result shape
is added; unresolved required state and failed coverage still refuse publication.

Revision 22 report-specific successor: `Reporter.run` / `report()` still return
`ReportResult(start, end, finalized, warnings)` compatibly; appended defaults are
`incomplete=False` and `status=0`. The public CLI returns `status`. An incomplete
preview or non-overridden final returns 1; an overridden final returns 0 only
after delivery and cursor saving. Exceptions retain the existing failure boundary.
Programmatic requests receive early duplicate/unknown/combination validation.

`report_recovery.Available` is command-local evidence with explicit
`complete=False`; it is not an exhausted `Retrieval`. `ReportHistory` retains
validated records and isolates record/owner failures only for report display.
Conflicting comment representations are excluded individually while subsequent
pages and independent owners remain useful. Recovery checks comment identity
across all scoped reads (including rejected representations) and current Sync
notes before merging display text. Only independently eligible, marked saved
comments may replace conflicting fresh evidence. An unavailable activity
capability under override skips that source while still attempting bounded
completed scopes and owner resolution; ordinary capability refusal is unchanged. After Current retrieval fails,
independently checked authenticated identity permits bounded reads of saved
bound scopes; failed Current data never becomes a Sync baseline. Account mismatch
stops those reads and discards incompatible results before mapping. Strict
HistoryAdapter, refresh and mutation semantics remain unchanged. Complete reports
retain existing candidate publication. Recovery builds a validated display from
independently usable evidence, marks bound saved fallback, and never publishes a
candidate or prunes pending history. It may save only the fixed-end cursor after
complete diagnostic/report delivery with explicit `--final --override`. Required
local state, boundary/account safety, local publication failure and interruption
remain fatal. No observation time becomes an activity timestamp.
