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
