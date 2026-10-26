# Security and privacy boundary

Status: **Accepted**

todo-3 specification, revision 2. See [README](README.md).

### REQ-SEC-004 — Credential source precedence and personal-token boundary

Authentication must resolve once per command before its first network request.
A nonempty `TODOIST_TOKEN` environment value takes precedence over `[todoist] token`;
if the environment value is absent or empty, the nonempty configured value is used.
The initial setup wizard in REQ-INIT-003 may obtain the token through a hidden
terminal prompt when configuration is absent/empty and the environment has no
nonempty token. Other synchronizing commands without either source must fail
before network access.

Only one Todoist personal API token and one bound account are supported. `todo init`
must not accept a token option, perform OAuth, start an authorization flow, or
create/rotate credentials. Its initial setup wizard may save a token supplied
through hidden input into protected configuration only under REQ-INIT-003. It must
never copy an environment token into configuration. Token rotation is valid only when the resolved
token authenticates the already bound account; another account requires the
deliberate full-local-directory fresh start in REQ-INIT-002. Deleting only config
does not authorize account switching.

### REQ-SEC-005 — Restrictive permissions, symlink rejection, and secret redaction

`~/.todo` must be a real directory, not a symbolic link, with POSIX mode `0700`.
Configuration, binding, cursor, cache, unreported history, editor buffers,
and replacement candidates must be regular non-symlink files with mode `0600`.
Lock state must not make local
data readable outside the current user. Creation and replacement must set restrictive
permissions before writing content; an existing relevant symlink or permissive
sensitive-file/directory mode must fail before credentials are read or state is
mutated and identify the local repair. The narrowly scoped exception is the
explicitly confirmed mode repair of an owned real directory or owned real empty
config during the terminal wizard under REQ-INIT-003. It must precede credential
access; all other path-safety rejections remain unchanged.

The token must never appear in normal output, errors, retry messages, tracebacks,
cache, unreported history, binding, cursor, test fixtures, source control,
subprocess arguments, or persistent diagnostic files. HTTP errors and unexpected exceptions must redact
authorization headers and any resolved token substring before display.

No persistent application log or telemetry file may be created. Tests must use
synthetic credentials only and must check repository content and captured output for
credential leakage.

### REQ-SEC-007 — Managed-data privacy and local-user threat boundary

Only managed-root data and the minimal account/current-capability metadata allowed by
REQ-CACHE-005 may be retained or rendered, except for the transient first-use
project/category choices in REQ-INIT-003. Unreported history under REQ-CACHE-006
has the same privacy boundary and must not be exposed under another account/root
binding. Data authoritatively moved outside managed scope must be removed from
retained history as well as current cache. The wizard may display eligible personal
root names and direct-child category names for selection before a root is bound.
Retain only the final chosen configuration and ordinary initialized state; do not
serialize or log the discovery catalogue. Unrelated Todoist task, comment, reminder,
activity, collaborator, workspace, or non-choice project data obtained during
retrieval or scope validation must be discarded before disk serialization and
must not be printed or logged.

The security boundary protects against accidental disclosure through CLI output,
files with ordinary permissive modes, symlink substitution of controlled paths,
test artifacts, and HTTP diagnostics. It does not promise encryption at rest,
keyring integration, defense from root, defense from a compromised same user,
malicious kernel/filesystem protection, or multi-user account isolation beyond
POSIX permissions.
