# todo

A Python standard-library CLI for personal Todoist work, nested steps, comments,
scheduling and reports. Verified target: Linux/amd64, CPython 3.11. Docker is the
build/verification environment; the installed CLI needs no Docker or Python packages.

Copy the executable and **entire sibling module tree** into a directory on PATH:

```sh
mkdir -p "$HOME/.local/bin"
cp -p todo "$HOME/.local/bin/todo"
cp -R todo_lib "$HOME/.local/bin/todo_lib"
export PATH="$HOME/.local/bin:$PATH"
todo help
todo init
```

Use an empty destination for a new installation, or replace the whole existing
`todo_lib` tree together with the matching launcher while no todo processes run.
Keep `todo` executable. Do not copy tests or install dependencies. `python3` on
PATH must be CPython 3.11; account timezone data must be available. GNU less is
optional for users and required in the pinned verification image.

`todo init` guides terminal setup when configuration is absent or empty. A
populated configuration is validated and used without rewriting it. Run `todo now`
for saved work, `todo --refresh now` to retrieve current work, and `todo help COMMAND`
for exact grammar and aliases. Reads use saved state unless refresh is requested.

See [configuration, backup and recovery](docs/user/operations.md), the
[explicitly user-run disposable-account smoke](docs/user/smoke.md), and
[observed acceptance evidence](docs/implementation/acceptance-evidence.md).

Offline release verification is `./scripts/verify-clean`: one complete
`scripts/check` suite, separate unchanged copied-runtime probes, real-less PTY
checks, and entry/end Git status and artifact checks. It uses temporary local state,
synthetic tokens and controlled transport only. It never runs the live smoke.
