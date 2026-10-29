# Named timezones in attention and absolute reminders — revision 15

Status: **Accepted**

## Agreement and precedence

The operator approved a timezone name at the end of each attention-date or
absolute-reminder argument, including recurring expressions. They approved keeping
an existing recurrence when moving one occurrence, and showing both account and
schedule timezones in details and scheduling receipts. They rejected a blanket
requirement for an explicit clock time: keep the existing local/Todoist parsing
split and let Todoist normalize delegated expressions. After discussing short-code
ambiguity, they approved passing CET/CEST and other abbreviations to Todoist
without an application-defined abbreviation mapping. The complete resulting scope
was confirmed with "yes"; the later instruction explicitly requested updating the
design documentation. Actual instructions and question context are retained in
the external Design handoff, separately from this interpretation.

These are successor obligations for new and follow-up work. Earlier definitions,
accepted assignments and evidence remain unchanged. Narrow precedence is:

| Successor | Replaced or extended scope |
| --- | --- |
| REQ-SCHED-017 | REQ-SCHED-012/013 and REQ-SCHED-015's input grammar, input-timezone selection and delegated parsing; REQ-CLI-024/033/037's corresponding help and alias surfaces. REQ-DOM-012 and REQ-LOCAL-005 continue governing the account timezone, except that an explicit input zone supplies the interpretation of that individual scheduling value. |
| REQ-SCHED-018 | Clarifies named-zone recurrence and one-occurrence moves under REQ-SCHED-012 and REQ-SCHED-015. |
| REQ-OUT-025 | Extends only scheduling values in selected-item TPL-DETAIL and scheduling/creation receipts under REQ-OUT-015/020/021/022 with the second-timezone fragment. Other output, including REQ-OUT-023/024 item rows, retains its current formats. |
| REQ-VERIFY-033 | Adds distinguishing outcomes using the existing offline isolation and representative-coverage policy. |

### REQ-SCHED-017 — Per-value named timezones and hybrid scheduling parsing

Attention and absolute-reminder arguments accept an optional final IANA location
timezone, such as Europe/Prague, America/New_York or Asia/Tokyo, or UTC. Keep the
whole expression in one shell argument, with the existing separated/equals scalar
spellings. Extend every existing surface accepting attention or --reminder-at:
canonical scheduling, applicable creation forms, task/step noun-action forms and
the existing --at/--due/--schedule aliases. Do not absorb selectors into the date
argument or change existing creation grouping and option applicability. Help must
teach the same syntax on those surfaces.

Examples of the new syntax:

```console
todo schedule 'Team meeting' --at '2026-11-12 09:00 America/New_York'
todo schedule 'Team meeting' --at 'tomorrow 09:00 America/New_York'
todo schedule 'Team meeting' --reminder-at 'Friday 08:30 Asia/Tokyo'
todo schedule 'Team meeting' --at 'every Monday at 09:00 America/New_York'
todo schedule 'Team meeting' --reminder-at 'every Monday at 08:30 Europe/London'
```

Each argument owns its timezone. Attention and several absolute reminders can use
different zones in the same command. An omitted timezone keeps the existing
account-timezone behavior; a reminder does not inherit another argument's zone.
Neither the shell/host timezone nor a preceding option changes this default.
Relative --reminder offsets retain their existing before-due meaning and grammar.

Extract and validate an explicit location-zone suffix locally. An unknown location
zone fails clearly before writes rather than silently becoming the account zone.
Resolve locally supported expressions in that supplied zone, using the same one
command-time reference. This includes a local ISO wall date-time such as
2026-11-12 09:00 followed by the named zone, instead of requiring a numeric offset
for that form. Preserve existing explicit-offset/Z input and precise instants.
The local grammar need not become a general natural-language parser.

Today, tomorrow, weekdays and calendar-unit arithmetic use the supplied zone when
interpreting that individual expression. For example, at 2026-10-29T00:30:00Z,
tomorrow is October 29 in America/New_York and October 30 in Europe/Prague.
Elapsed minutes/hours remain elapsed durations; calendar arithmetic retains the
existing local-wall-time, month-clamping and business-day semantics in the chosen
zone. Existing locally detected DST ambiguity/nonexistence fails before writes,
with explicit-offset input available to specify the intended instant. Stored
precision and the accepted command-time precision tolerance remain unchanged.

For other expressions, pass the expression to Todoist's English parser with the
explicit timezone field when one was supplied. Splitting the zone from the scalar
must preserve the remaining date/recurrence wording; do not translate or invent a
rule or substitute a guessed numeric offset. Existing restrictions on unresolved
expressions still apply when an operation requires a locally resolved pre-write
comparison, including hiding and relative-reminder eligibility. A zone name alone
does not make an unresolved expression locally known. No extra remote parsing or
freshness request is introduced.

Short codes such as CET, CEST, CST and EST remain part of the original expression
sent to Todoist through the existing unresolved-expression path. Do not define
application abbreviation-to-offset or abbreviation-to-city mappings, and do not
interpret a short code locally merely because the installed timezone database
accepts it as a legacy key. This does not promise that Todoist accepts every code,
or that its result has a particular fixed offset or recurrence zone. Reconcile
and display actual returned scheduling data; provider rejection is an error.

Do not add a blanket rule requiring an explicit clock token whenever a timezone
is supplied. Attention may normalize to a date-only value; retain that actual
date-only result without inventing midnight, a timed deadline or a persistent
clock-zone property. Let Todoist normalize delegated expressions. Absolute
reminders still require a timed result under REQ-SCHED-015: locally known date-only
reminder input fails before writes, while an accepted but unsuitable provider
result follows the existing nonzero partial-failure rules, preserving accepted
remote work and reporting actual outcomes without rollback.

The account binding remains the single default-timezone authority. An explicit
input zone is per-schedule information, not an account/configuration change.
Urgency buckets, hiding/visibility days, parent/step comparisons, reports, cursors
and ordinary account-local displays continue using their existing account-based
rules after input has been resolved. No timezone flag, new default setting or
report-boundary grammar is introduced.

### REQ-SCHED-018 — Named-zone recurrence and single-occurrence moves

New recurring attention and absolute-reminder expressions with an explicit named
zone retain that zone as part of the recurring schedule. A timed expression such
as every Monday at 09:00 America/New_York follows 09:00 in that zone as its offset
changes across DST. Preserve the authoritative recurring wording, language,
timezone and floating/fixed semantics rather than storing only the first firing's
numeric offset. Todoist remains responsible for recurrence parsing, normalized
state, advancement and notification delivery; no local recurrence engine or live
delivery guarantee is added. A provider-normalized date-only attention recurrence
stays date-only and does not acquire an invented clock-time guarantee.

A nonrecurring date expression used to move the current occurrence of an already
recurring task changes only that occurrence. Resolve its requested instant in the
supplied input zone, while preserving the existing recurring expression, language
and recurrence timezone for later occurrences. For a task repeating at 09:00 New
York time, --at 'tomorrow 09:00 Europe/Prague' moves the next occurrence to the
requested Prague instant; it does not turn future repeats into Prague-time events.
The input zone and retained recurrence zone have different roles in this case.
Do not introduce a separate persisted last-input-timezone field for presentation.

Supplying a new recurring expression may replace the repeating pattern and its
timezone through the existing provider-parser path. Omitting a new explicit zone
retains the established behavior for such inputs. Unrelated mutations preserve
the existing schedule and metadata. Task-attention changes without reminder
options preserve all reminders, including their independent timezones and stable
identities. Existing keep, replacement consent, exact local equivalence/no-op and
authoritative reconciliation rules remain; a shared first instant is not proof
that two recurring schedules or timezone semantics are equivalent.

### REQ-OUT-025 — Account and schedule timezones in details and scheduling receipts

In the selected task/step's detail scheduling values and scheduling/creation
receipts, retain the existing account-local value first. When an exact attention
or absolute reminder has a retained named schedule timezone different from the
account timezone, append one parenthesized rendering of that same instant in the
schedule timezone. Apply this independently to attention and each absolute
reminder, including previous/resulting or retained schedules already printed by
the receipt. Do not add unrelated fields to receipts that do not display schedules.
Do not mistake an absolute reminder's timezone for its owner's attention timezone.

The appended fragment is exactly:

```text
 (YYYY-MM-DD HH:MM:SS IANA_TIMEZONE)
```

Include the full date on both sides where the existing account-side representation
contains it, so a day crossing remains unambiguous. For the same named zone as the
account, omit the duplicate. For a floating, date-only or otherwise unzoned value,
retain its current representation without fabricating an original timezone. Use
the retained schedule zone returned by authoritative reconciliation, including
when Todoist parsed a short-code input. Do not echo unverified input as if it were
accepted metadata. Moving one recurring occurrence displays the retained schedule
zone, rather than inventing another persisted zone for the last entered expression.

For an account timezone of Europe/Prague, this exact timed-attention value is:

```text
2026-11-12 15:00:00 Europe/Prague (2026-11-12 09:00:00 America/New_York)
```

In TPL-DETAIL, place the parenthesized source-zone value immediately after the
existing actual attention date/time, before its existing middle-dot/countdown
suffix. For an absolute reminder, place it immediately after that reminder's
existing actual date/time, before any recurrence suffix. Keep existing recurrence,
relative-reminder wording, order, streams, color policy and color-stripped text
equivalence. This fragment changes presentation, not the schedule's instant.

Compact now/waiting rows, recursive Steps, search/someday and ambiguity candidates
keep their existing account-timezone presentation, without this second-zone
suffix. Reports, cursor displays, comment/completion timestamps, selection prompts
and reminder-removal previews retain their existing formats. An unresolved preview
continues showing the actual supplied expression, including its timezone, as
awaiting Todoist resolution; it is not an accepted scheduling receipt.

### REQ-VERIFY-033 — Distinguishing timezone scheduling outcomes

Establish representative offline evidence for named-zone attention and independent
absolute reminders through the supported shared scheduling surfaces. Distinguish
supplied-zone interpretation from account/host interpretation, including one case
where tomorrow differs between zones; keep omitted-zone behavior unchanged. Use
one representative local wall date-time and a delegated recurring expression with
its explicit timezone, plus short-code forwarding without a locally invented
mapping. Retain meaningful invalid-zone and locally ambiguous/nonexistent-time
failures, with no writes for locally detected errors.

Distinguish a named recurring pattern from a fixed first-occurrence offset across
a representative DST transition. Distinguish a one-occurrence move in another
input zone from changing the existing recurring pattern/timezone. Cover reminder
independence and applicable keep/removal-confirmation behavior through shared
evidence, rather than multiplying every option spelling and test layer.

Verify dual-timezone detail/receipt values, a calendar-date crossing, omitted
duplicate zones, and unchanged compact views. Retain provider-normalized date-only
attention and timed-absolute-reminder requirements, including actual accepted/
rejected/unknown and partial-failure distinctions where provider parsing is used.
Planning chooses focused tests, representative public/copied evidence and exact
commands under the existing isolation policy. No automated live account or new
provider-research gate is introduced. Synthetic fixtures establish forwarding and
response handling; they do not establish Todoist's live abbreviation interpretation,
notification delivery or future recurrence advancement.

## Evidence, boundaries and Planning handoff

The retained original API v1 evidence is
external/todoist/upstream/api-v1.openapi.json, with its original retrieval date and
checksum in external/todoist/manifest.json. The Due dates tag documents fixed named
timezones for both tasks and reminders, explicit due.string plus due.timezone,
and the timezone's role in calculating recurring iterations. The Sync tag's Add/
Update item and reminder commands consume that due contract; ReminderDueAttribute
and the separate reminder endpoints provide additional published examples.
These are provider facts, separate from this application's chosen CLI syntax and
validation. Original source bytes and accepted historical interpretations remain
unchanged. Reuse this evidence; no provider snapshot replacement was requested.

The Design discussion also inspected public Todoist scheduling documentation and
IANA guidance. It found no explicit Todoist CET/CEST mapping in the inspected
documentation or retained API specification. That is an evidence limit, not proof
of rejection. Numeric mappings used by other software are not Todoist guarantees.
The agreed product behavior is forwarding and reporting actual normalization;
precise short-code acceptance/interpretation remains provider-dependent.

An offline exploration using the existing Python timezone helper established a
09:00 New York to 15:00 Prague conversion on 2026-11-12, the differing tomorrow
dates above, and refusal of ambiguous/nonexistent New York wall times. This was
feasibility evidence, not implementation acceptance or a live provider probe.

The initial code baseline already retains provider timezone/recurrence metadata,
uses a shared attention parser for absolute reminders, and distinguishes local
from provider parsing. Planning owns exact parser/suffix boundaries, metadata
plumbing, request conformance, recurrence-preserving occurrence updates,
reconciliation and renderer/caller adaptations, test organization and any necessary
compatible persistence representation. It must inspect current consumers and
preserve all accepted assignments through supported successor work. Existing
numeric-offset input must not silently acquire a different instant; handling of
redundant combined offset/name spellings is delegated within that boundary.

This is one coherent scheduling capability; no architectural redesign or separate
research stage is prescribed. No new account timezone authority, configuration,
general date/recurrence parser, abbreviation dictionary, history policy, report
behavior, synchronization policy or network preflight is requested. Existing
credential/scope safety, cached selection, remote outcome classification,
per-file publication, report finalization and precise ordering remain binding.
There is no unresolved product decision in this scope. Technical conformance and
provider behavior have the evidence limits above. The Design handoff is
uncommitted and authorizes no plan change, application implementation or execution.
