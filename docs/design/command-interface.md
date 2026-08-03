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
todo done ITEM [TEXT]
todo reopen ITEM
```

Completing a parent task that still has open steps requires interactive
confirmation to complete all open steps first. Without explicit affirmative
confirmation, no item is completed.

Optional `TEXT` is supported when the selected item is a task and is stored as
a task comment prefixed with `Done: `. It is not valid for a step.

`todo reopen ITEM` changes only the selected task or step. Reopening a parent
does not reopen any of its completed steps.

## Creation and maintenance

```console
todo add CATEGORY TASK [STEP ...]
todo add step TASK STEP [STEP ...]
todo rename ITEM NEW_NAME
todo delete [--yes] ITEM
todo category
```

`todo delete ITEM` requests interactive confirmation before mutation. Only an
explicit affirmative response authorizes deletion. `--yes` skips the prompt
and is required for non-interactive deletion. Cancellation, end of input, or a
non-interactive invocation without `--yes` leaves the item unchanged and exits
nonzero.

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

Quoting controls selector structure:

- A single argument such as `todo task "deploy staging"` is one phrase and
  matches that contiguous phrase.
- Multiple arguments such as `todo task deploy staging` are independent terms.
  Every term must match, but the terms may occur in any order and need not be
  contiguous.

Shell quoting therefore affects matching semantics and is not merely a way to
preserve spaces in one equivalent selector string.

Candidate type depends on the command form:

- `todo task SELECTOR` searches parent tasks only. A matching step is not
  returned as the selected item.
- An implicit top-level selector such as `todo review` searches tasks and steps
  as independent candidates. A step may match even when its parent task title
  does not contain the selector.

If an implicit selector matches both tasks and steps, all matching candidates
participate in normal ambiguity handling.

Normal item selection matches titles only. Task descriptions, waiting metadata,
and comments do not make a task or step match a selector. A dedicated search
command may have broader searchable fields, but does not change targeting
semantics for mutation and inspection commands.

## Mutation output

After a successful attention or reminder change, print previous values when
present and print the resulting values. Do not print successful-change output
until Todoist has accepted the mutation.

Warnings and errors go to stderr. Normal results and successful change details
go to stdout.
