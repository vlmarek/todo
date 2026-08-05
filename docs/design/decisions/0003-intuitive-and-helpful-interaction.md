# 0003: Intuitive and helpful interaction

Status: Accepted

## Context

`todo` is used repeatedly during daily work. A command can be technically
complete yet still impose unnecessary cognitive load through inconsistent
syntax, unclear feedback, backend terminology, or errors that provide no
recovery path.

“Intuitive” is subjective unless translated into observable design rules. It
must also not weaken the existing protection against ambiguity, accidental
mutation, or concealed urgent work.

## Decision

Optimize common workflows for discoverability, consistency, and actionable
feedback.

- Teach one canonical form for each operation.
- Apply the same interaction rules to the same concepts.
- Confirm resulting state after successful changes.
- Explain failed operations in domain vocabulary.
- Suggest a next action only when it is known to be safe and applicable.
- Never guess an ambiguous target or silently repair unrelated state in the
  name of convenience.

## Consequences

- Help and workflow-level acceptance tests are part of the product contract.
- Compatibility aliases may remain but are secondary in documentation.
- Presentation and diagnostic behavior should be implemented through shared
  policies rather than independently in each command.
- Some rejected commands require more informative errors.
- Usability must be reviewed through representative workflows in addition to
  automated tests.
