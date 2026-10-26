# Product definition

Status: **Accepted**

todo-3 specification, revision 2. See [README](README.md).

### REQ-PROD-004 — Personal Todoist workflow

`todo` must serve one person operating one explicitly bound personal Todoist
account from a terminal. Todoist is authoritative for tasks and supplies phone
and web access plus reminder delivery; the CLI supplies a daily workflow and a
categorized report optimized for terminal use.

The primary workflow is:

1. Run `todo now` to see actionable work ordered by urgency.
2. Inspect and perform work.
3. Record progress with comments on tasks or steps.
4. Capture and maintain work with the documented create, completion, reopen,
   rename, category/parent move, schedule, reminder, hiding, and deletion operations.
5. Preview the cursor-bounded report with `todo report`.
6. Produce it and advance the cursor with `todo report --final`.

Success means these documented initialization, daily-work, progress, external
Todoist-change, and weekly-report workflows work without wrong-target mutation
or incorrect report-cursor advancement. “Weekly” describes normal human cadence;
the user invokes reports manually and receives them on stdout.

The interface must use the same domain vocabulary and interaction rules for the
same concepts, teach one canonical form before aliases, identify accepted
changes, and give applicable recovery information without guessing intent or
silently repairing unrelated state.

The implementation must prioritize avoiding these failures, in order:

1. omitting an urgent item;
2. omitting completed work or progress from a report;
3. advancing the cursor without completely producing the report;
4. mutating an ambiguously selected wrong item;
5. losing or duplicating Todoist data;
6. missing a requested supported reminder;
7. showing extra non-urgent work in `todo now`;
8. rejecting a valid request without understandable recovery guidance.

### REQ-PROD-005 — Managed-root scope and complete first release

`todo` must manage only tasks inside one bound, unshared, personally owned
Todoist root project. The initial root name is explicitly supplied by configuration;
the terminal wizard offers existing roots and the fallback `Work` under REQ-INIT-003.
`Oracle` is a valid configured example, not an implicit initial root. Direct child
projects are dynamic work categories; tasks directly in the root, deeper project
hierarchies, cycles, and task descendants beyond depth 4 are invalid managed state.
A top-level task has depth 0; every descendant at depth 1 through 4 is a step
under REQ-DOM-009. This task-depth limit is separate from project nesting.

Configured hidden categories are omitted from the normal actionable view;
the wizard suggests `someday`, but neither that spelling nor the `Someday`
example is hard-coded as a hidden category. Every step inherits its root task's
category through its ancestor chain.

The first release is the complete Accepted `REQ-*` contract. There is no smaller
implicit MVP. Every documented compatibility alias is public syntax with the
same observable behavior as its canonical operation.

Beyond the expressly required applicable task/step action-alias parity in
REQ-CLI-033, general feature symmetry is not a requirement. The implementation must choose the
smallest direct behavior satisfying the Accepted contract and must not add
unrequested Todoist features, generalized workflows, speculative abstractions,
or hidden guarantees.
