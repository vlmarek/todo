"""Bounded, one-to-one completion evidence association; no I/O or time tolerance.

Activity entries remain independent. Supplemental records prefer exact instants,
then nearest remaining chronological counterparts, with source order breaking ties.
Association precedes undo and caller interval selection. Provenance lives on pending
occurrences so overlapping reads cannot reapply a supplied undo or seed an alias.
"""
from dataclasses import replace
from todo_lib import domain as d
from todo_lib.local.occurrence import ObservedOccurrence


def event_key(event):
    return (d.instant_key(event.event_date), event.id is None,
            event.id or '', event.object_id)


def _observed(value):
    if isinstance(value, ObservedOccurrence):
        return value
    return ObservedOccurrence(value.id, value.item_id, value.completed_at,
                              value.recurring, value.undone)


def reconcile_completions(items, completed, activities, retained=(), *, end=None):
    items = {k: i for k, i in items.items() if i.completed or i.recurring}
    occurrences = {o.id: _observed(o) for o in retained if o.item_id in items}
    events, seen = [], set()
    for event in activities:
        if event.id is not None:
            if event.id in seen:
                continue
            seen.add(event.id)
        events.append(event)
    events.sort(key=event_key)
    # Anonymous multiplicity is local to an owner/type/instant. Unrelated
    # events in a global report must not change the keys from a scoped sync read.
    anonymous_counts, identities = {}, []
    for event in events:
        if event.id is not None:
            identities.append(('activity:' if event.event_type == 'completed' else 'undo:') + event.id)
        else:
            group = (event.object_id, event.event_type, d.instant_key(event.event_date))
            ordinal = anonymous_counts.get(group, 0)
            anonymous_counts[group] = ordinal + 1
            prefix = 'anonymous:' if event.event_type == 'completed' else 'undo-anonymous:'
            identities.append(prefix + event.object_id + '@' + str(group[2]) + ':' + str(ordinal))
    for order, event in enumerate(events):
        if (event.object_type != 'item' or event.event_type != 'completed'
                or event.object_id not in items):
            continue
        key = identities[order]
        old = occurrences.get(key)
        occurrences[key] = ObservedOccurrence(key, event.object_id, event.event_date,
            items[event.object_id].recurring, old.undone if old else False,
            event.id, order, old.completed_ids if old else (), old.undo_ids if old else (),
            activity_backed=True)
    # Include previously observed activity when bounded discovery only supplies
    # completed records. Ordinary fallback occurrences are supplemental too.
    backbone = {k: o for k, o in occurrences.items()
                if o.activity_backed}
    supplements = {o.id: o for o in occurrences.values() if o.id not in backbone}
    for record in completed:
        if not record.deleted and record.item.id in items:
            supplements.setdefault(record.occurrence.id, _observed(record.occurrence))
    used = {k for k, o in backbone.items() if o.completed_ids}
    remaining = []
    for key, value in supplements.items():
        existing = next((k for k, o in backbone.items() if key in o.completed_ids), None)
        if existing is not None:
            used.add(existing)
            occurrences.pop(key, None)
        else:
            remaining.append(value)
    # Greedy closest pairs align partially overlapping sequences without a
    # numerical threshold. Exact matches are consumed before unequal matches.
    by_owner = {}
    for key, value in backbone.items():
        if key not in used:
            by_owner.setdefault(value.item_id, []).append((key, value))
    pairs = sorted((abs(d.instant_key(c.completed_at) - d.instant_key(a.completed_at)),
                    d.instant_key(c.completed_at), a.source_order, c.id, k)
                   for c in remaining for k, a in by_owner.get(c.item_id, ()))
    matched = set()
    for _, _, _, identity, key in pairs:
        if identity in matched or key in used:
            continue
        value = supplements[identity]
        old = occurrences[key]
        occurrences[key] = replace(old, completed_ids=old.completed_ids + (identity,),
            undone=old.undone or value.undone,
            undo_ids=tuple(dict.fromkeys(old.undo_ids + value.undo_ids)))
        occurrences.pop(identity, None)
        used.add(key)
        matched.add(identity)
    for value in remaining:
        if value.id not in matched:
            occurrences[value.id] = value
    timeline = []
    for key, value in occurrences.items():
        timeline.append(((d.instant_key(value.completed_at), value.activity_id is None,
                          value.activity_id or '', value.item_id, value.source_order), 'completed', key, value.item_id))
    consumed = {identity for o in occurrences.values() for identity in o.undo_ids}
    for order, event in enumerate(events):
        if (event.object_type == 'item' and event.event_type == 'uncompleted'
                and (end is None or d.instant_key(event.event_date) <= d.instant_key(end))):
            key = identities[order]
            if key not in consumed:
                timeline.append(((*event_key(event), order), 'undo', key, event.object_id))
    stacks = {}
    for _, kind, key, owner in sorted(timeline):
        if owner not in items or not items[owner].recurring:
            continue
        stack = stacks.setdefault(owner, [])
        if kind == 'completed':
            if not occurrences[key].undone:
                stack.append(key)
        elif stack:
            target = stack.pop()
            old = occurrences[target]
            occurrences[target] = replace(old, undone=True, undo_ids=old.undo_ids + (key,))
    return occurrences
