"""Isolated invocation of the real CLI with synthetic transport and local state."""
from contextlib import ExitStack
from io import StringIO
import os
import sys
from unittest.mock import patch
from todo_lib import cli
from todo_lib.workflows.sync import Synchronizer
from todo_lib.workflows.report import Reporter
from tests.support import capture


def invoke(case, argv, transport=None, now=capture.NOW, output=None, error=None, input=None, environ=None):
    out = output if output is not None else StringIO()
    err = error if error is not None else StringIO()
    with ExitStack() as stack:
        stack.enter_context(patch.object(sys, 'stdin', input if input is not None else StringIO()))
        stack.enter_context(patch.object(sys, 'stdout', out))
        stack.enter_context(patch.object(sys, 'stderr', err))
        stack.enter_context(patch.dict(os.environ, {'TODOIST_TOKEN': 'secret', 'TERM': 'dumb', **(environ or {})}))
        stack.enter_context(patch.object(cli, 'StateStore', return_value=case.store))
        factory = stack.enter_context(patch.object(cli, 'Transport', return_value=transport))
        stack.enter_context(patch.object(cli, 'Synchronizer', side_effect=lambda wire, store:
            Synchronizer(wire, store, clock=lambda: now)))
        stack.enter_context(patch.object(cli, 'Reporter', side_effect=lambda wire, store, **kw:
            Reporter(wire, store, clock=lambda: now, **kw)))
        status = cli.main(argv)
    return status, out.getvalue(), err.getvalue(), factory


