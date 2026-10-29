"""Literal expectations from account-time policy (no network or host clock)."""
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, Inexact, localcontext
from zoneinfo import ZoneInfo
from todo_lib.domain import (
    ExactInstant, instant_from_wire, instant_key, instant_text, instant_datetime,
    DomainError, parse_attention, parse_boundary, parse_reminder,
    resolve_remote_due, same_attention, reconciles_attention, retain_recurrence,
    exact_attention, validate_reminder_offsets,
)


def dt(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


class TimeTests(unittest.TestCase):
    def setUp(self):
        self.now = dt('2026-10-23T08:12:34.123456Z')
        self.zone = 'Europe/Prague'

    def test_lossless_shared_instant_contract(self):
        text = '2026-10-23T08:00:00.123456789012345678901234567890123456789000Z'
        exact = instant_from_wire(text)
        self.assertEqual(instant_text(exact), text)
        later = instant_from_wire(text.replace('789000Z', '789001Z'))
        self.assertLess(instant_key(exact), instant_key(later))
        self.assertNotEqual(exact, later)
        from decimal import localcontext
        with localcontext() as context:
            context.prec = 2
            self.assertLess(instant_key(exact), instant_key(later))
            self.assertEqual(instant_text(exact), text)

        self.assertEqual(exact, instant_from_wire(text.replace('08:00:00', '10:00:00')[:-1] + '+02:00'))
        self.assertEqual(instant_datetime(exact), dt('2026-10-23T08:00:00.123456Z'))
        self.assertGreater(instant_key(exact), instant_key(instant_datetime(exact)))
        a = instant_from_wire('2026-10-23T08:00:00.123456000Z')
        self.assertEqual(a, dt('2026-10-23T10:00:00.123456+02:00'))
        with self.assertRaises(TypeError):
            hash(a)
        self.assertEqual(instant_text(instant_from_wire('2026-10-23T08:00:00.000000000Z')),
                         '2026-10-23T08:00:00.000000000Z')
        with self.assertRaises(AttributeError):
            exact._fraction = '0'
        for bad in (None, 1, dt('2026-10-23T08:00:00Z'), '2026-10-23T08:00:00',
                    '2026-02-30T08:00:00Z', '2026-10-23T08:00:00+00:60',
                    '2026-10-23T08:00:60Z', 'garbage'):
            with self.subTest(bad=bad), self.assertRaises(DomainError):
                instant_from_wire(bad)
        for bad in (None, '2026-10-23T08:00:00Z', datetime(2026, 1, 1), 4):
            for helper in (instant_key, instant_text, instant_datetime):
                with self.subTest(helper=helper, bad=bad), self.assertRaises(DomainError):
                    helper(bad)

    def test_mixed_fold_equality_uses_explicit_hash_keys(self):
        zone = ZoneInfo('Europe/Prague')
        for fold, utc in ((0, '2026-10-25T00:30:00Z'), (1, '2026-10-25T01:30:00Z')):
            with self.subTest(fold=fold):
                wall = datetime(2026, 10, 25, 2, 30, tzinfo=zone, fold=fold)
                exact = instant_from_wire(utc)
                self.assertEqual(exact, wall)
                self.assertEqual(wall, exact)
                # Native datetime hashes ignore fold; callers must normalize keys.
                with self.assertRaises(TypeError):
                    hash(exact)
                values = {instant_key(wall): 'found'}
                self.assertEqual(values[instant_key(exact)], 'found')
                self.assertEqual(hash(instant_key(wall)), hash(instant_key(exact)))

    def test_precise_boundary_offsets_and_wall_policy(self):
        fraction = '123456789012345678901234567890123456789'
        expected = '2026-10-23T08:00:00.' + fraction + 'Z'
        for value in ('2026-10-23T08:00:00.' + fraction + 'Z',
                      '2026-10-23T10:00:00.' + fraction + '+02:00',
                      '2026-10-23T10:00:00.' + fraction):
            with self.subTest(value=value), localcontext() as context:
                context.prec = 2
                context.traps[Inexact] = True
                boundary = parse_boundary(value, self.now, self.zone)
                self.assertEqual(instant_text(boundary), expected)
                self.assertEqual(instant_key(boundary), instant_key(instant_from_wire(expected)))
        for value in ('2026-10-25T02:30:00.123456789', '2026-03-29T02:30:00.123456789'):
            with self.assertRaises(DomainError):
                parse_boundary(value, self.now, self.zone)

    def test_month_direct_add_and_clamp(self):
        for start, expr, expected in [
            ('2026-01-31T09:15:00Z', '1 month', '2026-02-28T09:15:00Z'),
            ('2026-01-31T09:15:00Z', '2 months', '2026-03-31T08:15:00Z'),
            ('2028-01-31T09:15:00Z', '1 months', '2028-02-29T09:15:00Z'),
            ('2026-10-23T08:12:00Z', '1 MONTH', '2026-11-23T09:12:00Z'),
        ]:
            with self.subTest(expr=expr, start=start):
                self.assertEqual(parse_attention(expr, dt(start), self.zone).instant, dt(expected))
        with self.assertRaises(DomainError):
            parse_attention('0months', self.now, self.zone)

    def test_elapsed_calendar_and_business_arithmetic(self):
        start = dt('2026-03-28T11:00:00Z') # noon Prague before spring-forward
        expected = {'24h': '2026-03-29T11:00:00Z', '1d': '2026-03-29T10:00:00Z',
                    '1w': '2026-04-04T10:00:00Z', '1bd': '2026-03-30T10:00:00Z',
                    '5 business days': '2026-04-03T10:00:00Z'}
        for expr, value in expected.items():
            with self.subTest(expr=expr):
                self.assertEqual(parse_attention(expr, start, self.zone).instant, dt(value))
        for alias in ('1d', '1 day', '1DAY', '1days'):
            self.assertEqual(parse_attention(alias, start, self.zone).instant, dt(expected['1d']))
        self.assertEqual(parse_attention('0m', start, self.zone).instant, start)
        self.assertEqual(parse_attention('1m', start, self.zone).instant, start + timedelta(minutes=1))
        # Friday + business week skips weekend, retaining wall time.
        self.assertEqual(parse_attention('5bd', self.now, self.zone).instant, dt('2026-10-30T09:12:34.123456Z'))

    def test_strict_weekdays_and_monday(self):
        monday = dt('2026-10-19T08:00:00Z')
        for expr in ('monday', 'next week'):
            self.assertEqual(parse_attention(expr, monday, self.zone).date_value, date(2026, 10, 26))
        self.assertEqual(parse_attention('friday', self.now, self.zone).date_value, date(2026, 10, 30))
        self.assertEqual(parse_attention('today 9:05', self.now, self.zone).instant, dt('2026-10-23T07:05:00Z'))
        self.assertEqual(parse_attention('tomorrow', self.now, self.zone).date_value, date(2026, 10, 24))
        with self.assertRaises(DomainError):
            parse_attention('today 24:01', self.now, self.zone)

    def test_local_dst_refusal(self):
        for now, expr in [('2026-03-28T01:30:00Z', '1d'), ('2026-10-24T00:30:00Z', '1d'),
                          ('2026-03-28T12:00:00Z', 'tomorrow 2:30'),
                          ('2026-10-24T12:00:00Z', 'tomorrow 2:30')]:
            with self.subTest(expr=expr, now=now), self.assertRaisesRegex(DomainError, 'explicit ISO'):
                parse_attention(expr, dt(now), self.zone)
        for now in ('2026-03-30T00:30:00Z', '2026-10-26T01:30:00Z'):
            with self.assertRaisesRegex(DomainError, 'explicit ISO'):
                parse_boundary('1d ago', dt(now), self.zone)
        for value in ('2026-03-29T02:30:00', '2026-10-25T02:30:00'):
            with self.assertRaises(DomainError):
                parse_boundary(value, self.now, self.zone)
        self.assertEqual(parse_attention('2026-10-25T02:30:00+01:00', self.now, self.zone).instant,
                         dt('2026-10-25T01:30:00Z'))

    def test_remote_dst_and_fraction_preservation(self):
        for rawdate, expected in [('2026-10-25T02:30:00.123456789', '2026-10-25T00:30:00.123456Z'),
                                  ('2026-03-29T02:30:00.123456789', '2026-03-29T01:30:00.123456Z')]:
            raw = {'date': rawdate, 'timezone': None, 'is_recurring': True,
                   'string': 'every day at 2:30', 'lang': 'en', 'future': {'x': [1]}}
            result = resolve_remote_due(raw, self.zone)
            self.assertEqual(result.instant, dt(expected))
            self.assertEqual(result.kind, 'floating')
            self.assertEqual(result.raw_due, raw)
            self.assertEqual(result.epoch_seconds % 1, Decimal('.123456789'))
            raw['future']['x'].append(2)
            self.assertEqual(result.raw_due['future']['x'], [1])
        # Non-hour transition gap: Lord Howe advances thirty minutes.
        self.assertEqual(resolve_remote_due({'date': '2026-10-04T02:15:22.123456'}, 'Australia/Lord_Howe').instant,
                         dt('2026-10-03T15:45:22.123456Z'))

    def test_reresolve_floating_fixed_date_and_metadata(self):
        raw = {'date': '2026-11-12T16:00:00', 'timezone': None}
        self.assertEqual(resolve_remote_due(raw, self.zone).instant, dt('2026-11-12T15:00:00Z'))
        self.assertEqual(resolve_remote_due(raw, 'UTC').instant, dt('2026-11-12T16:00:00Z'))
        fixed = {'date': '2026-11-12T15:00:00.0000001Z', 'timezone': self.zone}
        self.assertEqual(resolve_remote_due(fixed, self.zone).instant, resolve_remote_due(fixed, 'UTC').instant)
        self.assertEqual(resolve_remote_due({'date': '2026-11-12'}, self.zone).kind, 'date')
        self.assertIsNone(resolve_remote_due(None, self.zone))
        for raw in ({}, {'datetime': '2026-11-12T15:00:00Z'}, {'date': None}, {'date': ''},
                    {'date': '2026-02-30'}, {'date': '2026-11-12', 'is_recurring': True},
                    {'date': '2026-11-12', 'is_recurring': 1}, {'date': '2026-11-12', 'timezone': 'UTC'}):
            with self.subTest(raw=raw), self.assertRaises(DomainError):
                resolve_remote_due(raw, self.zone)

    def test_unknown_vs_invalid_and_original_input(self):
        for expr in ('next Friday 10:00', 'every day', 'banana'):
            result = parse_attention(expr, self.now, self.zone)
            self.assertEqual((result.kind, result.expression), ('unresolved', expr))
            with self.assertRaisesRegex(DomainError, 'unresolved'):
                result.day(self.zone)
        result = parse_attention('  TOMORROW  ', self.now, self.zone)
        self.assertEqual(result.expression, '  TOMORROW  ')
        for expr in ('', 'none', 'ask', '-', '0month', '2026-02-30', '2026-10-23T09:00:00', '-1d', '1.5h', 'today\n'):
            with self.subTest(expr=expr), self.assertRaises(DomainError):
                parse_attention(expr, self.now, self.zone)

    def test_boundary_is_not_attention_grammar(self):
        start = dt('2026-03-30T10:10:00Z')
        self.assertEqual(parse_boundary('2 days ago', start, self.zone), dt('2026-03-28T11:10:00Z'))
        self.assertEqual(parse_boundary('2d ago', start, self.zone), dt('2026-03-28T11:10:00Z'))
        self.assertEqual(parse_boundary('2026-10-19', self.now, self.zone), dt('2026-10-18T22:00:00Z'))
        self.assertEqual(parse_boundary('2026-10-19T09:00:00', self.now, self.zone), dt('2026-10-19T07:00:00Z'))
        for value in ('monday', 'today', 'next week', '0d ago', '2h ago'):
            with self.assertRaises(DomainError):
                parse_boundary(value, self.now, self.zone)

    def test_reminder_grammar_and_imported_zero(self):
        for value, expected in [('0m', 0), ('0 MINUTES', 0), ('30mins', 30), ('2 HR', 120), ('1day', 1440), ('2wks', 20160)]:
            self.assertEqual(parse_reminder(value), expected)
        for value in ('00m', '0h', '0d', '0w', '-1m', '+1m', '1.5h', '1bd', '1month', '1h30m', 'clear', True):
            with self.subTest(value=value), self.assertRaises(DomainError):
                parse_reminder(value)
        validate_reminder_offsets([0, 30])
        for offsets in ([False], [-1], [1.0], [0, 0]):
            with self.assertRaises(DomainError):
                validate_reminder_offsets(offsets)

    def test_exact_noop_separate_from_remote_slack(self):
        a = parse_attention('2026-10-23T10:00:00+02:00', self.now, self.zone)
        equal = parse_attention('2026-10-23T08:00:00Z', self.now, self.zone)
        self.assertTrue(same_attention(a, equal, self.zone))
        for seconds in (-2, -1, 1, 2):
            b = exact_attention(a.instant + timedelta(seconds=seconds))
            self.assertFalse(same_attention(a, b, self.zone))
            self.assertTrue(reconciles_attention(a, b, self.zone))
        self.assertFalse(reconciles_attention(a, exact_attention(a.instant + timedelta(seconds=2, microseconds=1)), self.zone))
        end = parse_attention('2026-10-23T21:59:59Z', self.now, self.zone)
        self.assertFalse(reconciles_attention(end, exact_attention(end.instant + timedelta(seconds=2)), self.zone))
        for b in (None, replace(a, kind='floating'), replace(a, recurring=True, rule='every day'),
                  replace(a, zone='Europe/Prague')):
            self.assertFalse(reconciles_attention(a, b, self.zone))
        nano = resolve_remote_due({'date': '2026-10-23T08:00:00.000000001Z'}, self.zone)
        self.assertFalse(same_attention(a, nano, self.zone))
        self.assertTrue(reconciles_attention(a, nano, self.zone))

    def test_parser_and_published_due_metadata_equality(self):
        # Provider-shaped responses follow the pinned Due dates contract;
        # these dates are synthetic, not captured live responses.
        for expression, raw in [
            ('tomorrow', {'date': '2026-10-24', 'timezone': None,
                          'string': 'tomorrow', 'lang': 'en', 'is_recurring': False}),
            ('2026-10-23T08:00:00Z', {'date': '2026-10-23T08:00:00Z',
                                    'string': '2026-10-23 10:00', 'lang': 'en', 'is_recurring': False}),
        ]:
            with self.subTest(expression=expression):
                parsed = parse_attention(expression, self.now, self.zone)
                resolved = resolve_remote_due(raw, self.zone)
                for compare in (same_attention, reconciles_attention):
                    self.assertTrue(compare(parsed, resolved, self.zone))
                    self.assertTrue(compare(resolved, parsed, self.zone))
                self.assertEqual(resolved.raw_due, raw)
                self.assertEqual(resolved.language, 'en')
        # Language still determines the meaning of rules and unresolved text.
        for value in (replace(resolved, recurring=True, rule='every day'),
                      parse_attention('every week', self.now, self.zone)):
            for compare in (same_attention, reconciles_attention):
                self.assertFalse(compare(value, replace(value, language='fr'), self.zone))

    def test_recurrence_retention(self):
        old = resolve_remote_due({'date': '2026-10-23T08:00:00Z', 'timezone': self.zone,
                                  'is_recurring': True, 'string': 'every day at 10', 'lang': 'en'}, self.zone)
        moved = retain_recurrence(parse_attention('tomorrow', self.now, self.zone), old)
        self.assertEqual((moved.recurring, moved.rule, moved.language, moved.zone),
                         (True, 'every day at 10', 'en', None))
        expr = parse_attention('every week', self.now, self.zone)
        self.assertIs(retain_recurrence(expr, old), expr)

    def test_aware_now_and_zone_required(self):
        with self.assertRaises(DomainError):
            parse_attention('tomorrow', datetime(2026, 1, 1), self.zone)
        with self.assertRaises(DomainError):
            parse_attention('tomorrow', self.now, 'not/a/zone')
