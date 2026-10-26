# Todoist dependency inventory

Status: **Informative**

This inventory explains why Todoist is part of the accepted product. It defines no
additional obligations; binding behavior is in `REQ-PROD-*`, `REQ-DOM-*`, and
`REQ-SYNC-*`.

Todoist currently supplies durable task/category/comment/reminder identity and
state, phone and web clients, cross-device conflict resolution, notification
delivery, English due-expression parsing, recurrence advancement and undo,
project/task hierarchy mutation, current comment storage, activity history,
completed-object retrieval, account timezone, current capability reporting, and API
idempotency/rate-limit semantics.

The CLI owns selection, command grammar, domain validation, actionability and
urgency, temporary-hiding policy, category policy, human output, local binding and
cursor, disposable offline cache, and operational report construction.

Replacing Todoist would require a new accepted design for authoritative storage,
stable IDs, synchronization and conflicts, phone/web access, notification delivery,
natural-language dates, recurrence, comments, event history, retention, capability
reporting, and mutation failure semantics. `OUT-BACKEND-001` excludes that work from
this release.
