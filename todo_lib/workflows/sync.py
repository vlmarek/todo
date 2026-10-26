"""Synchronized state orchestration; no mutation gateway calls or history pruning.

refresh() owns the command lock. Call refresh_locked() / reconcile_accepted_locked()
when a composing workflow already holds exclusive_lock, from preflight through
its remote operations. Syntax validation belongs to that caller; clear_cache is
only valid for an applicable read with refresh. All local/config validation still
runs here before deletion. read_local() is lock-free and makes no HTTP requests.
"""
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from todo_lib import domain as d
from todo_lib.adapter.current import retrieve
from todo_lib.adapter.history import HistoryAdapter
from todo_lib.adapter.transport import HTTPFailure
from todo_lib.local import (StateStore, LocalState, LocalError, History, load_config,
                            exclusive_lock, merge_history, prepare_candidates)
from todo_lib.local.safety import read_bytes


@dataclass(frozen=True)
class SyncResult:
    state: LocalState
    now: d.ExactInstant | datetime
    warnings: tuple[str, ...] = ()
    cache_cleared: bool = False

    @property
    def snapshot(self):
        return self.state.snapshot

    @property
    def history(self):
        return self.state.history


class SyncError(LocalError):
    """Command failure facts; remote_outcome is never changed by local failure."""
    def __init__(self, phase, cause, *, cache_cleared=False,
                 publication_started=False, saved_state_available=False,
                 refresh_permitted=True, remote_outcome='unattempted'):
        self.phase = phase
        self.cache_cleared = cache_cleared
        self.publication_started = publication_started
        self.saved_state_available = saved_state_available
        self.refresh_permitted = refresh_permitted
        self.remote_outcome = remote_outcome
        message = f'{phase} failed: {cause}.'
        if remote_outcome != 'unattempted':
            message += f' Remote operation outcome: {remote_outcome}; do not replay the mutation.'
        if cache_cleared:
            message += ' Explicit cache clearing occurred; only the disposable cache was deleted.'
        if publication_started:
            message += (' Local files may be partially published; a new cache file may already have been written.'
                        ' The saved snapshot may be unusable; newly retrieved observations may not all be saved.')
        else:
            message += ' Previous protected files were preserved.'
            if not cache_cleared:
                message += ' The previous cache was not replaced.'
        if refresh_permitted:
            message += ' Read-only recovery: todo --refresh now.'
        else:
            message += (' Repair the identified local validation problem or restore a consistent saved set;'
                        ' rerun init where applicable. Cache clearing cannot repair required history/binding state.')
        super().__init__(message)


class SyncInterrupted(KeyboardInterrupt):
    def __init__(self, failure):
        self.failure = failure
        super().__init__(str(failure))


def _known(state):
    """Keep pending context independently of the disposable cache."""
    h, s = state.history.snapshot, state.snapshot
    if s is None:
        return h
    items = {**h.items, **s.items}
    collections = {}
    for name in ('comments', 'reminders'):
        collections[name] = {k: value for k, value in getattr(h, name).items()
                             if value.item_id not in s.items}
        collections[name].update(getattr(s, name))
    occurrences = {**h.occurrences, **s.occurrences}
    collections['occurrences'] = {k: value for k, value in occurrences.items()
        if items[value.item_id].completed or items[value.item_id].recurring}
    return d.validate(replace(s, items=items, **collections))


def _reconcile(current, known, history, adapter, start, end, cursor, hidden_names):
    s = current.snapshot
    removed = set(current.deleted_ids | current.departed_ids)
    # Explicit parent deletion/scope departure removes its known subtree too.
    while True:
        expanded = removed | {i.id for i in {**known.items, **s.items}.values() if i.parent_id in removed}
        if expanded == removed:
            break
        removed = expanded
    missing = set(known.items) - s.items.keys() - removed
    items, occurrences = dict(s.items), dict(s.occurrences)
    recurring = {i.id for i in s.items.values() if i.recurring}
    if missing or recurring:
        # A bounded supported endpoint, never active absence, proves completion.
        records = []
        for category in sorted(s.categories):
            records.extend(adapter.completed(start, end, {'project_id': category}).records)
        latest = {}
        for record in records:
            item = record.item
            # Do not retain unrelated returned data, even from an overbroad server.
            if item.category_id not in s.categories or item.id in removed:
                continue
            if item.id in recurring and not record.deleted:
                occurrences.setdefault(record.occurrence.id, record.occurrence)
            if item.id in s.items:
                continue  # current truth always supersedes historical fields
            if item.id not in missing:
                if record.deleted or d.instant_key(record.occurrence.completed_at) <= d.instant_key(cursor):
                    continue
                if not item.completed:
                    raise d.DomainError('unresolved historical recurring owner ' + item.id)
                # Eligible bounded observations join pending storage, with required
                # ancestor resolution below; this is not an arbitrary archive scan.
                missing.add(item.id)
            previous = latest.get(item.id)
            if previous is None or d.instant_key(record.occurrence.completed_at) > d.instant_key(previous.occurrence.completed_at):
                latest[item.id] = record
        removed.update(k for k, record in latest.items() if record.deleted)
        evidence_items = {**known.items, **{k: r.item for k, r in latest.items()}, **s.items}
        while True:
            expanded = removed | {i.id for i in evidence_items.values() if i.parent_id in removed}
            if expanded == removed:
                break
            removed = expanded
        for identity in sorted(missing - removed):
            record = latest.get(identity)
            if record is not None:
                if not record.item.completed:
                    raise d.DomainError('unresolved disappeared recurring/open item ' + identity)
                items[identity] = record.item
                occurrences[record.occurrence.id] = record.occurrence
            elif identity in known.items and known.items[identity].completed:
                # Omission does not retract an already established completion.
                item = known.items[identity]
                if (known.account.timezone != s.account.timezone
                        and item.attention is not None and item.attention.kind == 'floating'):
                    # Retain the wall time, not its resolution in the old account zone.
                    if item.attention.raw_due is None:
                        raise d.DomainError('retained floating attention requires original due metadata')
                    item = replace(item, attention=d.resolve_remote_due(
                        item.attention.raw_due, s.account.timezone))
                items[identity] = item
            else:
                raise d.DomainError('unresolved disappeared managed item ' + identity + '; supported lifecycle evidence required')
    while True:
        expanded = removed | {i.id for i in {**known.items, **items}.values() if i.parent_id in removed}
        if expanded == removed:
            break
        removed = expanded
    items = {k: v for k, v in items.items() if k not in removed}
    # Current live comments are authoritative, including absence/changed ownership.
    comments = {k: c for k, c in s.comments.items() if c.item_id in items}
    for identity in sorted(items.keys() - s.items.keys()):
        for comment in adapter.comments(identity).records:
            if comment.item_id != identity:
                raise d.DomainError('incompatible historical comment ownership')
            if comment.id in comments and comments[comment.id].item_id != identity:
                raise d.DomainError('incompatible comment ownership')
            comments[comment.id] = comment
    # Reopen supersedes old ordinary completion occurrences, including retained ones.
    for key, occurrence in known.occurrences.items():
        item = items.get(occurrence.item_id)
        if item is not None and (item.completed or item.recurring):
            occurrences.setdefault(key, occurrence)
    occurrences = {k: o for k, o in occurrences.items() if o.item_id in items
                   and (items[o.item_id].completed or items[o.item_id].recurring)}
    for identity in sorted(recurring):
        if not any(o.item_id == identity for o in occurrences.values()):
            continue
        events = adapter.activities(start, end, {'object_type': 'item', 'object_id': identity})
        for event in sorted(events.records, key=lambda e: d.instant_key(e.event_date)):
            if event.object_type != 'item' or event.object_id != identity or event.event_type != 'uncompleted':
                continue
            candidates = [o for o in occurrences.values() if o.item_id == identity
                          and d.instant_key(o.completed_at) <= d.instant_key(event.event_date)]
            latest = max(candidates, key=lambda o: d.instant_key(o.completed_at), default=None)
            if latest is not None:
                occurrences[latest.id] = replace(latest, undone=True)
    reminders = {k: r for k, r in known.reminders.items()
                 if r.item_id in items and r.item_id not in s.items}
    reminders.update(s.reminders)
    reminders = {k: r for k, r in reminders.items() if r.item_id in items}
    snapshot = d.validate(replace(s, items=items, comments=comments,
        reminders=reminders, occurrences=occurrences), hidden_names)
    incoming = History(snapshot, {k: end for k in items})
    removed_comments = set(history.snapshot.comments) - comments.keys()
    pending = merge_history(history, incoming, removed_item_ids=removed,
                            removed_comment_ids=removed_comments)
    # Both stores must carry authoritative current values, including known-to-null.
    # The candidate covers every retained identity. Collection omissions for its
    # resolved owners are authoritative too (notably reopen/reminder removal).
    return snapshot, replace(pending, snapshot=snapshot)


class Synchronizer:
    def __init__(self, transport, store=None, *, clock=None):
        self.transport = transport
        self.store = StateStore() if store is None else store
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def read_local(self):
        """Zero HTTP; compatible pending context is already in the saved snapshot."""
        load_config(self.store.root)
        state = self.store.load_consistent_state()
        now = self.clock()
        warnings = ()
        if d.instant_key(now) - d.instant_key(state.synced_at) > 24 * 60 * 60:
            warnings = ('Saved snapshot is older than 24 hours; use --refresh.',)
        return SyncResult(replace(state, snapshot=_known(state)), now, warnings)

    def refresh(self, *, clear_cache=False):
        with exclusive_lock('refresh', self.store.root):
            return self.refresh_locked(clear_cache=clear_cache)

    def reconcile_accepted_locked(self):
        """Call after EACH accepted gateway operation, before any next mutation.

        Raises with remote_outcome='accepted' even if retrieval or publication fails.
        Unknown/rejected gateway outcomes must not call this acceptance boundary.
        """
        return self.refresh_locked(remote_outcome='accepted')

    def refresh_locked(self, *, clear_cache=False, remote_outcome='unattempted'):
        """Caller holds exclusive_lock; no retries, token classifier or remote repair."""
        phase, cleared, before = 'local validation', False, None
        try:
            if type(clear_cache) is not bool:
                raise LocalError('clear_cache must be boolean')
            config = load_config(self.store.root)
            state = self.store.load_consistent_state(require_cache=False)
            try:
                state = self.store.load_consistent_state()
            except LocalError:
                # Disposable content may be rebuilt, required state was checked above.
                pass
            if clear_cache:
                existed = (self.store.root / 'cache.json').exists()
                self.store.clear_cache()
                cleared = existed
            now = self.clock()
            d.instant_key(now)
            known = _known(state)
            phase = 'current retrieval'
            current = retrieve(self.transport, known.binding, prior=known,
                sync_token=state.sync_token, replace=clear_cache or state.snapshot is None,
                hidden_names=config.hidden_from_now)
            phase = 'lifecycle reconciliation'
            adapter = HistoryAdapter(self.transport, timezone=current.account.timezone)
            start = min((state.cursor, state.synced_at or state.cursor), key=d.instant_key)
            snapshot, history = _reconcile(current, known, state.history, adapter,
                                           start, now, state.cursor, config.hidden_from_now)
            phase = 'candidate preparation'
            candidates = prepare_candidates(snapshot, history,
                account_display=state.binding.account_display,
                sync_token=current.sync_token, synced_at=now,
                hidden_names=config.hidden_from_now)
            # Observe actual destinations: publisher supplies per-file atomicity,
            # not a transaction. This also distinguishes first replacement failure.
            names = ('cache.json', 'history.json', 'binding.json')
            before = self._bytes(names)
            phase = 'local publication'
            self.store.publish_snapshot(candidates)
            return SyncResult(self.store.load_consistent_state(), now,
                ('Explicit cache clearing occurred; unreported history was preserved. '
                 'Clearing does not fill historical coverage gaps.',) if cleared else
                ('Cache was already absent; unreported history was preserved.',) if clear_cache else (), cleared)
        except (LocalError, d.DomainError, HTTPFailure, OSError, KeyboardInterrupt) as error:
            started = before is not None and self._bytes(before.keys()) != before
            try:
                load_config(self.store.root)
                self.store.load_consistent_state(require_cache=False)
                permitted = True
            except (LocalError, OSError):
                permitted = False
            try:
                load_config(self.store.root)
                self.store.load_consistent_state()
                available = True
            except (LocalError, OSError):
                available = False
            failure = SyncError(phase, error, cache_cleared=cleared,
                publication_started=started, saved_state_available=available,
                refresh_permitted=permitted, remote_outcome=remote_outcome)
            if isinstance(error, KeyboardInterrupt):
                raise SyncInterrupted(failure) from None
            raise failure from error

    def _bytes(self, names):
        result = {}
        for name in names:
            path = self.store.root / name
            try:
                result[name] = read_bytes(path) if path.exists() else None
            except (LocalError, OSError):
                # Unknown bytes cannot establish that the old set survived.
                result[name] = object()
        return result


def read_local(*, store=None, clock=None):
    """Public offline entry point; no transport or credentials required."""
    return Synchronizer(None, store, clock=clock).read_local()


def refresh(transport, *, store=None, clock=None, clear_cache=False):
    """Public lock-owning refresh for an already syntax-validated read command."""
    return Synchronizer(transport, store, clock=clock).refresh(clear_cache=clear_cache)
