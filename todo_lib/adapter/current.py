"""Current API-v1 Sync retrieval, without persistence or lifecycle guesses.

retrieve(transport, binding, *, prior=None, sync_token=None, replace=False)
returns Current(snapshot, sync_token, disappeared_ids, deleted_ids, departed_ids).
The snapshot exposes newly enrolled direct-child categories in snapshot.binding.
`prior` is a complete managed Snapshot, never an unscoped provider cache. Missing
known items are evidence requests for lifecycle reconciliation, not completions.
Callers publish snapshot/token together only after this function returns.

Wire authority: retained api-v1.openapi.json, Sync tag (Read resources,
Incremental sync, Projects, Tasks, Task comments, Reminders, User plan limits),
Due dates tag and ItemSyncView/NoteSyncView; inspected 2026-10-26. There is no
pinned invalid-sync-token discriminator. No HTTP error triggers replacement.
Project sharing follows required boolean is_shared in PersonalProjectSyncView/
WorkspaceProjectSyncView (inspected 2026-10-26); the retained Sync prose says
shared instead. Only the typed-schema spelling is supported.
"""
from copy import deepcopy
from dataclasses import dataclass, replace as dataclass_replace
import json

from todo_lib.domain import (
    Account, Binding, Capabilities, Comment, DomainError, Item, Project, Reminder,
    Snapshot, account_timezone, enroll_categories, instant_from_wire, instant_key, instant_text,
    resolve_remote_due, resolve_reminder_due, validate, incoming_text,
)
from .transport import HTTPFailure, Replay

RESOURCE_TYPES = ('user', 'user_plan_limits', 'projects', 'items', 'labels',
                  'notes', 'reminders')
_COLLECTIONS = RESOURCE_TYPES[2:]
_FIELDS = {
    'projects': ('id', 'name', 'parent_id', 'is_shared', 'inbox_project',
                 'workspace_id', 'is_archived', 'is_deleted'),
    'items': ('id', 'project_id', 'parent_id', 'content', 'description', 'priority',
              'checked', 'labels', 'due', 'added_at', 'completed_at', 'is_deleted'),
    'notes': ('id', 'item_id', 'content', 'posted_at', 'is_deleted'),
    'reminders': ('id', 'item_id', 'type', 'minute_offset', 'due', 'notify_uid', 'is_urgent', 'is_deleted'),
    'labels': ('id', 'name', 'is_deleted'),
}
_DUE_FIELDS = ('date', 'timezone', 'string', 'lang', 'is_recurring')


class CurrentError(DomainError):
    """Malformed Sync contract or unsupported managed state; no partial result."""


@dataclass(frozen=True)
class Current:
    """Mapped active truth plus final reminder facts awaiting lifecycle owners.

    unresolved_reminders/reminder_duplicates are transient provider evidence for
    Synchronizer; they are never stored without scope and model validation.
    reminder_ids distinguishes authoritative omission/deletion from a legacy
    caller's unspecified reminder resource. Full hydration replaces all these
    facts; no superseded historical contradiction tracker is maintained.
    current_snapshot explicitly identifies the proven Sync baseline for composed
    callers whose snapshot also carries archived context. Legacy constructors
    omit it and Gateway hydrates once instead of treating context as active.
    """
    snapshot: Snapshot
    sync_token: str
    disappeared_ids: frozenset[str] = frozenset()
    deleted_ids: frozenset[str] = frozenset()
    departed_ids: frozenset[str] = frozenset()
    unresolved_reminders: tuple = ()
    reminder_duplicates: tuple = ()
    reminder_ids: frozenset[str] | None = None
    current_snapshot: Snapshot | None = None
    waiting_label_ids: frozenset[str] | None = None
    removed_comment_ids: frozenset[str] = frozenset()

    @property
    def account(self):
        return self.snapshot.account

    @property
    def binding(self):
        return self.snapshot.binding


def _object(value, field):
    if not isinstance(value, dict):
        raise CurrentError(field + ' must be an object')
    return value


def _required(obj, field):
    if field not in obj:
        raise CurrentError('missing required ' + field)
    return obj[field]


def _id(value, field):
    if not isinstance(value, str) or not value:
        raise CurrentError(field + ' must be a nonempty string ID')
    return value


def _parent(value, field):
    return None if value is None else _id(value, field)


def _bool(value, field):
    if type(value) is not bool:
        raise CurrentError(field + ' must be a boolean')
    return value


def _timestamp(obj, field):
    value = _required(obj, field)
    return None if value is None else instant_from_wire(value)


def _account(user, limits, binding):
    uid = _id(_required(_object(user, 'user'), 'id'), 'user.id')
    if uid != binding.account_id:
        raise CurrentError('authenticated account differs from binding')
    tz = _required(_object(_required(user, 'tz_info'), 'tz_info'), 'timezone')
    account_timezone(tz)
    current = _object(_required(_object(limits, 'user_plan_limits'), 'current'),
                      'user_plan_limits.current')
    activity = _bool(_required(current, 'activity_log'), 'activity_log')
    reminders = _bool(_required(current, 'reminders'), 'reminders')
    days = _required(current, 'activity_log_limit')
    if type(days) is not int or days < -1:
        raise CurrentError('activity_log_limit must be -1 or a nonnegative integer')
    return Account(uid, tz, Capabilities(reminders, activity, days))


def _project(raw):
    _bool(_required(raw, 'is_deleted'), 'project.is_deleted')
    if 'is_shared' not in raw:
        raise CurrentError('missing required project.is_shared; expected boolean')
    value = raw['is_shared']
    if value is None:
        raise CurrentError('project.is_shared is null; expected boolean')
    shared = _bool(value, 'project.is_shared')
    archived = _bool(_required(raw, 'is_archived'), 'project.is_archived')
    inbox = _bool(raw.get('inbox_project', False), 'project.inbox_project')
    workspace = raw.get('workspace_id')
    # The Projects table uses strings; its retained example also uses an integer.
    if type(workspace) is int and workspace >= 0:
        workspace = str(workspace)
    if workspace is not None:
        _id(workspace, 'project.workspace_id')
    return Project(raw['id'], _required(raw, 'name'),
                   _parent(_required(raw, 'parent_id'), 'project.parent_id'),
                   not (shared or inbox or workspace is not None), shared,
                   workspace, archived, raw['is_deleted'])


def _item(raw, zone):
    _bool(_required(raw, 'is_deleted'), 'item.is_deleted')
    completed = _bool(_required(raw, 'checked'), 'item.checked')
    priority = _required(raw, 'priority')
    if type(priority) is not int or priority not in (1, 2, 3, 4):
        raise CurrentError('item.priority must be 1 through 4')
    labels = _required(raw, 'labels')
    if not isinstance(labels, list) or any(not isinstance(x, str) or not x for x in labels):
        raise CurrentError('item.labels must contain label names')
    description = raw.get('description')
    if description is None:
        description = ''
    if not isinstance(description, str):
        raise CurrentError('item.description must be text or null')
    title = incoming_text(_required(raw, 'content'), title=True)
    description = incoming_text(description, description=True)
    due = _required(raw, 'due')
    _due(due)
    return Item(raw['id'], raw['project_id'], title,
                _parent(_required(raw, 'parent_id'), 'item.parent_id'),
                description, 5 - priority, resolve_remote_due(due, zone),
                frozenset(labels), _timestamp(raw, 'added_at'), completed,
                _timestamp(raw, 'completed_at'))


def _due(due):
    """Validate consumed task recurrence metadata; timezone omission is null."""
    if due is not None:
        _object(due, 'due')
        for field in _DUE_FIELDS:
            if field != 'timezone':
                _required(due, field)
        _bool(due['is_recurring'], 'due.is_recurring')
        if not isinstance(due['string'], str) or not isinstance(due['lang'], str):
            raise CurrentError('due.string and due.lang must be strings')


def _seed(snapshot):
    """Reconstruct only consumed wire facts, preserving exact timestamp values."""
    state = {name: {} for name in _COLLECTIONS}
    for p in (snapshot.root, *snapshot.categories.values()):
        state['projects'][p.id] = dict(id=p.id, name=p.name, parent_id=p.parent_id,
            is_shared=p.shared, workspace_id=p.workspace_id, is_archived=p.archived,
            is_deleted=p.deleted)
    def stamp(value):
        return None if value is None else instant_text(value)
    for i in snapshot.items.values():
        if i.attention is not None and i.attention.raw_due is None:
            raise CurrentError('prior attention requires original wire due metadata; request replacement')
        state['items'][i.id] = dict(id=i.id, project_id=i.category_id,
            parent_id=i.parent_id, content=i.title, description=i.description,
            priority=5-i.priority, checked=i.completed, labels=list(i.labels),
            due=deepcopy(i.attention.raw_due) if i.attention else None,
            added_at=stamp(i.added_at), completed_at=stamp(i.completed_at), is_deleted=False)
    for c in snapshot.comments.values():
        state['notes'][c.id] = dict(id=c.id, item_id=c.item_id, content=c.body,
            posted_at=stamp(c.added_at), is_deleted=False)
    for r in snapshot.reminders.values():
        state['reminders'][r.id] = dict(id=r.id, item_id=r.item_id, type=r.type,
            minute_offset=r.minutes, due=deepcopy(r.due.raw_due if r.type == 'absolute' else r.raw_due), is_deleted=False)
        if r.type == 'absolute' and r.due.raw_due is None:
            if r.due.kind == 'floating':
                raise CurrentError('prior floating reminder requires original wire due metadata')
            from .commands import due_arguments
            state['reminders'][r.id]['due'] = due_arguments(r.due)
            if r.due.zone is not None:
                state['reminders'][r.id]['due']['timezone'] = r.due.zone
        for name in ('notify_uid', 'is_urgent'):
            if getattr(r, name) is not None:
                state['reminders'][r.id][name] = getattr(r, name)
    return state


def _signature(raw, name):
    """Compare consumed wire values without bool/int coercion or time rounding."""
    normalized = {k: v for k, v in raw.items() if k in _FIELDS[name]}
    if name == 'reminders':
        normalized.pop('due' if raw.get('type') == 'relative' else 'minute_offset', None)
        if raw.get('type') == 'absolute' and isinstance(raw.get('due'), dict):
            normalized['due'] = {k: v for k, v in raw['due'].items() if k in _DUE_FIELDS}
            # Match the reminder mapper's supported defaults without changing
            # retained wire data or treating supplied invalid values as absent.
            normalized['due'].setdefault('timezone', None)
            normalized['due'].setdefault('is_recurring', False)
    if name == 'notes':
        normalized['content'] = incoming_text(raw.get('content', ''))
    if name == 'items' and isinstance(raw.get('due'), dict):
        normalized['due'] = {k: raw['due'].get(k) for k in _DUE_FIELDS}
    if name == 'items':
        normalized['description'] = raw.get('description') if raw.get('description') is not None else ''
        timestamps = ('added_at', 'completed_at')
    else:
        timestamps = ('posted_at',) if name == 'notes' else ()
    for field in timestamps:
        if field in raw and raw[field] is not None:
            try:
                normalized[field] = ['instant', str(instant_key(instant_from_wire(raw[field])))]
            except DomainError:
                # Ownership-first validation still belongs to mapping.
                normalized[field] = ['invalid', raw[field]]
    return json.dumps(normalized, sort_keys=True)


def _merge(state, response, full):
    """Whole changed resources replace earlier resources; omissions retain state."""
    for name in _COLLECTIONS:
        if name not in response and not full:
            continue
        records = _required(response, name)
        if not isinstance(records, list):
            raise CurrentError(name + ' must be an array')
        live = {}
        for value in records:
            raw = _object(value, name + ' record')
            identity = _id(_required(raw, 'id'), name + '.id')
            raw = {k: deepcopy(raw[k]) for k in _FIELDS[name] if k in raw}
            if name == 'labels':
                relevant = state.setdefault('_waiting_seen', set())
                if raw.get('name') == 'waiting':
                    relevant.add(identity)
                if identity in relevant:
                    raw['is_deleted'] = _bool(raw.get('is_deleted', False), 'label.is_deleted')
                    if not raw['is_deleted']:
                        _id(_required(raw, 'name'), 'label.name')
            if name == 'items' and isinstance(raw.get('due'), dict):
                raw['due'] = {k: raw['due'][k] for k in _DUE_FIELDS if k in raw['due']}
            if raw.get('is_deleted') is not True:
                if identity in live:
                    state.setdefault('_duplicates', []).append((name, live[identity], raw))
                live[identity] = raw
            # Retain tombstones transiently for ordering and lifecycle evidence.
            state[name][identity] = raw


def _check_duplicates(state, projects, items):
    """Defer unused body comparisons until scope is established; context is strict."""
    contexts = {'projects': ('parent_id', 'is_deleted'),
                'items': ('project_id', 'is_deleted'),
                'notes': ('item_id', 'is_deleted'),
                'reminders': ('item_id', 'is_deleted'),
                'labels': ('is_deleted',)}
    for name, left, right in state.get('_duplicates', ()):
        if state[name][right['id']].get('is_deleted') is True:
            continue
        context = contexts[name]
        if any(left.get(k) != right.get(k) for k in context):
            raise CurrentError('contradictory ' + name + ' ownership/lifecycle ' + right['id'])
        if name == 'projects':
            relevant = right['id'] in projects
        elif name == 'items':
            relevant = _id(_required(right, 'project_id'), 'item.project_id') in projects
        elif name in ('notes', 'reminders'):
            relevant = _id(_required(right, 'item_id'), name + '.item_id') in items
        else:
            relevant = right['id'] in state.get('_waiting_seen', ())
        if relevant and _signature(left, name) != _signature(right, name):
            raise CurrentError('contradictory live ' + name + ' representations ' + right['id'])


def _projects(state, binding, known_items):
    projects = state['projects']
    root_raw = projects.get(binding.root_id)
    if root_raw is None or root_raw.get('is_deleted') is True:
        raise CurrentError('bound root disappeared or was deleted')
    root = _project(root_raw)
    categories = {}
    for identity, raw in projects.items():
        if raw.get('is_deleted') is not True:
            _parent(_required(raw, 'parent_id'), 'project.parent_id')
        if identity in binding.category_ids or raw.get('parent_id') == root.id:
            if raw.get('is_deleted') is True:
                continue
            categories[identity] = _project(raw)
    # Refuse moved/archived/shared bound records; enrollment also checks root.
    binding = enroll_categories(binding, root, categories, known_items)
    return root, categories, binding


def _reminder(raw, zone):
    """Map only the actual type's schedule, preserving retained ID metadata."""
    owner = _id(_required(raw, 'item_id'), 'reminder.item_id')
    _bool(_required(raw, 'is_deleted'), 'reminder.is_deleted')
    metadata = {}
    if 'notify_uid' in raw:
        metadata['notify_uid'] = _id(raw['notify_uid'], 'reminder.notify_uid')
    if 'is_urgent' in raw:
        metadata['is_urgent'] = _bool(raw['is_urgent'], 'reminder.is_urgent')
    kind = _required(raw, 'type')
    if kind == 'relative':
        minutes = _required(raw, 'minute_offset')
        if type(minutes) is not int or minutes < 0:
            raise CurrentError('minute_offset must be a nonnegative integer')
        return Reminder(raw['id'], owner, minutes, raw_due=deepcopy(raw.get('due')), **metadata)
    if kind == 'absolute':
        return Reminder(raw['id'], owner, type=kind,
                        due=resolve_reminder_due(_required(raw, 'due'), zone), **metadata)
    raise CurrentError('managed reminder type unsupported: ' + str(kind))


def _map(state, binding, account, prior, hidden_names, known=None):
    known_items = (known or prior).items if (known or prior) else {}
    root, categories, binding = _projects(state, binding, known_items)
    items, deleted, departed = {}, set(), set()
    for identity, raw in state['items'].items():
        if raw.get('is_deleted') is True:
            if identity in known_items:
                deleted.add(identity)
            continue
        project_id = _id(_required(raw, 'project_id'), 'item.project_id')
        if project_id not in categories:
            if project_id == root.id:
                raise CurrentError('managed items cannot belong directly to the root project')
            if identity in known_items:
                departed.add(identity)
            continue
        try:
            items[identity] = _item(raw, account.timezone)
        except DomainError as error:
            raise CurrentError(f'item {identity}: {error}') from error
    comments, reminders = {}, {}
    for name in ('notes', 'reminders'):
        for raw in state[name].values():
            if raw.get('is_deleted') is True:
                continue
            owner = _id(_required(raw, 'item_id'), name + '.item_id')
            if owner not in items:
                continue
            _bool(_required(raw, 'is_deleted'), name + '.is_deleted')
            if name == 'notes':
                try:
                    comments[raw['id']] = Comment(raw['id'], owner,
                        incoming_text(raw.get('content', '')), _timestamp(raw, 'posted_at'))
                except DomainError as error:
                    raise CurrentError(f'comment {raw["id"]} owner {owner}: {error}') from error
            else:
                reminders[raw['id']] = _reminder(raw, account.timezone)
    _check_duplicates(state, {root.id, *categories}, set(items))
    occurrences = {k: o for k, o in (prior.occurrences.items() if prior else ())
                   if o.item_id in items}
    snapshot = validate(Snapshot(binding, account, root, categories, items,
                                 comments, reminders, occurrences), hidden_names)
    missing = set(known_items) - items.keys() - deleted - departed
    return snapshot, frozenset(missing), frozenset(deleted), frozenset(departed)


def _read(transport, token):
    try:
        response = transport.request('POST', '/sync', operation='current Sync',
            replay=Replay.READ, form={'sync_token': token,
                'resource_types': json.dumps(list(RESOURCE_TYPES), separators=(',', ':'))})
    except HTTPFailure as error:
        # Preserve the transport's classified cause; never guess invalidation.
        if token != '*':
            guidance = ('correct credentials/account configuration' if error.status in (401, 403)
                else 'explicit todo --clear-cache --refresh now deletes current cache and preserves history')
            error.args = (str(error) + '; automatic sync-token recognition unavailable; ' + guidance,)
        raise
    response = _object(response, 'Sync response')
    new_token = _id(_required(response, 'sync_token'), 'sync_token')
    if new_token == '*':
        raise CurrentError('response sync_token must not be *')
    full = _bool(_required(response, 'full_sync'), 'full_sync')
    return response, new_token, full


def retrieve(transport, binding: Binding, *, prior: Snapshot | None = None,
             sync_token: str | None = None, replace=False, hidden_names=(),
             known=None, reminder_ids=None, waiting_label_ids=None, created_ids=frozenset()) -> Current:
    """Read a complete candidate. No mutation, files, retries beyond transport,
    or account history access. A full response receives exactly one freshness read.

    prior must be a proven current baseline; known optionally supplies retained
    identities for tombstone/departure reconciliation without seeding resources.
    On scope expansion from a minimal prior Snapshot, request a replacement to
    recover unchanged resources owned by entrants (Sync does not re-emit them).
    created_ids is a command-local exception for exact UUID/temp-ID-proven new
    objects, never title matches or arbitrary entrants. With a compatible prior
    and token, incremental resources establish these objects' complete own state.
    Other entrants still require unchanged-resource hydration. This is data
    hydration, never error/token recovery, and is bounded once.
    """
    if prior is not None:
        validate(prior, hidden_names)
        if prior.binding != binding:
            raise CurrentError('prior snapshot binding differs from supplied binding')
    if known is not None and known is not prior:
        validate(known, hidden_names)
        if known.binding != binding:
            raise CurrentError('known snapshot binding differs from supplied binding')
    if prior is None and sync_token is not None and not replace:
        raise CurrentError('incremental token requires a prior Snapshot')
    initial = prior is None or replace
    token = '*' if initial else _id(sync_token, 'prior sync_token')
    response, token, full = _read(transport, token)
    if initial and not full:
        raise CurrentError('requested full Sync returned a delta')
    state = {name: {} for name in _COLLECTIONS} if full else _seed(prior)
    if not full and known is not None and reminder_ids is not None:
        # Proven Sync reminder membership may include an archived owner. Seed
        # only those wire resources, never the archived items or their comments.
        reminder_seed = _seed(dataclass_replace(known,
            items={}, comments={}, occurrences={},
            reminders={k: r for k, r in known.reminders.items() if k in reminder_ids}))
        state['reminders'].update(reminder_seed['reminders'])
    labels_known = full or waiting_label_ids is not None
    state['_waiting_seen'] = set(waiting_label_ids or ())
    if not full and waiting_label_ids is not None:
        state['labels'] = {k: dict(id=k, name='waiting', is_deleted=False) for k in waiting_label_ids}
    _merge(state, response, full)
    account = prior.account if prior else None

    def metadata(response, full, account):
        if full:
            _required(response, 'user')
            _required(response, 'user_plan_limits')
        user = response.get('user', {'id': account.id, 'tz_info': {'timezone': account.timezone}} if account else None)
        c = account.capabilities if account else None
        limits = response.get('user_plan_limits', {'current': {'reminders': c.reminders,
            'activity_log': c.activity_history, 'activity_log_limit': c.history_limit}} if c else None)
        return _account(user, limits, binding)

    account = metadata(response, full, account)
    scoped_projects = binding.category_ids | {binding.root_id} | {
        k for k, v in state['projects'].items() if v.get('parent_id') == binding.root_id}
    scoped_items = {k for k, v in state['items'].items()
                    if v.get('is_deleted') is not True and isinstance(v.get('project_id'), str)
                    and v['project_id'] in scoped_projects}
    _check_duplicates(state, scoped_projects, scoped_items)
    earlier_departures = set()
    if not full:
        _, current_categories, _ = _projects(state, binding, prior.items)
        # A changed project may carry previously unrelated, unchanged items.
        expanded = any(raw.get('is_deleted') is not True and raw.get('parent_id') == binding.root_id
                       and identity not in binding.category_ids
                       for identity, raw in state['projects'].items())
        scoped = binding.category_ids | {identity for identity, raw in state['projects'].items()
                                        if raw.get('parent_id') == binding.root_id}
        expanded |= any(raw.get('is_deleted') is not True and raw.get('project_id') in scoped
                        and identity not in prior.items and identity not in created_ids for identity, raw in state['items'].items())
        if expanded:
            # Hydration must not become recovery for invalid incoming resources.
            # Parse own fields here; hierarchy waits for the complete replacement.
            for raw in state['items'].values():
                if raw.get('is_deleted') is not True and raw.get('project_id') in current_categories:
                    _item(raw, account.timezone)
            # A full active read can omit an item that already left scope and
            # was then completed. Keep only its confirmed identity, not its
            # unrelated live content. Later explicit item facts supersede this.
            for identity in (known or prior).items:
                raw = state['items'].get(identity)
                if raw is not None and raw.get('is_deleted') is not True:
                    project_id = _id(_required(raw, 'project_id'), 'item.project_id')
                    if project_id not in current_categories and project_id != binding.root_id:
                        earlier_departures.add(identity)
            response, token, full = _read(transport, '*')
            if not full:
                raise CurrentError('scope hydration requires a full Sync')
            earlier_tombstones = {identity: raw for identity, raw in state['items'].items()
                                  if identity in (known or prior).items and raw.get('is_deleted') is True}
            earlier_notes = {identity: raw for identity, raw in state['notes'].items()
                if known is not None and identity in known.comments
                and (raw.get('is_deleted') is True or raw.get('item_id') != known.comments[identity].item_id)}
            state = {name: {} for name in _COLLECTIONS}
            labels_known = True
            _merge(state, response, True)
            # Keep explicit deletion evidence across hydration, never stale live
            # objects. A later live representation supersedes that evidence.
            for identity, raw in earlier_tombstones.items():
                state['items'].setdefault(identity, raw)
            for identity, raw in earlier_notes.items():
                state['notes'].setdefault(identity, raw)
            account = metadata(response, True, account)
    if full:
        response, token, again_full = _read(transport, token)
        if again_full:
            raise CurrentError('freshness Sync returned another full response')
        _merge(state, response, False)
        account = metadata(response, False, account)
    snapshot, missing, deleted, departed = _map(state, binding, account, prior, hidden_names, known)
    departed = departed | (earlier_departures - state['items'].keys())
    missing = missing - departed
    # Owners absent from active Sync need lifecycle scope resolution before their
    # live reminder bodies can be consumed. A full hydration replaces this state,
    # including its duplicate evidence (REQ-SYNC-031).
    unresolved = tuple(raw for raw in state['reminders'].values()
        if raw.get('is_deleted') is not True and raw['item_id'] not in state['items'])
    unresolved_ids = {r['id'] for r in unresolved}
    duplicates = tuple((left, right) for name, left, right in state.get('_duplicates', ())
        if name == 'reminders' and right['id'] in unresolved_ids)
    # Preserve explicit note deletion/ownership loss even for deferred archived
    # owners. Their absence from mapped active comments alone proves nothing.
    removed_comments = frozenset(k for k, comment in (known or prior).comments.items()
        if k in state['notes'] and (state['notes'][k].get('is_deleted') is True
            or state['notes'][k].get('item_id') != comment.item_id)) if (known or prior) else frozenset()
    return Current(snapshot, token, missing, deleted, departed, unresolved, duplicates,
                   frozenset(k for k, raw in state['reminders'].items() if raw.get('is_deleted') is not True), snapshot,
                   frozenset(k for k, raw in state['labels'].items()
                       if raw.get('is_deleted') is not True and raw.get('name') == 'waiting') if labels_known else None,
                   removed_comments)
