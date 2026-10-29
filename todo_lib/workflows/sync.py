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
from todo_lib.adapter.history import CompletedRecord, HistoryAdapter, Retrieval
from todo_lib.adapter.transport import HTTPFailure
from todo_lib.local import (StateStore, LocalState, LocalError, History, load_config,
                            exclusive_lock, merge_history, prepare_candidates)
from todo_lib.local.safety import read_bytes
from .completion import reconcile_completions


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


class OperationEvidence:
    """Share command-local lifecycle facts and exhausted, explicitly scoped reads."""
    def __init__(self, adapter, result):
        self.adapter = adapter
        self.reads = tuple(e for e in result.evidence if isinstance(e, Retrieval))
        # Command-local current lifecycle facts are not interval coverage.
        self.lifecycle_records = tuple(e for e in result.evidence if isinstance(e, CompletedRecord))
        self.lifecycle_ids = ({result.target_id} if result.operation.type in
            ('item_close', 'item_complete', 'item_update_date_complete', 'item_uncomplete') else set())

    def _read(self, endpoint, start, end, scope):
        for evidence in self.reads:
            if (evidence.endpoint == endpoint and dict(evidence.scope) == dict(scope or {})
                    and evidence.start is not None and evidence.end is not None
                    and d.instant_key(evidence.start) <= d.instant_key(start)
                    and d.instant_key(evidence.end) >= d.instant_key(end)):
                activity = endpoint == '/activities'
                records = tuple(r for r in evidence.records if
                    d.instant_key(start) < d.instant_key(r.event_date if activity else r.occurrence.completed_at)
                    <= d.instant_key(end))
                return replace(evidence, records=records, start=start, end=end)
        return None

    def completed(self, start, end, scope=None):
        return self._read('/tasks/completed/by_completion_date', start, end, scope) or self.adapter.completed(start, end, scope)

    def activities(self, start, end, scope=None):
        return self._read('/activities', start, end, scope) or self.adapter.activities(start, end, scope)

    def comments(self, owner):
        for evidence in self.reads:
            if (evidence.endpoint == '/comments' and evidence.owner_id == owner
                    and evidence.required_ids is None):
                return evidence
        return self.adapter.comments(owner)


def affected_ids(result, known, current):
    """Known subtree and ancestry remain required operation context."""
    items = {**known.items, **current.snapshot.items}
    op = result.operation
    ids = {result.target_id} if op.type.startswith('item_') else {op.args.get('item_id')}
    resource = 'comments' if op.type.startswith('note_') else 'reminders' if op.type.startswith('reminder_') else None
    if resource is not None:
        for snapshot in (known, current.snapshot):
            value = getattr(snapshot, resource).get(result.target_id)
            if value is not None:
                ids.add(value.item_id)
    ids.discard(None)
    roots = set(ids)
    while True:
        expanded = ids | {i.id for i in (*known.items.values(), *current.snapshot.items.values()) if i.parent_id in ids}
        if expanded == ids:
            break
        ids = expanded
    for identity in roots:
        seen = set()
        while identity in items and identity not in seen:
            seen.add(identity)
            identity = items[identity].parent_id
            ids.add(identity)
    return ids - {None}


def _reconcile(current, known, history, adapter, start, end, cursor, hidden_names, *, affected=None):
    s = current.snapshot
    removed = set(current.deleted_ids | current.departed_ids)
    # Explicit parent deletion/scope departure removes its known subtree too.
    while True:
        expanded = removed | {i.id for i in {**known.items, **s.items}.values() if i.parent_id in removed}
        if expanded == removed:
            break
        removed = expanded
    missing = set(known.items) - s.items.keys() - removed
    deferred = set() if affected is None else {k for k in missing
        if known.items[k].completed and k not in affected}
    missing -= deferred
    items, occurrences = dict(s.items), dict(s.occurrences)
    def retained(item):
        if (known.account.timezone != s.account.timezone and item.attention is not None
                and item.attention.kind == 'floating'):
            if item.attention.raw_due is None:
                raise d.DomainError('retained floating attention requires original due metadata')
            return replace(item, attention=d.resolve_remote_due(item.attention.raw_due, s.account.timezone))
        return item

    items.update({k: retained(known.items[k]) for k in deferred})
    recurring = {i.id for i in s.items.values() if i.recurring}
    if affected is not None:
        recurring &= affected
        if isinstance(adapter, OperationEvidence):
            recurring &= adapter.lifecycle_ids
    records = []
    if isinstance(adapter, OperationEvidence):
        records = [r for e in adapter.reads if e.endpoint == '/tasks/completed/by_completion_date'
                   for r in e.records if r.item.id in affected]
        records.extend(r for r in adapter.lifecycle_records if r.item.id in affected)
    if missing or recurring:
        # A bounded supported endpoint, never active absence, proves completion.
        categories = s.categories if affected is None else {
            (s.items.get(k) or known.items[k]).category_id for k in missing | recurring}
        for category in sorted(categories):
            records.extend(adapter.completed(start, end, {'project_id': category}).records)
        if affected is not None:
            # Returned ancestry may differ from saved ancestry. Retain only the
            # required owner closure from a complete category-scoped response.
            needed = affected | missing
            while True:
                expanded = needed | {r.item.parent_id for r in records if r.item.id in needed
                                     and r.item.parent_id is not None}
                if expanded == needed:
                    break
                needed = expanded
            records = [r for r in records if r.item.id in needed]
            affected = needed
        latest = {}
        for record in records:
            item = record.item
            # Do not retain unrelated returned data, even from an overbroad server.
            if item.category_id not in s.categories or item.id in removed:
                continue
            if item.id in s.items:
                continue  # current truth always supersedes historical fields
            if item.id not in missing:
                if affected is not None and item.id not in affected:
                    continue
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
            elif identity in known.items and known.items[identity].completed:
                # Omission does not retract an already established completion.
                items[identity] = retained(known.items[identity])
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
        if identity in deferred:
            comments.update({k: c for k, c in known.comments.items()
                             if c.item_id == identity and k not in s.comments
                             and k not in current.removed_comment_ids})
            continue
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
    events = []
    for identity in sorted(recurring):
        events.extend(adapter.activities(start, end,
            {'object_type': 'item', 'object_id': identity}).records)
    occurrences = reconcile_completions(items, records, events, occurrences.values())
    reminders = {k: r for k, r in known.reminders.items()
                 if r.item_id in items and r.item_id not in s.items
                 and (current.reminder_ids is None or k in current.reminder_ids)}
    reminders.update(s.reminders)
    reminders = {k: r for k, r in reminders.items() if r.item_id in items}
    # Resolve final active reminder records against authoritative historical owners.
    from todo_lib.adapter.current import _reminder, _signature
    for raw in current.unresolved_reminders:
        owner = raw['item_id']
        if owner in removed:
            continue
        if owner not in items:
            raise d.DomainError('unresolved reminder owner ' + owner)
        for left, right in current.reminder_duplicates:
            if right['id'] == raw['id'] and _signature(left, 'reminders') != _signature(right, 'reminders'):
                raise d.DomainError('contradictory live reminders representations ' + raw['id'])
        reminders[raw['id']] = _reminder(raw, s.account.timezone)
    if known.account.timezone != s.account.timezone:
        reminders = {k: replace(r, due=d.resolve_reminder_due(r.due.raw_due, s.account.timezone))
            if r.type == 'absolute' and r.due.kind == 'floating' else r
            for k, r in reminders.items()}
    snapshot = d.validate(replace(s, items=items, comments=comments,
        reminders=reminders, occurrences=occurrences), hidden_names)
    observed = set(items) if affected is None else set(affected)
    if affected is not None:
        observed |= {k for k, item in s.items.items() if item != known.items.get(k)}
        for collection in ('comments', 'reminders'):
            old, new = getattr(known, collection), getattr(s, collection)
            observed |= {value.item_id for k, value in {**old, **new}.items()
                         if value.item_id in s.items and old.get(k) != new.get(k)}
    incoming = History(snapshot, {k: end for k in items if k in observed and k not in deferred})
    removed_comments = set(history.snapshot.comments) - comments.keys()
    # Resolve removals and rebase the entire retained context before merge's
    # validation. Unioning old reminders here would resurrect tombstones in the
    # old timezone, even though the final candidate already supersedes them.
    base = replace(history, snapshot=snapshot,
                   observations={k: v for k, v in history.observations.items() if k in items})
    pending = merge_history(base, incoming, removed_item_ids=removed,
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

    def reconcile_accepted_locked(self, result=None):
        """Call after EACH accepted gateway operation, before any next mutation.

        Raises with remote_outcome='accepted' even if retrieval or publication fails.
        Unknown/rejected gateway outcomes must not call this acceptance boundary.
        result is the exact Gateway Result from this operation. Matching complete
        after/scoped Retrieval evidence is reused, while uncovered required state
        is fetched. Omitting result retains full refresh policy for legacy callers
        and provisioning. No report cursor/coverage advancement or pruning occurs.
        """
        return self.refresh_locked(remote_outcome='accepted', operation_result=result)

    def refresh_locked(self, *, clear_cache=False, remote_outcome='unattempted', operation_result=None):
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
            if operation_result is not None and not operation_result.accepted:
                raise d.DomainError('accepted operation result required')
            current = operation_result.after if (operation_result is not None
                and operation_result.before_token == state.sync_token) else None
            if current is not None and (current.current_snapshot != current.snapshot
                    or current.binding.account_id != known.binding.account_id
                    or current.binding.root_id != known.binding.root_id):
                raise d.DomainError('incompatible operation current evidence')
            if current is None:
                current = retrieve(self.transport, known.binding, prior=state.current_snapshot or known,
                    sync_token=state.sync_token, replace=clear_cache or state.current_snapshot is None or state.waiting_label_ids is None,
                    hidden_names=config.hidden_from_now, known=known, waiting_label_ids=state.waiting_label_ids, reminder_ids=state.current_reminder_ids)
            phase = 'lifecycle reconciliation'
            adapter = HistoryAdapter(self.transport, timezone=current.account.timezone)
            # Cursor-bound coverage includes every deferred pending interval;
            # synced_at may widen that bound but can never advance it.
            start = min((state.cursor, state.synced_at or state.cursor), key=d.instant_key)
            affected = None
            upper = now
            if operation_result is not None:
                affected = affected_ids(operation_result, known, current)
                adapter = OperationEvidence(adapter, operation_result)
                # The gateway's completed read proves this operation's transition.
                # Wider coverage is still required for unrelated active disappearances.
                missing_open = {k for k, i in known.items.items() if not i.completed
                    and k not in current.snapshot.items and k not in current.deleted_ids | current.departed_ids}
                for evidence in adapter.reads:
                    if (evidence.endpoint == '/tasks/completed/by_completion_date'
                            and missing_open <= affected and evidence.start is not None):
                        start, upper = evidence.start, evidence.end
                        break
            snapshot, history = _reconcile(current, known, state.history, adapter,
                                           start, upper, state.cursor, config.hidden_from_now, affected=affected)
            if operation_result is not None and operation_result.operation.type == 'item_delete':
                target = operation_result.target_id
                ancestors = {i.id for i in d.ancestors(known, target)} if target in known.items else set()
                if target in snapshot.items or not ({target} | ancestors) & current.deleted_ids:
                    raise d.DomainError('accepted deletion lacks authoritative deletion evidence')
            phase = 'candidate preparation'
            candidates = prepare_candidates(snapshot, history,
                account_display=state.binding.account_display,
                sync_token=current.sync_token, synced_at=now, current_snapshot=current.snapshot,
                waiting_label_ids=current.waiting_label_ids, current_reminder_ids=current.reminder_ids,
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
