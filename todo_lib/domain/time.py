"""Pure account-time policy, independent of CLI arity and remote transport.

Attention retains raw due data and original scalar input. `instant` is UTC;
`epoch_seconds` retains arbitrary supplied fractional precision for comparisons.
Python datetime presentation has microsecond precision; raw text is never rounded
or rewritten. Local parsing errors raise DomainError; unknown English expressions
return kind='unresolved'. Only remote floating values use the fold/gap policy.
"""
from calendar import monthrange
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import re
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from .errors import DomainError

UTC = timezone.utc
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


def parse_boundary(value: str, now: datetime, account_zone: str | ZoneInfo) -> datetime:
    """ISO date/midnight, ISO date-time or positive Nd/N days ago -> UTC.

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
        parsed = _absolute(value.strip(), zone, offset_required=False)
        if parsed.kind == 'date':
            return resolve_wall(datetime.combine(parsed.date_value, time()), zone)
        return parsed.instant
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


def resolve_remote_due(raw_due: Mapping[str, Any] | None, account_zone: str | ZoneInfo) -> Attention | None:
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
    if recurring and (not rule or not rule.strip()):
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
            if floating and named_zone is not None:
                raise DomainError('floating due timezone must be null')
            instant = resolve_wall(dt, zone, remote=True) if floating else dt.astimezone(UTC)
            result = Attention('floating' if floating else 'fixed', instant=instant,
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
