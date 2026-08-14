# 0005: Explicit value markers and human output

Status: Accepted

## Context

The shell removes quote syntax before invoking the program. Inferring whether
arguments represent one or several steps/comments from embedded whitespace
would make structure depend on content and could not represent several
one-word values. The design also required golden output without defining a
stable human layout.

## Decision

- Unmarked trailing words form one logical title, comment, reason, or other
  free-text value where a shorthand permits them.
- Multiple steps and comments require repeated `--step` and `--comment`
  markers. Quoting never creates a batch boundary.
- Marker-based canonical forms separate selectors from values; legacy command
  aliases remain public but normalize into the same grammar and behavior.
- `--at` is the canonical attention marker and `--due` is its equivalent alias.
- Human-readable stdout/stderr layouts are deterministic and defined in
  `output-contract.md`; no structured scripting interface is promised.

## Consequences

- Unquoted prose remains convenient for the common single-value case.
- Creating several values is explicit and independently testable.
- Some old positional batching syntax is intentionally no longer meaningful;
  repeated markers are required even though command aliases remain.
- Machine-readable output and identity-safe selectors remain separate future
  work.
