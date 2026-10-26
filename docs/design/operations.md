# Initialization, backup and recovery

Status: **Accepted**

todo-3 specification, revision 2. See [README](README.md).

### REQ-INIT-005 — First initialization and structural provisioning

```console
todo init
```

When configuration is missing or empty, initialization first runs the terminal
setup wizard under REQ-INIT-003. That wizard may discover account/project/category
values through read-only Todoist requests before the complete configuration exists.
It must validate local path safety, credentials, and locally present authoritative
state before discovery. With populated configuration, the existing validation path
remains: configuration syntax, required settings, credentials, path types,
permissions, and locally present state must pass before any network request.

In either path, the complete configuration and locally present state must pass
validation before any Todoist mutation. Init must synchronize account identity,
account timezone, current capabilities under REQ-SYNC-021, projects, labels, and
the state needed to validate scope before provisioning.

Root discovery must examine active top-level projects by exact case-sensitive
configured name. Zero matches creates one personal root; one match is reused only
when it is unshared and personally owned; multiple matches or a sole shared/team
match fail without creating a competitor. Each `default_sections` name must reuse
one unique case-insensitive direct-child match or create the missing personal child;
case collisions or invalid hierarchy fail. Init must provision the `waiting` label
if absent. `hidden_from_now` names alone do not provision categories.

After provisioning, init must obtain full-plus-incremental current state, validate
the managed model, capture one binding instant, and prepare binding, cache, timezone,
unreported history under REQ-CACHE-006, and a cursor at that instant under
`REQ-INIT-002`. First initialization may start with empty, explicitly incomplete
history; exhaustive archive retrieval is not an initialization prerequisite.
Ordinary commands must never
provision structural objects.

Remote provisioning is idempotent but not transactional. A failure after Todoist
accepted one creation must report that accepted object and allow an explicit rerun
to reuse it and provision only remaining objects.

### REQ-INIT-008 — Read-only managed-task preflight before provisioning

Every initialization mode, including first-use wizard continuation, populated-config
init and repeat init, must validate the existing managed task
state in the selected target account before its first Todoist provisioning mutation.
Apply the existing local validation, target-account authorization, root-selection,
stable-binding, and hierarchy rules from REQ-INIT-005, REQ-INIT-002, REQ-INIT-003 first. This preflight
must use authoritative read-only retrieval under REQ-SYNC-013, including the
full-plus-incremental rule for initial/replacement state, rather than trusting the
offline cache or validating only projects and labels.

Where the selected root already exists, validate live tasks and steps in its
existing managed scope using the current API mapping, including REQ-SYNC-016,
and the existing domain invariants. Missing structure that init is permitted to
create is not itself a preflight failure: a nonexistent root has no existing
managed tasks, and missing configured categories or the `waiting` label must not
prevent validation of objects that do exist. Do not publish a prospective binding,
cache, or report cursor merely to perform preflight. Historical backfill and report
eligibility checks are not prerequisites for this live-task validation.

Preflight requires the current Sync resources under REQ-SYNC-013, not activity
history under REQ-SYNC-025. It must not request or require `activity` through
`/sync`, or fetch `/activities` as a prerequisite for initialization. A valid
full-plus-incremental response without `activity` must pass retrieval validation.
Validated `activity_log=false` or `activity_log_limit=0` capabilities must not
block initialization; their report restrictions remain under REQ-REPORT-009.

If retrieval is incomplete, fails, or exposes a managed-item mapping or invariant
violation, stop with status 1 before creating any root, category, or label. Identify
preflight as the failed phase and describe the field/expected type or violated
invariant. Distinguish missing fields from explicit null and wrong-type values.
Use a managed object ID when necessary to identify the affected object under the
existing output/privacy rules; never dump payloads, credentials, or unrelated data.
For invalid remote data, explain that correction is required before rerunning;
do not imply that retry alone fixes it. Mapping valid current-contract data must
not instruct the operator to alter a legitimate Todoist task to satisfy a wrong
application field assumption.

A wizard configuration already saved after confirmation remains saved on preflight
failure under REQ-INIT-003. Existing binding and cursor remain authoritative and
unchanged. Once preflight passes, provision only missing authorized structure and
retain full-plus-incremental post-provisioning validation and staged publication
under REQ-INIT-005, REQ-INIT-002. Preflight is not a transaction or a guarantee against
concurrent remote changes. Failures after accepted remote mutations retain the
existing partial-failure reporting, no-rollback, and explicit idempotent rerun rules.

For example, reusing Oracle with valid existing tasks containing `checked: false`
must succeed without an `is_completed` field, preserve the tasks, and make them
available to `todo now` according to the existing visibility rules. With the same
root but a managed task missing `checked`, init must fail preflight before creating
an otherwise missing category or `waiting` label. An empty account must still be
able to initialize its confirmed new structure.

The same populated-root path must accept documented floating/fixed timed
`due.date` values and account metadata changes under REQ-SYNC-021, REQ-SYNC-013. Valid
unrelated comments/reminders must be discarded before managed validation, including
types the product does not support. Shared/Inbox/workspace roots must fail the
documented project eligibility check before provisioning. Adapter assumptions or
unsupported managed features must be identified accurately; they are not evidence
that legitimate remote data is malformed or that retry alone repairs the adapter.

### REQ-INIT-002 — Stable binding, manual fresh start and cursor recovery

Subsequent `todo init` validates the bound account and stable root/category IDs;
renames retain identity. A token authenticating another account fails before
provisioning or mutation. Repeat init within a valid binding succeeds, provisions
only missing configured structure and preserves the existing cursor and unreported
history. It must not reset the report boundary to the current time.

There is no `--rebind` option or in-application account-switching workflow. For a
deliberate fresh start, stop `todo` processes, optionally back up local data, delete
the entire `~/.todo` directory and run `todo init` with the desired account/token.
Deleting only `config` does not remove an existing binding or authorize switching.
The documented full-directory reset discards configuration, binding, cursor, cache
and unreported history, leaves Todoist data unchanged and creates a new initial
report boundary on the next successful init. Unreported local observations can be
lost; no migration, inactive profile, undelete or automatic recovery is included.

Before init makes a Todoist mutation it rejects invalid existing authoritative
local state. A disposable cache cannot hide a binding or cursor error. Once a
binding exists, a missing or corrupt cursor requires explicit `report --set-cursor`
under REQ-REPORT-013; unsafe/unreadable paths first require their ordinary local
file/permission correction. Init never invents a replacement boundary.

Write and validate all prospective files as restrictive same-directory candidates.
Include unreported history in identity/publication association. Binding is the
final publication point: cache, history and the initial cursor are published first,
binding last. Per-file atomic replacement is not a multi-file transaction. Failure
before binding replacement leaves the old binding or no binding. Detect mixed
account/root/publication state and reject it, with explicit init rerun or manual
consistent-state restoration as applicable. Preserve recoverable pending history;
do not guess account/cursor values or add a transaction journal or rollback.

### REQ-INIT-003 — Terminal first-time configuration wizard

`todo init` must support starting with no `~/.todo` directory. It must also start
setup when `~/.todo/config` is missing or is an owned, real regular file of zero
bytes, including an empty file created by `touch`. A populated configuration must
never be overwritten, merged, or replaced by the wizard: it follows normal init
validation, with concrete repair instructions on failure. Whitespace-only or
malformed populated files are not considered empty.

The wizard requires both stdin and stdout to be interactive terminals under
REQ-CLI-032. Otherwise setup fails with status `1`, explains that `todo init` must
be rerun in a terminal, and creates or changes no local files or remote data.
`--yes` is not an init option and cannot bypass wizard interaction, permission-
repair confirmation or final setup confirmation.
Help remains available without configuration or network access. Commands other
than init do not run setup; missing configuration must identify `todo init` as the
first-use recovery command.

#### Local safety and permission repair

Before credential input or discovery, inspect paths without following symlinks.
Create a missing `~/.todo` directory owned by the current user with mode `0700`.
For an existing owned, real directory or owned, real empty config file with an
incorrect mode, show its path, current mode, and required mode and offer an
explicit confirmation to set directory mode `0700` or config mode `0600`.
Refusal stops setup before credentials are read and before network access. Never
change ownership, replace an unexpected type, follow a symlink, or repair binding,
cursor, cache, populated configuration, or unrelated paths through this exception.
Those unsafe states retain the rejection and concrete-repair behavior of
REQ-SEC-005. Acquire the ordinary fail-fast initialization lock under REQ-LOCAL-002
before reading coordinated state or discovering/provisioning remote structure.

#### Credential input and discovery

Use a nonempty `TODOIST_TOKEN` without prompting for a token and without copying
its value into configuration. Otherwise explain the personal API token requirement
and request a nonempty token through an input method that hides typed and pasted
characters. If input cannot be hidden, fail instead of accepting an echoed secret.
No token command-line option, credential-creation flow, OAuth, or token rotation is
introduced. The single resolved token is used for discovery and subsequent init.

Discover eligible active, unshared, personally owned top-level Todoist projects
through read-only requests. Present their names as choices, allowing the user to
select an existing root or enter a new root name. Offer `Work` as the suggested new
name when no existing root is chosen. Show enough non-secret context to distinguish
choices; stable identities remain internal. Selecting an existing project preserves
that identity and must not silently resolve duplicate configured names. Ambiguous
same-name roots retain the existing failure rule in REQ-INIT-005; discovery is not
permission to adopt an ambiguous root or create a competitor.

After a root is selected, offer its eligible existing direct-child category names,
preserving their spelling/case, as the initial `default_sections` list. If a new root
is chosen or no existing categories are found, offer `engineer, manager, someday`.
Explain that these are work categories represented by direct-child projects under
the managed root, rather than Todoist's within-project sections. Allow the user to
accept or edit the root and category suggestions. Re-discover categories if the
selected root changes. An empty or incomplete discovery response caused by network,
authentication, or response failure must never be treated as an empty account and
must not trigger fallback creation. Existing invalid hierarchy or case collisions
retain the normal validation failures; the wizard does not repair Todoist data.

Explain `hidden_from_now` as local policy for categories omitted from the normal
work view. Offer `someday` as its default and allow editing or an explicitly empty
list. Todoist supplies available category names, but does not supply this local
policy. Explain exact-case matching and flag a hidden name that matches no proposed
or existing category: it has no effect and does not create a category. Require the
user to review that fact rather than silently change names or add categories.
Keep report-warning and color defaults from REQ-CONFIG-002; no extra wizard pages
for those optional settings are required.

Existing binding/account/cursor rules in REQ-INIT-002 remain binding even if config
is missing or empty. Setup cannot implicitly switch accounts or root identities,
invent a cursor, or repair corrupt authoritative state. Discovery with another
account fails while the existing binding remains. Wizard confirmation does not
substitute for deleting all local state and explicitly initializing afresh.

#### Confirmation, publication, and failure

Validate the proposed INI values under REQ-CONFIG-002 and explain invalid entries
so the user can correct them before proceeding. Present a final summary containing
the root, category list, hidden list, existing versus proposed-new structure, config
path, credential source without the token, and the fact that confirmation saves
configuration and continues Todoist initialization. Require explicit confirmation
before saving config or starting remote provisioning. Permission repairs have
separate earlier confirmations and are not silently bundled into this step.

On confirmation, publish a complete mode-`0600` INI configuration using the
same-directory candidate and atomic-publication rules of REQ-LOCAL-003. Persist a
pasted token in `[todoist] token`; leave that setting empty or omitted when the token
came from the environment. Never overwrite a config that became populated during
setup. Continue the normal initialization in the same invocation; only the existing
REQ-INIT-005, REQ-INIT-002 workflows may provision structure and publish binding/cache/cursor.

Declining final confirmation or reaching EOF exits `1`; handled SIGINT exits `130`.
Before config publication, no token or proposed configuration is persisted and no
Todoist mutation is attempted. Clean temporary candidates and release the lock.
A safely created directory/lock and explicitly confirmed permission changes may
remain; explain changes already made rather than claim that nothing changed.

If initialization fails after config publication, retain the complete configuration,
identify its path, distinguish saved configuration from successful initialization,
and give the applicable recovery action. A normal rerun uses that config without
repeating the wizard. Remote accepted/unknown/unattempted work and existing binding
publication/cursor recovery still follow REQ-CLI-032, REQ-LOCAL-006, and REQ-INIT-002.
Success must identify the config path and initialized root/categories and give
`todo now` as the next normal workflow command, without exposing credentials.

#### Acceptance examples and isolated verification

- From a nonexistent `~/.todo`, terminal setup with a synthetic token and no eligible
  remote projects offers `Work`, `engineer, manager, someday`, hidden `someday`;
  confirmation saves protected INI and finishes ordinary init in the same command.
- Selecting an existing eligible root offers its existing direct-child names;
  accepting them reuses the structure and adds no fallback categories merely because
  the fallback names differ. A root with no children offers the category fallback.
- Nonempty `TODOIST_TOKEN` skips token input and its value is absent from saved INI.
  Hidden input, errors, summaries, and handled exceptions never disclose the token.
- An owned empty `0644` config offers confirmed repair to `0600` and then setup.
  Declining repair, foreign ownership, symlinks, and wrong types fail before credential
  access or discovery; a populated config is never rewritten or permission-repaired
  by the wizard.
- Redirected stdin or stdout fails unchanged when setup is needed. Cancellation
  before publication saves no token/config and makes no remote changes; discovery
  failure never provisions fallback structure. Provisioning failure retains a valid
  saved config for an explicit rerun and reports any accepted remote creations.
- Verification uses isolated temporary homes, synthetic credentials, controlled
  terminal/input/echo behavior, and fake Todoist responses under REQ-VERIFY-*.
  It must not read a developer's real `~/.todo`, use real credentials, or depend on
  a live Todoist account. Exact prompt prose and the input/adapter decomposition are
  delegated; the behavior, stream rules, privacy, and failure boundaries above are
  binding.
### REQ-OPS-001 — Manual backup, restore and fresh-start documentation

Provide a POSIX-safe manual procedure for backing up `~/.todo/config`,
`binding.json`, `report-cursor` and the separate unreported history under
REQ-CACHE-006, identifying its implementation path. Stop `todo` processes first;
copy the authoritative files as a consistent account/root set into a user-chosen
0700 directory and preserve 0600 file modes. Current cache, locks and unpublished
temporary files are reconstructable/runtime data, not required backup material.

Restore rejects symlinks, restores a matching account/root set with the required
permissions and validates it using an explicit read-only refresh. A missing or
corrupt cursor can be set explicitly under REQ-REPORT-013. Do not mix account
histories, infer a report boundary, or claim an older backup contains later work.
An old cursor can repeat report content; a newer cursor can skip it. A preview or
failed final report does not authorize discarding unreported history.

Document the deliberate fresh-start procedure in REQ-INIT-002: delete the entire
local directory after stopping processes, then run `todo init`. Explain local
configuration, pending-history and report-boundary loss, and that remote Todoist
data is unchanged. Back up first if that local information is wanted.

No backup/restore command, `doctor`, rebind command, automatic rollback, transaction
repair or corruption-recovery facility is included. Ordinary command errors give
the failed condition and an applicable correction when known; they need not
continue collecting all independently detectable problems.
