"""Complete, read-only API-v1 history retrieval; no persistence or cursor writes.

Offline authority (inspected 2026-10-26): retained api-v1.openapi.json paths
/tasks/completed/by_completion_date, /activities, /comments; schemas
TasksCompletedDateResponse, ActivityEvents, ItemSyncView and NoteSyncView.

HistoryAdapter(transport, timezone='UTC', stderr=None).completed(start,end,scope),
.activities(start,end,scope), and .comments(owner_id) return Retrieval records and
per-request continuation evidence. Scope is an optional endpoint-specific mapping
of documented string filters, copied before any request. Times use the domain's
precise values. CompletedRecord.item is historical evidence, never an instruction
to overwrite current lifecycle/text. Activity.annotation is retained as an unused compatibility slot; annotation
metadata is ignored. Only comments() supplies current surviving Comment records.

required_comments() composes current and bounded completed evidence for report
owners, including steps and ancestors, without an all-history scan. Unknown
archived owner/parent metadata fails explicitly. Callers must supply genuinely
current items (not last-observed cache records) separately from bounded history.
Nothing here establishes complete archived child enumeration.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
import re
import sys

from todo_lib.domain import (
    Comment, DomainError, ExactInstant, Item, Occurrence, instant_datetime, instant_from_wire,
    instant_key, instant_text, resolve_remote_due, incoming_text,
)
from .transport import HTTPFailure, Replay
from .current import _due


class HistoryError(DomainError):
    """Required history is incomplete; caller must not publish partial results."""


@dataclass(frozen=True)
class Page:
    endpoint: str
    parameters: tuple[tuple[str, str], ...]
    cursor: str | None
    next_cursor: str | None
    terminal: bool
    terminal_omission: bool = False


@dataclass(frozen=True)
class Retrieval:
    records: tuple
    pages: tuple[Page, ...]
    start: ExactInstant | datetime | None = None
    end: ExactInstant | datetime | None = None


@dataclass(frozen=True)
class CompletedRecord:
    item: Item
    occurrence: Occurrence
    deleted: bool = False


@dataclass(frozen=True)
class Activity:
    id: str | None
    object_type: str
    object_id: str
    event_type: str
    event_date: ExactInstant
    owner_id: str | None
    project_id: str | None
    annotation: str | None = None


@dataclass(frozen=True)
class CommentEvidence:
    owners: Mapping[str, Item]
    comments: Mapping[str, Comment]
    pages: tuple[Page, ...]


_CURSOR = re.compile(r'[0-9a-zA-Z_-]+\.[0-9a-zA-Z_-]+\Z')
_COMPLETED = '/tasks/completed/by_completion_date'
_EVENTS = ('item:completed', 'item:uncompleted', 'note:added', 'note:updated', 'note:deleted')
_FILTERS = {
    _COMPLETED: frozenset(('project_id', 'section_id', 'parent_id', 'filter_query', 'filter_lang')),
    '/activities': frozenset(('parent_project_id', 'parent_item_id', 'object_type', 'object_id')),
}


def _required(raw, key):
    if key not in raw:
        raise HistoryError('missing required ' + key)
    return raw[key]


def _object(value):
    if not isinstance(value, dict):
        raise HistoryError('expected an object')
    return value


def _id(value, field):
    if not isinstance(value, str) or not value:
        raise HistoryError(field + ' must be a nonempty string ID')
    return value


def _scope(scope, endpoint):
    if scope is None:
        return ()
    if not isinstance(scope, Mapping) or set(scope) - _FILTERS[endpoint]:
        raise HistoryError('unsupported ' + endpoint + ' scope parameters')
    result = tuple((key, _id(value, key)) for key, value in scope.items())
    if endpoint == '/activities':
        values = dict(result)
        if 'object_id' in values and 'object_type' not in values:
            raise HistoryError('object_id requires object_type')
        if 'object_type' in values and values['object_type'] not in ('item', 'note', 'project', 'section'):
            raise HistoryError('invalid object_type')
    return result


def _bounds(start, end):
    if instant_key(start) > instant_key(end):
        raise HistoryError('history start exceeds end')
    try:
        # These coarse bounds cover all exact instants; they never set eligibility.
        lower = instant_datetime(start).replace(microsecond=0)
        upper = instant_datetime(end).replace(microsecond=0) + timedelta(seconds=1)
        return lower, upper
    except (ValueError, OverflowError):
        raise HistoryError('cannot form covering UTC history bounds') from None


def _eligible(value, start, end):
    return instant_key(start) < instant_key(value) <= instant_key(end)


def _activity(raw):
    kind = _required(raw, 'object_type')
    if kind not in ('item', 'note', 'project', 'section'):
        raise HistoryError('invalid activity object_type')
    event = _id(_required(raw, 'event_type'), 'event_type')
    identity = raw.get('id')
    if identity is not None and type(identity) is not int:
        raise HistoryError('activity ID must be integer or null')
    identity = None if identity is None else str(identity)
    obj = _id(_required(raw, 'object_id'), 'object_id')
    owner = _id(_required(raw, 'parent_item_id'), 'parent_item_id') if kind == 'note' else (obj if kind == 'item' else None)
    project = raw.get('parent_project_id')
    if project is not None:
        _id(project, 'parent_project_id')
    return Activity(identity, kind, obj, event,
                    instant_from_wire(_required(raw, 'event_date')), owner, project)


class HistoryAdapter:
    def __init__(self, transport, *, timezone='UTC', stderr=None):
        self.transport = transport
        self.timezone = timezone
        self.stderr = stderr

    def _pages(self, endpoint, parameters, mapper, *, omission=False, count=None):
        """Freeze all fixed parameters, and never let a transport mutate them."""
        fixed = tuple(parameters)
        cursor, seen = None, set()
        count = [0] if count is None else count
        while True:
            query = fixed + (() if cursor is None else (('cursor', cursor),))
            context = f'history {endpoint} page {count[0] + 1} ({dict(fixed)})'
            try:
                raw = _object(self.transport.request('GET', endpoint,
                    operation='history ' + endpoint, replay=Replay.READ, query=list(query)))
                values = _required(raw, 'items' if omission else 'results')
                if not isinstance(values, list):
                    raise HistoryError('page records must be an array')
                absent = 'next_cursor' not in raw
                if absent and not omission:
                    raise HistoryError('missing required next_cursor')
                next_cursor = raw.get('next_cursor')
                terminal = absent if omission else next_cursor is None
                if not terminal:
                    if not isinstance(next_cursor, str) or not _CURSOR.fullmatch(next_cursor):
                        raise HistoryError('malformed next_cursor')
                    if next_cursor in seen:
                        raise HistoryError('repeated next_cursor')
                    seen.add(next_cursor)
                records = tuple(mapper(_object(value)) for value in values)
            except (DomainError, HTTPFailure) as error:
                raise HistoryError(context + ': ' + str(error)) from error
            count[0] += 1
            if count[0] % 10 == 0:
                resource = {'/activities': 'report activity', '/comments': 'comments',
                            _COMPLETED: 'completed tasks'}[endpoint]
                print(f'todo: loading {resource}: {count[0]} pages',
                      file=self.stderr if self.stderr is not None else sys.stderr)
            yield records, Page(endpoint, fixed, cursor, next_cursor, terminal, absent)
            if terminal:
                return
            cursor = next_cursor

    def completed(self, start, end, scope=None):
        filters = _scope(scope, _COMPLETED)
        project_filter = dict(filters).get('project_id')
        lower, upper = _bounds(start, end)
        records, pages, seen, count = [], [], set(), [0]

        def map_item(raw):
            _id(_required(raw, 'id'), 'item.id')
            _id(_required(raw, 'project_id'), 'item.project_id')
            completed_at = instant_from_wire(_required(raw, 'completed_at'))
            deleted = _required(raw, 'is_deleted')
            if type(deleted) is not bool:
                raise HistoryError('item.is_deleted must be boolean')
            if (not _eligible(completed_at, start, end) or
                (project_filter is not None and raw['project_id'] != project_filter)):
                return None
            parent = _required(raw, 'parent_id')
            if parent is not None:
                _id(parent, 'item.parent_id')
            if deleted:
                # A tombstone carries lifecycle context, never live display content.
                item = Item(raw['id'], raw['project_id'], '', parent,
                            completed=True, completed_at=completed_at)
                identity = item.id + '@' + str(instant_key(completed_at))
                return CompletedRecord(item, Occurrence(identity, item.id, completed_at, False), True)
            added_at = _required(raw, 'added_at')
            added_at = None if added_at is None else instant_from_wire(added_at)
            title = _required(raw, 'content')
            title = incoming_text(title, title=True)
            description = raw.get('description')
            description = '' if description is None else description
            description = incoming_text(description, description=True)
            priority = _required(raw, 'priority')
            if type(priority) is not int or priority not in (1, 2, 3, 4):
                raise HistoryError('item.priority must be 1 through 4')
            labels = _required(raw, 'labels')
            if not isinstance(labels, list) or any(not isinstance(x, str) or not x for x in labels):
                raise HistoryError('item.labels must contain label names')
            for field in ('checked', 'is_deleted'):
                if type(_required(raw, field)) is not bool:
                    raise HistoryError('item.' + field + ' must be boolean')
            _due(_required(raw, 'due'))
            item = Item(raw['id'], raw['project_id'], title, parent, description,
                5 - priority, resolve_remote_due(_required(raw, 'due'), self.timezone),
                frozenset(labels), added_at, raw['checked'], completed_at)
            # checked=false is documented for recurring completion records.
            identity = item.id + '@' + str(instant_key(completed_at))
            return CompletedRecord(item, Occurrence(identity, item.id,
                                   completed_at, item.recurring), raw['is_deleted'])

        while lower < upper:
            # 80 days is strictly shorter than every three-calendar-month span.
            boundary = min(lower + timedelta(days=80), upper) if (upper - lower).days >= 80 else upper
            parameters = filters + (('since', instant_text(lower)),
                                    ('until', instant_text(boundary)), ('limit', '200'))
            for values, page in self._pages(_COMPLETED, parameters, map_item,
                                            omission=True, count=count):
                pages.append(page)
                for value in values:
                    if value is None:
                        continue
                    key = (value.item.id, instant_key(value.occurrence.completed_at))
                    if _eligible(value.occurrence.completed_at, start, end) and key not in seen:
                        seen.add(key)
                        records.append(value)
            lower = boundary
        return Retrieval(tuple(records), tuple(pages), start, end)

    def activities(self, start, end, scope=None):
        filters = _scope(scope, '/activities')
        lower, upper = _bounds(start, end)
        parameters = filters + (('date_from', instant_text(lower)),
            ('date_to', instant_text(upper)), ('limit', '200'))
        parameters += tuple(('object_event_types', value) for value in _EVENTS)
        records, pages, seen = [], [], set()
        for values, page in self._pages('/activities', parameters, _activity):
            pages.append(page)
            for value in values:
                if not _eligible(value.event_date, start, end):
                    continue
                if value.id is not None:
                    if value.id in seen:
                        continue
                    seen.add(value.id)
                records.append(value)
        return Retrieval(tuple(records), tuple(pages), start, end)

    def comments(self, owner_id):
        return self._comments(owner_id)

    def _comments(self, owner_id, count=None, *, required_ids=None):
        owner_id = _id(owner_id, 'comment owner')
        records, pages, seen = [], [], {}

        def map_comment(raw):
            identity = _id(_required(raw, 'id'), 'comment.id')
            deleted = _required(raw, 'is_deleted')
            if type(deleted) is not bool:
                raise HistoryError('comment.is_deleted must be boolean')
            if deleted or (required_ids is not None and identity not in required_ids):
                return identity, None
            posted = _required(raw, 'posted_at')
            posted = None if posted is None else instant_from_wire(posted)
            body = raw.get('content', '')  # documented default, domain still requires text
            body = incoming_text(body)
            return identity, Comment(identity, owner_id, body, posted)

        for values, page in self._pages('/comments', (('task_id', owner_id), ('limit', '200')), map_comment, count=count):
            pages.append(page)
            for identity, comment in values:
                if identity in seen:
                    if seen[identity] != comment:
                        raise HistoryError('history /comments: contradictory comment representations')
                    continue
                seen[identity] = comment
                if comment is not None:
                    records.append(comment)
        return Retrieval(tuple(records), tuple(pages))

    def required_comments(self, current_items, completed, activities):
        """Return current text separately from events and historical item text.

        completed/activities are successfully exhausted Retrieval values. No cache
        writes, active-only lookup or guessed archive scan occurs on this path.
        Missing comments in a complete scoped response establish comment absence,
        never owner deletion. Returned owners include needed ancestor context.
        """
        for field in ('start', 'end'):
            left, right = getattr(completed, field), getattr(activities, field)
            if left is not None and right is not None and instant_key(left) != instant_key(right):
                raise HistoryError('history completed/activity interval mismatch: ' + field)
        owners = {}
        for record in sorted(completed.records, key=lambda r: instant_key(r.occurrence.completed_at)):
            if not record.deleted:
                owners[record.item.id] = record.item
        owners.update(current_items)
        requested = {identity: set() for identity in owners}
        for event in activities.records:
            if event.object_type == 'note' and event.event_type in ('added', 'updated'):
                requested.setdefault(event.owner_id, set()).add(event.object_id)
        comments, pages, count = {}, [], [0]
        needed = set(owners)
        for owner in requested:
            result = self._comments(owner, count,
                required_ids=requested[owner] if owner not in owners else None)
            pages.extend(result.pages)
            for comment in result.records:
                if owner not in owners and comment.id not in requested[owner]:
                    continue
                if comment.id in comments and comments[comment.id].item_id != owner:
                    raise HistoryError('history /comments: incompatible comment ownership ' + comment.id)
                comments[comment.id] = comment
                needed.add(owner)
        resolved = {}

        def resolve(identity, path):
            if identity in path:
                raise HistoryError('history unresolved cyclic owner/parent ' + identity)
            if identity in resolved:
                return
            item = owners.get(identity)
            if item is None:
                raise HistoryError('history unresolved archived owner/parent ' + identity +
                    '; bounded completed/current evidence is insufficient')
            if item.parent_id is not None:
                resolve(item.parent_id, path | {identity})
            resolved[identity] = item

        for identity in sorted(needed):
            resolve(identity, set())
        return CommentEvidence(resolved, comments, tuple(pages))


def completed(transport, start, end, scope=None, *, timezone='UTC', stderr=None):
    """Functional entrypoint for callers that do not retain a HistoryAdapter."""
    return HistoryAdapter(transport, timezone=timezone, stderr=stderr).completed(start, end, scope)


def activities(transport, start, end, scope=None, *, stderr=None):
    return HistoryAdapter(transport, stderr=stderr).activities(start, end, scope)


def comments(transport, owner_id, *, stderr=None):
    return HistoryAdapter(transport, stderr=stderr).comments(owner_id)
