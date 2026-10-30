"""Offline, bounded diagnostics for consumed reminder fields only."""
from .text import scalar_title


def safe(value):
    if isinstance(value, str):
        value = scalar_title(value)
        return ''.join(c if ord(c) >= 32 and not 127 <= ord(c) <= 159
                       else '\\u%04x' % ord(c) for c in value)
    if value is None:
        return 'null'
    if type(value) in (bool, int, float):
        return str(value)
    return '<malformed object>' if isinstance(value, dict) else '<malformed value>'


def context(reminder, items=(), categories=(), *, cached=False):
    """Accept wire or model records; never stringify arbitrary provider objects."""
    def get(record, name, default=None):
        return record.get(name, default) if isinstance(record, dict) else getattr(record, name, default)
    owner = get(reminder, 'item_id')
    item = items.get(owner) if hasattr(items, 'get') and isinstance(owner, str) else None
    parts = ['reminder ' + safe(get(reminder, 'id')), 'owner ' + safe(owner)]
    if item is not None:
        parts.append(('cached ' if cached else '') + 'title ' + safe(get(item, 'title', get(item, 'content'))))
        category_id = get(item, 'category_id', get(item, 'project_id'))
        category = categories.get(category_id) if hasattr(categories, 'get') and isinstance(category_id, str) else None
        if category is not None:
            parts.append(('cached ' if cached else '') + 'category ' + safe(get(category, 'name')))
    kind = get(reminder, 'type')
    parts.append('type ' + safe(kind))
    if kind == 'relative':
        parts.append('offset ' + safe(get(reminder, 'minute_offset', get(reminder, 'minutes'))))
    else:
        due = get(reminder, 'due')
        if not isinstance(reminder, dict):
            due = getattr(due, 'raw_due', None)
        if isinstance(due, dict):
            summary = ', '.join(k + '=' + safe(due[k])
                for k in ('date', 'timezone') if k in due)
            parts.append('schedule ' + (summary or '<missing date>'))
        else:
            parts.append('schedule ' + safe(due))
    return '; '.join(parts)


def failure(error, *contexts):
    """Retain the original exception class/cause and identify repairable remote data."""
    result = type(error)(str(error) + ' [' + ' | '.join(contexts) + ']')
    result.managed_reminder = True
    return result


class ReminderDiagnostic(str):
    """A string issue retaining command-local reminder repair classification."""
    managed_reminder = True


def repair_guidance(issues):
    if any(getattr(issue, 'managed_reminder', False) for issue in issues):
        return 'Repair the identified managed reminder in the provider before synchronizing; do not replay the mutation.'
    return 'Read-only recovery: todo --refresh now; do not replay the mutation.'
