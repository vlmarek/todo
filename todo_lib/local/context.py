"""Saved current/history composition, with explicit owner-collection authority."""
from dataclasses import replace

from todo_lib import domain as d
from .safety import LocalError


def saved_context(current, history, *, authoritative_collections=True):
    """Current item fields win; reopened objects discard old completion evidence.

    Ordinary reads treat current owners' omitted comments/reminders as removed.
    Initialization retains those collections until its fresh discovery resolves
    their ownership and omission. Neither policy invents current membership.
    """
    if current is None:
        return history
    if (current.binding != history.binding or current.account != history.account
            or current.categories != history.categories):
        raise LocalError('incompatible retained history; restore a consistent saved set')
    items = {**history.items, **current.items}
    collections = {}
    for name in ('comments', 'reminders'):
        retained = getattr(history, name)
        collections[name] = {k: value for k, value in retained.items()
            if not authoritative_collections or value.item_id not in current.items}
        collections[name].update(getattr(current, name))
    occurrences = {**history.occurrences, **current.occurrences}
    collections['occurrences'] = {k: value for k, value in occurrences.items()
        if items[value.item_id].completed or items[value.item_id].recurring}
    return d.validate(replace(current, items=items, **collections))
