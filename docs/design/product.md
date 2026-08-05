# Product definition

Status: Proposed

## Purpose

`todo` maintains a trustworthy, prioritized view of work, records progress as
work happens, and turns that history into a categorized weekly report.

Todoist is the source of truth for tasks. It provides synchronization, phone
access, and notifications. The CLI provides a workflow and presentation
optimized for daily terminal use.

The configured root Todoist project is currently `Oracle`. Its child projects
are treated as work categories. The root project name is configurable.

## Primary workflow

1. Run `todo now` to see actionable work ordered by urgency.
2. Choose and perform work.
3. Record progress with `todo comment TASK COMMENT`.
4. Keep work accurate using commands such as `add`, `done`, `rename`,
   `reopen`, `delete`, and date/reminder operations.
5. Run `todo report` to preview the report period.
6. Run `todo report --final` to produce the final report and advance the
   report cursor.

## Goals

- Make common workflows easy to discover and predictable to use.
- Make interaction helpful: output should confirm what happened, and errors
  should explain what failed and how to recover when a valid recovery is known.
- Make the next work to consider visible and give a useful indication of
  relative urgency.
- Keep the normal actionable list small enough to be usable.
- Never hide an item beyond a date on which it requires attention.
- Preserve progress information needed for weekly reporting.
- Group work by configurable categories representing fields of work.
- Allow tasks to be refined into steps, each with its own priority and
  attention date.
- Work with Todoist so that tasks can be viewed and changed on a phone and
  reminders can produce phone notifications.
- Permit read-only use without network access through a local cache.
- Keep the command vocabulary and choices during capture small.

## Guiding principles

- Use the same language and interaction rules for the same concepts throughout
  the CLI.
- Give each operation one canonical command form. Compatibility aliases may
  remain, but help and examples should teach the canonical form first.
- Optimize the common successful path for few decisions and little required
  syntax.
- When a command cannot proceed, identify the affected item or setting, explain
  the violated rule, and suggest a valid next action when one is known.
- Helpfulness does not authorize guessing an ambiguous target, silently
  changing unrelated state, or hiding a failure.
- Todoist is authoritative for task data.
- A task describes an outcome; steps may refine the work and carry their own
  scheduling information.
- The interface need not classify why a date exists. A date may represent a
  deadline, meeting, follow-up, planned work, or recurring occurrence.
- Visibility is a separate choice expressed by `--hide`.
- Errors that could modify the wrong item or conceal urgent work must fail
  before mutation.
- A command expressing a state transition must fail when the selected item is
  not in the required source state. Treating an already-satisfied transition as
  success can conceal a mistaken selection or command.
- More generally, a mutation whose complete proposed result equals current
  state must fail as a likely user mistake rather than report success.
- The design favors the actual personal workflow over general-purpose Todoist
  client behavior.
- Prefer the simplest implementation that satisfies the established workflow,
  safety rules, and observable behavior. Do not add state reconstruction or
  automation without a demonstrated need.
- Feature completeness is not a goal by itself. Do not implement uncommon
  mutations or Todoist quirks merely for symmetry when they add complexity and
  are not part of the normal workflow.
- Decisions may be revisited when sustained usage demonstrates a missing
  workflow; speculative future needs do not require implementation now.
- Validate external capabilities and structural objects only when the requested
  operation depends on them. Avoid unrelated preflight checks on every command.

## Scope

Only tasks inside the configured root Todoist project are considered. Its
child projects provide dynamic categories. Steps inherit their parent task's
category.

One or more categories can be configured as hidden categories. `Someday` is a
typical hidden category but is not hard-coded by name.

## Non-goals

- Eliminating all need to learn the task model
- Guessing the user's intent when a command or selector is ambiguous
- Providing suggestions that have not been validated as applicable
- Replacing Todoist as the task system of record
- Managing unrelated Todoist projects
- Multi-user workflow or permissions
- Making every Todoist feature available from the CLI
- Inferring whether a date semantically means blocked, deferred, scheduled, or
  deadline

## Failure priorities

From most harmful to least harmful:

1. Failing to show an urgent item
2. Omitting completed work or progress from a report
3. Advancing the report cursor without successfully producing the report
4. Modifying the wrong ambiguously matched item
5. Losing or duplicating Todoist data
6. Missing a configured phone reminder
7. Showing extra non-urgent work in `todo now`
8. Leaving the user unable to understand or recover from a validly rejected
   command
