# todo design

This directory describes the intended behavior and design of `todo`, a
personal command-line workflow built on Todoist.

The documents are the proposed source of truth for future development. They
describe existing behavior where it is intentional and proposed behavior where
the current program is expected to change. Unresolved matters belong in
`open-questions.md`; they must not be silently decided during implementation.

## Documents

- `product.md` — purpose, users, workflows, goals, and non-goals
- `domain-model.md` — terminology, derived properties, and invariants
- `command-interface.md` — public command-line contract
- `behavior.md` — detailed rules, decision tables, and acceptance examples
- `quality-requirements.md` — safety, reliability, synchronization, and testing
- `architecture.md` — system context and responsibility boundaries
- `todoist-dependencies.md` — capabilities supplied by Todoist and replacement
  requirements for another backend
- `open-questions.md` — decisions that remain unresolved
- `decisions/` — accepted design decisions and their rationale

## Status vocabulary

- **Existing** — behavior of the current implementation that should be retained
- **Proposed** — desired behavior not yet confirmed in the implementation
- **Accepted** — an intentional design decision
- **Open** — requires a decision or further examples

Passing tests do not override these documents. If implementation, tests, and
design disagree, the discrepancy must be resolved explicitly.
