"""Pure scheduling proposals and the canonical scheduling workflow entry point.

Unknown English expressions remain unresolved through removal consent. The
gateway owns parser reconciliation; local predictions never become remote facts. All replacements preserve the model's precise unrelated fields.
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


def equivalent(left, right, zone):
    """Bounded local identity match, never infer expression equivalence."""
    if left.type != right.type:
        return False
    if left.type == 'relative':
        return left.minutes == right.minutes
    a, b = (d.attention_prediction(v, zone) for v in (left.due, right.due))
    if a.kind == 'unresolved' or b.kind == 'unresolved':
        return False
    for due in (a, b):
        # The open provider due object permits omissions. Its mapper's default
        # is useful for display, but cannot establish nonrecurrence for identity
        # matching. Known recurrence also needs its original rule wording.
        if due.raw_due is not None and 'is_recurring' not in due.raw_due:
            return False
        if due.recurring and (not due.rule or not due.rule.strip()):
            return False
    # Recurrence wording and parser language are part of scheduling semantics.
    return (d.same_attention(a, b, zone) and a.language == b.language
            and (not a.recurring or a.rule == b.rule))


@dataclass(frozen=True)
class Proposal:
    item: d.Item
    desired: tuple[d.Reminder, ...] = ()
    unresolved: bool = False
    enable: bool = False
    retained: tuple[d.Reminder, ...] = ()
    additions: tuple[d.Reminder, ...] = ()
    removals: tuple[d.Reminder, ...] = ()


def propose(request, snapshot, item, now):
    options = dict(request.options)
    clear = bool(options.get('clear'))
    unhide = request.command == 'unhide'
    enable = request.command == 'hide' or bool(options.get('hide'))
    attention = item.attention
    if 'at' in options:
        attention = d.retain_recurrence(d.parse_attention(options['at'], now,
            snapshot.account.timezone), item.attention, snapshot.account.timezone)
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
    existing = tuple(sorted((r for r in snapshot.reminders.values() if r.item_id == item.id),
        key=lambda r: (0, r.minutes, r.id) if r.type == 'relative' else
                      (1, d.attention_order(r.due, snapshot.account.timezone), r.id)))
    markers = request.reminder_markers or tuple((k, v) for k in ('reminder', 'reminder-at') for v in options.get(k, ()))
    desired, retained, additions = [], [], []
    if not markers and not clear:
        desired.extend(existing)
        retained.extend(existing)
    elif not clear and markers != (('reminder', 'clear'),):
        for kind, value in markers:
            reminder_type = 'relative' if kind == 'reminder' else 'absolute'
            if value == 'keep':
                contributions = [r for r in existing if r.type == reminder_type]
            elif reminder_type == 'relative':
                contributions = [d.Reminder('requested', item.id, d.parse_reminder(value))]
            else:
                due = d.parse_attention(value, now, snapshot.account.timezone)
                if due.kind != 'unresolved' and not due.exact:
                    raise d.DomainError('absolute reminders require an exact time')
                due = replace(due, language='en')
                contributions = [d.Reminder('requested', item.id, None, type='absolute', due=due)]
            prior = tuple(desired)
            for reminder in contributions:
                if any(equivalent(reminder, other, snapshot.account.timezone) or
                       (reminder.id != 'requested' and reminder.id == other.id) for other in prior):
                    raise d.DomainError('duplicate requested reminder schedule (including keep)')
                match = reminder if value == 'keep' else next((r for r in existing if equivalent(r, reminder, snapshot.account.timezone)), None)
                if match is not None:
                    desired.append(match)
                    retained.append(match)
                else:
                    desired.append(reminder)
                    additions.append(reminder)
    removals = tuple(r for r in existing if r.id not in {v.id for v in retained})
    reminders = tuple(r.minutes for r in desired if r.type == 'relative')
    d.validate_reminder_offsets(reminders)
    if (additions or removals) and not snapshot.account.capabilities.reminders:
        raise d.DomainError('reminders require a supported account capability')
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
            raise d.DomainError('relative reminders require timed attention; explicitly clear or replace relative reminders, using --reminder-at keep to preserve absolute reminders')
    return Proposal(replace(item, attention=attention, labels=frozenset(labels),
                            description=description), tuple(desired), unresolved, enable,
                    tuple(retained), tuple(additions), removals)


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
        reminders = {k: r for k, r in reminders.items() if r.item_id != item.id}
        for j, reminder in enumerate(proposal.desired):
            if reminder.type == 'absolute' and reminder.due.kind == 'unresolved':
                continue
            if reminder.type == 'relative' and proposal.unresolved:
                continue
            key = f'proposal-reminder-{index}-{j}'
            reminders[key] = replace(reminder, id=key)
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
