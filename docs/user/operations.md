# Configuration and local operations

The supported runtime is Linux/amd64 CPython 3.11 with standard-library modules
and system timezone data. No pip, SDK, package installation or Docker is needed
for installed use. Copy `todo` and the complete `todo_lib` tree together as shown
in [README](../../README.md). Help works without configuration or credentials.

`~/.todo` must be an owned real directory, mode 0700. Sensitive files must be
owned regular files, mode 0600; symlinks are refused. Ordinary reads do not repair
permissions. Missing/zero-byte configuration enters terminal-only `todo init`
setup; a populated configuration must already be valid. Minimal populated INI:

```ini
[main]
project=Disposable work
default_sections=Work,Personal
hidden_from_now=Personal
pager=less -FR

[report]
warn_limited_history=true
```

The root must be personal and eligible; init reuses
matching existing categories and the waiting label, creating missing structure
only after read-only preflight. Repeat init preserves valid binding, pending
history and report cursor. It observes actual edits/nulls and current ownership;
a later read omission does not discard pending context. Unsupported managed
features or invalid hierarchy require correction before init can succeed.

Set `TODOIST_TOKEN` privately in your shell or put `token=...` under `[todoist]`
in the protected config. Nonempty environment wins; empty environment falls back
to config. Never put tokens in command arguments, logs or version control. Wizard
token input is hidden; an environment token is not persisted. There is no default
pager. `pager` is direct argv parsed with shell-like quoting, without shell
expansion. `less -FR` is an optional example. Read views may page only with both
input/output terminals; final reports always write and flush directly. Use
`todo help` for color flags; `[colors]` accepts the documented Solarized slot names
`base01`, `base1`, `red`, `green`, `yellow`, `blue`, `magenta`, `cyan` as `#RRGGBB`.
Editor commands likewise use direct argv (`VISUAL`, then `EDITOR`).

## Backup a consistent set

Stop all todo processes first. Choose a **new**, private backup directory, outside
`~/.todo`. The authoritative set is `config`, `binding.json`, `report-cursor`, and
**`history.json`**, the separate pending/unreported history. Current `cache.json`,
locks and unpublished temporary files are reconstructable/runtime data. A preview
or failed final report never authorizes discarding history.

This POSIX-shell command uses Python 3.11 only for explicit path/type/mode checks
and copying. Substitute your own new destination. It refuses symlinks and unsafe
modes; it does not repair source data. Keep processes stopped for the whole copy.

```sh
python3.11 -B - "$HOME/todo-backup-chosen-name" <<'PY'
import os, pathlib, shutil, stat, sys
source = pathlib.Path.home() / '.todo'
target = pathlib.Path(sys.argv[1])
def checked(path, directory=False):
    s = path.lstat()
    assert s.st_uid == os.getuid(), 'wrong owner'
    assert (stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode)), 'unsafe path'
    assert stat.S_IMODE(s.st_mode) == (0o700 if directory else 0o600), 'unsafe permissions'
checked(source, True)
names = ('config', 'binding.json', 'report-cursor', 'history.json')
for name in names: checked(source / name)
target.mkdir(mode=0o700)  # existing file/directory/symlink fails
for name in names:
    shutil.copyfile(source / name, target / name)
    (target / name).chmod(0o600)
print('Saved consistent account/root set:', target)
PY
```

Do not mix files from different accounts, roots, publication generations or backup
dates. Backups contain secrets and private work. This procedure expects all four
files; if one is missing/corrupt, preserve the available bytes separately before
recovery rather than claiming a valid backup. An older backup cannot contain later
observations. An old cursor may repeat report content; a newer cursor may skip it.

## Restore and validate

Stop todo processes. Preserve the current directory separately if wanted; before
moving it, verify it is a real directory and that the chosen saved location does
not exist (including a dangling symlink). For example:

```sh
test -d "$HOME/.todo" && test ! -L "$HOME/.todo" &&
  test ! -e "$HOME/.todo-before-restore" && test ! -L "$HOME/.todo-before-restore" &&
  mv "$HOME/.todo" "$HOME/.todo-before-restore"
```

Restore to an absent `~/.todo`, refusing existing paths/symlinks and checking the
backup's directory/files before reading. Use the same backup directory as above:

```sh
python3.11 -B - "$HOME/todo-backup-chosen-name" <<'PY'
import os, pathlib, shutil, stat, sys
source = pathlib.Path(sys.argv[1])
target = pathlib.Path.home() / '.todo'
def checked(path, directory=False):
    s = path.lstat()
    assert s.st_uid == os.getuid(), 'wrong owner'
    assert (stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode)), 'unsafe path'
    assert stat.S_IMODE(s.st_mode) == (0o700 if directory else 0o600), 'unsafe permissions'
checked(source, True)
names = ('config', 'binding.json', 'report-cursor', 'history.json')
for name in names: checked(source / name)
target.mkdir(mode=0o700)
for name in names:
    shutil.copyfile(source / name, target / name)
    (target / name).chmod(0o600)
PY
todo --refresh now
```

The last command is the explicit **remote-read-only refresh** validating the
restored association against the authenticated account/root and rebuilding cache.
It publishes local observations but performs no remote mutation. Require success
before treating restoration as usable. If a missing/corrupt cursor blocks it,
choose an explicit known boundary using
`todo report --set-cursor '2026-10-20T00:00:00Z'` (substitute your intended instant,
confirm the warning), then refresh. Do not infer a boundary from cache/history or
use cursor setting as permission to delete pending history. `todo report
--show-cursor` displays the saved boundary without HTTP.

## Cache rebuild, failed publication, and fresh start

`todo --refresh --clear-cache now` deliberately deletes only disposable cache,
then retrieves a replacement. It retains binding, config, report cursor and
required `history.json`. Rebuild failure may leave no cache. Missing/corrupt/foreign
required history is an error; cache clearing never silently resets it. A cold
installation cannot reconstruct every previously observed completed step/comment
and must disclose incomplete retained history.

Publication is atomic **per file**, with binding last. Before the first successful
destination replacement, previous protected snapshot files remain unchanged
(unless cache was explicitly cleared). After any successful replacement, later
failure or interruption can leave individually complete old/candidate files in a
mixed set. The saved snapshot may be unusable. A new offline reader refuses an
inconsistent set; never accept it as a usable old snapshot. Preserve available
files, especially recoverable pending-history content. New observations may not
all have been saved. Do not replay an accepted or unknown mutation to fix local
publication. Later batch operations stop; remote acceptance remains truthful.

Where validation still permits it, `todo --refresh now` is an optional remote-read-
only recovery attempt. It must not complete or undo another recurring occurrence.
If association validation blocks refresh, manually restore a matching consistent
set and validate as above. First-init partial publication has the same per-file
completeness/refusal guarantees, but **rerunning init is not guaranteed to recover
every partial state**, including changed timezone with old unbound floating history.
A safe normal init rerun can reuse remotely accepted structure when local validation
allows it. A failed phase/nonzero result is not successful initialization.

For an explicit fresh start, stop processes, optionally back up wanted local
information, then delete the **entire** local directory and rerun init:

```sh
# Deliberate local data loss: confirm the directory and backup yourself first.
rm -r -- "$HOME/.todo"
todo init
```

This discards configuration, account/root binding, cache, pending history and
report cursor. Unreported observations may be lost. Successful init establishes a
new initial report boundary. Remote Todoist data is unchanged by local deletion;
init itself can provision missing authorized structure. Deleting config alone does
not authorize changing account/root. No automatic deletion, rollback, shared-store
repair, recovery command, backup/restore command, doctor or rebind facility exists.

Final reporting writes and flushes complete output before publishing its exact
fixed-end cursor, then cleans only covered history. Failure before cursor success
preserves the old cursor and pending data; failure/interruption during cleanup can
leave safe extra records without undoing finalization. Required ancestry for newer
pending work stays. Covered objects may disappear from local search/inspection
after cleanup. Copy/report timestamps preserve supplied fractional precision;
calendar/display/relative command calculations may use ordinary aware datetimes.
