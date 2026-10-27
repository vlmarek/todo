"""Schema-1 codec with lossless UTC timestamps and no timezone copy.

instant accepts domain.ExactInstant or aware datetime; parse_instant accepts
aware RFC 3339 text and returns ExactInstant. Invalid timestamps raise LocalError.
Null is decoded only at nullable model fields; domain validation checks required
completion times. asdict keeps the immutable non-dataclass value intact and the
record converter explicitly serializes it, never its internal slots. Attention
retains its established datetime projection plus exact due metadata contract.
"""
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
import json
from todo_lib import domain as d
from .safety import LocalError


def instant(value):
    try:
        return d.instant_text(value)
    except d.DomainError:
        raise LocalError('timestamp must be an exact instant or aware datetime') from None


def parse_instant(value):
    try:
        return d.instant_from_wire(value)
    except d.DomainError:
        raise LocalError('timestamp must be an aware RFC 3339 instant') from None


def _default(value):
    if isinstance(value, (datetime, d.ExactInstant)):
        return instant(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    raise TypeError('unsupported local value')


def dumps(value):
    return (json.dumps(value, default=_default, ensure_ascii=False, allow_nan=False,
                       sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')


def loads(content):
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                raise ValueError('duplicate field')
            result[key] = value
        return result
    try:
        return json.loads(content, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, TypeError):
        raise LocalError('corrupt local JSON') from None


def snapshot_data(snapshot):
    try:
        d.validate(snapshot)
    except d.DomainError as error:
        raise LocalError(str(error)) from None
    def record(entries):
        return {k: instant(v) if isinstance(v, (d.ExactInstant, datetime)) else v
                for k, v in entries}
    data = asdict(snapshot, dict_factory=record)
    del data['account']['timezone']
    return data


def snapshot_from(data, zone):
    """Zone comes exclusively from the checked binding, never from JSON cache."""
    try:
        if 'timezone' in data['account'] or 'last_synced_account_timezone' in data:
            raise ValueError('second timezone authority')
        binding = d.Binding(**{**data['binding'], 'category_ids': frozenset(data['binding']['category_ids'])})
        account = d.Account(data['account']['id'], zone, d.Capabilities(**data['account']['capabilities']))
        def attention_from(raw):
            a = dict(raw)
            if a.get('date_value') is not None:
                a['date_value'] = date.fromisoformat(a['date_value'])
            if a.get('instant') is not None:
                a['instant'] = d.instant_datetime(parse_instant(a['instant']))
            if a.get('epoch_seconds') is not None:
                a['epoch_seconds'] = Decimal(a['epoch_seconds'])
            return d.Attention(**a)
        items = {}
        for key, raw in data['items'].items():
            value = dict(raw)
            for name in ('added_at', 'completed_at'):
                if value.get(name) is not None:
                    value[name] = parse_instant(value[name])
            value['labels'] = frozenset(value['labels'])
            if value.get('attention') is not None:
                value['attention'] = attention_from(value['attention'])
            items[key] = d.Item(**value)
        def timed(records, cls, field):
            if cls is d.Comment:
                records = {k: {name: v for name, v in raw.items() if name != 'file_attachment'}
                           for k, raw in records.items()}
            return {key: cls(**{**value, field: parse_instant(value[field]) if value[field] is not None else None})
                    for key, value in records.items()}
        return d.validate(d.Snapshot(binding, account, d.Project(**data['root']),
            {k: d.Project(**v) for k, v in data['categories'].items()}, items,
            timed(data['comments'], d.Comment, 'added_at'),
            {k: d.Reminder(**{**v, 'due': attention_from(v['due']) if v.get('due') is not None else None}) for k, v in data['reminders'].items()},
            timed(data['occurrences'], d.Occurrence, 'completed_at')))
    except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError):
        raise LocalError('invalid stored managed snapshot') from None
