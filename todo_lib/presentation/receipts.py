"""Receipts consume accepted outcomes only; never infer remote acceptance."""
from todo_lib.domain import scalar_title
from dataclasses import dataclass
from todo_lib.domain import ancestors
from .formatting import actual_due, compact, multiline, owner_title, edge
from .render import document


def _scalar(value):
    if isinstance(value, str):
        value = edge(value)
    if value is None or value == '' or value == () or value == []:
        return 'none'
    if isinstance(value, bool):
        return 'on' if value else 'off'
    return str(value)


def _change_line(field, before, after):
    if field == 'Title':
        before, after = scalar_title(before), scalar_title(after)
    return multiline(_scalar(before) + ' -> ' + _scalar(after), f'  {field}: ', '    ')


def _changes(changes):
    lines = []
    for field, before, after in changes:
        if before != after:
            lines.append(_change_line(field, before, after))
    return lines


def render_mutation(snapshot, item, action='Updated', *, changes=(), attention=None, also_reopened=()):
    """Scalar values are display-ready; priority callers supply P1..P4 strings."""
    changed = _changes(changes)
    if action in ('Updated', 'Moved') and not changed:
        return document()
    text = [f'{action} {item.role}: ' + owner_title(snapshot, item, deep_only=True), *changed]
    if action == 'Created' and attention is not None:
        text.append('  Due: ' + actual_due(attention, snapshot.account.timezone))
    if also_reopened:
        text.append('Also reopened:')
        for ancestor in also_reopened:
            text.append(f'  {ancestor.role}: {owner_title(snapshot, ancestor)} — {snapshot.categories[ancestor.category_id].name}')
    return document('\n'.join(text))


def render_move(before_snapshot, before, after_snapshot, after):
    def parent_value(snapshot, item):
        if item.parent_id is None:
            return None
        parent = snapshot.items[item.parent_id]
        return ' > '.join(scalar_title(a.title) for a in (*ancestors(snapshot, parent.id), parent))
    # Display paths and names are context, not identity: different parents can
    # render identically, and the same parent can be renamed between snapshots.
    changes = []
    if before.parent_id != after.parent_id:
        changes.append(_change_line('Parent', parent_value(before_snapshot, before),
                                    parent_value(after_snapshot, after)))
    if before.category_id != after.category_id:
        changes.append(_change_line('Category', before_snapshot.categories[before.category_id].name,
                                    after_snapshot.categories[after.category_id].name))
    if not changes:
        return document()
    return document('\n'.join([
        f'Moved {after.role}: ' + owner_title(after_snapshot, after, deep_only=True), *changes]))


def render_created_category(category):
    return document('Created category: ' + category.name)


def render_comment_bodies(snapshot, owner, bodies, *, owner_identified=False):
    bodies = tuple(bodies)
    if not bodies:
        return document()
    lines = [] if owner_identified else ['Comments for: ' + owner_title(snapshot, owner)]
    lines.extend(multiline(body, '-> ', '  ') for body in bodies)
    return document('\n'.join(lines))


@dataclass(frozen=True)
class CommentOutcome:
    """One attempted/unattempted editor operation, in actual operation order.

    status: Accepted, Failed, Unknown, Not attempted. operation: added, edited,
    deleted (accepted), or add, edit, delete (other statuses). body is used for
    additions, timestamp for existing comments, position when timestamp is absent.
    """
    status: str
    operation: str
    body: str | None = None
    timestamp: object = None
    position: int | None = None
    reason: str | None = None


def render_comment_edit(snapshot, owner, *, added=0, edited=0, deleted=0, outcomes=None):
    if outcomes is None:
        if added + edited + deleted == 0:
            return document()
        return document(f'Comments updated: {owner_title(snapshot, owner)} · {added} added, {edited} edited, {deleted} deleted')
    stdout, stderr = [], ['Comments for: ' + owner_title(snapshot, owner) + ' — partial failure']
    for outcome in outcomes:
        if outcome.status not in ('Accepted', 'Failed', 'Unknown', 'Not attempted'):
            raise ValueError('unknown comment outcome status')
        if outcome.body is not None:
            identity = '“' + edge(outcome.body) + '”'
        elif outcome.timestamp is not None:
            identity = 'comment from ' + compact(outcome.timestamp, snapshot.account.timezone)
        else:
            if outcome.position is None:
                raise ValueError('comment outcome requires body, timestamp or operation position')
            identity = 'comment at position ' + str(outcome.position)
        line = multiline(identity, f'  {outcome.status}: {outcome.operation} ', '    ')
        if outcome.reason:
            line += multiline(outcome.reason, ' — ', '    ')
        (stdout if outcome.status == 'Accepted' else stderr).append(line)
    return document('\n'.join(stdout), '\n'.join(stderr))


def render_receipts(receipts):
    """Compose accepted-operation documents in operation order, per stream.

    Group each owner's comment bodies in one render_comment_bodies call, or use
    owner_identified=True after an earlier receipt identifies that owner. Supply
    the preserved pre-completion snapshot when rendering departed ancestors.
    """
    receipts = tuple(receipts)
    return document('\n'.join(r.stdout for r in receipts if r.stdout),
                    '\n'.join(r.stderr for r in receipts if r.stderr))


def render_reminder_replacement(snapshot, item, removals, additions):
    """Proposed removals only; unresolved expressions are never accepted dates."""
    from .formatting import reminders_text
    zone = snapshot.account.timezone
    lines = ['Reminder replacement for: ' + owner_title(snapshot, item), 'Remove:']
    lines.extend('  - ' + reminders_text([r], zone) for r in removals)
    lines.append('Add:')
    for r in additions:
        value = ('expression (Todoist): ' + scalar_title(r.due.expression)
                 if r.type == 'absolute' and r.due.kind == 'unresolved'
                 else reminders_text([r], zone))
        lines.append('  - ' + value)
    if not additions:
        lines.append('  None.')
    lines.append('To keep existing reminders, include:')
    hints = []
    for r in removals:
        hint = '--reminder-at keep'
        if r.type == 'relative':
            value = '0m' if r.minutes == 0 else reminders_text([r], zone).removesuffix(' before')
            hint = '--reminder ' + value
        if hint not in hints:
            hints.append(hint)
    lines.extend('  ' + hint for hint in hints)
    return document('\n'.join(lines))
