"""Protected local publications. Writers must hold exclusive_lock before reads.

Successful prepare_candidates validates all complete prospective content before
any replacement. Publication order is cache, history, optional initial cursor,
binding. A later replacement failure may leave a mixed set: readers reject it.
There is deliberately no journal, rollback, or multi-file transaction guarantee.
Timestamp arguments accept domain.ExactInstant or aware datetime. Loaded cursor,
synced_at, model and history timestamps are ExactInstant; nullable fields retain
None. Schema-1 UTC strings preserve all fraction digits. Invalid required stored
times raise LocalError without repairing files. write_cursor additionally requires
UTC for datetime inputs; ExactInstant is intrinsically UTC.
Optional cache current_resources stores only proven item/reminder membership,
paired with that cache's token. Active owners' own comments come from the same
validated merged snapshot; archived context never supplies active membership.
waiting_label_ids independently records exact-name label membership proven at the
same sync_token; it stores no unrelated label names. Missing means unknown.
Legacy caches omit current membership and remain usable offline, requiring hydration
before online incremental retrieval.
"""
from dataclasses import dataclass, replace
from datetime import datetime, timezone, timedelta
from pathlib import Path
import uuid
from todo_lib import domain as d
from .codec import dumps, loads, snapshot_data, snapshot_from, instant, parse_instant
from .history import History, Coverage, validate_history
from .safety import LocalError, check_paths, read_bytes, atomic_write, regular


@dataclass(frozen=True)
class Binding:
    account_id: str
    account_display: str
    root_id: str
    root_name: str
    categories: dict[str, str]
    last_synced_account_timezone: str
    publication: str
    schema: int = 1


@dataclass(frozen=True)
class LocalState:
    binding: Binding
    cursor: d.ExactInstant | datetime
    snapshot: d.Snapshot | None
    history: History
    sync_token: str | None
    synced_at: d.ExactInstant | datetime | None
    # Reconstructed Sync resources only; None on compatible legacy caches.
    current_snapshot: d.Snapshot | None = None
    current_reminder_ids: frozenset[str] | None = None
    waiting_label_ids: frozenset[str] | None = None


@dataclass(frozen=True)
class Candidates:
    """Complete immutable serialized candidates; publish revalidates all bytes."""
    binding: bytes
    cache: bytes
    history: bytes
    cursor: bytes | None = None


def _binding_data(binding):
    from dataclasses import asdict
    return asdict(binding)


def _binding(content):
    try:
        raw = loads(content)
        if type(raw['schema']) is not int or raw['schema'] != 1:
            raise LocalError('unsupported binding schema')
        b = Binding(**raw)
        for name in ('account_id', 'root_id', 'publication'):
            if not isinstance(getattr(b, name), str) or not getattr(b, name):
                raise LocalError(f'binding.{name}: nonempty string required')
        for name in ('account_display', 'root_name'):
            if not isinstance(getattr(b, name), str) or not getattr(b, name).strip():
                raise LocalError(f'binding.{name}: nonempty display name required')
        if not isinstance(b.categories, dict) or any(not isinstance(k, str) or not k or not isinstance(v, str) or not v.strip() for k, v in b.categories.items()):
            raise LocalError('binding.categories: string IDs/names required')
        d.account_timezone(b.last_synced_account_timezone)
        return b
    except LocalError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError):
        raise LocalError('invalid binding.json') from None


def _association(binding):
    return dict(account_id=binding.account_id, root_id=binding.root_id, publication=binding.publication)


def _envelope(raw, binding, kind):
    if not isinstance(raw, dict) or type(raw.get('schema')) is not int or raw['schema'] != 1:
        raise LocalError(f'unsupported {kind} schema')
    if raw.get('association') != _association(binding):
        raise LocalError(f'{kind}: mixed account/root/publication; rerun init or restore a consistent set')
    if 'timezone' in raw or 'last_synced_account_timezone' in raw:
        raise LocalError(f'{kind}: conflicting timezone authority')


def _snapshot_matches(snapshot, binding):
    if (snapshot.binding.account_id != binding.account_id or snapshot.binding.root_id != binding.root_id
            or set(snapshot.binding.category_ids) != set(binding.categories)
            or snapshot.root.name != binding.root_name
            or {k: v.name for k, v in snapshot.categories.items()} != binding.categories
            or snapshot.account.timezone != binding.last_synced_account_timezone):
        raise LocalError('snapshot differs from authoritative binding')


def _cache(content, binding, context=None):
    try:
        raw = loads(content)
        _envelope(raw, binding, 'cache')
        token = raw['sync_token']
        if not isinstance(token, str) or not token:
            raise LocalError('cache.sync_token: nonempty string required')
        s = snapshot_from(raw['snapshot'], binding.last_synced_account_timezone)
        _snapshot_matches(s, binding)
        baseline = reminder_ids = None
        if 'current_resources' in raw:
            members = raw['current_resources']
            names = ('items', 'reminders')
            if not isinstance(members, dict) or set(members) != set(names):
                raise LocalError('invalid current-resource provenance')
            resources = {}
            for name in names:
                ids = members[name]
                collection = getattr(s, name)
                if name == 'reminders' and context is not None:
                    collection = {**{k: r for k, r in context.reminders.items()
                        if r.item_id not in members['items']}, **collection}
                if (not isinstance(ids, list) or any(not isinstance(k, str) or k not in collection for k in ids)
                        or len(set(ids)) != len(ids)):
                    raise LocalError('invalid current-resource provenance')
                resources[name] = {k: collection[k] for k in ids}
            reminder_ids = frozenset(resources['reminders'])
            resources['reminders'] = {k: r for k, r in resources['reminders'].items()
                                     if r.item_id in resources['items']}
            active = resources['items']
            baseline = d.validate(replace(s, **resources,
                comments={k: c for k, c in s.comments.items() if c.item_id in active},
                occurrences={}))
        waiting = raw.get('waiting_label_ids')
        if 'waiting_label_ids' in raw:
            if (not isinstance(waiting, list)
                    or any(not isinstance(k, str) or not k for k in waiting)
                    or len(set(waiting)) != len(waiting)):
                raise LocalError('invalid saved waiting-label context; use --refresh')
            waiting = frozenset(waiting)
        return s, token, parse_instant(raw['synced_at']), baseline, reminder_ids, waiting
    except (TypeError, KeyError, d.DomainError):
        raise LocalError('invalid cache; use --refresh') from None


def _history(content, binding):
    try:
        raw = loads(content)
        _envelope(raw, binding, 'history')
        snapshot = snapshot_from(raw['snapshot'], binding.last_synced_account_timezone)
        _snapshot_matches(snapshot, binding)
        observations = {k: parse_instant(v) if v is not None else None for k, v in raw['observations'].items()}
        return validate_history(History(snapshot, observations,
            tuple(Coverage(parse_instant(c['start']), parse_instant(c['end'])) for c in raw['coverage']), raw['complete']))
    except (ValueError, TypeError, KeyError, AttributeError):
        raise LocalError('invalid required history.json; preserve bytes and restore consistent state') from None


def _cursor(content):
    try:
        text = content.decode('ascii')
        if not text.endswith('\n') or text.count('\n') != 1:
            raise ValueError()
        result = parse_instant(text[:-1])
        # Stored cursor is UTC, including the +00:00 RFC3339 spelling.
        if not (text[:-1].endswith('Z') or text[:-1].endswith('+00:00')):
            raise ValueError()
        return result
    except (ValueError, UnicodeError):
        raise LocalError('invalid report-cursor; use report --set-cursor') from None


def prepare_candidates(snapshot, history, *, account_display, sync_token, synced_at,
                       initial_cursor=None, publication=None, hidden_names=(),
                       current_snapshot=None, current_reminder_ids=None, waiting_label_ids=None):
    """Pure complete validation for init/sync, before publication or HTTP mutation.

    Repeat init/sync supplies merged existing history and omits initial_cursor.
    Omit publication to generate a fresh association. An explicit association
    must differ from the existing binding; publish_snapshot checks this under
    the caller's lock before replacing any file.
    Tokens here are opaque incremental Sync tokens, never API credentials.
    current_snapshot is the actual merged Sync view paired with sync_token.
    current_reminder_ids also covers Sync reminders with archived owners, whose
    bodies may live only in protected pending context after report selection.
    Omission invalidates disposable provenance; combined history is never inferred
    to be current. Membership only is stored beside the token in cache.json.
    """
    try:
        d.validate(snapshot, hidden_names)
        if current_snapshot is not None:
            d.validate(current_snapshot, hidden_names)
    except d.DomainError as error:
        raise LocalError(str(error)) from None
    validate_history(history)
    binding = Binding(snapshot.account.id, account_display, snapshot.root.id,
        snapshot.root.name, {k: v.name for k, v in snapshot.categories.items()},
        snapshot.account.timezone, publication or uuid.uuid4().hex)
    _snapshot_matches(history.snapshot, binding)
    assoc = _association(binding)
    b = dumps(_binding_data(binding))
    cache_data = dict(schema=1, association=assoc, snapshot=snapshot_data(snapshot),
                      sync_token=sync_token, synced_at=instant(synced_at))
    if current_snapshot is not None:
        _snapshot_matches(current_snapshot, binding)
        members = {}
        for name in ('items', 'comments', 'reminders'):
            collection = getattr(current_snapshot, name)
            if any(getattr(snapshot, name).get(k) != v for k, v in collection.items()):
                raise LocalError('current baseline differs from published resource')
            if name != 'comments':
                members[name] = sorted(collection)
        if {k: c for k, c in snapshot.comments.items() if c.item_id in current_snapshot.items} != current_snapshot.comments:
            raise LocalError('current baseline differs from published comments')
        if current_reminder_ids is not None:
            members['reminders'] = sorted(set(current_reminder_ids) &
                (snapshot.reminders.keys() | history.snapshot.reminders.keys()))
        cache_data['current_resources'] = members
    if waiting_label_ids is not None and (not isinstance(waiting_label_ids, (set, frozenset))
            or any(not isinstance(k, str) or not k for k in waiting_label_ids)):
        raise LocalError('invalid saved waiting-label context')
    if waiting_label_ids is not None:
        cache_data['waiting_label_ids'] = sorted(waiting_label_ids)
    cache = dumps(cache_data)
    h = dumps(dict(schema=1, association=assoc, snapshot=snapshot_data(history.snapshot),
        observations=history.observations, coverage=[dict(start=c.start, end=c.end) for c in history.coverage], complete=history.complete))
    cursor = None
    if initial_cursor is not None:
        cursor = (instant(initial_cursor) + '\n').encode('ascii')
    candidate = Candidates(b, cache, h, cursor)
    validate_candidates(candidate)
    return candidate


def validate_candidates(candidates):
    binding = _binding(candidates.binding)
    history = _history(candidates.history, binding)
    _cache(candidates.cache, binding, history.snapshot)
    if candidates.cursor is not None:
        _cursor(candidates.cursor)
    return candidates


class StateStore:
    def __init__(self, root=None):
        self.root = Path.home() / '.todo' if root is None else Path(root)

    def load_binding(self):
        check_paths(self.root)
        return _binding(read_bytes(self.root / 'binding.json'))

    def load_cursor(self):
        check_paths(self.root)
        return _cursor(read_bytes(self.root / 'report-cursor'))

    def load_history(self, binding=None):
        check_paths(self.root)
        binding = self.load_binding() if binding is None else binding
        return _history(read_bytes(self.root / 'history.json'), binding)

    def load_consistent_state(self, *, require_cache=True):
        """Lock-free coherent read or rejection, including concurrent publication.

        Refresh may pass require_cache=False, ignoring disposable cache content.
        Required binding/cursor/history are still checked. Unsafe cache paths fail.
        """
        check_paths(self.root)
        before = read_bytes(self.root / 'binding.json')
        binding = _binding(before)
        history = self.load_history(binding)
        cursor = self.load_cursor()
        snapshot = token = synced = baseline = reminder_ids = waiting = None
        if require_cache:
            try:
                snapshot, token, synced, baseline, reminder_ids, waiting = _cache(read_bytes(self.root / 'cache.json'), binding, history.snapshot)
            except LocalError as error:
                raise LocalError(f'{error}; use --refresh') from None
        if before != read_bytes(self.root / 'binding.json'):
            raise LocalError('publication changed while reading; retry')
        return LocalState(binding, cursor, snapshot, history, token, synced, baseline, reminder_ids, waiting)

    def publish_snapshot(self, candidates):
        """Caller holds the lock. Revalidate before any write; binding is last."""
        check_paths(self.root)
        validate_candidates(candidates)
        binding = _binding(candidates.binding)
        if regular(self.root / 'binding.json', missing=True) is not None:
            old = self.load_consistent_state(require_cache=False)
            if (old.binding.account_id, old.binding.root_id) != (binding.account_id, binding.root_id):
                raise LocalError('account/root change requires deliberate full-directory fresh start')
            # Reusing the current association would let lock-free readers accept
            # changed cache with old history after an interrupted replacement.
            # Require freshness even for identical content or a missing cache.
            if binding.publication == old.binding.publication:
                raise LocalError('snapshot publication requires a fresh publication association')
            if candidates.cursor is not None:
                raise LocalError('existing binding: init must preserve cursor')
        else:
            # An interrupted first initialization may have published protected
            # history/cursor already. A rerun must not treat those bytes as
            # disposable or use a missing binding to authorize an account switch.
            history_path = self.root / 'history.json'
            if regular(history_path, missing=True) is not None:
                raw = loads(read_bytes(history_path))
                try:
                    old_publication = raw['association']['publication']
                except (KeyError, TypeError):
                    raise LocalError('invalid pending initialization history; preserve and restore local state') from None
                _history(dumps(raw), replace(binding, publication=old_publication))
            cursor_path = self.root / 'report-cursor'
            if regular(cursor_path, missing=True) is not None:
                old_cursor = read_bytes(cursor_path)
                _cursor(old_cursor)
                if candidates.cursor is not None and _cursor(candidates.cursor) != _cursor(old_cursor):
                    raise LocalError('pending initialization cursor must be preserved')
            elif candidates.cursor is None:
                raise LocalError('initial publication requires a report cursor')
        for name, data, validator in (
            ('cache.json', candidates.cache, lambda c: _cache(c, binding, _history(candidates.history, binding).snapshot)),
            ('history.json', candidates.history, lambda c: _history(c, binding)),
            ('report-cursor', candidates.cursor, _cursor),
            ('binding.json', candidates.binding, _binding),
        ):
            if data is not None:
                atomic_write(self.root / name, data, validator)

    def write_cursor(self, aware_utc):
        """Explicit setter repairs readable corrupt/missing content, never unsafe paths.

        No history cleanup or network activity. Workflow holds the process lock.
        """
        check_paths(self.root)
        instant(aware_utc)
        if isinstance(aware_utc, datetime) and aware_utc.utcoffset() != timedelta(0):
            raise LocalError('write_cursor requires an aware UTC instant')
        path = self.root / 'report-cursor'
        if regular(path, missing=True) is not None:
            read_bytes(path)  # Readability is mandatory, validity intentionally not.
        atomic_write(path, (instant(aware_utc) + '\n').encode('ascii'), _cursor)

    def save_history(self, history, *, binding=None):
        """Locked history-only update, retaining current publication association."""
        check_paths(self.root)
        current = self.load_binding()
        if binding is not None and binding != current:
            raise LocalError('history binding changed')
        # Never turn a corrupt/missing required store into a fresh empty one.
        self.load_history(current)
        validate_history(history)
        _snapshot_matches(history.snapshot, current)
        data = dumps(dict(schema=1, association=_association(current),
            snapshot=snapshot_data(history.snapshot), observations=history.observations,
            coverage=[dict(start=c.start, end=c.end) for c in history.coverage], complete=history.complete))
        atomic_write(self.root / 'history.json', data, lambda c: _history(c, current))

    def clear_cache(self):
        """Explicit current-cache deletion only; no HTTP, cursor or pruning."""
        check_paths(self.root)
        path = self.root / 'cache.json'
        if regular(path, missing=True) is not None:
            path.unlink()


def load_consistent_state(root=None, **kwargs):
    return StateStore(root).load_consistent_state(**kwargs)


def publish_snapshot(candidates, root=None):
    return StateStore(root).publish_snapshot(candidates)


def write_cursor(aware_utc, root=None):
    return StateStore(root).write_cursor(aware_utc)
