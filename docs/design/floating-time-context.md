# Floating-time provider evidence and conformance cases

This supplies source navigation and concrete cases, not a second product policy.
REQ-SYNC-021 defines remote floating interpretation; REQ-SCHED-013 defines local
input refusal. No old task IDs or implementation interfaces are inputs here.

## Retained sources

- external/todoist/manifest.json authenticates the API v1 JSON snapshot. Its
  Due dates tag distinguishes date-only, floating offset-free account-local wall
  times with null timezone, and fixed UTC instants with recurrence timezone.
  The malformed 2016-12-0 example is not valid date grammar or a DST policy.
- external/floating-time/manifest.yaml authenticates the unchanged official Help
  article bytes. Floating/Fixed sections discuss zone changes but supply no
  overlap/gap resolution or notification-delivery promise.

## Distinguishing cases

1. Prague remote 2026-10-25T02:30:00 overlaps. Valid instants are 00:30Z and 01:30Z;
   the selected application policy uses 00:30Z.
2. Prague remote 2026-03-29T02:30:00 is in a gap. Shift forward by the actual gap to
   03:30 local / 01:30Z, preserving minutes/seconds/fractions rather than snapping.
3. Preserve raw floating data and recurrence metadata, re-resolving it after an
   account-zone change. Fixed instants remain fixed and date-only values stay dates.
4. Local entered/calculated overlap/gap times still require an explicit offset.
   Interpreting a remote value causes no remote edit or occurrence advancement.

Use retained official evidence and independent literal UTC/round-trip expectations
with Python zoneinfo. Apply the result consistently to mapping, serialization,
urgency, presentation and scheduling reconciliation. Fakes establish application
conformance to this chosen policy, not Todoist's live DST or notification behavior.
No credentials, network, repeated provider download or source-project tests are
required as an automated gate. Planning chooses implementation and verification.
