# GNU less: retained evidence and application boundary

This is provider evidence and authored interpretation, not another requirement.
The binding behavior is REQ-OUT-018, REQ-PLAT-001 and REQ-VERIFY-020.

## Upstream facts

The original upstream version-590 manual source is retained unchanged in
[upstream/less-590.txt](upstream/less-590.txt), retrieved from the official
[release archive](https://www.greenwoodsoftware.com/less/less-590.tar.gz) on
2026-10-25. [manifest.yaml](manifest.yaml) records the archive member, exact
checksum and byte count. This is a consumed-interface baseline, not a request
to install version 590 or a claim about the newest release.

Relevant source locations are the COMMANDS entries for forward/backward movement,
G and q; OPTIONS entries for -R, -F, -K and initial + commands; and ENVIRONMENT
VARIABLES entries for LESS, LESSANSIENDCHARS and LESSANSIMIDCHARS. The manual
states that -R passes ANSI color sequences and assumes normal color at the start
of each line. Cross-line color state alone therefore cannot establish correct
multiline rendering. LESS can supply options and initial commands; command-line
options override matching environment options. These are provider facts, not a
requirement to expose a pager configuration interface.

The official [FAQ](https://www.greenwoodsoftware.com/less/faq.html), under
“Why does -r cause display problems?”, corroborates -R for color pass-through.
The retained manual supplies the offline source for verification.

## Application interpretation and remaining evidence

GNU less is the operator's example, not the required/default pager. The current
agreement configures an optional external command via `[main] pager`, such as
`less -FR`, across read-only result views except final reports. There is no pager
by default and no terminal-height check. GNU less -F supplies fit behavior, and -R
displays the application's ANSI colors. Other configured commands receive their
own arguments unchanged; todo does not inject GNU-less-specific flags.

The application renders the existing view, including its chosen colors, before
feeding the configured pager. Color selection uses the original stdout terminal
and existing flags/environment rather than the child's input pipe. The external
command owns fit/navigation; the app owns invocation eligibility, complete rendered
data, stderr, normal exit versus failure/SIGINT outcomes and complete-output
fallback. Final reports always write directly and retain existing cursor safeguards;
non-final reports never change the cursor, including on early normal quit.

A disposable local PTY probe of /usr/bin/less version 590, with an 8-row terminal,
40 sample rows and -R, observed the first row initially, reached the last via G,
retained red SGR bytes, and exited 0 on q. A follow-up stdin-fed PTY probe of
`less -FR` checks automatic successful exit on a short sample and navigable color
output with normal q exit on a long sample. Those observations are inherited source-project evidence; no probe was
rerun in todo-3. They are not a host-only prerequisite for implementation. These probes do not establish production
configuration/color routing, failure/interrupt recovery or pinned-image availability.
Those remain bounded Planning and implementation responsibilities; no comprehensive
pager conformance suite or live Todoist dependency is required.
