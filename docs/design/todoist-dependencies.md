# Todoist dependency inventory

Status: Accepted

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
- hiding-reason metadata stored inside task descriptions
- creation, update, and completion timestamps; task details specifically depend
  on each step's stable `added_at` and each current comment's posting timestamp
  to build a reverse-chronological history

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
advances the item to its next occurrence. Its Sync command can also undo the
latest occurrence by moving backward. It applies timezone and recurrence rules.

A replacement needs recurrence parsing, next/previous-occurrence calculation,
ordered completion and undo history, and daylight-saving behavior, or must omit
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

Todoist stores task comments and their original posting timestamps and supports
adding, editing, and deleting them. Separate activity events provide edit times.
Reports use the latest qualifying event with current surviving content. Steps
intentionally do not have comments in the `todo` domain.

A replacement needs comment identity, current content, original posting time,
edit/delete events, and survival behavior.

## Activity and completion history

Todoist supplies plan-limited activity events used to build cursor-bounded
reports, including task/step completed and uncompleted events and comment
add/update/delete activity. Completed object bodies come from the separate
completion-date endpoint in bounded date windows; normal sync aggregates alone
are insufficient.

This is a major backend dependency. A replacement needs an append-oriented
event model, completed-object lookup, recurring occurrence/undo pairing, and
retention capability reporting in addition to current task state. Current state
alone is insufficient to reconstruct operational reports.

## API mutation semantics

The Todoist API supplies command identifiers/idempotency behavior, authoritative
responses, retryable HTTP failures, rate-limit information, and direct
operations for task, comment, reminder, and project mutation.

A local backend would not need HTTP retry or rate-limit handling, but a remote
replacement would need equivalent failure, idempotency, and reconciliation
semantics.

## User-facing backend boundary

Todoist supplies API terminology, identifiers, HTTP errors, rate limits, and
account capability failures. The CLI is responsible for translating these into
the domain vocabulary used by `todo`.

A replacement backend must preserve the meaning of user-facing outcomes and
recovery guidance, but it need not reproduce Todoist's raw error text or API
object names. Backend-specific diagnostic details may be retained for
debugging without becoming the primary error message.

## User/account configuration

Todoist supplies natural-language date parsing (selected as English by this
CLI), the authoritative account IANA timezone, plan capabilities/retention,
stable account identity, and personal API-token authentication. Reports,
offset-free input, overdue buckets, and attention-day visibility all use that
account timezone, including during offline reads through its cached value.

A replacement must provide equivalent account identity, timezone, capability,
and retention contracts or make them explicit local configuration.

## Capabilities already owned locally

These are primarily `todo` behavior and can survive a backend replacement:

- actionable-list filtering and urgency ordering
- temporary hiding policy and parent/step validation
- configured hidden-category semantics
- selector matching and ambiguity handling
- CLI grammar and output
- help, diagnostic, and recovery conventions
- report formatting and cursor policy
- local configuration
- local cache and runtime locking concepts

Some of these currently encode Todoist identifiers and data shapes and would
need an adapter-neutral domain representation before replacing the backend.
