# Todoist dependency inventory

Status: Initial inventory

This document identifies behavior and infrastructure currently delegated to
Todoist. Its purpose is to make the cost and capability loss of a future
non-Todoist backend visible.

## Authoritative durable storage

Todoist stores:

- tasks and direct steps with stable identifiers
- open and completed state
- titles and task descriptions
- task comments
- priorities
- project/category membership
- due/attention values and recurrence definitions
- reminders
- the `waiting` label used as the persisted own hiding policy
- creation, update, and completion timestamps

A replacement backend needs durable storage and stable object identity. The
local cache is not currently designed to be authoritative.

## Cross-device synchronization

Todoist synchronizes changes between the CLI, phone, web, and other Todoist
clients. It determines authoritative current state when different clients make
changes.

A local-only replacement would lose phone and web access unless it also
provides a synchronization protocol, authentication, remote hosting, conflict
handling, and mobile/web clients.

## Phone interface and notifications

Todoist provides the phone user interface and delivers relative reminder
notifications. The CLI stores reminder intent in Todoist but does not schedule
or deliver notifications itself.

A replacement needs a notification scheduler and delivery channel, plus a
phone application or integration, or must explicitly give up these features.

## Natural-language attention parsing

Todoist parses due strings that the local parser does not understand, including
natural-language and recurring expressions. It returns a normalized due object
containing the current occurrence, exact-time information, time zone, and
recurrence metadata.

A replacement must either implement an equivalent parser or restrict the
accepted attention grammar to expressions the CLI can parse locally.

## Recurrence engine

When a recurring task or step is completed, Todoist records the occurrence and
advances the item to its next occurrence. It applies time-zone and recurrence
rules.

A replacement needs recurrence parsing, next-occurrence calculation,
completion history, and daylight-saving/time-zone behavior, or must omit
recurring items.

## Reminder model

Todoist associates multiple relative reminders with a timed item, advances
them with recurring occurrences, and enforces account-plan limits and reminder
validity.

A replacement needs reminder persistence, validation, recurrence interaction,
scheduling, and notification delivery.

## Project hierarchy and categories

Todoist projects provide the configured root project and its dynamic child
categories. Moving or renaming projects determines current category membership.

A replacement needs category storage, hierarchy, rename/move behavior, and
stable category identity or an intentionally simpler category model.

## Task-tree behavior

Todoist stores parent/step relationships and defines cascade behavior for
completion, recurrence, deletion, and reopening. The design adds stricter CLI
validation but still relies on Todoist to execute individual task-tree
mutations.

A replacement must define and implement those persistence semantics directly.

## Comments and editing

Todoist stores task comments and their timestamps and supports adding, editing,
and deleting them. Reports use current surviving comments and their activity.
Steps intentionally do not have comments in the `todo` domain.

A replacement needs comment identity, content, timestamps, edit-as-replacement
semantics, and deletion behavior.

## Activity and completion history

Todoist supplies activity events used to build cursor-bounded reports,
including task and step completions and comment activity. It also retains
completed items in account history so they can be reopened or deleted.

This is a major backend dependency. A replacement needs an append-oriented
event/history model in addition to current task state. Current state alone is
insufficient to reconstruct weekly reports.

## API mutation semantics

The Todoist API supplies command identifiers/idempotency behavior, authoritative
responses, retryable HTTP failures, rate-limit information, and direct
operations for task, comment, reminder, and project mutation.

A local backend would not need HTTP retry or rate-limit handling, but a remote
replacement would need equivalent failure, idempotency, and reconciliation
semantics.

## User/account configuration

Todoist supplies user-level date language, time-zone context, account-plan
capabilities, and authentication. The CLI additionally uses the executing
machine's local time zone for reports and attention-day visibility.

A replacement must decide which settings become local configuration and how
time-zone changes affect recurrence, reminders, and reports.

## Capabilities already owned locally

These are primarily `todo` behavior and can survive a backend replacement:

- actionable-list filtering and urgency ordering
- temporary hiding policy and parent/step validation
- configured hidden-category semantics
- selector matching and ambiguity handling
- CLI grammar and output
- report formatting and cursor policy
- local configuration
- local cache and runtime locking concepts

Some of these currently encode Todoist identifiers and data shapes and would
need an adapter-neutral domain representation before replacing the backend.
