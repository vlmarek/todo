# Command interface

Status: Initial outline

This document will define the complete public CLI. The forms below record the
parts established so far; omitted commands still require documentation.

## Work views

```console
todo now
todo now --all
todo now --refresh
todo task SELECTOR
```

## Progress and completion

```console
todo comment TASK COMMENT
todo done ITEM
todo reopen ITEM
```

## Creation and maintenance

```console
todo add CATEGORY TASK [STEP ...]
todo add step TASK STEP [STEP ...]
todo rename ITEM NEW_NAME
todo delete ITEM
todo category
```

## Attention and reminders

`wait`, `due`, and `schedule` are equivalent aliases.

```console
todo wait [--hide] [--reminder OFFSET ...] ITEM DATE
todo due [--hide] [--reminder OFFSET ...] ITEM DATE
todo schedule [--hide] [--reminder OFFSET ...] ITEM DATE

todo wait ITEM clear
todo wait --reminder clear ITEM
```

The equivalent `due` and `schedule` clearing forms are also accepted.

Supplying a date without `--hide` removes the item's own hiding policy.
Supplying `--hide` enables it. Clearing the item removes attention, recurrence,
reminders, and its own hiding policy.

One or more supplied `--reminder OFFSET` arguments replace the complete
existing reminder set. Repeating the option defines multiple reminders in the
replacement set. `--reminder clear ITEM` removes the complete set without
changing the attention value.

## Reporting

```console
todo report
todo report --final
```

## Selection

Selectors may match tasks or steps as allowed by the command. If a selector is
ambiguous in an interactive terminal, the command displays matching choices
and asks the user to select one. A non-interactive mutating command must refuse
to guess.

An exact title match does not take precedence over other matching results. For
example, selector `Deploy` remains ambiguous when both `Deploy` and
`Deploy staging` match, and both are presented for selection.

Task and step selectors are case-insensitive. This does not change category
matching, which remains case-sensitive.

## Mutation output

After a successful attention or reminder change, print previous values when
present and print the resulting values. Do not print successful-change output
until Todoist has accepted the mutation.

Warnings and errors go to stderr. Normal results and successful change details
go to stdout.
