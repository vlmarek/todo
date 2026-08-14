# todo design

This directory describes the intended behavior and design of `todo`, a
personal command-line workflow built on Todoist.

The documents are the proposed source of truth for future development. They
describe existing behavior where it is intentional and proposed behavior where
the current program is expected to change. Unresolved matters belong in
`open-questions.md`; they must not be silently decided during implementation.

The design also treats usability as a cross-cutting requirement. Common
workflows should be discoverable, commands using the same concepts should
behave consistently, and failures should help the user recover without
silently guessing their intent.

## Documents

- `product.md` — purpose, users, workflows, goals, and non-goals
- `domain-model.md` — terminology, derived properties, and invariants
- `command-interface.md` — public command-line contract
- `behavior.md` — detailed rules, decision tables, and acceptance examples
- `quality-requirements.md` — safety, reliability, synchronization, and testing
- `architecture.md` — system context and responsibility boundaries
- `todoist-dependencies.md` — capabilities supplied by Todoist and replacement
  requirements for another backend
- `todoist-adapter.md` — concrete Todoist API, synchronization, and pagination
  contract
- `open-questions.md` — decisions that remain unresolved
- `decisions/` — accepted design decisions and their rationale

## Suggested reading order

1. `product.md`
2. `domain-model.md`
3. `command-interface.md`
4. `behavior.md`
5. `quality-requirements.md`
6. `architecture.md`
7. `todoist-dependencies.md`
8. `decisions/`

The first three documents explain what the product is, the language it uses,
and how the user interacts with it. The remaining documents explain detailed
behavior, verification, implementation boundaries, and rationale.

## Status vocabulary

- **Existing** — behavior of the current implementation that should be retained
- **Proposed** — desired behavior not yet confirmed in the implementation
- **Accepted** — an intentional design decision
- **Open** — requires a decision or further examples

Passing tests do not override these documents. If implementation, tests, and
design disagree, the discrepancy must be resolved explicitly.
