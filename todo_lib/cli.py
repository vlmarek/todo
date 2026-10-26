"""Public composition boundary; workflow and transport hooks stay in Python tests."""
import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

from todo_lib import presentation as p
from todo_lib.adapter.transport import Transport, HTTPFailure, redact
from todo_lib.domain import DomainError, parse_boundary
from todo_lib.local import StateStore, LocalError, load_config
from todo_lib.syntax import parse, HelpRequest, render_help, UsageError, InputError
from todo_lib.workflows.sync import Synchronizer
from todo_lib.workflows.reads import ReadWorkflow, SelectionError
from todo_lib.workflows.capture import CaptureWorkflow
from todo_lib.workflows.moves import MoveWorkflow
from todo_lib.workflows.comments import CommentWorkflow
from todo_lib.workflows.lifecycle import LifecycleWorkflow
from todo_lib.workflows.init import Initializer
from todo_lib.workflows.report import Reporter


class _SafeStream:
    def __init__(self, stream, secrets):
        self.stream, self.secrets = stream, secrets

    def sanitize(self, text):
        safe = text
        for secret in self.secrets:
            safe = redact(safe, secret)
        return safe

    def write(self, text):
        safe = self.sanitize(text)
        written = self.stream.write(safe)
        return len(text) if written == len(safe) else 0

    def __getattr__(self, name):
        return getattr(self.stream, name)


def _run(argv=None):
    """Return a public status. No application state is touched for help/syntax.

    Context managers in dependencies own locks, terminal state and temporary
    files. This boundary never repairs, rolls back, clears or finalizes state.
    """
    secrets = [os.environ.get('TODOIST_TOKEN', '')]
    original = p.OriginalStreams.current()
    streams = p.OriginalStreams(original.stdin, _SafeStream(original.stdout, secrets),
                                _SafeStream(original.stderr, secrets))

    def diagnostic(text):
        try:
            streams.stderr.write('todo: ' + text.rstrip('\n') + '\n')
            streams.stderr.flush()
        except (OSError, ValueError):
            pass

    try:
        request = parse(sys.argv[1:] if argv is None else argv)
        if isinstance(request, HelpRequest):
            p.deliver(p.Document(render_help(request.command)), SimpleNamespace(pager=()), streams, 'help')
            return 0
        if request.command == 'report':
            for name in ('since', 'until', 'set-cursor'):
                if request.option(name) is not None:
                    try:
                        d_now = datetime.now(timezone.utc)
                        parse_boundary(request.option(name), d_now, 'UTC')
                    except DomainError as error:
                        raise UsageError('report', str(error), request.option(name)) from None
        store = StateStore()
        if request.command == 'init':
            def init_transport(token):
                # Register before discovery, wizard choices or success output.
                # Initializer remains the sole credential resolver.
                secrets.append(token)
                return Transport(token, stderr=streams.stderr)

            Initializer(store=store, stdin=streams.stdin, stdout=streams.stdout,
                                 stderr=streams.stderr,
                                 transport_factory=init_transport).run()
            return 0
        settings = load_config(store.root)
        # Keep configuration credentials out of all later diagnostics, even when
        # an environment credential takes precedence for HTTP.
        secrets.append(settings._token)
        read = request.command in ('now', 'waiting', 'someday', 'task', 'step',
                                   'category', 'search', 'lookup') or (
            request.command == 'comment' and not request.groups and not request.option('edit'))
        local_report = request.command == 'report' and (
            request.option('show-cursor') or request.option('set-cursor') is not None)
        transport = None
        if (not read and not local_report) or request.option('refresh'):
            credentials = settings.resolve_credentials()
            secrets.append(credentials.token())
            transport = Transport(credentials.token(), stderr=streams.stderr)
        if request.command == 'report':
            Reporter(transport, store, streams=streams).run(request)
            return 0
        synchronizer = Synchronizer(transport, store)
        options = dict(settings=settings, streams=streams)
        if read:
            result = ReadWorkflow(synchronizer, **options).execute(request, deliver=True)
        else:
            workflow = {'add': CaptureWorkflow, 'priority': CaptureWorkflow,
                        'rename': CaptureWorkflow, 'schedule': CaptureWorkflow,
                        'hide': CaptureWorkflow, 'unhide': CaptureWorkflow,
                        'move': MoveWorkflow, 'comment': CommentWorkflow,
                        'done': LifecycleWorkflow, 'reopen': LifecycleWorkflow,
                        'delete': LifecycleWorkflow}[request.command]
            result = workflow(synchronizer, **options).execute(request, deliver=True)
        return result.status if hasattr(result, 'status') else 0
    except UsageError as error:
        diagnostic(str(error))
        return 2
    except SelectionError as error:
        try:
            p.deliver(error.document, SimpleNamespace(pager=()), streams, 'diagnostic')
        except (OSError, ValueError):
            diagnostic('could not write complete output')
        return 1
    except (LocalError, DomainError, HTTPFailure, InputError, OSError) as error:
        diagnostic(str(error))
        return 130 if getattr(error, 'status', None) == 130 else 1
    except KeyboardInterrupt as error:
        diagnostic(str(error) or 'interrupted; stopped without rollback or mutation replay')
        return 130
    except Exception:
        # Unexpected exception messages and tracebacks may contain credentials,
        # provider bodies or editor contents. Do not serialize them.
        diagnostic('unexpected internal failure; stopped without mutation replay')
        return 1


def main(argv=None):
    """Keep even failures during error reporting inside the public boundary."""
    try:
        return _run(argv)
    except KeyboardInterrupt:
        status, message = 130, 'interrupted; stopped without rollback or mutation replay'
    except Exception:
        status, message = 1, 'unexpected internal failure; stopped without mutation replay'
    try:
        sys.stderr.write('todo: ' + message + '\n')
        sys.stderr.flush()
    except (Exception, KeyboardInterrupt):
        pass
    return status
