# Operation evidence

`Gateway.execute(Operation, before=Current, ...) -> Result` retains exact command
UUID/status and creation temporary-ID attribution. `Result.before_token` is the
submitted baseline token; `Result.after` is its complete retrieved `Current`.
`actual`, `issues`, `restored_ancestors` and `occurrences` retain their existing
semantics, including accepted operations whose verification failed. The added
field is optional and follows all existing positional fields.

`Result.evidence` includes exhausted `HistoryAdapter` `Retrieval` values. Their
optional `endpoint`, `scope` (a tuple of filter pairs), and `owner_id` identify the
original request; `start`, `end` and `pages` preserve interval/pagination coverage.
Completed and activity producers populate endpoint/scope; comments populate
endpoint/owner. Legacy constructors remain valid but unspecified provenance is
not shared as complete operation evidence. Filtered relevance reads retain `required_ids` and cannot supply complete owner
evidence; failed/partial retrievals produce no reusable result.

`current.retrieve(..., created_ids=frozenset())` accepts command-local IDs whose
creation is proven by this operation's UUID and temporary-ID mapping. Gateway
supplies only previously unknown identities. With a valid saved current baseline
and token, these objects' incremental resources establish their own complete
state without hydration. Ordinary scope entrants still hydrate unchanged own
comments/reminders; scope expansion and legacy baselines still hydrate, validate,
and receive the existing full-candidate freshness delta. Errors never authorize
an automatic token reset.

`Current.removed_comment_ids` retains explicit comment tombstones or prior-owner
loss for deferred archived context. It does not infer deletion from omission.
The value is transient; reconciliation removes superseded saved comments while
retaining authoritative current live ownership and complete scoped responses.
