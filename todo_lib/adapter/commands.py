"""One-operation Sync gateway; no replay, rollback, cache or workflow publication.

Gateway.execute(Operation, before=Current) returns Result. Direct methods construct
operations with fresh UUIDs (and fresh temporary IDs for creates). Callers may
construct Operation themselves to retain those IDs across transport status retries.
An unresolved result must stop the workflow. `accepted` proves the remote command,
not whole-tree validity or successful local publication: workflows must inspect
issues, validate the returned current/history evidence and publish themselves.

Wire authority: retained api-v1.openapi.json, Sync tag, Command UUID, Response /
Error, Projects, Tasks, Task comments, Reminders and Due dates. Read-only Sync
responses may supply attribution; there is no invented command-status endpoint.
Current/history model records are returned directly, never rebuilt via datetime.
"""
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from fractions import Fraction
import json
from uuid import UUID, uuid4

from todo_lib.domain import (
    Attention, DomainError, Item, instant_key, instant_text,
    reconciles_attention, retain_recurrence, validate_body,
    validate_title,
)
from . import current
from .history import HistoryAdapter
from .transport import HTTPFailure, Replay


class Outcome(str, Enum):
    ACCEPTED = 'accepted'
    REJECTED = 'rejected'
    UNKNOWN = 'unknown'


_CREATES = frozenset(('project_add', 'label_add', 'item_add', 'note_add', 'reminder_add'))
_FIELDS = {
    'project_add': ({'name'}, {'parent_id'}),
    'label_add': ({'name'}, set()),
    'item_add': ({'content', 'project_id'}, {'parent_id', 'description', 'priority', 'due', 'labels', 'auto_reminder'}),
    'item_update': ({'id'}, {'content', 'description', 'priority', 'due', 'labels'}),
    'item_move': ({'id'}, {'parent_id', 'project_id'}),
    'item_close': ({'id'}, set()),
    'item_complete': ({'id'}, set()),
    'item_uncomplete': ({'id'}, set()),
    'item_update_date_complete': ({'id', 'is_forward', 'reset_subtasks'}, {'due'}),
    'item_delete': ({'id'}, set()),
    'note_add': ({'item_id', 'content'}, set()),
    'note_update': ({'id', 'content'}, set()),
    'note_delete': ({'id'}, set()),
    'reminder_add': ({'item_id', 'type', 'minute_offset'}, set()),
    'reminder_update': ({'id', 'type', 'minute_offset'}, set()),
    'reminder_delete': ({'id'}, set()),
}
_UNSET = object()


def _id(value):
    if not isinstance(value, str) or not value:
        raise DomainError('nonempty stable ID required')
    return value


def _uuid(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value.lower():
            raise ValueError()
    except (ValueError, AttributeError):
        raise DomainError('canonical UUID required') from None


@dataclass(frozen=True)
class Operation:
    type: str
    args: Mapping
    uuid: str = field(default_factory=lambda: str(uuid4()))
    temp_id: str | None = None
    expected_attention: object = field(default=_UNSET, repr=False)

    def __post_init__(self):
        if self.type not in _FIELDS:
            raise DomainError('unsupported mutation')
        _uuid(self.uuid)
        if self.type in _CREATES:
            if self.temp_id is None:
                object.__setattr__(self, 'temp_id', str(uuid4()))
            _uuid(self.temp_id)
            if self.uuid == self.temp_id:
                raise DomainError('command UUID and temporary ID must differ')
        elif self.temp_id is not None:
            raise DomainError('temporary ID only belongs to creates')
        args = deepcopy(dict(self.args))
        required, optional = _FIELDS[self.type]
        if not required <= args.keys() or args.keys() - required - optional:
            raise DomainError('incorrect mutation arguments')
        for key in ('id', 'item_id', 'project_id', 'parent_id'):
            if key in args and not (self.type == 'project_add' and args[key] is None):
                _id(args[key])
        if 'name' in args:
            validate_title(args['name'])
        if 'content' in args:
            (validate_body if self.type.startswith('note_') else validate_title)(args['content'])
        if 'description' in args:
            if not isinstance(args['description'], str):
                raise DomainError('description must be text')
        if 'priority' in args and (type(args['priority']) is not int or args['priority'] not in (1, 2, 3, 4)):
            raise DomainError('wire priority must be 1 through 4')
        if 'labels' in args and (not isinstance(args['labels'], list) or any(not isinstance(x, str) or not x for x in args['labels'])):
            raise DomainError('labels must be a list of names')
        if self.type == 'item_move' and len(args.keys() & {'parent_id', 'project_id'}) != 1:
            raise DomainError('move requires exactly one destination')
        if self.type == 'item_update' and len(args) == 1:
            raise DomainError('update requires changed fields')
        if self.type == 'item_update_date_complete':
            if type(args['is_forward']) is not int or args['is_forward'] not in (0, 1) or type(args['reset_subtasks']) is not int or args['reset_subtasks'] != 0:
                raise DomainError('recurrence requires direction 1/0 and reset_subtasks=0')
        if self.type in ('reminder_add', 'reminder_update'):
            if args['type'] != 'relative' or type(args['minute_offset']) is not int or args['minute_offset'] < 0:
                raise DomainError('relative reminder requires a nonnegative integer offset')
        if 'due' in args and args['due'] is not None:
            if not isinstance(args['due'], dict):
                raise DomainError('due must be an object or null')
            args['due']['lang'] = 'en'
        if self.expected_attention is not _UNSET and self.expected_attention is not None and not isinstance(self.expected_attention, Attention):
            raise DomainError('expected attention must be an Attention value or null')
        if 'auto_reminder' in args and type(args['auto_reminder']) is not bool:
            raise DomainError('auto_reminder must be boolean')
        # The copy isolates the submitted command from caller-owned containers.
        object.__setattr__(self, 'args', args)

    def command(self):
        result = {'type': self.type, 'uuid': self.uuid, 'args': deepcopy(dict(self.args))}
        if self.temp_id is not None:
            result['temp_id'] = self.temp_id
        return result


@dataclass(frozen=True)
class Label:
    id: str
    name: str


@dataclass(frozen=True)
class Result:
    outcome: Outcome
    operation: Operation
    target_id: str | None = None
    after: current.Current | None = None
    actual: object = None
    evidence: tuple = ()
    issues: tuple[str, ...] = ()
    restored_ancestors: tuple[Item, ...] = ()
    occurrences: tuple = ()

    @property
    def accepted(self):
        return self.outcome == Outcome.ACCEPTED

    @property
    def partial(self):
        return self.accepted and bool(self.issues)


class _Observed:
    """Capture attribution from actual reads without altering retrieval semantics."""
    def __init__(self, transport):
        self.transport, self.responses, self.reads = transport, [], []

    def request(self, *args, **kwargs):
        result = self.transport.request(*args, **kwargs)
        if isinstance(result, dict):
            self.responses.append(result)
            if args[:2] == ('POST', '/sync') and kwargs.get('replay') is Replay.READ:
                self.reads.append(result)
        return result


def _proof(op, responses):
    statuses, mappings = [], set()
    for response in responses:
        status = response.get('sync_status')
        if isinstance(status, dict) and op.uuid in status:
            value = status[op.uuid]
            if value == 'ok':
                statuses.append(Outcome.ACCEPTED)
            elif (isinstance(value, dict) and type(value.get('error_code')) is int
                  and isinstance(value.get('error'), str) and value['error']):
                statuses.append(Outcome.REJECTED)
        mapping = response.get('temp_id_mapping')
        if isinstance(mapping, dict):
            value = mapping.get(op.temp_id)
            if isinstance(value, str) and value:
                mappings.add(value)
    if len(set(statuses)) != 1 or len(mappings) > 1:
        target = next(iter(mappings)) if op.temp_id and len(mappings) == 1 else op.args.get('id')
        return Outcome.UNKNOWN, target
    outcome = statuses[0]
    target = next(iter(mappings), None) if op.temp_id else op.args.get('id')
    if outcome == Outcome.ACCEPTED and op.temp_id and target is None:
        return Outcome.UNKNOWN, None
    return outcome, target


def due_arguments(attention, previous=None):
    """English input; preserve provider recurrence rule/timezone/raw metadata."""
    if attention is None:
        return None
    if not isinstance(attention, Attention):
        raise DomainError('attention must be an Attention value')
    value = retain_recurrence(attention, previous)
    raw = deepcopy(dict(value.raw_due or {}))
    if previous is not None and previous.recurring and value.recurring:
        raw = {**deepcopy(dict(previous.raw_due or {})), **raw}
    if value.kind == 'unresolved':
        raw['string'] = value.expression
    elif value.kind == 'date':
        raw['date'] = value.date_value.isoformat()
    else:
        # raw_due is the lossless provider representation, when available.
        if not value.raw_due or 'date' not in value.raw_due:
            text = instant_text(value.instant)
            if value.epoch_seconds is not None:
                scale = max(0, -value.epoch_seconds.as_tuple().exponent)
                if scale:
                    fraction = Fraction(value.epoch_seconds) % 1
                    digits = str(fraction.numerator * (10**scale // fraction.denominator)).zfill(scale)
                    text = text.split('.')[0].removesuffix('Z') + '.' + digits + 'Z'
            raw['date'] = text
    raw['lang'] = 'en'
    if value.recurring:
        raw.update(string=value.rule, is_recurring=True, timezone=value.zone)
    return raw


class Gateway:
    def __init__(self, transport, *, history=None, retrieve=current.retrieve, clock=None):
        self.transport = transport
        self.history = history
        self.retrieve = retrieve
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._used = set()

    def execute(self, operation, *, before=None, known_owners=None, owner_id=None, start=None, end=None):
        """Submit once, then read current and required bounded history.

        before is the synchronized preflight Current. known_owners supplies already
        resolved archived Items for own comments. start/end bound lifecycle evidence;
        defaults cover the call with a five-minute lookback for provider clock skew.
        No valid state or matching title alone establishes operation acceptance.
        """
        op = operation
        # Revalidate even a caller-mutated args mapping before sending bytes.
        op = Operation(op.type, op.args, op.uuid, op.temp_id, op.expected_attention)
        identities = {op.uuid} | ({op.temp_id} if op.temp_id else set())
        if identities & self._used:
            raise DomainError('operation already attempted; reconcile without replay')
        if before is None and op.type not in ('project_add', 'label_add'):
            raise DomainError('synchronized preflight Current required')
        owners = dict(known_owners or {})
        if before is not None:
            owners.update(before.snapshot.items)
        owner = op.args.get('item_id', owner_id)
        if op.type.startswith('note_') and owner is None and before is not None:
            note = before.snapshot.comments.get(op.args['id'])
            owner = note.item_id if note else None
        if op.type.startswith('note_') and owner not in owners:
            raise DomainError('known comment owner required')
        if op.type.startswith('item_') and op.type != 'item_add' and op.args['id'] not in owners:
            raise DomainError('known managed item required')
        if op.type.startswith('reminder_') and op.type != 'reminder_add' and op.args['id'] not in before.snapshot.reminders:
            raise DomainError('known managed reminder required')
        old_ancestors = []
        if op.type == 'item_uncomplete':
            node, seen = owners[op.args['id']], {op.args['id']}
            while node.parent_id is not None:
                if node.parent_id in seen or node.parent_id not in owners:
                    raise DomainError('reopen requires known acyclic ancestor context')
                seen.add(node.parent_id)
                node = owners[node.parent_id]
                old_ancestors.append(node)
        lower = start if start is not None else self.clock() - timedelta(minutes=5)
        instant_key(lower)
        self._used.update(identities)
        observed = _Observed(self.transport)
        issues, evidence = [], []
        http_rejected = False
        try:
            observed.request('POST', '/sync', operation=op.type, replay=Replay.IDEMPOTENT,
                form={'commands': json.dumps([op.command()], ensure_ascii=False, separators=(',', ':'))},
                command_uuids=(op.uuid,))
        except HTTPFailure as error:
            http_rejected = error.outcome == 'rejected'
            evidence.append(('transport', error.outcome))
        after, actual, records, restored = None, None, (), ()
        try:
            if before is not None:
                after = self.retrieve(observed, before.binding, prior=before.snapshot,
                                      sync_token=before.sync_token)
            else:
                # Provisioning before a root binding exists: only project/label
                # resources, full plus one bounded freshness delta.
                response = observed.request('POST', '/sync', operation='provision reconciliation',
                    replay=Replay.READ, form={'sync_token': '*', 'resource_types': '["projects","labels"]'})
                if not isinstance(response, dict) or response.get('full_sync') is not True:
                    raise DomainError('provision reconciliation requires full Sync')
                token = _id(response.get('sync_token'))
                if token == '*' or any(not isinstance(response.get(name), list) for name in ('projects', 'labels')):
                    raise DomainError('invalid provision resources/token')
                fresh = observed.request('POST', '/sync', operation='provision freshness', replay=Replay.READ,
                    form={'sync_token': token, 'resource_types': '["projects","labels"]'})
                if not isinstance(fresh, dict) or fresh.get('full_sync') is not False or not isinstance(fresh.get('sync_token'), str) or not fresh['sync_token'] or fresh['sync_token'] == '*':
                    raise DomainError('invalid provision freshness response')
        except (DomainError, HTTPFailure) as error:
            issues.append('current reconciliation unavailable: ' + str(error))
        outcome, target = _proof(op, observed.responses)
        if http_rejected and outcome == Outcome.UNKNOWN:
            outcome = Outcome.REJECTED
        evidence.append(('command', op.uuid, outcome.value))
        if op.temp_id and target:
            evidence.append(('temporary ID', op.temp_id, target))
        snapshot = after.snapshot if after is not None else None
        if snapshot is not None:
            collection = (snapshot.comments if op.type.startswith('note_') else
                          snapshot.reminders if op.type.startswith('reminder_') else
                          snapshot.categories if op.type == 'project_add' else snapshot.items)
            actual = collection.get(target)
        account_zone = after.account.timezone if after is not None else before.account.timezone if before else 'UTC'
        history = self.history or HistoryAdapter(observed, timezone=account_zone)
        try:
            if op.type.startswith('note_'):
                # Scoped REST comments work for supported known archived owners,
                # without requiring them to remain in active Sync.
                comments = history.comments(owner)
                actual = next((c for c in comments.records if c.id == target), None)
                evidence.append(comments)
            if op.type in ('item_close', 'item_complete', 'item_update_date_complete'):
                upper = end if end is not None else self.clock()
                instant_key(upper)
                if instant_key(lower) > instant_key(upper):
                    raise DomainError('reconciliation interval is reversed')
                category = owners.get(op.args['id'])
                if category is None:
                    raise DomainError('known lifecycle owner required')
                completed = history.completed(lower, upper, {'project_id': category.category_id})
                records = tuple(r for r in completed.records if r.item.id == op.args['id'] and not r.deleted)
                evidence.append(completed)
                if actual is None and records and op.type != 'item_update_date_complete':
                    actual = max(records, key=lambda r: instant_key(r.occurrence.completed_at)).item
                # Occurrences are compared by exact instant, never datetime's
                # microsecond projection or a reconstructed historical Item.
                previous = before.snapshot.occurrences.values()
                seen = {(r.item_id, instant_key(r.completed_at)) for r in previous}
                seen.update((i.id, instant_key(i.completed_at)) for i in owners.values() if i.completed_at is not None)
                new = tuple(r for r in records if (r.occurrence.item_id, instant_key(r.occurrence.completed_at)) not in seen)
                # A changed recurring occurrence is necessary but not alone a
                # command receipt. Without UUID proof we conservatively stay unknown.
                if op.type == 'item_update_date_complete':
                    evidence.append(('new completion occurrences', tuple(r.occurrence for r in new)))
                    if op.args['is_forward'] == 0:
                        activities = history.activities(lower, upper, {'object_type': 'item', 'object_id': op.args['id']})
                        evidence.append(activities)
            if op.type in ('project_add', 'label_add'):
                resources = {}
                name = 'projects' if op.type == 'project_add' else 'labels'
                # Only read responses establish current resource state. Delta
                # omissions preserve fields; full replacement discards old IDs.
                for response in observed.reads:
                    if response.get('full_sync') is True:
                        resources.clear()
                    for raw in response.get(name, ()):
                        if isinstance(raw, dict) and isinstance(raw.get('id'), str):
                            resources.setdefault(raw['id'], {}).update(raw)
                raw = resources.get(target)
                if raw is not None and raw.get('is_deleted') is False:
                    if name == 'labels':
                        actual = Label(_id(raw['id']), raw['name'])
                        validate_title(actual.name)
                    elif actual is None:
                        actual = current._project(raw)
        except (DomainError, HTTPFailure, KeyError, TypeError) as error:
            issues.append('history/resource reconciliation unavailable: ' + str(error))
        if op.type == 'item_uncomplete' and snapshot is not None and before is not None:
            restored = tuple(snapshot.items[i.id] for i in old_ancestors
                if i.completed and i.id in snapshot.items and not snapshot.items[i.id].completed)
        if outcome == Outcome.ACCEPTED:
            if actual is None and not op.type.endswith('_delete'):
                issues.append('accepted object unavailable in authoritative state')
            if actual is not None and op.type in ('item_add', 'item_update'):
                for wire, attribute in (('content', 'title'), ('description', 'description'), ('priority', 'priority'), ('labels', 'labels')):
                    if wire in op.args:
                        expected = op.args[wire]
                        expected = 5 - expected if wire == 'priority' else frozenset(expected) if wire == 'labels' else expected
                        if getattr(actual, attribute) != expected:
                            issues.append('accepted ' + attribute + ' differs from request')
            if actual is not None and op.type.startswith('note_') and not op.type.endswith('_delete'):
                if actual.item_id != owner or actual.body != op.args['content']:
                    issues.append('accepted comment differs from requested owner/text')
            if actual is not None and op.type in ('reminder_add', 'reminder_update'):
                if actual.minutes != op.args['minute_offset'] or (op.type == 'reminder_add' and actual.item_id != op.args['item_id']):
                    issues.append('accepted reminder differs from request')
            if actual is not None and op.type in ('project_add', 'label_add'):
                if actual.name != op.args['name'] or (op.type == 'project_add' and actual.parent_id != op.args.get('parent_id')):
                    issues.append('accepted provision differs from request')
            if isinstance(actual, Item) and op.type == 'item_add':
                if (actual.parent_id, actual.category_id) != (op.args.get('parent_id'), op.args['project_id']):
                    issues.append('accepted creation owner/category differs from request')
            if (isinstance(actual, Item) and op.args.get('due') is not None
                    and 'due' in op.args and actual.attention is None
                    and op.expected_attention is _UNSET):
                issues.append('accepted attention expression returned no attention')
            if actual is not None and op.expected_attention is not _UNSET:
                requested = op.expected_attention
                returned = actual.attention
                # English parser input has no locally predicted occurrence,
                # kind or recurrence to compare. Current/history mapping validates
                # the provider's resolved value; missing attention is still partial.
                if requested is not None and requested.kind == 'unresolved':
                    matches = returned is not None and returned.kind in ('date', 'floating', 'fixed')
                else:
                    matches = reconciles_attention(requested, returned, account_zone)
                if not matches:
                    issues.append('requested attention ' + repr(requested) + '; actual attention ' + repr(returned))
            if isinstance(actual, Item):
                if op.type in ('item_close', 'item_complete') and not actual.completed:
                    issues.append('accepted completion has no completed lifecycle')
                if op.type == 'item_uncomplete' and actual.completed:
                    issues.append('accepted reopen remains completed')
                if op.type == 'item_move':
                    parent = op.args.get('parent_id')
                    destination = snapshot.items.get(parent) if parent else None
                    category = destination.category_id if destination else op.args.get('project_id')
                    if (actual.parent_id, actual.category_id) != (parent, category):
                        issues.append('accepted move destination differs from request')
            if op.type.endswith('_delete') and actual is not None:
                issues.append('accepted deletion still present')
        return Result(outcome, op, target, after, actual, tuple(evidence), tuple(issues),
                      restored, tuple(r.occurrence for r in records))

    def provision_root(self, name, **context):
        return self.execute(Operation('project_add', {'name': name, 'parent_id': None}), **context)

    def provision_category(self, root_id, name, **context):
        return self.execute(Operation('project_add', {'name': name, 'parent_id': root_id}), **context)

    def provision_label(self, name, **context):
        return self.execute(Operation('label_add', {'name': name}), **context)

    def create_task(self, category_id, title, *, parent_id=None, description='', priority=2,
                    attention=_UNSET, labels=(), **context):
        args = dict(project_id=category_id, content=title, description=description,
                    priority=5-priority, labels=list(labels), auto_reminder=False)
        if parent_id is not None:
            args['parent_id'] = parent_id
        if attention is not _UNSET:
            args['due'] = due_arguments(attention)
        return self.execute(Operation('item_add', args, expected_attention=attention), **context)

    create_step = create_task

    def update_task(self, item_id, *, title=_UNSET, description=_UNSET, priority=_UNSET,
                    attention=_UNSET, labels=_UNSET, **context):
        args = {'id': item_id}
        for name, value in (('content', title), ('description', description), ('labels', labels)):
            if value is not _UNSET:
                args[name] = list(value) if name == 'labels' else value
        if priority is not _UNSET:
            args['priority'] = 5-priority
        expected = attention
        if attention is not _UNSET:
            before = context['before'].snapshot.items[item_id]
            expected = retain_recurrence(attention, before.attention) if attention is not None else None
            args['due'] = due_arguments(expected, before.attention)
        return self.execute(Operation('item_update', args, expected_attention=expected), **context)

    update_step = update_task

    def move(self, item_id, *, parent_id=None, project_id=None, **context):
        if (parent_id is None) == (project_id is None):
            raise DomainError('move requires exactly one destination')
        return self.execute(Operation('item_move', {'id': item_id, **(
            {'parent_id': parent_id} if parent_id is not None else {'project_id': project_id})}), **context)

    def complete(self, item_id, *, recurring=None, attention=_UNSET, close=True, **context):
        return self._lifecycle(item_id, recurring, True, attention, close, context)

    def reopen(self, item_id, *, recurring=None, attention=_UNSET, **context):
        return self._lifecycle(item_id, recurring, False, attention, False, context)

    def _lifecycle(self, item_id, recurring, forward, attention, close, context):
        args = {'id': item_id}
        expected = attention
        if recurring is None:
            source = context['before'].snapshot.items.get(item_id) or (context.get('known_owners') or {}).get(item_id)
            if source is None:
                raise DomainError('known lifecycle owner required')
            recurring = source.recurring
        if recurring:
            args.update(is_forward=int(forward), reset_subtasks=0)
            if attention is not _UNSET:
                source = context['before'].snapshot.items.get(item_id) or (context.get('known_owners') or {}).get(item_id)
                expected = retain_recurrence(attention, source.attention) if attention is not None else None
                args['due'] = due_arguments(expected, source.attention)
            kind = 'item_update_date_complete'
        else:
            kind = ('item_close' if close else 'item_complete') if forward else 'item_uncomplete'
        return self.execute(Operation(kind, args, expected_attention=expected), **context)

    def delete_task(self, item_id, **context):
        return self.execute(Operation('item_delete', {'id': item_id}), **context)

    delete_step = delete_task

    def create_comment(self, owner_id, body, **context):
        return self.execute(Operation('note_add', {'item_id': owner_id, 'content': body}), **context)

    def update_comment(self, comment_id, body, **context):
        return self.execute(Operation('note_update', {'id': comment_id, 'content': body}), **context)

    def delete_comment(self, comment_id, **context):
        return self.execute(Operation('note_delete', {'id': comment_id}), **context)

    def create_reminder(self, owner_id, minutes, **context):
        return self.execute(Operation('reminder_add', {'item_id': owner_id, 'type': 'relative', 'minute_offset': minutes}), **context)

    def update_reminder(self, reminder_id, minutes, **context):
        return self.execute(Operation('reminder_update', {'id': reminder_id, 'type': 'relative', 'minute_offset': minutes}), **context)

    def delete_reminder(self, reminder_id, **context):
        return self.execute(Operation('reminder_delete', {'id': reminder_id}), **context)
