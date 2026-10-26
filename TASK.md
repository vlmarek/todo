# todo-3 implementation assignment

The complete Accepted design in `docs/design/` is the product authority. The
operator controls intended behavior. `TASK_GRAPH.yaml` revision TODO3-PLAN-001
assigns the complete first release in one final stage; nothing is deferred.
Design, tasks and graph remain revisable through preparation. Workers use their
recorded inputs; a later initialized run adopts changes only through the runner's
supported revision workflow. The external runner owns live orchestration state.
Do not create an in-repository run-state file or modify frozen planning inputs.

This is a fresh implementation: the initial repository contains accepted design
revision 2, provider evidence and planning inputs, and contains no application or
test implementation. Historical todo-2 references establish provenance only.
Do not inspect or copy sibling implementations, previous test suites, local user
data, runtime assignments or hidden evaluators. No migration is requested.

Implement the smallest direct solution satisfying owned requirements and consumed
interfaces. Keep one implementation path for shared rules and aliases. Do not add
speculative behavior, abstractions, guarantees, dependencies or test obligations.
Unnecessary implementation or test complexity is a review defect even if checks
pass. Report graph defects, missing inputs or concrete provider contradictions;
do not conceal them with guessed wire fields, skipped tests or weakened contracts.

`COMPONENTS.yaml` describes proposed capability contracts, inputs, results and
errors. Provider tasks create documented concrete Python APIs in their declared
modules. Consumers read those completed dependency modules/docstrings and focused
tests before implementation; they do not invent alternate types or rely on another
worker's transcript. The proposed package is `todo_lib`, copied unchanged beside
the executable root launcher `todo`. Each task creates importable test packages inside its owned suite. T01 owns
the top-level tests package; T04 and T08 own the adapter/workflow package
initializers, and T16 owns the delivery package initializer. Initializers must not
import future modules. Module decomposition within an owned path remains delegated. Domain code does no I/O. HTTP wire shapes are governed by the
retained upstream bytes, not the proposed Python API or synthetic fixtures.

All runtime code uses Python 3.11 standard library. Eventual implementation and
acceptance use the runner at `/home/neuron/Documents/ai-automated-runner`, with
Linux/amd64 CPython 3.11 in a pinned Docker image invoking Codex directly. Execution
setup must supply that image, tzdata and GNU less for bounded pager acceptance;
these planning files do not establish environment readiness. GNU less remains an
optional user-provided runtime tool, with no default pager. No pip/uv/SDK runtime,
packaging system, generated bundle or installer belongs in this product.

Automated checks must isolate HOME, environment, credentials, HTTP, clocks,
editors/pagers/terminals and signals as consumed. Use synthetic secrets and no
uncontrolled network or real Todoist requests. Test dependencies are standard
library only. Test-only controlled transport hooks must not become public endpoint
or test-mode configuration. Independent endpoint-shaped fixtures cite retained
source locations and inspection date; a fake must reject meaningful wrong
requests rather than mirror whatever the implementation emits. Never import or
execute retained upstream material as application code.

Each task has a focused unittest command with nonzero discovery. Create its named
suite as part of the task and fail missing required suites or required skips.
Domain/adapter/workflow tests can run before the final launcher; no task is allowed
to require unfinished unrelated work. Workers run directed focused checks and
expand them for relevant dependency concerns. The runner performs broad acceptance
on integrated subjects; task check references do not order a worker to repeat the
complete suite. Broad reruns need a changed subject or concrete evidence gap.

`scripts/check`, introduced by T16, checks launcher/shebang/imports/syntax and runs
the complete current offline unittest suite once, without generated repository
state. `scripts/verify-clean`, introduced by T17, records full Git status, calls
`scripts/check` exactly once, then adds distinct unchanged copied-runtime/PATH
probes outside the source tree, bounded real-less evidence and artifact/secret
checks, all in temporary directories. Verification script self-tests use tiny
synthetic suites and never recursively launch the full application suite.
Completion requires installed-entry-point evidence and the full offline suite.

The cheap after-merge gate is `git diff --check`. After integration,
`integrated-complete` is deferred until T16 is available and executes
`scripts/check`. Once executable `scripts/verify-clean` exists from T17, that
pre-final gate performs only hygiene; `final-delivery` runs verify-clean and the
full suite once on the final subject. The same final-delivery ID supplies task,
integration, stage and project roles through runner-supported check sharing.
An earlier integrated run covers a different pre-audit subject. No wrapper or test
may relaunch complete suites merely to satisfy another role label. Focused task
checks remain separate, small evidence for their assignment.

T01–T15 and T18 have distinct expected write paths. Shared interfaces are read
through dependencies, not jointly edited by parallel workers. T16 follows all
producers and may repair demonstrated integration defects across runtime/tests;
T17 follows T16 and may make demonstrated acceptance/coverage repairs across the
declared components. No task may change the frozen design, graph, component map, TASK.md,
provider-contract notes or prepared contract-map ledger. Report a required
protected-input correction to Planning. Runtime scheduling and concurrency are
configured externally; the graph declares semantic prerequisites only.

Execution evidence goes in `docs/implementation/acceptance-evidence.md` under T17,
with observed subjects, commands, results and limitations. Do not modify the
protected `contract-map.md` or relabel test passes as independent review/live
provider verification. A manual disposable-account smoke is documentation for the
operator, never an automated runner action.
