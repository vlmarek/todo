"""Pending observations only; no HTTP, cursor changes, or implicit cleanup.

The report workflow alone supplies finalized output/cursor evidence to pruning.
Unknown activity times are retained conservatively. Coverage is supplied evidence,
not inferred from observed objects. Initial coverage is explicitly incomplete.
"""
from dataclasses import dataclass, field, replace
from datetime import datetime
from todo_lib import domain as d
from .safety import LocalError


@dataclass(frozen=True)
class Coverage:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class History:
    snapshot: d.Snapshot
    observations: dict[str, datetime | None] = field(default_factory=dict)
    coverage: tuple[Coverage, ...] = ()
    complete: bool = False


def validate_history(history):
    d.validate(history.snapshot)
    if type(history.complete) is not bool:
        raise LocalError('history.complete must be boolean')
    for key, when in history.observations.items():
        if key not in history.snapshot.items:
            raise LocalError('history observation requires managed item')
        if when is not None:
            d.require_aware(when)
    for span in history.coverage:
        if d.require_aware(span.start) > d.require_aware(span.end):
            raise LocalError('history coverage start exceeds end')
    return history


def empty_history(snapshot):
    """New initialization only; never a recovery for missing required history."""
    return History(replace(snapshot, items={}, comments={}, reminders={}, occurrences={}))


def merge_history(history, incoming, *, removed_item_ids=(), removed_comment_ids=()):
    """Stable-ID merge. Incoming current evidence wins; omission never deletes.

    Caller explicitly supplies confirmed deletions/departures and comment removals
    (including loss of ownership). Descendants of removed items are removed too.
    Absence in active Sync is not such evidence. Both inputs are complete domain
    models, including necessary ancestor context.
    """
    validate_history(history)
    validate_history(incoming)
    old, new = history.snapshot, incoming.snapshot
    if (old.binding.account_id, old.binding.root_id) != (new.binding.account_id, new.binding.root_id):
        raise LocalError('foreign history account/root')
    items = {**old.items, **new.items}
    removed = set(removed_item_ids)
    while True:
        expanded = removed | {i.id for i in items.values() if i.parent_id in removed}
        if expanded == removed:
            break
        removed = expanded
    # Retired managed categories are current scope departures.
    removed |= {i.id for i in items.values() if i.category_id not in new.categories}
    items = {k: v for k, v in items.items() if k not in removed}
    collections = {}
    for name in ('comments', 'reminders', 'occurrences'):
        merged = {**getattr(old, name), **getattr(new, name)}
        collections[name] = {k: v for k, v in merged.items() if v.item_id in items
                             and not (name == 'comments' and k in removed_comment_ids)}
    observations = dict(history.observations)
    for key, value in incoming.observations.items():
        previous = observations.get(key)
        # A newer pending context must survive overlapping older fetch windows.
        observations[key] = None if value is None or (key in observations and previous is None) else max(previous, value) if previous else value
    observations = {k: v for k, v in observations.items() if k in items}
    merged = replace(new, items=items, **collections)
    return validate_history(History(merged, observations,
        tuple(dict.fromkeys(history.coverage + incoming.coverage)), history.complete or incoming.complete))


def prune_history(history, finalized_cursor, *, output_finalized=False, saved_cursor=None):
    """T15-only authorization boundary: call after output flush AND cursor save.

    Pure/idempotent: no cursor I/O, rollback, or implicit authorization from a
    cursor setter. Keep all context required by activity newer than the boundary.
    """
    validate_history(history)
    d.require_aware(finalized_cursor)
    if not output_finalized or saved_cursor is None or d.require_aware(saved_cursor) < finalized_cursor:
        raise LocalError('history cleanup requires finalized output and published cursor')
    s = history.snapshot
    keep = {k for k, when in history.observations.items() if when is None or when > finalized_cursor}
    keep |= {i.id for i in s.items.values() if i.completed_at is not None and i.completed_at > finalized_cursor}
    keep |= {o.item_id for o in s.occurrences.values() if o.completed_at > finalized_cursor}
    keep |= {c.item_id for c in s.comments.values() if c.added_at is None or c.added_at > finalized_cursor}
    for key in tuple(keep):
        keep.update(i.id for i in d.ancestors(s, key))
    items = {k: v for k, v in s.items.items() if k in keep}
    # Ancestor own comments remain context for newer descendant activity.
    result = replace(s, items=items,
        comments={k: v for k, v in s.comments.items() if v.item_id in keep},
        reminders={k: v for k, v in s.reminders.items() if v.item_id in keep},
        occurrences={k: v for k, v in s.occurrences.items() if v.item_id in keep and v.completed_at > finalized_cursor})
    coverage = tuple(Coverage(max(c.start, finalized_cursor), c.end) for c in history.coverage if c.end > finalized_cursor)
    return validate_history(History(result,
        {k: v for k, v in history.observations.items() if k in keep and (v is None or v > finalized_cursor)}, coverage, history.complete))
