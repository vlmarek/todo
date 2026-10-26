"""Report presentation only. Callers own interval selection and finalization."""
from dataclasses import dataclass
from todo_lib.domain import instant_key, root_task, split_waiting
from .formatting import absolute, multiline, owner_title
from .render import document, _population, _list_due


@dataclass(frozen=True)
class ReportEvent:
    item_id: str
    instant: object
    kind: str = 'completed'
    body: str | None = None
    event_id: str | None = None
    source_order: int = 0


def _event_key(event):
    return (instant_key(event.instant), event.event_id is None,
            event.event_id or '', event.item_id, event.source_order)


def render_report(snapshot, start, until, *, finished=(), progress=(), hidden=()):
    """Render supplied eligible populations, even outside the displayed interval.

    ReportEvent.kind is completed or comment. Finished receives root occurrences;
    progress receives step completions and owner comments. No history/network or
    current visibility eligibility is inferred here. Stable input order breaks
    otherwise identical source ties.
    """
    zone = snapshot.account.timezone
    sections = [f'Report\nFrom (exclusive): {absolute(start, zone)}\nUntil (inclusive): {absolute(until, zone)}\nTimezone: {zone}']
    def events_section(name, events, is_finished):
        events = tuple(events)
        if not events:
            return name + '\n  None.'
        groups = {}
        for event in events:
            item = snapshot.items[event.item_id]
            if is_finished and item.parent_id is not None:
                raise ValueError('Finished requires supplied root-task occurrences')
            root = root_task(snapshot, item.id)
            groups.setdefault(root.category_id, {}).setdefault(root.id, []).append(event)
        lines = [name]
        for category_id in sorted(groups, key=lambda cid: (snapshot.categories[cid].name.lower(), cid)):
            lines.append('  ' + snapshot.categories[category_id].name)
            roots = groups[category_id]
            for root_id in sorted(roots, key=lambda rid: (min(instant_key(e.instant) for e in roots[rid]), rid)):
                events = sorted(roots[root_id], key=_event_key)
                if is_finished:
                    for event in events:
                        lines.append('    ' + absolute(event.instant, zone) + ' — ' + snapshot.items[root_id].title)
                    continue
                lines.append('    ' + snapshot.items[root_id].title)
                for event in events:
                    item = snapshot.items[event.item_id]
                    context = owner_title(snapshot, item, deep_only=True)
                    if event.kind == 'comment':
                        label = 'Comment: ' if item.parent_id is None else 'Comment on step: ' + context + ' — '
                        text = multiline(event.body or '', '      ' + absolute(event.instant, zone) + ' — ' + label, '        ')
                    elif event.kind == 'completed':
                        text = '      ' + absolute(event.instant, zone) + ' — Completed step: ' + context
                    else:
                        raise ValueError('unknown supplied report event kind')
                    lines.append(text)
        return '\n'.join(lines)
    sections.extend([events_section('Finished', finished, True), events_section('Progress', progress, False)])
    selected, population = _population(snapshot, hidden)
    if not selected:
        sections.append('Hidden\n  None.')
    else:
        lines = ['Hidden']
        def visit(parent_id, category_id, depth):
            for item in sorted((i for i in population.values() if i.parent_id == parent_id and i.category_id == category_id), key=lambda i: (i.title.lower(), i.id)):
                indent = '  ' * depth
                lines.append(indent + item.title + ('  [context]' if item.id not in selected else ''))
                if item.id in selected:
                    lines.append(indent + '  Until: ' + _list_due(item, zone))
                    _, reason = split_waiting(item.description)
                    if reason is not None:
                        lines.append(multiline(reason, indent + '  Reason: ', indent + '    '))
                visit(item.id, category_id, depth + 1)
        for category in sorted(snapshot.categories.values(), key=lambda c: (c.name.lower(), c.id)):
            if any(i.category_id == category.id for i in population.values()):
                lines.append('  ' + category.name)
                visit(None, category.id, 2)
        sections.append('\n'.join(lines))
    return document('\n\n'.join(sections))
