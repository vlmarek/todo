"""Report-only partial evidence. Never supplied to sync or cache publication."""
from dataclasses import dataclass, replace
from todo_lib import domain as d
from todo_lib.adapter.history import HistoryAdapter, _object
from todo_lib.adapter.current import CurrentError
from todo_lib.adapter.transport import HTTPFailure


@dataclass(frozen=True)
class Available:
    records: tuple = ()
    pages: tuple = ()
    start: object = None
    end: object = None
    complete: bool = False


class AccountRead:
    """Retain only independently checked identity across a failed Current read.

    No raw response is exposed to recovery or diagnostics. A mismatch poisons all
    command-local remote evidence; neither cached identity nor an HTTP success
    alone authorizes further account-scoped reads.
    """
    def __init__(self, transport, account_id, *, allow_delta=False):
        self.transport, self.account_id = transport, account_id
        self.allow_delta = allow_delta
        self.matched = False
        self.incompatible = False

    def request(self, *args, **kwargs):
        response = self.transport.request(*args, **kwargs)
        if isinstance(response, dict):
            if 'user' in response:
                user = response['user']
                if not isinstance(user, dict) or user.get('id') != self.account_id:
                    self.incompatible = True
                    raise CurrentError('authenticated account differs from binding; incompatible remote results discarded')
                self.matched = True
            elif self.allow_delta and response.get('full_sync') is False:
                # Same account inheritance as strict incremental Current mapping.
                self.matched = True
        return response


class ReportHistory(HistoryAdapter):
    def __init__(self, *args, override=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.override = override
        self.failures = []
        self.owners = {}
        self.removed_comments = set()
        self.comment_owners = {}
        self.partial = []
        self.page_evidence = []

    def _pages(self, endpoint, parameters, mapper, **kwargs):
        # Preserve strict page/cursor validation and retry bounds. Only report
        # records are isolated; a rejected row cannot certify complete evidence.
        scope = 'history ' + endpoint + ' (' + str(dict(parameters)) + ')'
        seen, conflicts = {}, set()
        def map_record(raw):
            if endpoint == '/comments' and isinstance(raw, dict) and isinstance(raw.get('id'), str):
                self.comment_owners.setdefault(raw['id'], set()).add(dict(parameters)['task_id'])
            try:
                return mapper(_object(raw))
            except d.DomainError as error:
                identity = raw.get('id') if isinstance(raw, dict) else None
                identity = d.scalar_title(str(identity)) if isinstance(identity, (str, int)) else 'unknown'
                if endpoint == '/comments' and isinstance(raw, dict) and isinstance(raw.get('id'), str):
                    self.rejected_comments.add(raw['id'])
                self.failures.append(scope + ': omitted record ' + identity + ': ' + str(error))
                return None
        for records, page in super()._pages(endpoint, parameters, map_record, **kwargs):
            records = tuple(r for r in records if r is not None)
            self.partial.extend(records)
            self.page_evidence.append(page)
            if endpoint == '/comments':
                for identity, comment in records:
                    if identity in seen and seen[identity] != comment:
                        conflicts.add(identity)
                        self.failures.append(scope + ': contradictory comment ' + d.scalar_title(identity) + '; omitted')
                    seen[identity] = comment
                # Let strict composition finish paging without feeding it a
                # rejected representation. _read removes the earlier one too.
                records = tuple(r for r in records if r[0] not in conflicts)
            yield records, page

    def _records(self, values, mapper):
        return tuple(mapper(value) for value in values)

    def _read(self, method, *args, owner_read=False, activity_read=False, **kwargs):
        self.partial, self.page_evidence = [], []
        self.rejected_comments = set()
        before = len(self.failures)
        try:
            result = method(*args, **kwargs)
            if len(self.failures) == before:
                return result
        except (d.DomainError, HTTPFailure) as error:
            if not self.override and not owner_read:
                raise
            self.failures.append(str(error))
        records = self.partial
        if owner_read:
            # Page mapping retains rejected pairs for this final exclusion.
            # No conflicting version can become current display text.
            seen, conflicts = {}, set(self.rejected_comments)
            for identity, comment in records:
                if identity in seen and seen[identity] != comment:
                    conflicts.add(identity)
                seen[identity] = comment
            for identity in sorted(conflicts):
                self.failures.append('history /comments task ' + d.scalar_title(args[0]) +
                    ': omitted unusable comment ' + d.scalar_title(identity))
            self.removed_comments.update(identity for identity, comment in records
                                         if comment is None and identity not in conflicts)
            records = [comment for identity, comment in seen.items()
                       if comment is not None and identity not in conflicts]
        elif activity_read:
            records = [e for e in records if d.instant_key(args[0]) < d.instant_key(e.event_date) <= d.instant_key(args[1])]
        return Available(tuple(records), tuple(self.page_evidence),
                         None if owner_read else args[0], None if owner_read else args[1])

    def completed(self, *args, **kwargs):
        return self._read(super().completed, *args, **kwargs)

    def activities(self, *args, **kwargs):
        return self._read(super().activities, *args, activity_read=True, **kwargs)

    def _comments(self, owner, *args, **kwargs):
        key = (owner, None if kwargs.get('required_ids') is None else frozenset(kwargs['required_ids']))
        if (owner, None) in self.owners:
            return self.owners[(owner, None)]
        if key not in self.owners:
            self.owners[key] = self._read(super()._comments, owner, *args, owner_read=True, **kwargs)
        return self.owners[key]


def recover(state, current, completed, activities, adapter, start, end, override, diagnostics):
    """Build a validated display only, omitting owners without safe ancestry."""
    from .sync import _known
    known = _known(state)
    base = current.snapshot if current is not None else replace(known, items={}, comments={}, reminders={}, occurrences={})
    records = list(completed.records)
    events = [e for e in activities.records if e.owner_id in known.items or e.owner_id in base.items
              or e.project_id is None or e.project_id in base.categories or e.project_id == base.root.id]
    historical = {r.item.id: r.item for r in sorted(records, key=lambda r: d.instant_key(r.occurrence.completed_at)) if not r.deleted}
    items = {**(known.items if override else {}), **historical, **base.items}
    removed = set() if current is None else set(current.deleted_ids | current.departed_ids)
    removed.update(r.item.id for r in records if r.deleted)
    removed.update(e.object_id for e in events if e.object_type == 'item' and e.event_type == 'deleted')
    removed = d.descendant_ids(items.values(), removed)
    items = {k: i for k, i in items.items() if k not in removed and i.category_id in base.categories}
    unsafe_lifecycle = {k for k, i in historical.items() if not i.completed and k not in base.items
                        and (not override or k not in known.items)}
    for identity in sorted(unsafe_lifecycle):
        diagnostics.append('omitted task ' + d.scalar_title(identity) + ': historical open/recurring owner lacks safe current lifecycle context')
    items = {k: i for k, i in items.items() if k not in unsafe_lifecycle}
    fallback = set(items) - (historical.keys() | base.items.keys())
    # Resolve each owner independently; never invent parentage or promote a step.
    def safe(identity, path=frozenset()):
        if identity in path or identity not in items:
            return False
        parent = items[identity].parent_id
        return parent is None or (parent in items and items[parent].category_id == items[identity].category_id
                                  and safe(parent, path | {identity}))
    invalid = {k for k in items if not safe(k)}
    # Mixed observations can conflict even when each saved/fresh source was
    # independently valid. Validate owner closures, dropping only unsafe owners.
    for identity in sorted(set(items) - invalid):
        closure, ancestor = {}, identity
        while ancestor is not None:
            closure[ancestor] = items[ancestor]
            ancestor = items[ancestor].parent_id
        try:
            d.validate(replace(base, items=closure, comments={}, reminders={}, occurrences={}),
                       cached_owner_ids=set(closure) - base.items.keys())
        except d.DomainError as error:
            invalid.add(identity)
            diagnostics.append('omitted task ' + d.scalar_title(identity) + ' (' + d.scalar_title(items[identity].title) + '): unsafe mixed context: ' + str(error))
    for identity in sorted(invalid):
        diagnostics.append('omitted task ' + d.scalar_title(identity) + ' (' + d.scalar_title(items[identity].title) + '): unresolved ancestor/parent field')
    items = {k: i for k, i in items.items() if k not in invalid}
    fallback &= items.keys()
    removed_comments = set() if current is None else set(current.removed_comment_ids)
    removed_comments.update(e.object_id for e in events if e.object_type == 'note' and e.event_type == 'deleted')
    comments = {k: c for k, c in base.comments.items() if k not in removed_comments}
    note_events = [e for e in events if e.object_type == 'note' and e.event_type in ('added', 'updated') and d.instant_key(start) < d.instant_key(e.event_date) <= d.instant_key(end)]
    owners = (set(historical) | {e.owner_id for e in note_events}) - base.items.keys() - removed
    owner_results = {}
    for owner in sorted(owners):
        required = {e.object_id for e in note_events if e.owner_id == owner}
        result = adapter._comments(owner, required_ids=required if owner not in items else None) if adapter is not None else Available()
        owner_results[owner] = result
        if adapter is not None:
            removed_comments.update(adapter.removed_comments)
        for comment in result.records:
            if owner in items and comment.id not in removed_comments:
                comments[comment.id] = comment
    # Identity is global, even though REST ownership comes from each request.
    # Include earlier reconciliation reads and Sync notes, not just the last
    # representation assigned to the display dictionary.
    ownership = {} if adapter is None else {k: set(v) for k, v in adapter.comment_owners.items()}
    for comment in base.comments.values():
        ownership.setdefault(comment.id, set()).add(comment.item_id)
    conflicts = {identity for identity, assigned in ownership.items() if len(assigned) > 1}
    for identity in sorted(conflicts):
        diagnostics.append('history /comments and current Sync: omitted incompatible comment ownership ' +
            d.scalar_title(identity) + ' across tasks ' +
            ', '.join(d.scalar_title(owner) for owner in sorted(ownership[identity])))
        comments.pop(identity, None)
    # A saved comment can survive unusable fresh evidence only with its own
    # bound owner context and qualifying activity; mark that context as cached.
    for owner, result in owner_results.items():
        if override:
            required = {e.object_id for e in note_events if e.owner_id == owner}
            for identity, comment in known.comments.items():
                if (comment.item_id == owner and identity in required and owner in items
                        and identity not in comments and identity not in removed_comments
                        and (identity in conflicts or not getattr(result, 'endpoint', None))):
                    comments[identity] = comment
                    fallback.add(owner)
    for event in events:
        if not (d.instant_key(start) < d.instant_key(event.event_date) <= d.instant_key(end)) or event.owner_id in removed:
            continue
        if event.object_type == 'item' and event.event_type == 'completed' and event.object_id not in items:
            diagnostics.append('omitted completion task ' + d.scalar_title(event.object_id) + ': unresolved owner/lifecycle context')
        if event in note_events and (event.owner_id not in items or event.object_id not in comments
                                    or comments[event.object_id].item_id != event.owner_id):
            diagnostics.append('omitted comment ' + d.scalar_title(event.object_id) + ' task ' + d.scalar_title(event.owner_id) + ': missing owner/ancestor or surviving comment text')
    comments = {k: c for k, c in comments.items() if c.item_id in items and k not in removed_comments}
    if override:
        for identity, comment in known.comments.items():
            if comment.item_id in items and not any(e.object_id == identity for e in note_events):
                diagnostics.append('omitted cached comment ' + d.scalar_title(identity) + ': add/edit activity timing unproved; creation/observation time is not edit activity')
        retained = [o for o in known.occurrences.values() if o.item_id in items]
    else:
        retained = []
    # Fresh reopen beats saved completion and completion-only historical fields.
    from .completion import event_key
    lifecycle = {}
    for event in sorted(events, key=event_key):
        if event.object_type == 'item' and event.event_type in ('completed', 'uncompleted'):
            lifecycle[event.object_id] = event
    reopened = {identity for identity, event in lifecycle.items() if event.event_type == 'uncompleted'
                and not any(r.item.id == identity and not r.deleted
                    and d.instant_key(r.occurrence.completed_at) > d.instant_key(event.event_date) for r in records)}
    for identity in reopened - base.items.keys():
        if identity in items and not items[identity].recurring:
            items[identity] = replace(items[identity], completed=False, completed_at=None)
    reopened |= {k for k, i in base.items.items() if not i.completed and not i.recurring}
    retained = [o for o in retained if o.item_id not in reopened or items[o.item_id].recurring]
    records = [r for r in records if r.item.id in items and not r.deleted and (r.item.id not in reopened or items[r.item.id].recurring)]
    fallback.update(o.item_id for o in retained if not o.undone and d.instant_key(start) < d.instant_key(o.completed_at) <= d.instant_key(end))
    if override:
        for identity in sorted(fallback):
            when = state.history.observations.get(identity, state.synced_at if state.snapshot is not None and identity in state.snapshot.items else None)
            diagnostics.append('cached fallback task ' + d.scalar_title(identity) + ' (' + d.scalar_title(items[identity].title) + '), last observed ' + (d.instant_text(when) if when is not None else 'unknown') + '; title, hierarchy, category, completion and Hidden state may be stale')
    # _select uses the shared completion reconciliation; retained evidence remains
    # explicit rather than fabricated activity events.
    occurrences = {o.id: o for o in retained}
    snapshot = d.validate(replace(base, items=items, comments=comments, reminders={}, occurrences=occurrences), cached_owner_ids=set(items) - base.items.keys())
    annotations = {}
    for identity in fallback:
        when = state.history.observations.get(identity, state.synced_at if state.snapshot is not None and identity in state.snapshot.items else None)
        annotations[identity] = ('cached fallback; observed ' + (d.instant_text(when) if when is not None else 'unknown') + '; context/state may be stale')
    return snapshot, Available(tuple(records)), Available(tuple(events)), annotations
