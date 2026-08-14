# todo design

This directory describes the intended behavior and design of `todo`, a
personal command-line workflow built on Todoist.

The Accepted documents are the binding source of truth for the first
implementation. This is a greenfield contract: behavior is retained only when
these documents state it, regardless of an older implementation. If a future
question is recorded in `open-questions.md`, it must be resolved explicitly
before implementation chooses behavior.

The design also treats usability as a cross-cutting requirement. Common
workflows should be discoverable, commands using the same concepts should
behave consistently, and failures should help the user recover without
silently guessing their intent.

Module names, library choices, and reconstructable JSON layout details remain
implementation choices. They may vary only when they preserve every observable
behavior, safety property, migration rule, and recovery guarantee stated here.
An implementation choice must not resolve an ambiguous user-visible behavior
that the contract leaves open.

## Documents

- `product.md` — purpose, users, workflows, goals, and non-goals
- `domain-model.md` — terminology, derived properties, and invariants
- `command-interface.md` — public command-line contract
- `output-contract.md` — deterministic human-readable output layouts
- `behavior.md` — detailed rules, decision tables, and acceptance examples
- `quality-requirements.md` — safety, reliability, synchronization, and testing
- `architecture.md` — system context and responsibility boundaries
- `todoist-dependencies.md` — capabilities supplied by Todoist and replacement
  requirements for another backend
- `todoist-adapter.md` — concrete Todoist API, synchronization, and pagination
  contract
- `open-questions.md` — confirmation that no first-release decisions remain
- `out-of-scope.md` — possible future work explicitly excluded from the current
  application contract
- `decisions/` — accepted design decisions and their rationale

## Suggested reading order

1. `product.md`
2. `domain-model.md`
3. `command-interface.md`
4. `output-contract.md`
5. `behavior.md`
6. `quality-requirements.md`
7. `architecture.md`
8. `todoist-dependencies.md`
9. `decisions/`

The first four documents define the product, its language, its command
interface, and its output. The remaining documents explain detailed behavior,
verification, implementation boundaries, and rationale.

## Status vocabulary

- **Existing** — behavior of the current implementation that should be retained
- **Proposed** — desired behavior not yet confirmed in the implementation
- **Accepted** — an intentional design decision
- **Open** — requires a decision or further examples

All current contract documents are Accepted. Passing tests do not override
these documents. If implementation, tests, and design disagree, the
discrepancy must be resolved explicitly through an Accepted decision; the
implementation must not choose a different behavior silently.
