"""Identity-preserving moves of the complete known subtree.

The caller may pass argv or a normalized syntax request. One lock covers refresh,
selection, validation, the single direct move and authoritative reconciliation.
No lifecycle operation, rollback, retry, or report-cursor update occurs here.
"""
from copy import copy
from dataclasses import dataclass, replace

from todo_lib import domain as d, presentation as p
from todo_lib.adapter.commands import Gateway, Outcome
from todo_lib.adapter.current import Current, retrieve
from todo_lib.adapter.history import HistoryAdapter
from todo_lib.adapter.transport import HTTPFailure, redact
from todo_lib.local import LocalError, exclusive_lock, load_config, prepare_candidates
from todo_lib.syntax import parse
from .reads import combined_snapshot, choose, select_child, select_title
from .sync import SyncError, SyncInterrupted, SyncResult, _reconcile


class MoveError(d.DomainError):
    status = 1

    def __init__(self, message, *, remote_outcome='unattempted'):
        self.remote_outcome = remote_outcome
        super().__init__(message)


class _MoveEvidence:
    """Keep UUID-attributed receipts even if gateway reconciliation is interrupted.

    This delegates every request unchanged; it neither retries nor reconciles.
    Only the single move's status is retained, never unrelated response data.
    """
    def __init__(self, transport):
        self.transport = transport
        self.uuid = None
        self.statuses = set()
        self.reasons = []
        self.http_rejected = False

    def request(self, *args, **kwargs):
        if kwargs.get('operation') == 'item_move':
            self.uuid, = kwargs['command_uuids']
        try:
            response = self.transport.request(*args, **kwargs)
        except HTTPFailure as error:
            if kwargs.get('operation') == 'item_move' and error.outcome == 'rejected':
                self.http_rejected = True
                self.reasons.append(str(error))  # Transport diagnostics are already safe.
            raise
        status = response.get('sync_status') if isinstance(response, dict) else None
        value = status.get(self.uuid) if isinstance(status, dict) and self.uuid else None
        if value == 'ok':
            self.statuses.add('accepted')
        elif (isinstance(value, dict) and type(value.get('error_code')) is int
              and isinstance(value.get('error'), str) and value['error']):
            self.statuses.add('rejected')
            # Only the resolved transport credential can safely redact provider text.
            secret = getattr(self.transport, '_secret', None)
            if secret is not None:
                self.reasons.append(' '.join(redact(value['error'], secret).split()))
        return response

    @property
    def outcome(self):
        if len(self.statuses) == 1:
            return next(iter(self.statuses))
        return 'rejected' if self.http_rejected else 'unknown'


class MoveReceiptError(MoveError):
    """Acceptance and complete publication survive a failed receipt."""
    def __init__(self, phase, cause, snapshot, selected):
        self.phase = phase
        self.selected = selected
        self.publication_started = True
        self.publication_completed = True
        self.saved_state_available = True
        self.refresh_permitted = True
        path = ' > '.join(i.title for i in (*d.ancestors(snapshot, selected.id), selected))
        super().__init__(f'{phase} failed: {cause}. Remote operation outcome: accepted '
            f'for {selected.role} {path} in {snapshot.categories[selected.category_id].name}; '
            'local snapshot publication completed. Do not replay the mutation. '
            'Inspect the saved result with read-only todo now, or reconcile with '
            'read-only todo --refresh now.', remote_outcome='accepted')


@dataclass(frozen=True)
class MoveResult:
    document: p.Document
    snapshot: d.Snapshot
    now: object
    selected: d.Item
    remote_outcome: str = 'accepted'
    status: int = 0


def destination_candidates(snapshot, query, kind):
    """Category names are full names; item selectors retain term boundaries."""
    from .reads import title_candidates
    categories = tuple(c for c in snapshot.categories.values()
                       if d.title_key(c.name) == d.title_key(' '.join(query)))
    if kind == 'category':
        return categories
    items = title_candidates(snapshot, query)
    return items if kind == 'parent' else categories + items


def moved_snapshot(snapshot, source, parent_id, category_id, hidden_names=()):
    d.validate_move_depth(snapshot, source.id, parent_id)
    branch = {i.id for i in d.subtree(snapshot, source.id)}
    items = dict(snapshot.items)
    for identity in branch:
        item = items[identity]
        items[identity] = replace(item, category_id=category_id,
            parent_id=parent_id if identity == source.id else item.parent_id)
    return d.validate(replace(snapshot, items=items), hidden_names)


class MoveWorkflow:
    def __init__(self, synchronizer, *, gateway=None, settings=None, streams=None):
        self.synchronizer = synchronizer
        self.gateway = gateway or Gateway(synchronizer.transport)
        self.settings, self.streams = settings, streams

    def execute(self, request, *, deliver=False):
        if isinstance(request, (list, tuple)):
            request = parse(request)  # Operand failures precede config, lock and HTTP.
        if request.command != 'move':
            raise ValueError('not a move command')
        sync = self.synchronizer
        settings = self.settings or load_config(sync.store.root)
        with exclusive_lock('move', sync.store.root):
            result = sync.refresh_locked()
            snapshot = combined_snapshot(result)
            d.validate(snapshot, settings.hidden_from_now)
            source = (select_child(snapshot, request.parent, request.selector, result.now,
                                   streams=self.streams) if request.parent else
                      select_title(snapshot, request.selector, result.now,
                                   target=request.target or 'item', streams=self.streams))
            kind = request.destination_kind
            explicit_category = request.option('category')
            category = None
            parent_id = source.parent_id
            if kind != 'category' and kind != 'promotion':
                destination = choose(snapshot, request.destination,
                    destination_candidates(snapshot, request.destination, kind),
                    result.now, streams=self.streams)
                if isinstance(destination, d.Item):
                    if destination.completed:
                        raise MoveError('completed destination cannot be a parent')
                    parent_id, category = destination.id, destination.category_id
                else:
                    if source.parent_id is not None:
                        raise MoveError('a step requires explicit promotion or reparenting')
                    category = destination.id
            elif kind == 'promotion':
                parent_id = None
            if explicit_category is not None:
                selected_category = d.lookup_category(snapshot, explicit_category)
                if category is not None and category != selected_category.id:
                    raise MoveError('explicit category differs from destination parent category')
                category = selected_category.id
            category = source.category_id if category is None else category
            if kind == 'category' and source.parent_id is not None:
                raise MoveError('a step requires explicit promotion or reparenting')
            if (source.parent_id, source.category_id) == (parent_id, category):
                raise MoveError('move would change nothing')
            candidate = moved_snapshot(snapshot, source, parent_id, category,
                                       settings.hidden_from_now)
            # Category changes invalidate retained completed rows as delta seeds:
            # Sync need not re-emit archived descendants. Read a replacement and
            # keep the full known tree separately for inheritance/history below.
            # Retaining the original prior also preserves explicit deletion and
            # scope-departure attribution; never seed the requested open hierarchy.
            before = Current(snapshot, '*' if category != source.category_id
                             else result.state.sync_token)
            context = ('move ' + self._item_context(snapshot, source) + ' to ' +
                (self._item_context(snapshot, snapshot.items[parent_id]) if parent_id else
                 'standalone task in ' + snapshot.categories[category].name))
            gateway, evidence = self.gateway, None
            if isinstance(gateway, Gateway):
                # A per-call facade preserves the gateway's UUID replay guard and
                # injected retrieval hooks without replacing its caller-owned transport.
                gateway = copy(gateway)
                evidence = _MoveEvidence(gateway.transport)
                gateway.transport = evidence
            try:
                operation = gateway.move(source.id, before=before, **(
                    {'parent_id': parent_id} if parent_id is not None else {'project_id': category}))
            except KeyboardInterrupt:
                outcome = evidence.outcome if evidence else 'unknown'
                phase = 'move reconciliation' if outcome != 'unknown' else 'remote move'
                reason = '; '.join(dict.fromkeys(evidence.reasons)) if evidence else ''
                raise SyncInterrupted(SyncError(phase, context + '; interrupted' +
                    (('; ' + reason) if reason else ''),
                    saved_state_available=True, remote_outcome=outcome)) from None
            if operation.outcome != Outcome.ACCEPTED:
                reason = '; '.join(dict.fromkeys(evidence.reasons)) if evidence else ''
                raise MoveError(context + ': Remote move outcome: ' + operation.outcome.value +
                    (('; ' + reason) if reason else '') +
                    '; stopped without replay. Use read-only todo --refresh now for reconciliation.',
                    remote_outcome=operation.outcome.value)
            reconciled = self._publish(operation, result, snapshot, candidate, source, settings)
            after = reconciled.snapshot.items[source.id]
            phase = 'move receipt rendering'
            try:
                document = p.render_move(snapshot, source, reconciled.snapshot, after)
                if deliver:
                    phase = 'move receipt delivery'
                    p.deliver(document, settings, self.streams or p.OriginalStreams.current(),
                              view_kind='move')
            except (Exception, KeyboardInterrupt) as error:
                failure = MoveReceiptError(phase, error, reconciled.snapshot, after)
                if isinstance(error, KeyboardInterrupt):
                    raise SyncInterrupted(failure) from None
                raise failure from error
            return MoveResult(document, reconciled.snapshot, result.now, after)

    @staticmethod
    def _item_context(snapshot, item):
        path = ' > '.join(i.title for i in (*d.ancestors(snapshot, item.id), item))
        return f'{item.role} {path} in {snapshot.categories[item.category_id].name}'

    def _publish(self, operation, result, original, candidate, source, settings):
        sync, state = self.synchronizer, result.state
        phase, before_bytes = 'move reconciliation', None
        try:
            current = operation.after
            if current is None:
                current = retrieve(sync.transport, original.binding, prior=original,
                                   sync_token=state.sync_token,
                                   replace=candidate.items[source.id].category_id != source.category_id,
                                   hidden_names=settings.hidden_from_now)
            # An accepted direct move changes the known subtree's inherited
            # category. Retained completed descendants omitted by bounded history
            # keep their own fields; any newly returned fields remain authoritative.
            adapter = HistoryAdapter(sync.transport, timezone=current.account.timezone)
            snapshot, history = _reconcile(current, candidate, state.history, adapter,
                min((state.cursor, state.synced_at or state.cursor), key=d.instant_key),
                result.now, state.cursor, settings.hidden_from_now)
            for item in d.subtree(candidate, source.id):
                actual = snapshot.items.get(item.id)
                if actual is None:
                    if item.id == source.id:
                        raise MoveError('accepted source unavailable')
                    continue  # only authoritative deletion/scope departure removes known work
                if (actual.parent_id, actual.category_id) != (item.parent_id, item.category_id):
                    raise MoveError('accepted move differs from requested subtree hierarchy')
            phase = 'candidate preparation'
            candidates = prepare_candidates(snapshot, history,
                account_display=state.binding.account_display, sync_token=current.sync_token,
                synced_at=result.now, hidden_names=settings.hidden_from_now)
            before_bytes = sync._bytes(('cache.json', 'history.json', 'binding.json'))
            phase = 'local publication'
            sync.store.publish_snapshot(candidates)
            return SyncResult(sync.store.load_consistent_state(), result.now)
        except (LocalError, d.DomainError, HTTPFailure, OSError, KeyboardInterrupt) as error:
            started = before_bytes is not None and sync._bytes(before_bytes) != before_bytes
            try:
                sync.store.load_consistent_state(require_cache=False)
                permitted = True
            except (LocalError, OSError):
                permitted = False
            try:
                sync.store.load_consistent_state()
                available = True
            except (LocalError, OSError):
                available = False
            failure = SyncError(phase, error, publication_started=started,
                saved_state_available=available, refresh_permitted=permitted,
                remote_outcome='accepted')
            if isinstance(error, KeyboardInterrupt):
                raise SyncInterrupted(failure) from None
            raise failure from error


def execute(request, synchronizer, **kwargs):
    deliver = kwargs.pop('deliver', False)
    return MoveWorkflow(synchronizer, **kwargs).execute(request, deliver=deliver)
