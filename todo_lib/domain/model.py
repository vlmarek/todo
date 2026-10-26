"""Concrete shared managed model and offline predicates.

All IDs are nonempty strings. Collections are keyed by those IDs. A Snapshot is a
complete candidate merge, never a provider page. Roles and depths derive from
parent links. Call validate before publishing a candidate; validation returns the
same snapshot without rewriting text, replacing null times, or doing I/O.

A project/category record describes *current* scope. Binding records authoritative
stable identity. Discovery/enrollment is explicit through enroll_categories;
validation never adopts a replacement with the same name. Lifecycle occurrences
are supplied facts, not report current-truth/event eligibility calculations.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import IntEnum
from decimal import Decimal
from typing import Mapping, Iterable
from .errors import DomainError
from .text import validate_title, validate_body, title_key, split_waiting
from .time import (Attention, account_timezone, require_aware, attention_order,
                   validate_reminder_offsets, resolve_remote_due, same_attention)


@dataclass(frozen=True)
class Capabilities:
    """Last authoritative account capabilities; None history_limit is unknown."""
    reminders: bool = False
    activity_history: bool = False
    history_limit: int | None = None


@dataclass(frozen=True)
class Account:
    id: str
    timezone: str
    capabilities: Capabilities = field(default_factory=Capabilities)


@dataclass(frozen=True)
class Binding:
    account_id: str
    root_id: str
    category_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Project:
    """Current root/category scope facts, already mapped by the adapter.

    Personal ownership is explicit; no absent wire owner field is inferred here.
    """
    id: str
    name: str
    parent_id: str | None = None
    personally_owned: bool = True
    shared: bool = False
    workspace_id: str | None = None
    archived: bool = False
    deleted: bool = False


Category = Project


@dataclass(frozen=True)
class Item:
    """Task/step with own fields. None added_at is authoritative unknown.

    Priority uses product numbering (1 is highest), not Todoist wire numbering.
    Empty description means absence. `waiting` is determined by the label, not
    by a reason block. Comments/reminders are separate ID-owned collections.
    """
    id: str
    category_id: str
    title: str
    parent_id: str | None = None
    description: str = ''
    priority: int = 2
    attention: Attention | None = None
    labels: frozenset[str] = frozenset()
    added_at: datetime | None = None
    completed: bool = False
    completed_at: datetime | None = None

    @property
    def role(self) -> str:
        return 'task' if self.parent_id is None else 'step'

    @property
    def waiting(self) -> bool:
        return 'waiting' in self.labels

    @property
    def recurring(self) -> bool:
        return self.attention is not None and self.attention.recurring


@dataclass(frozen=True)
class Comment:
    id: str
    item_id: str
    body: str
    added_at: datetime | None = None


@dataclass(frozen=True)
class Reminder:
    id: str
    item_id: str
    minutes: int


@dataclass(frozen=True)
class Occurrence:
    """One authoritative completion occurrence; undone occurrences are ineligible."""
    id: str
    item_id: str
    completed_at: datetime
    recurring: bool = False
    undone: bool = False


@dataclass(frozen=True)
class Snapshot:
    binding: Binding
    account: Account
    root: Project
    categories: Mapping[str, Category] = field(default_factory=dict)
    items: Mapping[str, Item] = field(default_factory=dict)
    comments: Mapping[str, Comment] = field(default_factory=dict)
    reminders: Mapping[str, Reminder] = field(default_factory=dict)
    occurrences: Mapping[str, Occurrence] = field(default_factory=dict)


def _id(value, name):
    if not isinstance(value, str) or not value:
        raise DomainError(f'{name} must be a nonempty string ID')


def _keyed(collection, name, record_type):
    if not isinstance(collection, Mapping):
        raise DomainError(f'{name} must be ID-keyed')
    for key, obj in collection.items():
        _id(key, name + '.id')
        if not isinstance(obj, record_type):
            raise DomainError(f'{name} must contain {record_type.__name__} records')
        if key != obj.id:
            raise DomainError(f'{name} key/ID mismatch')


def _project(project, parent):
    if not isinstance(project, Project):
        raise DomainError('project must be a Project record')
    _id(project.id, 'project.id')
    if any(type(v) is not bool for v in (project.personally_owned, project.shared, project.archived, project.deleted)):
        raise DomainError('project scope flags must be booleans')
    validate_title(project.name)
    if (project.parent_id != parent or not project.personally_owned or project.shared
            or project.workspace_id is not None or project.archived or project.deleted):
        raise DomainError('root/category scope must be active, personally owned, unshared and correctly nested')


def hierarchy_depths(snapshot: Snapshot) -> dict[str, int]:
    """Resolve complete graph regardless of response order; reject invalid links.

    Iterative traversal also safely rejects arbitrarily long cycles/chains.
    """
    depths: dict[str, int] = {}
    for start in snapshot.items:
        chain, seen = [], set()
        current = start
        while current is not None and current not in depths:
            if current in seen:
                raise DomainError('item.parent_id cycle')
            if current not in snapshot.items:
                raise DomainError('item.parent_id orphan or out-of-scope ancestor')
            seen.add(current)
            chain.append(current)
            item = snapshot.items[current]
            if item.category_id not in snapshot.categories:
                raise DomainError('item.category_id outside managed categories (including project root)')
            if item.parent_id is not None:
                parent = snapshot.items.get(item.parent_id)
                if parent is None:
                    raise DomainError('item.parent_id orphan or out-of-scope ancestor')
                if parent.category_id != item.category_id:
                    raise DomainError('item.parent_id cross-category link')
                if not item.completed and parent.completed:
                    raise DomainError('open item under completed ancestor')
            current = item.parent_id
        depth = depths[current] if current is not None else -1
        for ident in reversed(chain):
            depth += 1
            if depth > 4:
                raise DomainError('item depth exceeds 4')
            depths[ident] = depth
    return depths


def ancestors(snapshot: Snapshot, item_id: str) -> tuple[Item, ...]:
    """Root-to-immediate-parent path, excluding the selected item."""
    hierarchy_depths(snapshot)
    path = []
    current = snapshot.items[item_id].parent_id
    while current is not None:
        path.append(snapshot.items[current])
        current = snapshot.items[current].parent_id
    return tuple(reversed(path))


def root_task(snapshot: Snapshot, item_id: str) -> Item:
    path = ancestors(snapshot, item_id)
    return path[0] if path else snapshot.items[item_id]


def _sibling_key(item: Item):
    if item.added_at is None:
        return (1, 0, item.id)
    require_aware(item.added_at, 'item.added_at')
    # datetime subtraction rather than float timestamp avoids precision loss.
    from datetime import timezone
    return (0, -(item.added_at.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)), item.id)


def ordered_siblings(snapshot: Snapshot, category_id: str, parent_id: str | None = None) -> tuple[Item, ...]:
    """All immediate siblings: known creation newest first, unknown last by ID."""
    return tuple(sorted((i for i in snapshot.items.values() if i.category_id == category_id and i.parent_id == parent_id), key=_sibling_key))


def subtree(snapshot: Snapshot, item_id: str) -> tuple[Item, ...]:
    """Selected root plus every descendant in deterministic preorder."""
    hierarchy_depths(snapshot)
    children: dict[str, list[Item]] = {}
    for item in snapshot.items.values():
        if item.parent_id is not None:
            children.setdefault(item.parent_id, []).append(item)
    result, pending = [], [snapshot.items[item_id]]
    while pending:
        item = pending.pop()
        result.append(item)
        pending.extend(reversed(sorted(children.get(item.id, []), key=_sibling_key)))
    return tuple(result)


def subtree_depths(snapshot: Snapshot, item_id: str) -> dict[str, int]:
    """Absolute depths for the complete selected known subtree."""
    depths = hierarchy_depths(snapshot)
    return {i.id: depths[i.id] for i in subtree(snapshot, item_id)}


def validate_sibling_uniqueness(items: Iterable[Item]) -> None:
    """Preflight all proposed active sibling sets; completed titles are ignored."""
    seen = set()
    for item in items:
        if item.completed:
            continue
        key = (item.category_id, item.parent_id, title_key(item.title))
        if key in seen:
            raise DomainError('active sibling titles must be unique')
        seen.add(key)


def lookup_category(snapshot: Snapshot, name: str) -> Category:
    """Case-insensitive category lookup; scope never follows a renamed ID."""
    matches = [c for c in snapshot.categories.values() if title_key(c.name) == title_key(name)]
    if len(matches) != 1:
        raise DomainError('category name missing or ambiguous')
    return matches[0]


def bind_root(account_id: str, projects: Iterable[Project], configured_name: str) -> Binding:
    """First initialization only: exact, case-sensitive name and valid root."""
    _id(account_id, 'account.id')
    matches = [p for p in projects if p.name == configured_name]
    if len(matches) != 1:
        raise DomainError('configured root name missing or ambiguous')
    _project(matches[0], None)
    return Binding(account_id, matches[0].id)


def enroll_categories(binding: Binding, root: Project, current: Mapping[str, Category], items: Mapping[str, Item]) -> Binding:
    """Enroll valid current direct children; retire only empty missing categories.

    Callers must include known moved/deleted category facts, or fail discovery
    rather than silently discarding work. This helper does no discovery or repair.
    """
    if root.id != binding.root_id:
        raise DomainError('bound root ID changed')
    _project(root, None)
    _keyed(current, 'categories', Category)
    for category in current.values():
        _project(category, root.id)
    missing = binding.category_ids - current.keys()
    if any(i.category_id in missing for i in items.values()):
        raise DomainError('removed category could discard managed work')
    return Binding(binding.account_id, binding.root_id, frozenset(current))


def effective_priority(snapshot: Snapshot, item_id: str) -> int | None:
    """Highest stored priority of open root/descendants, independent of hiding."""
    return min((i.priority for i in subtree(snapshot, item_id) if not i.completed), default=None)


def creation_priority(snapshot: Snapshot, parent_id: str | None = None) -> int:
    """Default from synchronized pre-creation subtree; copy once into new item."""
    if parent_id is None:
        return 2
    if snapshot.items[parent_id].completed:
        raise DomainError('cannot create under completed parent')
    return effective_priority(snapshot, parent_id)


def effective_attention(snapshot: Snapshot, item_id: str) -> Attention | None:
    values = [i.attention for i in subtree(snapshot, item_id) if not i.completed and i.attention is not None]
    return min(values, key=lambda a: attention_order(a, snapshot.account.timezone), default=None)


@dataclass(frozen=True)
class Visibility:
    """Independent own/ancestor/category suppression facts for an item."""
    own_hidden: bool
    ancestor_hidden: bool
    category_hidden: bool
    completed: bool

    @property
    def actionable(self) -> bool:
        return not (self.own_hidden or self.ancestor_hidden or self.category_hidden or self.completed)


def visibility(snapshot: Snapshot, item_id: str, now: datetime, hidden_names: Iterable[str] = ()) -> Visibility:
    """Waiting suppresses until the start of its attention day, never its time."""
    today = require_aware(now, 'now').astimezone(account_timezone(snapshot.account.timezone)).date()
    item = snapshot.items[item_id]
    def hidden(i):
        if not i.waiting:
            return False
        if i.attention is None:
            raise DomainError('waiting label requires attention')
        return today < i.attention.day(snapshot.account.timezone)
    return Visibility(hidden(item), any(hidden(a) for a in ancestors(snapshot, item_id)),
                      snapshot.categories[item.category_id].name in hidden_names, item.completed)


def validate_hiding(snapshot: Snapshot, hidden_names: Iterable[str] = ()) -> None:
    hidden_names = frozenset(hidden_names)
    zone = snapshot.account.timezone
    reminded = {r.item_id for r in snapshot.reminders.values()}
    for item in snapshot.items.values():
        _, reason = split_waiting(item.description)
        if reason is not None and not item.waiting:
            raise DomainError('waiting reason block requires waiting label')
        if item.waiting and item.attention is None:
            raise DomainError('waiting label requires attention')
        if snapshot.categories[item.category_id].name in hidden_names:
            if item.attention is not None or item.waiting or item.id in reminded:
                raise DomainError('hidden category forbids attention, reminders and own hiding policy')
        if item.completed:
            continue
        if item.attention is not None:
            day = item.attention.day(zone)
            for parent in ancestors(snapshot, item.id):
                if parent.waiting and day < parent.attention.day(zone):
                    raise DomainError('descendant attention day precedes waiting ancestor day')


def validate_hiding_enable(snapshot: Snapshot, item_id: str, now: datetime, hidden_names: Iterable[str] = ()) -> None:
    """Explicit enable/update preflight, unlike validation of expired policies."""
    item = snapshot.items[item_id]
    if item.attention is None:
        raise DomainError('enabling hiding requires attention')
    today = require_aware(now, 'now').astimezone(account_timezone(snapshot.account.timezone)).date()
    if item.attention.day(snapshot.account.timezone) <= today:
        raise DomainError('enabling or updating hiding requires a future attention day')
    validate(snapshot, hidden_names)


def validate(snapshot: Snapshot, hidden_names: Iterable[str] = ()) -> Snapshot:
    """Validate complete candidate scope, hierarchy, own fields and invariants.

    No mutation, I/O, inference of timestamps or report-event eligibility occurs.
    Provider length-limit errors must be translated by the adapter to DomainError;
    this model does not invent undocumented local text length limits.
    """
    if not isinstance(snapshot, Snapshot) or not isinstance(snapshot.binding, Binding) or not isinstance(snapshot.account, Account):
        raise DomainError('snapshot requires Binding and Account records')
    if not isinstance(snapshot.root, Project):
        raise DomainError('snapshot.root must be a Project record')
    _id(snapshot.binding.account_id, 'binding.account_id')
    _id(snapshot.binding.root_id, 'binding.root_id')
    if snapshot.account.id != snapshot.binding.account_id or snapshot.root.id != snapshot.binding.root_id:
        raise DomainError('bound account/root stable ID mismatch')
    account_timezone(snapshot.account.timezone)
    caps = snapshot.account.capabilities
    if not isinstance(caps, Capabilities):
        raise DomainError('account.capabilities must be a Capabilities record')
    if type(caps.reminders) is not bool or type(caps.activity_history) is not bool:
        raise DomainError('account capabilities must be booleans')
    if caps.history_limit is not None and (type(caps.history_limit) is not int or caps.history_limit < -1):
        raise DomainError('history_limit must be -1 or a nonnegative integer')
    _project(snapshot.root, None)
    for name, record_type in (('categories', Category), ('items', Item), ('comments', Comment), ('reminders', Reminder), ('occurrences', Occurrence)):
        _keyed(getattr(snapshot, name), name, record_type)
    for category_id in snapshot.binding.category_ids:
        _id(category_id, 'binding.category_ids')
    for item in snapshot.items.values():
        _id(item.category_id, 'item.category_id')
        if item.parent_id is not None:
            _id(item.parent_id, 'item.parent_id')
    if set(snapshot.categories) != set(snapshot.binding.category_ids):
        raise DomainError('category IDs differ from binding; explicit enrollment/retirement required')
    category_names = set()
    for category in snapshot.categories.values():
        if category.id == snapshot.root.id:
            raise DomainError('root cannot be a category')
        _project(category, snapshot.root.id)
        key = title_key(category.name)
        if key in category_names:
            raise DomainError('category names must be unique case-insensitively')
        category_names.add(key)
    hierarchy_depths(snapshot)
    for item in snapshot.items.values():
        validate_title(item.title)
        split_waiting(item.description)
        if type(item.priority) is not int or item.priority not in (1, 2, 3, 4):
            raise DomainError('item.priority must be P1 through P4')
        if type(item.completed) is not bool:
            raise DomainError('item.completed must be a boolean')
        if not isinstance(item.labels, (set, frozenset, tuple, list)):
            raise DomainError('item.labels must be a collection of label strings')
        if any(not isinstance(label, str) or not label for label in item.labels):
            raise DomainError('item.labels must contain nonempty strings')
        if item.added_at is not None:
            require_aware(item.added_at, 'item.added_at')
        if item.completed_at is not None:
            require_aware(item.completed_at, 'item.completed_at')
        if item.completed and item.completed_at is None:
            raise DomainError('completed item requires completed_at')
        if item.recurring and item.completed:
            raise DomainError('recurring occurrence completion must leave the object open')
        if item.attention is not None:
            _validate_attention(item.attention, snapshot.account.timezone)
    validate_sibling_uniqueness(snapshot.items.values())
    for comment in snapshot.comments.values():
        if comment.item_id not in snapshot.items:
            raise DomainError('comment.item_id outside managed items')
        validate_body(comment.body)
        if comment.added_at is not None:
            require_aware(comment.added_at, 'comment.added_at')
    offsets: dict[str, list[int]] = {}
    for reminder in snapshot.reminders.values():
        if reminder.item_id not in snapshot.items:
            raise DomainError('reminder.item_id outside managed items')
        item = snapshot.items[reminder.item_id]
        if not caps.reminders or item.attention is None or not item.attention.exact:
            raise DomainError('reminders require account capability and exact attention')
        offsets.setdefault(item.id, []).append(reminder.minutes)
    for values in offsets.values():
        validate_reminder_offsets(values)
    for occurrence in snapshot.occurrences.values():
        if occurrence.item_id not in snapshot.items:
            raise DomainError('occurrence.item_id outside surviving managed items')
        require_aware(occurrence.completed_at, 'occurrence.completed_at')
        if type(occurrence.recurring) is not bool or type(occurrence.undone) is not bool:
            raise DomainError('occurrence lifecycle flags must be booleans')
    validate_hiding(snapshot, hidden_names)
    return snapshot


def _validate_attention(value: Attention, zone: str) -> None:
    if not isinstance(value, Attention) or value.kind not in ('date', 'fixed', 'floating'):
        raise DomainError('snapshot attention must be a resolved due value')
    if value.kind == 'date':
        from datetime import date
        if type(value.date_value) is not date or value.instant is not None or value.epoch_seconds is not None:
            raise DomainError('date-only attention fields inconsistent')
    else:
        require_aware(value.instant, 'attention.instant')
        if value.date_value is not None:
            raise DomainError('exact attention must not carry a second date')
        from .time import exact_attention
        if value.epoch_seconds is not None and (not isinstance(value.epoch_seconds, Decimal) or not value.epoch_seconds.is_finite() or not Decimal(0) <= value.epoch_seconds - exact_attention(value.instant).epoch_seconds < Decimal('0.000001')):
            raise DomainError('attention precision inconsistent with instant')
    if any(v is not None and not isinstance(v, str) for v in (value.rule, value.language, value.zone)):
        raise DomainError('attention rule/language/zone must be strings or null')
    if type(value.recurring) is not bool or (value.recurring and (not value.rule or not value.rule.strip())):
        raise DomainError('recurring attention requires a rule')
    if value.zone is not None:
        account_timezone(value.zone)
    if value.raw_due is not None:
        resolved = resolve_remote_due(value.raw_due, zone)
        if not same_attention(value, resolved, zone):
            raise DomainError('attention raw due disagrees with resolved value/account timezone')


class Urgency(IntEnum):
    OVERDUE = 0
    TODAY = 1
    NEXT_7_DAYS = 2
    NO_DATE = 3
    LATER = 4


def urgency(item: Item, now: datetime, account_zone: str) -> Urgency:
    """Classify using this item's own due only. Exact equality is Today."""
    zone = account_timezone(account_zone)
    require_aware(now, 'now')
    value = item.attention
    if value is None:
        return Urgency.NO_DATE
    today, day = now.astimezone(zone).date(), value.day(zone)
    from .time import exact_attention
    if (value.exact and attention_order(value, zone) < exact_attention(now).epoch_seconds) or (not value.exact and day < today):
        return Urgency.OVERDUE
    if day == today:
        return Urgency.TODAY
    if today < day <= today + timedelta(days=7):
        return Urgency.NEXT_7_DAYS
    return Urgency.LATER


def now_queue(snapshot: Snapshot, now: datetime, hidden_names: Iterable[str] = ()) -> tuple[Item, ...]:
    """Independent task/step rows by section, own priority, own due, title and ID."""
    hidden_names = tuple(hidden_names)
    zone = snapshot.account.timezone
    def key(i):
        return (urgency(i, now, zone), i.priority, attention_order(i.attention, zone) if i.attention else 0, i.title.lower(), i.id)
    return tuple(sorted((i for i in snapshot.items.values() if visibility(snapshot, i.id, now, hidden_names).actionable), key=key))


def validate_move_depth(snapshot: Snapshot, item_id: str, parent_id: str | None) -> None:
    """Known subtree preflight, including cycle prevention and resulting depth."""
    depths = hierarchy_depths(snapshot)
    branch = subtree(snapshot, item_id)
    if parent_id in {i.id for i in branch}:
        raise DomainError('move would create a cycle')
    base = 0 if parent_id is None else depths[parent_id] + 1
    if base + max(depths[i.id] - depths[item_id] for i in branch) > 4:
        raise DomainError('move would exceed depth 4')


def completion_order(snapshot: Snapshot, item_id: str) -> tuple[Item, ...]:
    """Postorder in inspection sibling order, skipping completed items.

    Workflows must use an occurrence operation for a recurring selected root.
    """
    if snapshot.items[item_id].completed:
        raise DomainError('completion requires an open item')
    items = subtree(snapshot, item_id)
    if any(i.recurring and not i.completed for i in items[1:]):
        raise DomainError('open recurring descendant blocks subtree completion')
    children: dict[str, list[Item]] = {}
    # Preorder already contains each direct sibling set in inspection order.
    for item in items[1:]:
        children.setdefault(item.parent_id, []).append(item)
    result = []
    def visit(item):
        for child in children.get(item.id, ()):
            visit(child)
        if not item.completed:
            result.append(item)
    visit(items[0])
    return tuple(result)


@dataclass(frozen=True)
class LifecycleCandidate:
    """Reopen/delete selection fact; occurrence is present for recurring undo."""
    item_id: str
    completed_at: datetime
    occurrence_id: str | None = None


def _interval(cursor: datetime, now: datetime):
    cursor = require_aware(cursor, 'report cursor').astimezone(timezone.utc)
    now = require_aware(now, 'now').astimezone(timezone.utc)
    if cursor > now:
        raise DomainError('report cursor must not be after now')
    return cursor, now


def recent_reopen_candidates(snapshot: Snapshot, cursor: datetime, now: datetime) -> tuple[LifecycleCandidate, ...]:
    """Eligible completions in absolute (cursor, now], retaining supplied times."""
    cursor, now = _interval(cursor, now)
    result = [LifecycleCandidate(i.id, i.completed_at) for i in snapshot.items.values()
              if i.completed and not i.recurring and cursor < i.completed_at.astimezone(timezone.utc) <= now]
    for item in snapshot.items.values():
        if not item.recurring or item.completed:
            continue
        events = [o for o in snapshot.occurrences.values() if o.item_id == item.id and o.recurring]
        latest = max(events, key=lambda o: (o.completed_at.astimezone(timezone.utc), o.id), default=None)
        if latest and not latest.undone and cursor < latest.completed_at.astimezone(timezone.utc) <= now:
            result.append(LifecycleCandidate(item.id, latest.completed_at, latest.id))
    return tuple(sorted(result, key=lambda c: (c.completed_at.astimezone(timezone.utc), c.item_id)))


def completed_deletion_candidates(snapshot: Snapshot, cursor: datetime, now: datetime) -> tuple[LifecycleCandidate, ...]:
    """Currently completed nonrecurring objects only, never historical recurrence."""
    cursor, now = _interval(cursor, now)
    return tuple(sorted((LifecycleCandidate(i.id, i.completed_at) for i in snapshot.items.values()
                         if i.completed and not i.recurring and cursor < i.completed_at.astimezone(timezone.utc) <= now),
                        key=lambda c: (c.completed_at.astimezone(timezone.utc), c.item_id)))


def reopen_chain(snapshot: Snapshot, item_id: str) -> tuple[Item, ...]:
    """Proposed completed ancestor chain to reopen, validating active uniqueness.

    Eligibility selection is separate. This helper never edits completed items.
    """
    from dataclasses import replace
    selected = snapshot.items[item_id]
    if not selected.completed:
        raise DomainError('ordinary reopen requires a completed item')
    chain = tuple(i for i in (*ancestors(snapshot, item_id), selected) if i.completed)
    reopened = {i.id for i in chain}
    validate_sibling_uniqueness(replace(i, completed=False) if i.id in reopened else i for i in snapshot.items.values())
    return chain


def require_editable(item: Item) -> None:
    """Ordinary mutation precondition; completed items are immutable."""
    if item.completed:
        raise DomainError('completed item is immutable; use eligible reopen or deletion')
