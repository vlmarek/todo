"""Owned comment creation and locked editor reconciliation.

CommentWorkflow.execute accepts normalized syntax requests or argv. Reads delegate
to ReadWorkflow; mutations return documents and ordered remote outcomes. A local
publication failure stops the sequence without changing remote classifications.
The buffer codec is pure: timestamps are display-only, stable IDs are authority.
"""
from dataclasses import dataclass, replace
import os
import re
import signal
import subprocess
import tempfile
import termios

from todo_lib import domain as d
from todo_lib import presentation as p
from todo_lib.adapter.commands import Gateway, Operation, Outcome, Result, _Observed, _proof
from todo_lib.adapter.current import Current
from todo_lib.adapter.transport import HTTPFailure, redact
from todo_lib.local import LocalError, command_argv, exclusive_lock, load_config
from todo_lib.local.safety import read_bytes
from todo_lib.syntax import parse
from todo_lib.syntax.input import Cancelled, Interrupted, prompt
from .reads import ReadWorkflow, select_child, select_title
from .sync import SyncError, SyncInterrupted


class CommentError(LocalError):
    pass


class _CommentObserved(_Observed):
    """Retain transport evidence for this mutation as well as JSON receipts."""
    def __init__(self, transport, operation):
        super().__init__(transport)
        self.operation = operation
        self.failures = []

    def request(self, *args, **kwargs):
        try:
            return super().request(*args, **kwargs)
        except HTTPFailure as error:
            # A rejected reconciliation read says nothing about the mutation.
            if args[:2] == ('POST', '/sync') and kwargs.get('command_uuids') == (self.operation.uuid,):
                self.failures.append(error)
            raise

    def mutation_issues(self):
        # HTTPFailure diagnostics are already safe and attributable to this
        # mutation. Gateway retains their classification, but not their text.
        issues = [str(error) for error in self.failures]
        # Recover only this UUID's valid rejection message, including receipts
        # found by read-only reconciliation. Never expose raw response fields.
        for response in self.responses:
            statuses = response.get('sync_status')
            rejection = statuses.get(self.operation.uuid) if isinstance(statuses, dict) else None
            if (isinstance(rejection, dict) and type(rejection.get('error_code')) is int
                    and isinstance(rejection.get('error'), str) and rejection['error']):
                issues.append(redact(rejection['error'], getattr(self.transport, '_secret', '')))
        return tuple(dict.fromkeys(issues))


def ordered_comments(comments):
    """Known times oldest first, then unknown times, with stable-ID ties."""
    return tuple(sorted(comments, key=lambda c: (
        c.added_at is None, d.instant_key(c.added_at) if c.added_at is not None else 0, c.id)))


_EXISTING = re.compile(r'\[id: ([^\s\[\]]+) posted: ([^\[\]\r\n]+)\]')


def _header_like(line):
    return line.startswith(('[id:', '[new')) or (line.startswith('[') and line.endswith(']'))


def encode_buffer(comments, timezone='UTC'):
    blocks = []
    for comment in ordered_comments(comments):
        body = '\n'.join('\\' + line if line.startswith('\\') or _header_like(line) else line
                         for line in p.edge(d.incoming_text(comment.body)).split('\n'))
        blocks.append(f'[id: {comment.id} posted: {p.compact(comment.added_at, timezone)}]\n{body}')
    return '\n\n'.join((*blocks, '[new]\n'))


@dataclass(frozen=True)
class Change:
    kind: str
    comment_id: str | None = None
    body: str | None = None
    timestamp: object = None
    position: int | None = None


@dataclass(frozen=True)
class EditPlan:
    changes: tuple[Change, ...]
    delete_all: bool = False


def decode_buffer(text, originals):
    """Validate every observable block before computing edits/adds/deletes.

    Only one empty final new block is ignored. Removing an interior header joins
    its remaining text to the preceding body, exactly as the saved file says.
    """
    originals = ordered_comments(originals)
    known = {c.id: c for c in originals}
    blocks, seen = [], set()
    for line in d.incoming_text(text).split('\n'):
        if line == '[new]':
            blocks.append((None, []))
        elif _header_like(line):
            match = _EXISTING.fullmatch(line)
            if match is None:
                raise CommentError('malformed or unknown comment header')
            identity = match[1]
            if identity not in known or identity in seen:
                raise CommentError('foreign or duplicate comment ID')
            seen.add(identity)
            blocks.append((identity, []))
        else:
            if not blocks:
                if line.strip():
                    raise CommentError('text before the first comment header')
                continue
            # A prefix is protective only before a backslash or header-like line.
            if line.startswith('\\') and (line[1:].startswith('\\') or _header_like(line[1:])):
                line = line[1:]
            blocks[-1][1].append(line)
    edits, additions = [], []
    retained = set()
    for index, (identity, lines) in enumerate(blocks):
        body = p.edge('\n'.join(lines))
        if identity is None and not body and index == len(blocks) - 1:
            continue
        unchanged = identity is not None and body == p.edge(d.incoming_text(known[identity].body))
        if not unchanged:
            d.validate_body(body)  # New text and emptied nonblank bodies stay strict.
        if identity is None:
            additions.append(Change('add', body=body))
        else:
            retained.add(identity)
            old = known[identity]
            if not unchanged:
                edits.append(Change('edit', identity, body, old.added_at, originals.index(old) + 1))
    deletions = [Change('delete', c.id, timestamp=c.added_at, position=i)
                 for i, c in enumerate(originals, 1) if c.id not in retained]
    return EditPlan(tuple(edits + additions + deletions),
                    bool(originals) and not retained and not additions)


@dataclass(frozen=True)
class CommentResult:
    document: p.Document
    snapshot: d.Snapshot | None = None
    now: object = None
    selected: object = None
    status: int = 0
    outcomes: tuple[p.CommentOutcome, ...] = ()
    operations: tuple = ()


class CommentWorkflow:
    def __init__(self, synchronizer, gateway=None, *, settings=None, streams=None, environ=None):
        self.synchronizer = synchronizer
        self.gateway = gateway if gateway is not None else Gateway(synchronizer.transport)
        self.settings = settings
        self.streams = streams or p.OriginalStreams.current()
        self.environ = os.environ if environ is None else environ

    def execute(self, request, *, deliver=False):
        if isinstance(request, (list, tuple)):
            request = parse(request)
        if request.command != 'comment':
            raise ValueError('not a comment command')
        if not request.groups and not request.option('edit'):
            return ReadWorkflow(self.synchronizer, settings=self.settings, streams=self.streams).execute(
                request, deliver=deliver)
        # Also validate programmatically constructed requests before any mutation.
        bodies = tuple(body for group in request.groups for body in group.values)
        for body in bodies:
            d.validate_body(body)
        if bodies and request.option('edit'):
            raise CommentError('editor conflicts with comment creation')
        root = self.synchronizer.store.root
        with exclusive_lock('comment edit' if request.option('edit') else 'comment', root):
            settings = self.settings or load_config(root)
            initial = self.synchronizer.read_local()
            snapshot = initial.snapshot
            color = p.Color.for_stdout(self.streams.stdout, request.option('color', 'auto'), slots=settings.colors)
            if request.parent:
                owner = select_child(snapshot, request.parent, request.selector, initial.now,
                                     streams=self.streams, color=color)
            else:
                owner = select_title(snapshot, request.selector, initial.now, target=request.target,
                                     streams=self.streams, color=color)
            editing = bool(request.option('edit'))
            if editing:
                originals = tuple(c for c in snapshot.comments.values() if c.item_id == owner.id)
                try:
                    saved = self._edit(encode_buffer(originals, snapshot.account.timezone))
                    plan = decode_buffer(saved, originals)
                    if plan.delete_all:
                        answer = prompt('Delete all shown comments? [y/N] ', stdin=self.streams.stdin,
                                        stdout=self.streams.stdout, stderr=self.streams.stderr, default='n')
                        if answer.lower() not in ('y', 'yes'):
                            raise Cancelled('comments unchanged')
                except (KeyboardInterrupt, Interrupted):
                    result = CommentResult(p.document(warnings='todo: comment editing interrupted'),
                                           snapshot, initial.now, owner, 130)
                else:
                    current = initial
                    result = self._apply(current, owner, plan.changes, editing=True)
            else:
                result = self._apply(initial, owner, tuple(Change('add', body=b) for b in bodies))
            if deliver:
                p.deliver(result.document, settings, self.streams, view_kind='mutation')
            return result

    def _edit(self, text):
        argv = command_argv(self.environ.get('VISUAL') or self.environ.get('EDITOR') or 'vi', 'editor')
        path = None
        try:
            fd, path = tempfile.mkstemp(prefix='comment-', suffix='.txt', dir=self.synchronizer.store.root)
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as buffer:
                os.fchmod(buffer.fileno(), 0o600)
                buffer.write(text)
            # Inherit terminal streams. subprocess restores child signal defaults;
            # its context cleans the child on interruption before buffer cleanup.
            terminal = None
            try:
                terminal = (self.streams.stdin.fileno(), termios.tcgetattr(self.streams.stdin.fileno()))
            except (AttributeError, OSError, ValueError, termios.error):
                pass
            try:
                result = subprocess.run([*argv, path], check=False)
            finally:
                if terminal is not None:
                    termios.tcsetattr(terminal[0], termios.TCSADRAIN, terminal[1])
            if result.returncode in (-signal.SIGINT, 128 + signal.SIGINT):
                raise KeyboardInterrupt
            if result.returncode:
                raise CommentError(f'editor exited with status {result.returncode}; comments unchanged')
            return read_bytes(self.synchronizer.store.root / os.path.basename(path)).decode('utf-8').replace('\r\n', '\n')
        except (OSError, UnicodeError) as error:
            raise CommentError('comment editor failed: ' + str(error)) from error
        finally:
            if path is not None:
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass

    def _execute_operation(self, operation, current, owner):
        # Retain the gateway's own attribution evidence across SIGINT in its
        # read-only reconciliation. Reuse its classifier, including UUID and
        # temporary-ID requirements; current text alone never proves acceptance.
        transport = self.gateway.transport if isinstance(self.gateway, Gateway) else None
        observed = _CommentObserved(transport, operation) if transport is not None else None
        if observed is not None:
            self.gateway.transport = observed
        try:
            result = self.gateway.execute(operation, before=Current(current.snapshot, current.state.sync_token, current_snapshot=current.state.current_snapshot,
                waiting_label_ids=current.state.waiting_label_ids, reminder_ids=current.state.current_reminder_ids),
                                          known_owners={owner.id: owner}, owner_id=owner.id)
            if observed is not None:
                result = replace(result, issues=tuple(dict.fromkeys((*result.issues, *observed.mutation_issues()))))
            return result, False
        except KeyboardInterrupt:
            if observed is None:
                raise
            outcome, target = _proof(operation, observed.responses)
            if outcome == Outcome.UNKNOWN and any(e.outcome == 'rejected' for e in observed.failures):
                outcome = Outcome.REJECTED
            return Result(outcome, operation, target_id=target,
                          evidence=tuple(('transport', e.outcome) for e in observed.failures) +
                                   (('command', operation.uuid, outcome.value),),
                          issues=observed.mutation_issues()), True
        finally:
            if observed is not None:
                self.gateway.transport = transport

    def _apply(self, current, owner, changes, *, editing=False):
        snapshot, now = current.snapshot, current.now
        outcomes, operations, accepted_bodies, diagnostics = [], [], [], []
        unavailable_bodies = []
        local_failure = None
        status = 0
        for index, change in enumerate(changes):
            reason, accepted, remote = None, False, None
            state = 'Failed'
            try:
                args = ({'item_id': owner.id, 'content': change.body} if change.kind == 'add' else
                        {'id': change.comment_id, 'content': change.body} if change.kind == 'edit' else
                        {'id': change.comment_id})
                op = Operation({'add': 'note_add', 'edit': 'note_update', 'delete': 'note_delete'}[change.kind], args)
                # The observer preserves definitive evidence if reconciliation
                # is interrupted; otherwise the in-flight outcome is unknown.
                try:
                    remote, interrupted = self._execute_operation(op, current, owner)
                except KeyboardInterrupt:
                    state = 'Unknown'
                    raise
                except (OSError, HTTPFailure) as error:
                    state = 'Failed' if getattr(error, 'outcome', None) == 'rejected' else 'Unknown'
                    raise
                operations.append(remote)
                accepted = remote.outcome == Outcome.ACCEPTED
                state = 'Accepted' if accepted else 'Unknown' if remote.outcome == Outcome.UNKNOWN else 'Failed'
                reason = '; '.join(remote.issues) or None
                if accepted:
                    if remote.after is not None and owner.id in remote.after.snapshot.items:
                        snapshot = remote.after.snapshot
                        owner = snapshot.items[owner.id]
                    if change.kind == 'add' and isinstance(remote.actual, d.Comment):
                        accepted_bodies.append(remote.actual.body)
                    if reason:
                        status = 1
                        diagnostics.append(reason)
                    if interrupted:
                        raise KeyboardInterrupt
                    # Always reconcile accepted work, including accepted outcomes
                    # with incomplete gateway evidence. Never retry the mutation.
                    current = self.synchronizer.reconcile_accepted_locked(remote)
                    if owner.id in current.snapshot.items:
                        snapshot = current.snapshot
                        owner = snapshot.items[owner.id]
                else:
                    if interrupted:
                        raise KeyboardInterrupt
                    status = 1
                    reason = reason or ('remote outcome unknown; do not replay the mutation' if state == 'Unknown'
                                        else 'remote operation rejected')
            except (KeyboardInterrupt, Interrupted) as error:
                status = 130
                reason = '; '.join(x for x in (reason, str(error) or 'interrupted') if x)
                if isinstance(error, SyncInterrupted):
                    local_failure = error.failure
                    diagnostics.append(str(error.failure))
            except (LocalError, d.DomainError, HTTPFailure, OSError) as error:
                status = 1
                reason = str(error)
                if isinstance(error, SyncError):
                    local_failure = error
                    diagnostics.append(str(error))
            # Accepted detail describes authoritative text only. Operational
            # failures belong to stderr even when the mutation was accepted.
            if accepted and reason and reason not in diagnostics:
                diagnostics.append(reason)
            outcome = self._outcome(change, state, None if accepted else reason,
                                    actual=remote.actual if remote is not None else None,
                                    position=index + 1)
            outcomes.append(outcome)
            if accepted and change.kind == 'add' and not isinstance(remote.actual, d.Comment):
                unavailable_bodies.append(outcome)
            if status:
                outcomes.extend(self._outcome(later, 'Not attempted') for later in changes[index + 1:])
                break
        if status:
            if local_failure is None and state in ('Accepted', 'Unknown'):
                diagnostics.append('Remote operation outcome: ' + state.lower() +
                    '; do not replay the mutation. Read-only recovery: todo --refresh now.')
            document = p.render_comment_edit(snapshot, owner, outcomes=outcomes)
            if not editing:
                # Ordinary creation retains arrow receipts, once per destination;
                # detailed nonaccepted operations remain on stderr.
                document = p.document(p.render_comment_bodies(snapshot, owner, accepted_bodies,
                                                              owner_identified=True).stdout,
                                      document.stderr)
                if unavailable_bodies:
                    details = p.render_comment_edit(snapshot, owner, outcomes=unavailable_bodies).stdout
                    document = p.document(document.stdout, document.stderr + '\n' + details)
            if diagnostics:
                document = p.document(document.stdout, document.stderr + '\n' + '\n'.join('todo: ' + x for x in diagnostics))
        elif editing:
            document = p.render_comment_edit(snapshot, owner,
                **{name: sum(c.kind == kind for c in changes) for name, kind in
                   (('added', 'add'), ('edited', 'edit'), ('deleted', 'delete'))})
        else:
            document = p.render_comment_bodies(snapshot, owner, accepted_bodies)
        return CommentResult(document, current.snapshot, now, owner, status, tuple(outcomes), tuple(operations))

    @staticmethod
    def _outcome(change, state, reason=None, *, actual=None, position=None):
        body = change.body if change.kind == 'add' else None
        if state == 'Accepted' and change.kind == 'add':
            body = actual.body if isinstance(actual, d.Comment) else None
            if body is None:
                reason = 'actual accepted body unavailable'
        operation = {'add': 'added', 'edit': 'edited', 'delete': 'deleted'}[change.kind] if state == 'Accepted' else change.kind
        return p.CommentOutcome(state, operation, body=body,
                                timestamp=change.timestamp, position=change.position or position, reason=reason)


def execute(request, synchronizer, **kwargs):
    deliver = kwargs.pop('deliver', False)
    return CommentWorkflow(synchronizer, **kwargs).execute(request, deliver=deliver)
