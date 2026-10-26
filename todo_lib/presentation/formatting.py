"""Shared pure display helpers. Exact keys order; datetime projections display."""
from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction
import os
import re
from todo_lib.domain import (account_timezone, ancestors, instant_datetime,
                             instant_key, split_waiting, attention_order)
from todo_lib.local.config import SOLARIZED


def edge(text):
    """Ignore blank edge lines, retaining every byte of internal content."""
    lines = text.split('\n')
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return '\n'.join(lines)


def multiline(text, first='', continuation=''):
    lines = edge(text).split('\n')
    return first + lines[0] + ''.join('\n' + continuation + line for line in lines[1:])


def absolute(value, zone):
    if value is None:
        return 'none'
    local = instant_datetime(value).astimezone(account_timezone(zone))
    # Locale independent English template.
    weekdays = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
    months = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
    return f'{weekdays[local.weekday()]} {local.day:02d} {months[local.month-1]} {local.year:04d}, {local:%H:%M:%S}'


def compact(value, zone):
    if value is None:
        return 'none'
    local = instant_datetime(value).astimezone(account_timezone(zone))
    return f'{local.year:04d}-{local:%m-%d %H:%M}'


def actual_due(value, zone):
    if value is None:
        return 'none'
    if not value.exact:
        return value.date_value.isoformat()
    local = instant_datetime(value.instant).astimezone(account_timezone(zone))
    return f'{local.year:04d}-{local:%m-%d %H:%M:%S} {zone}'


def ancestor_path(snapshot, item):
    return ' > '.join(i.title for i in ancestors(snapshot, item.id))


def owner_title(snapshot, item, *, deep_only=False):
    path = ancestors(snapshot, item.id)
    return item.title + (' — ' + ' > '.join(i.title for i in path) if path and (not deep_only or len(path) > 1) else '')


def waiting_reason(item, now, zone):
    """Interpret optional Since metadata without changing the canonical body."""
    _, body = split_waiting(item.description)
    if body is None:
        return None, None
    original = edge(body)
    reason = original.removeprefix('Reason: ')
    lines = reason.split('\n')
    age = None
    since_lines = [i for i, line in enumerate(lines) if line.startswith('Since: ')]
    if since_lines == [len(lines) - 1] and re.fullmatch(r'Since: \d{4}-\d{2}-\d{2}', lines[-1]):
        try:
            since = date.fromisoformat(lines[-1][7:])
            today = instant_datetime(now).astimezone(account_timezone(zone)).date()
            if since <= today:
                age = (today - since).days
                lines.pop()
        except ValueError:
            pass
    reason = edge('\n'.join(lines))
    if not reason.strip():
        return original, None
    return reason, age


@dataclass(frozen=True)
class Color:
    enabled: bool = False
    slots: dict = field(default_factory=lambda: dict(SOLARIZED))

    @classmethod
    def for_stdout(cls, stdout, mode='auto', *, environ=None, slots=None):
        env = os.environ if environ is None else environ
        enabled = mode == 'always' or (mode == 'auto' and stdout.isatty() and 'NO_COLOR' not in env and env.get('TERM') != 'dumb')
        return cls(enabled, dict(SOLARIZED if slots is None else slots))

    def paint(self, text, slot):
        if not self.enabled:
            return text
        color = self.slots[slot].lstrip('#')
        rgb = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
        return '\x1b[38;2;%d;%d;%dm%s\x1b[0m' % (*rgb, text)

    def priority(self, value):
        text = f'P{value}'
        return '\x1b[1m' + text + '\x1b[0m' if self.enabled and value == 1 else text

    def context(self, value):
        return self.paint(value, 'base01')


def reminder_text(minutes):
    if minutes == 0:
        return 'at due'
    for divisor, unit in ((10080, 'w'), (1440, 'd'), (60, 'h'), (1, 'm')):
        if minutes % divisor == 0:
            return f'{minutes // divisor}{unit} before'


def timing(value, reminders, now, zone):
    """Return relative text and overdue state, using exact rational arithmetic."""
    if value is None:
        return 'none', False
    if not value.exact:
        days = (value.date_value - instant_datetime(now).astimezone(account_timezone(zone)).date()).days
        core = 'today' if days == 0 else f'in {days}d' if days > 0 else f'{-days}d overdue'
        overdue = days < 0
    else:
        delta = Fraction(attention_order(value, zone)) - instant_key(now)
        overdue = delta < 0
        seconds = abs(delta)
        if seconds == 0:
            core = 'now'
        else:
            if seconds < 60:
                magnitude = '<1m'
            else:
                units = ((86400, 'd'), (3600, 'h')) if seconds >= 86400 else ((3600, 'h'), (60, 'm'))
                parts = []
                for size, suffix in units:
                    amount = int(seconds // size)
                    seconds %= size
                    if amount:
                        parts.append(f'{amount}{suffix}')
                magnitude = ' '.join(parts)
            core = magnitude + (' overdue' if overdue else ' left')
    if value.recurring:
        core += ' ↻ ' + (value.rule if value.rule and value.rule.strip() else 'recurring')
    offsets = sorted(r.minutes if hasattr(r, 'minutes') else r for r in reminders)
    if offsets:
        core += ' reminders:' + ', '.join(reminder_text(m) for m in offsets)
    return core, overdue


def time_block(value, reminders, now, zone, color=Color(), *, detail=False):
    relative, overdue = timing(value, reminders, now, zone)
    if value is None:
        return 'none' if detail else 'due:none'
    text = actual_due(value, zone) + ' · ' + relative if detail else 'due:' + relative
    return color.paint(text, 'red' if overdue else 'blue')
