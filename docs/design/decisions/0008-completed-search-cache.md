# 0008: Best-effort completed search cache

Status: Accepted

## Context

The normal Todoist sync does not return arbitrary completed parent history.
Tying completed search to the current report cursor discards useful older
results, while guaranteeing all account history would require an expensive
backfill and a new user interface.

## Decision

`todo search --all` searches every completed task and step plus their surviving
task comments currently retained in the disposable cache, including objects
older than the report cursor. Reports and completed-object operations add
fetched objects to that cache; cursor advancement and ordinary refresh do not
purge them. Output always states the earliest cached completion and that
coverage may be incomplete.

No `--since` search option or automatic full-history backfill is part of the
first release.

## Consequences

- Completed search becomes more useful over time and remains available offline.
- Cache deletion or incompatible replacement loses accumulated completed-search
  history without losing authoritative task data.
- An empty cached search never claims that all Todoist history was searched.
