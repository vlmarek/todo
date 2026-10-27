"""Pure scheduling proposals and the canonical scheduling workflow entry point.

Unknown English expressions are submitted only when no preflight day comparison
is needed. The gateway owns parser reconciliation; local predictions never become
remote facts. All replacements preserve the model's precise unrelated fields.
"""
from dataclasses import dataclass, replace
from todo_lib import domain as d
from todo_lib.domain.text import START, END


def offsets(snapshot, item_id):
    return tuple(r.minutes for r in snapshot.reminders.values() if r.item_id == item_id and r.type == 'relative')


def offset_text(values):
    def scalar(minutes):
        if minutes == 0:
            return '0m'
        for divisor, unit in ((10080, 'w'), (1440, 'd'), (60, 'h'), (1, 'm')):
            if minutes % divisor == 0:
                return f'{minutes // divisor}{unit}'
    return ', '.join(scalar(n) for n in values) or None


@dataclass(frozen=True)
class Proposal:
    item: d.Item
    reminders: tuple[int, ...]
    unresolved: bool = False
    enable: bool = False
    retain_absolute: bool = True


def propose(request, snapshot, item, now):
    options = dict(request.options)
    clear = bool(options.get('clear'))
    unhide = request.command == 'unhide'
    enable = request.command == 'hide' or bool(options.get('hide'))
    attention = item.attention
    if 'at' in options:
        attention = d.retain_recurrence(d.parse_attention(options['at'], now,
            snapshot.account.timezone), item.attention)
        # Locally resolved instants serialize as fixed UTC due.date values.
        # The provider defaults their omitted timezone to the account timezone.
        # Retained recurring zones (including floating None) remain authoritative.
        if attention.exact and not attention.recurring and attention.zone is None:
            attention = replace(attention, zone=snapshot.account.timezone)
        # Date-only occurrences have no applicable recurrence timezone on the wire.
        if attention.kind == 'date' and attention.zone is not None:
            attention = replace(attention, zone=None)
    if clear:
        attention = None
    labels = item.labels - {'waiting'} if clear or unhide else item.labels
    if enable:
        labels = labels | {'waiting'}
    description = item.description
    if clear or unhide:
        if d.item_description(item)[1] is not None:
            description = d.with_waiting_reason(description, None)
    elif 'reason' in options:
        if not enable:
            raise d.DomainError('reason requires explicit hiding')
        try:
            if d.convention_diagnostic(item) and any(line in (START, END) for line in description.split('\n')):
                raise d.DomainError('unsafe waiting reason rewrite: literal block')
            description = d.with_waiting_reason(description, options['reason'] or None)
        except d.DomainError as error:
            raise d.DomainError(d.scalar_title(item.title) + ': ' + str(error)) from None
    markers = options.get('reminder')
    reminders = offsets(snapshot, item.id)
    if markers is not None:
        reminders = () if markers == ('clear',) else tuple(d.parse_reminder(v) for v in markers)
    if clear:
        reminders = ()
    d.validate_reminder_offsets(reminders)
    unresolved = attention is not None and attention.kind == 'unresolved'
    if enable and attention is None:
        raise d.DomainError('hiding requires an attention day; use --due tomorrow')
    if unresolved and ('waiting' in labels or any(a.waiting and a.attention is not None for a in d.ancestors(snapshot, item.id))):
        attention.day(snapshot.account.timezone)  # specific expression + ISO advice
    if enable and attention.day(snapshot.account.timezone) <= now.astimezone(
            d.account_timezone(snapshot.account.timezone)).date():
        raise d.DomainError('hiding requires a future attention day; hiding ends at the start of that day')
    if reminders:
        if not snapshot.account.capabilities.reminders:
            raise d.DomainError('relative reminders require a supported account capability')
        if attention is None or (not unresolved and not attention.exact):
            raise d.DomainError('reminders require timed attention; clear or replace reminders with a timed date')
    return Proposal(replace(item, attention=attention, labels=frozenset(labels),
                            description=description), reminders, unresolved, enable, markers is None and not clear)


def validate_proposals(snapshot, proposals, hidden_names=()):
    """Validate the complete resulting tree before executing any operation.

    An unresolved occurrence has no locally comparable day. Its absence here is
    only a structural-validation placeholder, never a published/accepted value.
    All required day comparisons and capabilities were checked by propose().
    """
    items = dict(snapshot.items)
    reminders = dict(snapshot.reminders)
    for index, proposal in enumerate(proposals):
        item = proposal.item
        items[item.id] = replace(item, attention=None) if proposal.unresolved else item
        reminders = {k: r for k, r in reminders.items() if r.item_id != item.id or (r.type == 'absolute' and proposal.retain_absolute)}
        if not proposal.unresolved:
            for j, minutes in enumerate(proposal.reminders):
                key = f'proposal-reminder-{index}-{j}'
                reminders[key] = d.Reminder(key, item.id, minutes)
    return d.validate(replace(snapshot, items=items, reminders=reminders), hidden_names)


class SchedulingWorkflow:
    def __init__(self, synchronizer, **kwargs):
        from .capture import CaptureWorkflow
        self.workflow = CaptureWorkflow(synchronizer, **kwargs)

    def execute(self, request, **kwargs):
        return self.workflow.execute(request, **kwargs)


def execute(request, synchronizer, **kwargs):
    delivery = kwargs.pop('deliver', False)
    return SchedulingWorkflow(synchronizer, **kwargs).execute(request, deliver=delivery)
