"""Locked lifecycle transitions with exact bounded selection and no mutation replay.

LifecycleWorkflow(synchronizer, gateway=None).execute accepts argv or a parsed
request and returns LifecycleResult. Preview is always written before confirmation;
receipts are returned as a Document (and emitted per operation with deliver=True).
Selection/preflight errors propagate without mutation. Once mutation starts, results
record every accepted/rejected/unknown/unattempted operation, including local failures.
"""
from dataclasses import dataclass, replace

from todo_lib import domain as d, presentation as p
from todo_lib.adapter.commands import Gateway, Operation
from todo_lib.adapter.current import Current
from todo_lib.adapter.history import HistoryAdapter
from todo_lib.adapter.transport import HTTPFailure
from todo_lib.local import (History, LocalError, exclusive_lock, load_config,
                            merge_history, prepare_candidates)
from todo_lib.local.safety import read_bytes
from todo_lib.syntax import parse
from todo_lib.syntax.input import prompt, Cancelled, InputError
from .reads import choose, matches, title_candidates, recent_candidates, deletion_candidates
from .sync import SyncError, SyncInterrupted


@dataclass(frozen=True)
class LifecycleOperation:
    operation: Operation
    outcome: str
    result: object = None


@dataclass(frozen=True)
class LifecycleResult:
    document: p.Document
    operations: tuple[LifecycleOperation, ...]
    snapshot: d.Snapshot
    now: object
    status: int = 0
    failure: object = None

    @property
    def accepted(self):
        return tuple(o for o in self.operations if o.outcome == 'accepted')

    @property
    def unattempted(self):
        return tuple(o for o in self.operations if o.outcome == 'unattempted')


def _preview(snapshot, root, included):
    depths = d.subtree_depths(snapshot, root.id)
    offset = depths[root.id]
    return '\n'.join('  ' * (depths[i.id] - offset) + i.title +
                     (' [completed]' if i.completed else '')
                     for i in d.subtree(snapshot, root.id) if i.id in included)


def _recent_snapshot(synchronizer, result, hidden_names):
    """Discover bounded archived owners even when no known item disappeared.

    Current owners always win over historical object fields. Unknown ancestry is
    an explicit evidence failure, never inferred from an active GET 404.
    """
    s = result.snapshot
    adapter = HistoryAdapter(synchronizer.transport, timezone=s.account.timezone)
    items, occurrences, latest = dict(s.items), dict(s.occurrences), {}
    for category in sorted(s.categories):
        for record in adapter.completed(result.state.cursor, result.now,
                                        {'project_id': category}).records:
            at = record.occurrence.completed_at
            if not (d.instant_key(result.state.cursor) < d.instant_key(at) <= d.instant_key(result.now)):
                continue
            if record.item.category_id != category:
                continue
            old = latest.get(record.item.id)
            if old is None or d.instant_key(at) > d.instant_key(old.occurrence.completed_at):
                latest[record.item.id] = record
    for identity, record in latest.items():
        if record.deleted:
            continue
        if identity not in items and record.item.completed and not record.item.recurring:
            items[identity] = record.item
        if identity in items and (items[identity].completed or items[identity].recurring):
            occurrences.setdefault(record.occurrence.id, record.occurrence)
    snapshot = d.validate(replace(s, items=items, occurrences=occurrences), hidden_names)
    if snapshot != s:
        # These observations are needed even if selection is cancelled or a
        # different owner is deleted. Reconciliation reloads the store, so a
        # transient selection snapshot alone cannot protect the discoveries.
        comments = dict(snapshot.comments)
        for identity in sorted(items.keys() - s.items.keys()):
            for comment in adapter.comments(identity).records:
                if comment.item_id != identity or (comment.id in comments
                        and comments[comment.id].item_id != identity):
                    raise d.DomainError('incompatible historical comment ownership')
                comments[comment.id] = comment
        snapshot = d.validate(replace(snapshot, comments=comments), hidden_names)
        history = merge_history(result.history,
            History(snapshot, {identity: result.now for identity in latest if identity in items}))
        candidates = prepare_candidates(snapshot, replace(history, snapshot=snapshot),
            account_display=result.state.binding.account_display,
            sync_token=result.state.sync_token, synced_at=result.state.synced_at,
            hidden_names=hidden_names)
        _publish_discoveries(synchronizer.store, candidates)
    return snapshot


def _publish_discoveries(store, candidates):
    """Publish before mutation, with the same per-file failure facts as refresh."""
    paths = [store.root / name for name in ('cache.json', 'history.json', 'binding.json')]
    before = [read_bytes(path) for path in paths]
    try:
        store.publish_snapshot(candidates)
    except (LocalError, OSError, KeyboardInterrupt) as error:
        try:
            started = before != [read_bytes(path) for path in paths]
        except (LocalError, OSError):
            started = True  # Unknown bytes cannot prove preservation.
        available, permitted = False, False
        try:
            store.load_consistent_state(require_cache=False)
            permitted = True
            store.load_consistent_state()
            available = True
        except (LocalError, OSError):
            pass
        failure = SyncError('bounded discovery publication', error,
            publication_started=started, saved_state_available=available,
            refresh_permitted=permitted)
        if isinstance(error, KeyboardInterrupt):
            raise SyncInterrupted(failure) from None
        raise failure from error


def _recurring_preflight(snapshot, item, forward, hidden_names):
    # Validate all locally known policy/hierarchy/reminder facts. For the small
    # date-only rules with an unambiguous next day, also validate that prediction.
    # Other rules remain provider authority and are reconciled after acceptance.
    from datetime import timedelta
    d.validate(snapshot, hidden_names)
    attention = item.attention
    days = {'every day': 1, 'daily': 1, 'every week': 7, 'weekly': 7}.get(attention.rule.lower())
    if attention.kind == 'date' and days is not None:
        proposal = replace(attention, date_value=attention.date_value + timedelta(days=days if forward else -days),
                           raw_due=None)
        items = {**snapshot.items, item.id: replace(item, attention=proposal)}
        d.validate(replace(snapshot, items=items), hidden_names)


class LifecycleWorkflow:
    def __init__(self, synchronizer, *, gateway=None, settings=None, streams=None):
        self.synchronizer = synchronizer
        self.gateway = gateway or Gateway(synchronizer.transport, clock=synchronizer.clock)
        self.settings = settings
        self.streams = streams or p.OriginalStreams.current()

    def execute(self, request, *, deliver=False):
        if isinstance(request, (list, tuple)):
            request = parse(request)
        command = request.command
        if command not in ('done', 'reopen', 'delete'):
            raise ValueError('not a lifecycle command: ' + command)
        if command != 'delete' and request.option('yes'):
            raise d.DomainError('only delete accepts --yes')
        if command != 'done' and request.groups:
            raise d.DomainError(command + ' accepts no comment text')
        if len(request.groups) > 1 or any(g.kind != 'comment' for g in request.groups):
            raise d.DomainError('done accepts one --comment group')
        # Validate the complete list before synchronization, prompting or mutation.
        bodies = tuple('Done: ' + d.validate_body(body)
                       for group in request.groups for body in group.values)
        with exclusive_lock(command, self.synchronizer.store.root):
            settings = self.settings or load_config(self.synchronizer.store.root)
            state = self.synchronizer.refresh_locked()
            snapshot, now, cursor = state.snapshot, state.now, state.state.cursor
            if command in ('reopen', 'delete'):
                snapshot = _recent_snapshot(self.synchronizer, state, settings.hidden_from_now)
            d.validate(snapshot, settings.hidden_from_now)
            candidates = (title_candidates(snapshot, request.selector, target=request.target) if command == 'done'
                else recent_candidates(snapshot, request.selector, cursor, now, target=request.target) if command == 'reopen'
                else deletion_candidates(snapshot, request.selector, cursor, now, target=request.target))
            if request.parent:
                # Reopen/delete parent operands supply context, not a lifecycle
                # target: a known completed parent need not itself be recent.
                parents = (title_candidates(snapshot, request.parent) if command == 'done' else
                    tuple(sorted((i for i in snapshot.items.values() if matches(i.title, request.parent)),
                        key=lambda i: (snapshot.categories[i.category_id].name.lower(),
                            tuple(a.title.lower() for a in d.ancestors(snapshot, i.id)),
                            i.title.lower(), i.id))))
                parent = choose(snapshot, request.parent, parents, now, streams=self.streams)
                candidates = tuple(c for c in candidates if snapshot.items[
                    c.item_id if isinstance(c, d.LifecycleCandidate) else c.id].parent_id == parent.id)
            candidate = choose(snapshot, request.selector, candidates, now, streams=self.streams)
            root = snapshot.items[candidate.item_id] if isinstance(candidate, d.LifecycleCandidate) else candidate
            tree = d.subtree(snapshot, root.id)
            if command == 'done':
                recurring = [i for i in tree[1:] if i.recurring and not i.completed]
                if recurring:
                    context = {a.id for i in recurring for a in (*d.ancestors(snapshot, i.id), i)}
                    text = _preview(snapshot, root, context)
                    self._show(text)
                    raise d.DomainError('Recurring descendants block completion:\n' + text +
                        '\nRemove recurrence, delete the step, or separate recurring work.')
                order = d.completion_order(snapshot, root.id)
                if root.recurring:
                    predicted = replace(snapshot, items={**snapshot.items, **{
                        i.id: replace(i, completed=True, completed_at=now)
                        for i in order[:-1]}})
                    _recurring_preflight(predicted, root, True, settings.hidden_from_now)
                if len(order) > 1:
                    self._show(_preview(snapshot, root, {i.id for i in order}))
                    self._confirm('Complete this open subtree? [y/yes]: ')
                operations = [Operation('item_update_date_complete', {'id': i.id, 'is_forward': 1, 'reset_subtasks': 0})
                    if i.recurring else Operation('item_complete', {'id': i.id}) for i in order]
                operations.extend(Operation('note_add', {'item_id': root.id, 'content': body}) for body in bodies)
            elif command == 'reopen':
                if root.recurring:
                    _recurring_preflight(snapshot, root, False, settings.hidden_from_now)
                    operations = [Operation('item_update_date_complete', {'id': root.id, 'is_forward': 0, 'reset_subtasks': 0})]
                else:
                    chain = d.reopen_chain(snapshot, root.id)
                    proposed = replace(snapshot, items={**snapshot.items, **{
                        i.id: replace(i, completed=False, completed_at=None) for i in chain}})
                    d.validate(proposed, settings.hidden_from_now)
                    operations = [Operation('item_uncomplete', {'id': root.id})]
            else:
                eligible = {c.item_id for c in d.completed_deletion_candidates(snapshot, cursor, now)}
                included = {root.id} | {i.id for i in tree if not i.completed or i.id in eligible}
                # Include ancestor context for every shown bounded descendant.
                included.update(a.id for i in tree if i.id in included for a in d.ancestors(snapshot, i.id))
                self._show('Delete scope:\n' + _preview(snapshot, root, included))
                self.streams.stderr.write('Older completed descendants are outside this bounded preview '
                    'and may also be cascade-deleted by Todoist.\n')
                self.streams.stderr.flush()
                if not request.option('yes'):
                    self._confirm('Delete this subtree? [y/yes]: ')
                operations = [Operation('item_delete', {'id': root.id})]
            return self._run(operations, snapshot, state, now, deliver)

    def _show(self, text):
        self.streams.stdout.write(text + '\n')
        self.streams.stdout.flush()

    def _confirm(self, question):
        answer = prompt(question, stdin=self.streams.stdin, stdout=self.streams.stdout, stderr=self.streams.stderr)
        if answer.strip().lower() not in ('y', 'yes'):
            raise Cancelled('operation cancelled')

    def _run(self, operations, snapshot, state, now, deliver):
        outcomes, receipts, failure, status = [], [], None, 0
        identities = {i.id: i.role + ': ' + p.owner_title(snapshot, i) for i in snapshot.items.values()}
        for index, operation in enumerate(operations):
            result = None
            try:
                result = self.gateway.execute(operation, before=Current(snapshot, state.state.sync_token),
                    known_owners=snapshot.items, start=state.state.cursor)
                outcomes.append(LifecycleOperation(operation, result.outcome.value, result))
                if result.accepted:
                    owner = snapshot.items[operation.args.get('id', operation.args.get('item_id'))]
                    if operation.type == 'note_add':
                        receipt = (p.render_comment_bodies(snapshot, owner, [result.actual.body], owner_identified=True)
                            if isinstance(result.actual, d.Comment) and result.actual.item_id == owner.id else p.document())
                    else:
                        action = {'item_complete': 'Completed', 'item_uncomplete': 'Reopened',
                                  'item_delete': 'Deleted'}.get(operation.type)
                        if action is None:
                            action = 'Completed' if operation.args['is_forward'] else 'Reopened'
                        restored = result.restored_ancestors
                        receipt = p.render_mutation(snapshot, owner, action, also_reopened=restored)
                    receipts.append(receipt)
                    if deliver and receipt.stdout:
                        self._show(receipt.stdout.rstrip('\n'))
                    # Acceptance is recorded before any reconciliation/publication.
                    state = self.synchronizer.reconcile_accepted_locked()
                    snapshot = state.snapshot
                    if result.issues:
                        raise d.DomainError('; '.join(result.issues) +
                            '. Remote operation accepted; do not replay. Read-only recovery: todo --refresh now.' +
                            ' If synchronization still rejects invalid remote state, repair that state externally.')
                else:
                    # Read-only reconciliation also follows API rejection/unknown.
                    self.synchronizer.refresh_locked(remote_outcome=result.outcome.value)
                    raise d.DomainError('remote operation ' + result.outcome.value +
                        (': ' + '; '.join(result.issues) if result.issues else '') + '; do not replay blindly')
            except (LocalError, d.DomainError, HTTPFailure, OSError, KeyboardInterrupt, InputError) as error:
                failure = error.failure if isinstance(error, SyncInterrupted) else error
                status = 130 if isinstance(error, KeyboardInterrupt) or getattr(error, 'status', None) == 130 else 1
                if len(outcomes) == index:
                    outcomes.append(LifecycleOperation(operation, 'unknown', result))
                outcomes.extend(LifecycleOperation(op, 'unattempted') for op in operations[index + 1:])
                break
        stderr = []
        if failure is not None:
            stderr.append('Lifecycle partial failure: ' + str(failure))
            if (getattr(failure, 'phase', None) in ('current retrieval', 'lifecycle reconciliation')
                    and isinstance(failure.__cause__, d.DomainError)):
                stderr.append('Authoritative state could not be validated; repair the reported remote state externally, then synchronize read-only.')
            for outcome in outcomes:
                op = outcome.operation
                target = op.args.get('id', op.args.get('item_id'))
                action = {'item_complete': 'complete', 'item_uncomplete': 'reopen',
                          'item_delete': 'delete', 'note_add': 'add Done comment to'}.get(op.type)
                if action is None:
                    action = 'complete occurrence of' if op.args['is_forward'] else 'undo latest occurrence of'
                label = {'rejected': 'failed', 'unknown': 'outcome unknown',
                         'unattempted': 'not attempted'}.get(outcome.outcome, outcome.outcome)
                stderr.append(f'{label}: {action} {identities[target]}')
            if any(o.outcome in ('accepted', 'unknown') for o in outcomes):
                stderr.append('Do not repeat completion or undo to repair the cache.' +
                    (' After repairing the local validation problem or manually restoring a consistent saved set, use todo --refresh now.'
                     if getattr(failure, 'refresh_permitted', True) is False else
                     ' Read-only recovery: todo --refresh now.'))
        document = p.document('\n'.join(r.stdout for r in receipts if r.stdout), '\n'.join(stderr))
        if deliver and document.stderr:
            self.streams.stderr.write(document.stderr + '\n')
        return LifecycleResult(document, tuple(outcomes), snapshot, now, status, failure)


def execute(request, synchronizer, **kwargs):
    deliver = kwargs.pop('deliver', False)
    return LifecycleWorkflow(synchronizer, **kwargs).execute(request, deliver=deliver)
