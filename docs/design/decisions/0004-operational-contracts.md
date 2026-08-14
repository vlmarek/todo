# 0004: Operational and persistence contracts

Status: Accepted

## Context

The behavioral design left cache compatibility, cursor initialization, crash
behavior, locking, runtime support, API coupling, and presentation stability
open. Choosing them silently could cause omitted reports, stale offline views,
corrupt local state, or inconsistent command behavior.

## Decision

- First successful account binding creates the report cursor after provisioning
  and binding persistence. Once binding exists, init never recreates a missing
  or corrupt cursor; recovery is an explicit cursor operation.
- Account, root, and managed category IDs live in authoritative binding state
  outside the disposable cache. Account changes require confirmed rebind.
- Final reports capture their end before the first request, then completely
  write and flush output before advancing the cursor. A crash or broken pipe
  may repeat work but must not skip an unprinted period.
- Cursor changes are explicit confirmed local operations accepting ISO and
  past-relative input.
- Cache-backed reads share global `--refresh` and warn after 24 hours. There is
  no standalone refresh command.
- Disposable caches are schema-versioned and rebuilt rather than migrated.
  Cursor files receive stronger crash durability than caches.
- State-changing and synchronizing operations use a bounded exclusive lock;
  atomic cache-only reads do not lock.
- Deterministic human-readable output is defined in `output-contract.md` and
  verified with golden fixtures, but is not a machine interface. Exit codes
  distinguish success, usage, cancellation, and operational failure.
- The supported distribution is a Python 3.11+ package installed through
  `pipx` on Linux and macOS.
- The Todoist adapter explicitly targets API v1 and Sync behavior, exhausts
  pagination, ignores unknown fields, and rejects unsupported recognized
  behavior-affecting values.

## Consequences

- First initialization intentionally excludes earlier Todoist activity from
  default reports; later cursor loss cannot silently establish another gap.
- A final report may repeat after a narrow crash window, which is safer than
  silently losing report content.
- Offline reads remain fast and concurrent while stale data is visible.
- Cache upgrades remain simple because no authoritative identity lives in the cache; accumulated completed-search history may be lost.
- Windows support and persistent diagnostic logging remain outside scope.
