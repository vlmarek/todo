# 0002: Todoist is the source of truth

Status: Accepted

## Context

Tasks are viewed and modified both through the CLI and through Todoist on a
phone. Todoist also provides reminder notifications.

## Decision

Todoist is authoritative for task, step, category, date, completion, comment,
priority, recurrence, and reminder data. The local cache supports offline
read-only operations and can be reconstructed from Todoist.

Local configuration and the report cursor remain locally authoritative because
they cannot be reconstructed from Todoist.

State-changing commands and report generation synchronize before operating.
Failed synchronization prevents mutation.

## Consequences

- Phone changes become visible after synchronization.
- Mutations require Todoist access.
- Read-only commands can use stale cached data unless refreshed.
- Cache loss is recoverable; configuration and report-cursor loss are not.

