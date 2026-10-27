"""Pure account-time policy, independent of CLI arity and remote transport.

Attention retains raw due data and original scalar input. `instant` is UTC;
`epoch_seconds` retains arbitrary supplied fractional precision for comparisons.
Python datetime presentation has microsecond precision; raw text is never rounded
or rewritten. Local parsing errors raise DomainError; unknown English expressions
return kind='unresolved'. Only remote floating values use the fold/gap policy.

ExactInstant is the shared immutable timestamp value. instant_from_wire accepts
aware RFC 3339 text; instant_key/text/datetime accept it or aware datetime, never
None, naive datetime or other types. Invalid values raise DomainError. Exact keys
are fractions.Fraction seconds with unbounded arithmetic, independent of Decimal
context. instant_text preserves fractional digits in UTC. instant_datetime alone
projects to microseconds for display/calendar use, never comparison/persistence.
"""
from calendar import monthrange
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
from functools import total_ordering
import re
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from .errors import DomainError

UTC = timezone.utc
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
WIRE = re.compile(r'(\d{4}-\d\d-\d\d)[Tt](\d\d:\d\d:\d\d)(?:\.([0-9]+))?([Zz]|[+-]\d\d:\d\d)\Z')


@total_ordering
class ExactInstant:
    """Immutable UTC second plus fraction; construct with instant_from_wire.

    Equality and ordering use exact instants, including against aware datetime.
    Unhashable: use instant_key for dictionary/set keys. Datetime fold hashing
    cannot represent this exact mixed-type equality consistently.
    Fraction spelling (including trailing zeros) is retained for serialization.
    This deliberately offers no implicit datetime projection or calendar API.
    """
    __slots__ = ('_second', '_fraction')

    def __init__(self, second, fraction=''):
        if (not isinstance(second, datetime) or second.tzinfo is None
                or second.utcoffset() != timedelta(0) or second.microsecond
                or not isinstance(fraction, str)
                or (fraction and not re.fullmatch('[0-9]+', fraction))):
            raise DomainError('ExactInstant requires a whole UTC second and fractional digits')
        object.__setattr__(self, '_second', second.astimezone(UTC))
        object.__setattr__(self, '_fraction', fraction)

    def __setattr__(self, name, value):
        raise AttributeError('ExactInstant is immutable')

    def __delattr__(self, name):
        raise AttributeError('ExactInstant is immutable')

    def __deepcopy__(self, memo):
        return self

    def __eq__(self, other):
        if not isinstance(other, (ExactInstant, datetime)):
            return NotImplemented
        return instant_key(self) == instant_key(other)

    def __lt__(self, other):
        if not isinstance(other, (ExactInstant, datetime)):
            return NotImplemented
        return instant_key(self) < instant_key(other)

    __hash__ = None

    def __repr__(self):
        return f'ExactInstant({instant_text(self)!r})'


def instant_from_wire(text: str) -> ExactInstant:
    """Parse aware RFC 3339 text, preserving every supplied fraction digit."""
    match = WIRE.fullmatch(text) if isinstance(text, str) else None
    if not match:
        raise DomainError('timestamp must be aware RFC 3339 text')
    day, clock, fraction, offset = match.groups()
    try:
        if offset.lower() != 'z' and (int(offset[1:3]) > 23 or int(offset[4:]) > 59):
            raise ValueError()
        second = datetime.fromisoformat(day + 'T' + clock + ('+00:00' if offset.lower() == 'z' else offset))
        return ExactInstant(second.astimezone(UTC), fraction or '')
    except (ValueError, OverflowError):
        raise DomainError('invalid RFC 3339 timestamp') from None


def instant_key(value: 'ExactInstant | datetime') -> Fraction:
    """Return an exact, mutually comparable UTC rational number of seconds."""
    if isinstance(value, ExactInstant):
        delta = value._second - EPOCH
        return Fraction(delta.days * 86400 + delta.seconds) + Fraction(Decimal('0.' + (value._fraction or '0')))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DomainError('timestamp must be an ExactInstant or aware datetime')
    delta = value.astimezone(UTC) - EPOCH
    return Fraction(delta.days * 86400 + delta.seconds) + Fraction(delta.microseconds, 1000000)


def instant_text(value: 'ExactInstant | datetime') -> str:
    """Emit UTC RFC 3339, retaining all supplied fractional digits."""
    instant_key(value)
    if isinstance(value, ExactInstant):
        return value._second.isoformat()[:-6] + ('.' + value._fraction if value._fraction else '') + 'Z'
    return value.astimezone(UTC).isoformat().replace('+00:00', 'Z')


def instant_datetime(value: 'ExactInstant | datetime') -> datetime:
    """Return UTC aware datetime, truncating beyond microseconds for display."""
    instant_key(value)
    if isinstance(value, ExactInstant):
        return value._second.replace(microsecond=int((value._fraction + '000000')[:6]))
    return value.astimezone(UTC)


DATE = re.compile(r'\d{4}-\d{2}-\d{2}\Z')
ISO = re.compile(r'\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:[Zz]|[+-]\d{2}:\d{2})?\Z')
UNITS = {
    'm': 'minutes', 'min': 'minutes', 'mins': 'minutes', 'minute': 'minutes', 'minutes': 'minutes',
    'h': 'hours', 'hr': 'hours', 'hrs': 'hours', 'hour': 'hours', 'hours': 'hours',
    'd': 'days', 'day': 'days', 'days': 'days',
    'w': 'weeks', 'wk': 'weeks', 'wks': 'weeks', 'week': 'weeks', 'weeks': 'weeks',
    'bd': 'business', 'business day': 'business', 'business days': 'business',
    'month': 'months', 'months': 'months',
}
WEEKDAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')


def account_timezone(value: str | ZoneInfo) -> ZoneInfo:
    """Resolve only the supplied authoritative IANA zone, never the host zone."""
    try:
        return value if isinstance(value, ZoneInfo) else ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise DomainError('account_zone must be a valid IANA timezone') from None


def require_aware(value: datetime, field: str = 'timestamp') -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DomainError(f'{field} must be an aware instant')
    return value


def _epoch(value: datetime) -> Decimal:
    delta = require_aware(value).astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
    return Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / 1000000


def _precise_epoch(value: datetime, raw: str) -> Decimal:
    fraction = re.search(r':\d{2}\.(\d+)', raw)
    if fraction:
        return _epoch(value.replace(microsecond=0)) + Decimal('0.' + fraction[1])
    return _epoch(value)


def resolve_wall(wall: datetime, account_zone: str | ZoneInfo, *, remote: bool = False) -> datetime:
    """Local wall time -> UTC. Remote overlap chooses early; gap shifts forward."""
    zone = account_timezone(account_zone)
    wall = wall.replace(tzinfo=None)
    guesses = [wall.replace(tzinfo=zone, fold=f).astimezone(UTC) for f in (0, 1)]
    valid = sorted({g for g in guesses if g.astimezone(zone).replace(tzinfo=None) == wall})
    if len(valid) == 1:
        return valid[0]
    if not remote:
        raise DomainError('ambiguous or nonexistent local wall time; supply an explicit ISO instant with offset')
    if valid:
        return valid[0]
    # A gap's two projections straddle the transition; the later projection
    # retains the wall minutes/seconds and advances by the actual gap size.
    return max(guesses)


@dataclass(frozen=True)
class Attention:
    """One due occurrence, optional rule and lossless raw representation.

    kind is 'date', 'fixed', 'floating', or 'unresolved'. date_value belongs only
    to date-only values; instant belongs only to exact values. Use constructors
    below rather than combining inconsistent fields manually.
    """
    kind: str
    date_value: date | None = None
    instant: datetime | None = None
    expression: str | None = None
    recurring: bool = False
    rule: str | None = None
    language: str | None = None
    zone: str | None = None
    raw_due: Mapping[str, Any] | None = None
    epoch_seconds: Decimal | None = None

    @property
    def exact(self) -> bool:
        return self.kind in ('fixed', 'floating')

    def day(self, account_zone: str | ZoneInfo) -> date:
        """The occurrence's account-local day, including remote DST resolution."""
        if self.kind == 'date' and self.date_value is not None:
            return self.date_value
        if self.exact and self.instant is not None:
            return self.instant.astimezone(account_timezone(account_zone)).date()
        raise DomainError(f'attention day unresolved for {self.expression!r}; supply a local expression such as tomorrow or an ISO date')


def exact_attention(instant: datetime, *, expression: str | None = None) -> Attention:
    """Construct a fixed UTC occurrence from an aware instant."""
    instant = require_aware(instant).astimezone(UTC)
    return Attention('fixed', instant=instant, expression=expression, epoch_seconds=_epoch(instant))


def _absolute(value: str, zone: str | ZoneInfo, *, offset_required: bool) -> Attention:
    try:
        if DATE.fullmatch(value):
            return Attention('date', date_value=date.fromisoformat(value), expression=value)
        if not ISO.fullmatch(value):
            raise ValueError
        dt = datetime.fromisoformat(value.replace('z', '+00:00').replace('Z', '+00:00'))
        if dt.tzinfo is None:
            if offset_required:
                raise DomainError('attention date-time requires an explicit ISO offset or Z')
            dt = resolve_wall(dt, zone)
        result = exact_attention(dt, expression=value)
        return replace(result, epoch_seconds=_precise_epoch(dt, value))
    except DomainError:
        raise
    except (ValueError, OverflowError):
        raise DomainError('invalid ISO date or date-time') from None


def parse_attention(expression: str, now: datetime, account_zone: str | ZoneInfo) -> Attention:
    """Resolve supported scalar grammar; pass other English expressions unchanged.

    ISO attention date-times require an offset. Relative days/weeks/business days
    and directly-added months retain local wall time and refuse DST folds/gaps.
    """
    require_aware(now, 'now')
    zone = account_timezone(account_zone)
    if not isinstance(expression, str) or not expression.strip():
        raise DomainError('attention expression must be nonempty')
    if any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in expression):
        raise DomainError('attention expression contains a control character')
    value = expression.strip()
    lower = value.lower()
    if lower in ('ask', 'none', '-', 'clear'):
        raise DomainError('invalid attention expression')
    if re.match(r'^\d{4}-\d{2}-\d{2}', value):
        return replace(_absolute(value, zone, offset_required=True), expression=expression)
    local = now.astimezone(zone)
    match = re.fullmatch(r'(today|tomorrow|' + '|'.join(WEEKDAYS) + r')(?:\s+(\d{1,2})(?::(\d{2}))?)?', lower)
    if lower == 'next week' or match:
        name = 'monday' if lower == 'next week' else match[1]
        days = 0 if name == 'today' else 1 if name == 'tomorrow' else ((WEEKDAYS.index(name) - local.weekday()) % 7 or 7)
        target = local.date() + timedelta(days=days)
        if match and match[2] is not None:
            try:
                wall = datetime.combine(target, time(int(match[2]), int(match[3] or 0)))
            except ValueError:
                raise DomainError('attention clock time is invalid') from None
            return exact_attention(resolve_wall(wall, zone), expression=expression)
        return Attention('date', date_value=target, expression=expression)
    match = re.fullmatch(r'(\d+)\s*([a-z]+(?: [a-z]+)?)', lower)
    if match and match[2] in UNITS:
        count, unit = int(match[1]), UNITS[match[2]]
        try:
            if unit in ('minutes', 'hours'):
                return exact_attention(now.astimezone(UTC) + timedelta(**{unit: count}), expression=expression)
            wall = local.replace(tzinfo=None)
            if unit == 'months':
                if count == 0:
                    raise DomainError('calendar months must be positive')
                index = wall.year * 12 + wall.month - 1 + count
                year, month = index // 12, index % 12 + 1
                wall = wall.replace(year=year, month=month, day=min(wall.day, monthrange(year, month)[1]))
            elif unit == 'business':
                weeks, rest = divmod(count, 5)
                # Start on a weekday before applying complete business weeks.
                if count and wall.weekday() >= 5:
                    wall += timedelta(days=7 - wall.weekday())
                    weeks, rest = divmod(count - 1, 5)
                wall += timedelta(days=weeks * 7)
                for _ in range(rest):
                    wall += timedelta(days=1)
                    while wall.weekday() >= 5:
                        wall += timedelta(days=1)
            else:
                wall += timedelta(days=count * (7 if unit == 'weeks' else 1))
            return exact_attention(resolve_wall(wall, zone), expression=expression)
        except DomainError:
            raise
        except (ValueError, OverflowError):
            raise DomainError('attention arithmetic is outside the supported date range') from None
    if re.fullmatch(r'[+-]?\d+(?:\.\d+)?\s*(?:' + '|'.join(UNITS) + ')', lower):
        raise DomainError('attention count must be a nonnegative integer (months positive)')
    return Attention('unresolved', expression=expression)


def parse_boundary(value: str, now: datetime, account_zone: str | ZoneInfo) -> ExactInstant | datetime:
    """ISO date/midnight, ISO date-time or positive Nd/N days ago -> UTC.

    Returns ExactInstant for fractional ISO input and aware datetime otherwise.
    Preserves every supplied digit, including offset-free wall-time fractions,
    without traversing Attention or context-dependent Decimal arithmetic.
    Does not enforce workflow range/future checks or accept attention weekdays.
    """
    require_aware(now, 'now')
    zone = account_timezone(account_zone)
    if not isinstance(value, str):
        raise DomainError('boundary must be text')
    match = re.fullmatch(r'([1-9]\d*)\s*(?:d|days?) ago', value.strip(), re.I)
    try:
        if match:
            wall = now.astimezone(zone).replace(tzinfo=None) - timedelta(days=int(match[1]))
            return resolve_wall(wall, zone)
        text = value.strip()
        if DATE.fullmatch(text):
            return resolve_wall(datetime.combine(date.fromisoformat(text), time()), zone)
        if not ISO.fullmatch(text):
            raise ValueError('invalid ISO boundary')
        parsed = datetime.fromisoformat(text.replace('z', '+00:00').replace('Z', '+00:00'))
        fraction = re.search(r':\d{2}\.([0-9]+)', text)
        # Calendar/DST resolution needs only the whole second. Fractional digits
        # are independent of minute-based offsets and never enter arithmetic.
        if fraction:
            parsed = parsed.replace(microsecond=0)
        resolved = resolve_wall(parsed, zone) if parsed.tzinfo is None else parsed.astimezone(UTC)
        return ExactInstant(resolved, fraction[1]) if fraction else resolved
    except DomainError as exc:
        raise DomainError(str(exc) + '; boundary examples: 2026-10-19, 2026-10-19T09:00:00+02:00, \"2d ago\", \"2 days ago\"; offset-free values use account timezone and days retain local wall time') from exc
    except (ValueError, OverflowError) as exc:
        raise DomainError('boundary: use 2026-10-19, 2026-10-19T09:00:00+02:00, "2d ago" or "2 days ago"; offset-free values use account timezone and days retain local wall time') from exc


def parse_reminder(value: str) -> int:
    """One scalar reminder -> whole minutes. Zero is accepted only as 0 minutes."""
    if not isinstance(value, str):
        raise DomainError('reminder must be scalar text')
    match = re.fullmatch(r'(0|[1-9]\d*)\s*([a-z]+)', value.strip(), re.I)
    if not match:
        raise DomainError('reminder must be an integer minute/hour/day/week offset')
    count, unit = int(match[1]), UNITS.get(match[2].lower())
    factors = {'minutes': 1, 'hours': 60, 'days': 1440, 'weeks': 10080}
    if unit not in factors or (count == 0 and unit != 'minutes'):
        raise DomainError('reminder unit invalid; zero requires minutes')
    return count * factors[unit]


def validate_reminder_offsets(offsets: tuple[int, ...] | list[int]) -> None:
    """Validate imported offsets, including present integer zero and duplicates."""
    if any(type(n) is not int or n < 0 for n in offsets):
        raise DomainError('reminder offsets must be nonnegative whole minutes, excluding booleans')
    if len(set(offsets)) != len(offsets):
        raise DomainError('duplicate reminder offsets')


def resolve_remote_due(raw_due: Mapping[str, Any] | None, account_zone: str | ZoneInfo, *, reminder=False) -> Attention | None:
    """Interpret a supplied due object, not an HTTP response or wire request.

    Only `date` carries an occurrence. Unknown metadata is retained unchanged;
    documented null timezone means floating. No due.datetime fallback is invented.
    """
    zone = account_timezone(account_zone)
    if raw_due is None:
        return None
    if not isinstance(raw_due, Mapping):
        raise DomainError('due must be an object or null')
    raw = deepcopy(dict(raw_due))
    value = raw.get('date')
    if not isinstance(value, str):
        raise DomainError('due.date must be an ISO date or date-time')
    recurring = raw.get('is_recurring', False)
    rule, lang, named_zone = raw.get('string'), raw.get('lang'), raw.get('timezone')
    if type(recurring) is not bool or any(v is not None and not isinstance(v, str) for v in (rule, lang, named_zone)):
        raise DomainError('due recurrence/language/timezone fields invalid')
    if recurring and not reminder and (not rule or not rule.strip()):
        raise DomainError('recurring due requires a rule')
    if named_zone is not None:
        account_timezone(named_zone)
    try:
        if DATE.fullmatch(value):
            if named_zone is not None:
                raise DomainError('date-only due timezone must be null')
            result = Attention('date', date_value=date.fromisoformat(value))
        elif ISO.fullmatch(value):
            dt = datetime.fromisoformat(value.replace('Z', '+00:00').replace('z', '+00:00'))
            floating = dt.tzinfo is None
            if floating and named_zone is not None and not reminder:
                raise DomainError('floating due timezone must be null')
            instant = resolve_wall(dt, named_zone or zone, remote=True) if floating else dt.astimezone(UTC)
            result = Attention('floating' if floating and named_zone is None else 'fixed', instant=instant,
                               epoch_seconds=_precise_epoch(instant, value))
        else:
            raise ValueError
    except DomainError:
        raise
    except (ValueError, OverflowError):
        raise DomainError('due.date is invalid') from None
    return replace(result, recurring=recurring, rule=rule, language=lang, zone=named_zone, raw_due=raw)


def attention_order(value: Attention, account_zone: str | ZoneInfo) -> Decimal:
    """Full instant ordering; date-only uses start of account-local date."""
    if value.exact:
        return value.epoch_seconds if value.epoch_seconds is not None else _epoch(value.instant)
    if value.kind == 'date':
        return _epoch(resolve_wall(datetime.combine(value.date_value, time()), account_zone, remote=True))
    raise DomainError('unresolved attention cannot be ordered')


def same_attention(left: Attention | None, right: Attention | None, account_zone: str | ZoneInfo) -> bool:
    """Exact semantic no-op comparison, never using reconciliation slack."""
    return _compare(left, right, account_zone, Decimal(0))


def reconciles_attention(left: Attention | None, right: Attention | None, account_zone: str | ZoneInfo) -> bool:
    """Remote-only <=2s tolerance; local day, kind, rule and zone remain strict."""
    return _compare(left, right, account_zone, Decimal(2))


def _compare(left, right, zone, tolerance):
    if left is None or right is None:
        return left is right
    if (left.kind, left.recurring, left.rule if left.recurring else None, left.zone) != (right.kind, right.recurring, right.rule if right.recurring else None, right.zone):
        return False
    # Language interprets provider expressions and recurring rules. Once a
    # nonrecurring occurrence is resolved, returned parser metadata is immaterial.
    if (left.recurring or left.kind == 'unresolved') and left.language != right.language:
        return False
    if left.kind == 'unresolved':
        return left.expression == right.expression
    if left.day(zone) != right.day(zone):
        return False
    return abs(attention_order(left, zone) - attention_order(right, zone)) <= tolerance


def retain_recurrence(proposal: Attention, previous: Attention | None) -> Attention:
    """Copy a current recurring rule onto a locally resolved occurrence move."""
    if previous is None or not previous.recurring or proposal.kind == 'unresolved':
        return proposal
    return replace(proposal, recurring=True, rule=previous.rule, language=previous.language, zone=previous.zone)


def resolve_reminder_due(raw_due, account_zone):
    """Reminder open due object, including the pinned named-zone wall example.

    Missing recurrence wording/flag is allowed; supplied fields remain meaningful.
    Task due validation stays unchanged. No recurrence text is parsed locally.
    """
    if not isinstance(raw_due, Mapping):
        raise DomainError('absolute reminder requires due object')
    for name in ('string', 'lang', 'timezone'):
        if name in raw_due and raw_due[name] is None and name != 'timezone':
            raise DomainError('reminder due.' + name + ' must be text')
    result = resolve_remote_due(raw_due, account_zone, reminder=True)
    if not result.exact:
        raise DomainError('absolute reminder requires exact time')
    return result


def rebase_attention(value, account_zone, *, reminder=False):
    """Resolve retained floating wall time under current account authority."""
    if value is not None and value.kind == 'floating':
        return resolve_remote_due(value.raw_due, account_zone, reminder=reminder)
    return value
