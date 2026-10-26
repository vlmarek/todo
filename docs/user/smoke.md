# Optional live smoke — user run only

The runner never executes this procedure. It is an optional operator check against
Todoist, using a disposable personal account/root and ordinary successful actions.
Do not use production work, deliberately induce partial failures, or automate real
credentials. Automated failure evidence is isolated and offline.

Install the matching launcher/module tree first. In a terminal, choose a new empty
private HOME so your normal local binding is untouched. Keep its path for cleanup:

```sh
smoke_home=$(mktemp -d)
chmod 700 "$smoke_home"
export HOME="$smoke_home"
unset TODOIST_TOKEN
# Keep PATH pointing at your installed todo and CPython 3.11.
todo help
todo init
```

Enter the disposable account's token through hidden wizard input. Choose a new
personal root named `Todo smoke` and a category named `Work`, with no hidden
categories. Expected: init reports success and the root/category/waiting label are
created or safely reused. Record the account timezone and history capabilities.
Do not paste tokens or private contents into results.

Run these ordinary commands, observing receipts and resulting views:

```sh
todo now
todo add task Work 'Smoke parent'
todo add step 'Smoke parent' 'Smoke step'
todo rename 'Smoke parent' --to 'Smoke plan'
todo priority 'Smoke plan' P1
todo comment 'Smoke step' --comment 'Progress from CLI'
todo 'Smoke plan'
todo search 'Progress from CLI'
todo schedule 'Smoke step' --at 'tomorrow 15:00'
todo schedule 'Smoke step' --reminder 0m
todo waiting
todo done 'Smoke step' --comment 'Reviewed'
todo 'Smoke plan'
todo reopen 'Smoke step'
```

Expected: stable nested step under the renamed parent; own comment searchable;
priority change affects the selected parent independently. Scheduling uses the
account's local calendar/timezone; the zero reminder is shown at due. Reminder
creation requires the disposable account's advertised reminder capability. If it
is unavailable, record that limitation and omit the reminder command rather than
claiming it passed. Completion records progress and shows a checked nested step;
reopen restores the ordinary step and preserves comments. `waiting` accurately
shows the applicable hidden/waiting population (possibly empty).

In the Todoist web/mobile client, edit the step title to `Smoke external`, add a
comment `Progress from web`, and then complete that step while leaving `Smoke
plan` open. Run:

```sh
todo --refresh task 'Smoke plan'
todo search --all 'Progress from web'
todo report --show-cursor
todo report
todo report --show-cursor
todo report --final
todo report --show-cursor
```

Expected: explicit refresh observes external current truth and retains available
completed-step context/comments under the open parent. Coverage warnings are
honest; absent/unavailable provider history is not a full-history guarantee.
Preview lists eligible finished/progress/hidden work and leaves the cursor
unchanged. Final output succeeds directly and advances the cursor to its fixed
end; the next display shows the new boundary. An account lacking required history
capabilities may refuse reports explicitly; record this as unverified report smoke,
not a pass. Never finalize if you want to retain that local report boundary.

Record date, installed revision, Python/platform, timezone/capabilities, each
observed outcome and any omissions. This document supplies expected outcomes,
not observed live results. No live smoke has been run by automated acceptance.

Cleanup: in the disposable account's web UI remove only the `Todo smoke` root and
its test contents; remove a newly created waiting label only if you know it is
unused. Stop todo processes, retain any desired results/backup, and delete only
the saved disposable HOME:

```sh
# Verify this is the mktemp path from setup before deleting it.
rm -r -- "$smoke_home"
```

Exit the smoke shell to restore your normal HOME/environment. Local deletion loses
that smoke configuration/history/cursor; it does not remove remote data. Never
reuse this cleanup against your normal HOME or another account's root.
