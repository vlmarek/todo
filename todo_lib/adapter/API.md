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

For ordinary item/note/reminder writes with a proven `before.current_snapshot`
and non-wildcard token, Gateway submits one command plus that exact `sync_token`
and JSON `current.RESOURCE_TYPES` in the original form. Project/label creation
and legacy/provisioning paths retain their policy.

`current.retrieve(..., supplied_response=None, supplied_token=None)` consumes an
actual combined response in place of the initial read. `supplied_token` must equal
the requested baseline token; `prior` must be its proven current snapshot, separate
from archived `known` context. The same merge, metadata, membership, hydration and
validation path applies. Server full responses still receive one freshness delta.
No transport replay or predicted patch supplies resources. Gateway passes these
optional keywords only when consuming combined resource/control evidence; injected
retrievers used for that path must accept them. Receipt-only responses use the
original proven baseline/token for necessary retrieval. A delta missing the
operation's own resource likewise requires supported retrieval from that baseline;
its receipt token cannot skip unincorporated changes. Invalid resources fail
validation rather than authorizing replacement recovery.

Complete current notes can verify active-owner comment content/deletion. Archived
owners still use exhausted scoped comments. An ordinary completed `Item` with
`completed_at` may supply a command-local `CompletedRecord` in `Result.evidence`
and its occurrence in `Result.occurrences`. This is actual lifecycle evidence,
not completed-endpoint pagination or historical interval coverage. Recurring
completion/undo retains scoped occurrence retrieval. Own-resource inclusion is
checked from actual returned resources; the retained Sync capability does not
promise every mutation response contains its normalized effect.
