"""Complete pure documents; no transport, cursor decisions or terminal I/O."""
from todo_lib.domain import scalar_title, item_description
from dataclasses import dataclass
from todo_lib.domain import (ancestors, ordered_siblings, instant_key, instant_datetime,
                             account_timezone, urgency, Urgency, now_queue, visibility,
                             attention_order, subtree)
from .formatting import (Color, edge, multiline, absolute, compact, owner_title,
                         waiting_reason, time_block, ancestor_path, convention_warnings)


@dataclass(frozen=True)
class Document:
    stdout: str = ''
    stderr: str = ''


def document(text='', warnings=''):
    return Document(edge(text), edge(warnings))


def _item(snapshot, item):
    return snapshot.items[item] if isinstance(item, str) else item


def _reminders(snapshot, item):
    return [r for r in snapshot.reminders.values() if r.item_id == item.id]


def _comments(snapshot, item, indent=''):
    comments = sorted((c for c in snapshot.comments.values() if c.item_id == item.id),
                      key=lambda c: (c.added_at is None, instant_key(c.added_at) if c.added_at is not None else 0, c.id))
    return [multiline(c.body if c.body.strip() else '[no text]', indent + '- ' + compact(c.added_at, snapshot.account.timezone) + '  ', indent + '  ') for c in comments]


def render_comments(snapshot, item):
    item = _item(snapshot, item)
    return document('\n'.join(['Comments for: ' + owner_title(snapshot, item)] + (_comments(snapshot, item) or ['Comments: none'])))


def render_now(snapshot, now, *, items=None, hidden_names=(), all_items=False, category_id=None, color=Color()):
    """Optional items is an already selected population; selection never refetches."""
    zone = snapshot.account.timezone
    if items is None:
        items = (i for i in snapshot.items.values() if not i.completed) if all_items else now_queue(snapshot, now, hidden_names)
    rows = [i for i in items if category_id is None or i.category_id == category_id]
    rows.sort(key=lambda i: (urgency(i, now, zone), i.priority,
                            attention_order(i.attention, zone) if i.attention else 0, i.title.lower(), i.id))
    if not rows:
        return document('No actionable items.')
    local = instant_datetime(now).astimezone(account_timezone(zone))
    header_day = absolute(now, zone).split(',')[0]
    counts = {section: sum(urgency(i, now, zone) == section for i in rows) for section in Urgency}
    sections = [f'NOW · {header_day} · {local:%H:%M} {zone}\n{len(rows)} actions · {counts[Urgency.OVERDUE]} overdue · {counts[Urgency.TODAY]} today']
    for section in Urgency:
        if not counts[section]:
            continue
        lines = [section.name.replace('_', ' ') + f' ({counts[section]})']
        for item in rows:
            if urgency(item, now, zone) != section:
                continue
            text = '  ' + color.priority(item.priority) + ' ' + scalar_title(item.title)
            if item.attention is not None:
                text += '  ' + time_block(item.attention, _reminders(snapshot, item), now, zone, color)
            reason, _ = waiting_reason(item, now, zone) if item.waiting else (None, None)
            if reason is not None:
                text += multiline(reason, ' (', '    ') + ')'
            if item.parent_id is not None:
                text += color.context(' — ' + ancestor_path(snapshot, item))
            lines.append(text)
        sections.append('\n'.join(lines))
    return document('\n\n'.join(sections), convention_warnings(snapshot, rows))


def _waiting_section(snapshot, item, now):
    zone = snapshot.account.timezone
    policies = [item] if item.waiting and item.attention is not None else [a for a in ancestors(snapshot, item.id) if a.waiting and a.attention is not None]
    inactive = item.waiting and item.attention is None
    if not policies:
        return 'Waiting: inactive (no attention date)' if inactive else 'Waiting: none'
    entries = []
    for policy in policies:
        reason, age = waiting_reason(policy, now, zone)
        own = policy.id == item.id
        context = ' > '.join(scalar_title(a.title) for a in (*ancestors(snapshot, policy.id), policy))
        if reason is None:
            if len(policies) == 1:
                return 'Waiting: enabled' if own else ('Waiting: inactive (no attention date)\n' if inactive else '') + 'Waiting: inherited from ' + context
            entries.append('- Inherited from ' + context)
        else:
            prefix = '- ' if own else '- Inherited from ' + context + ': '
            entries.append(multiline(reason, prefix, '  ') + (f' ({age}d)' if age is not None else ''))
    return ('Waiting: inactive (no attention date)\n' if inactive else '') + 'Waiting\n' + '\n'.join(entries)


def render_detail(snapshot, item, now, *, color=Color()):
    item = _item(snapshot, item)
    zone = snapshot.account.timezone
    title = scalar_title(item.title) + (color.context(' — ' + ancestor_path(snapshot, item)) if item.parent_id is not None else '')
    sections = [f'{color.priority(item.priority)}  {snapshot.categories[item.category_id].name}  {title}\nDue: ' + time_block(item.attention, _reminders(snapshot, item), now, zone, color, detail=True), _waiting_section(snapshot, item, now)]
    ordinary, _ = item_description(item)
    if edge(ordinary):
        sections.append('Description\n' + multiline(ordinary, '  ', '  '))
    steps = []
    def visit(parent, depth):
        for child in ordered_siblings(snapshot, item.category_id, parent.id):
            indent = '  ' * depth
            added = compact(child.added_at, zone) if child.added_at is not None else 'unknown'
            steps.append(f'{indent}- [{"x" if child.completed else " "}] P{child.priority} {scalar_title(child.title)} — added {added}')
            comments = _comments(snapshot, child, indent + '  ')
            if comments:
                steps.extend([indent + '  Comments', *comments])
            visit(child, depth + 1)
    visit(item, 0)
    sections.append('Steps\n' + '\n'.join(steps) if steps else 'Steps: none')
    comments = _comments(snapshot, item)
    sections.append('Comments\n' + '\n'.join(comments) if comments else 'Comments: none')
    return document('\n\n'.join(sections), '\n'.join(filter(None, ('todo: completed steps use retained history; coverage may be incomplete', convention_warnings(snapshot, (*ancestors(snapshot, item.id), *subtree(snapshot, item.id)))))))


def render_categories(snapshot):
    return document('\n'.join(c.name for c in sorted(snapshot.categories.values(), key=lambda c: (c.name.lower(), c.id))))


def _population(snapshot, items):
    selected = {i.id: i for i in items}
    contexts = {}
    for item in selected.values():
        for ancestor in ancestors(snapshot, item.id):
            if ancestor.id not in selected:
                contexts[ancestor.id] = ancestor
    return selected, {**contexts, **selected}


def render_waiting(snapshot, now, *, items=None, hidden_names=()):
    if items is None:
        items = [i for i in snapshot.items.values() if not i.completed and
                 visibility(snapshot, i.id, now, hidden_names).own_hidden and
                 not visibility(snapshot, i.id, now, hidden_names).category_hidden]
    selected, population = _population(snapshot, items)
    if not selected:
        return document('No waiting items.')
    lines = []
    def visit(parent_id, category_id, depth):
        for item in sorted((i for i in population.values() if i.parent_id == parent_id and i.category_id == category_id), key=lambda i: (i.title.lower(), i.id)):
            indent = '  ' * depth
            text = f'{indent}P{item.priority} {scalar_title(item.title)}'
            if item.id not in selected:
                text += '  [context]'
            else:
                text += '  until:' + item.attention.day(snapshot.account.timezone).isoformat()
                reason, _ = waiting_reason(item, now, snapshot.account.timezone)
                if reason is not None:
                    text += multiline(reason, ' (', indent + '  ') + ')'
            lines.append(text)
            visit(item.id, category_id, depth + 1)
    for category in sorted(snapshot.categories.values(), key=lambda c: (c.name.lower(), c.id)):
        if any(i.category_id == category.id for i in population.values()):
            lines.append(category.name)
            visit(None, category.id, 1)
    return document('\n'.join(lines), convention_warnings(snapshot, population.values()))


def _list(snapshot, items, empty):
    selected, population = _population(snapshot, items)
    if not selected:
        return empty
    # Task group ordering is priority/category/title; categories may recur when
    # priorities differ, preserving the specified group ordering.
    roots = sorted((i for i in population.values() if i.parent_id is None),
                   key=lambda i: (i.priority, snapshot.categories[i.category_id].name.lower(), i.title.lower(), i.id))
    lines = []
    last_category = None
    def visit(item, depth):
        indent = '  ' * depth
        lines.append(f'{indent}[{"x" if item.completed else " "}] P{item.priority} {scalar_title(item.title)} — ' + _list_due(item, snapshot.account.timezone))
        if item.waiting and item.attention is not None and item.id in selected:
            _, reason = item_description(item)
            lines.append(indent + '  Hidden until: ' + _list_due(item, snapshot.account.timezone))
            if reason is not None:
                lines.append(multiline(reason, indent + '  Reason: ', indent + '    '))
        children = sorted((i for i in population.values() if i.parent_id == item.id), key=lambda i: (i.priority, i.title.lower(), i.id))
        for child in children:
            visit(child, depth + 1)
    for root in roots:
        if root.category_id != last_category:
            lines.append(snapshot.categories[root.category_id].name)
            last_category = root.category_id
        visit(root, 1)
    return '\n'.join(lines)


def _list_due(item, zone):
    if item.attention is None:
        return 'none'
    if item.attention.exact:
        return absolute(item.attention.instant, zone)
    # Date-only attention retains its actual date, never inventing a timed due.
    return item.attention.date_value.isoformat()


def render_someday(snapshot, *, hidden_names=(), items=None):
    if items is None:
        items = [i for i in snapshot.items.values() if not i.completed and snapshot.categories[i.category_id].name in hidden_names]
    items = tuple(items)
    return document(_list(snapshot, items, 'No someday items.'), convention_warnings(snapshot, items))


def render_search(snapshot, items, *, all_items=False, earliest_completion=None):
    warning = ''
    if all_items:
        warning = 'todo: completed search uses retained history; earliest retained completion: ' + absolute(earliest_completion, snapshot.account.timezone) + '; coverage may be incomplete'
    empty = 'No matches in open or retained completed items.' if all_items else 'No matches.'
    items = tuple(items)
    return document(_list(snapshot, items, empty), '\n'.join(filter(None, (warning, convention_warnings(snapshot, items)))))


def render_ambiguity(snapshot, query, candidates, now, *, interactive=True, color=Color()):
    lines = [f'Multiple items match "{scalar_title(query)}":']
    for n, candidate in enumerate(candidates, 1):
        if not hasattr(candidate, 'title'):
            lines.append(f'  {n}. category: {candidate.name}')
            continue
        text = f'  {n}. {candidate.role}: {scalar_title(candidate.title)}  ' + time_block(candidate.attention, _reminders(snapshot, candidate), now, snapshot.account.timezone, color)
        if candidate.parent_id is not None:
            text += color.context(' — ' + ancestor_path(snapshot, candidate))
        text += ' — ' + snapshot.categories[candidate.category_id].name
        if candidate.completed:
            text += ' — completed ' + absolute(candidate.completed_at, snapshot.account.timezone)
        lines.append(text)
    if interactive:
        lines.append(f'Select 1-{len(candidates)}, or q to cancel:')
    return document('\n'.join(lines), '' if interactive else 'todo: multiple items match; interactive selection is unavailable')


def invalid_selection(count):
    return document(f'Enter a number from 1-{count}, or q.')


def history_warning(days):
    return document(warnings=f'todo: warning: Your Todoist account keeps {days} days of report history; set [report] warn_limited_history=false to hide this warning.')


def pagination_progress(resource, pages):
    return document(warnings=f'todo: loading {resource}: {pages} pages')


def render_report_cursor(cursor, zone):
    """A read-only scalar view; fetching/persisting the cursor is not rendering."""
    return document('Report cursor: ' + absolute(cursor, zone) + '\nTimezone: ' + zone)
