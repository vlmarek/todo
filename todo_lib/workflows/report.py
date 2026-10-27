"""Current-truth reports. Only complete final delivery authorizes cursor/pruning.

Public entry points: Reporter(transport, store=None, clock=None, streams=None).run
accepts the normalized report CommandRequest (or report argv); report() is the
functional equivalent. Operational failures propagate to the CLI's status handler.
ReportResult records the fixed endpoints and any safe post-finalization warning.
"""
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from todo_lib import domain as d
from todo_lib.adapter.current import retrieve
from todo_lib.adapter.history import HistoryAdapter, Retrieval
from todo_lib.adapter.transport import HTTPFailure
from todo_lib.local import (StateStore, LocalError, History, load_config,
    exclusive_lock, merge_history, prune_history, prepare_candidates)
from todo_lib.local.safety import read_bytes, regular
from todo_lib.presentation import (Document, OriginalStreams, ReportEvent, deliver,
    history_warning, render_report, render_report_cursor)
from todo_lib.syntax import parse
from todo_lib.syntax.input import prompt, Cancelled
from todo_lib.syntax.parser import UsageError
from .sync import Synchronizer, SyncError, SyncInterrupted, _known, _reconcile


@dataclass(frozen=True)
class ReportResult:
    start: object = None
    end: object = None
    finalized: bool = False
    warnings: tuple[str, ...] = ()


def _within(value, start, end):
    return d.instant_key(start) < d.instant_key(value) <= d.instant_key(end)


def _key(event):
    return (d.instant_key(event.event_date), event.id is None,
            event.id or '', event.object_id)


def _select(snapshot, completed, activities, start, end, hidden_names, *, now=None):
    # Use one shared exact chronological stream, irrespective of wire order/IDs.
    events = sorted((e for e in activities.records
                     if d.instant_key(e.event_date) <= d.instant_key(end)), key=_key)
    completions = []
    activity_instants = set()
    for source_order, event in enumerate(events):
        if (event.object_type == 'item' and event.event_type == 'completed'
                and event.object_id in snapshot.items):
            completions.append((event.object_id, event.event_date, event.id, source_order))
            activity_instants.add((event.object_id, d.instant_key(event.event_date)))
    # Completed-object evidence supplements activity, rather than creating a
    # second occurrence for the same observation. Anonymous activities remain
    # separate occurrences in their stable endpoint source order.
    for record in completed.records:
        item = snapshot.items.get(record.item.id)
        at = record.occurrence.completed_at
        if (item is not None and not record.deleted
                and (item.id, d.instant_key(at)) not in activity_instants):
            completions.append((item.id, at, None, len(events) + len(completions)))
    effective = set(range(len(completions)))
    timeline = []
    for index, (owner, at, identity, source_order) in enumerate(completions):
        timeline.append(((d.instant_key(at), identity is None, identity or '', owner, source_order),
                         'completed', owner, index))
    for source_order, event in enumerate(events):
        if event.object_type == 'item' and event.event_type == 'uncompleted':
            timeline.append(((*_key(event), source_order), 'uncompleted', event.object_id, None))
    stacks = {}
    for _, kind, owner, index in sorted(timeline, key=lambda row: row[0]):
        item = snapshot.items.get(owner)
        if item is None or not item.recurring:
            continue
        stack = stacks.setdefault(item.id, [])
        if kind == 'completed':
            stack.append(index)
        elif stack:
            effective.remove(stack.pop())
    finished, progress = [], []
    for index in sorted(effective):
        owner, at, identity, source_order = completions[index]
        item = snapshot.items[owner]
        if not _within(at, start, end) or not (item.completed or item.recurring):
            continue
        entry = ReportEvent(item.id, at, event_id=identity, source_order=source_order)
        (finished if item.parent_id is None else progress).append(entry)
    latest = {}
    for event in events:
        if (event.object_type == 'note' and event.event_type in ('added', 'updated')
                and _within(event.event_date, start, end)):
            latest[event.object_id] = event
    for identity, event in latest.items():
        comment = snapshot.comments.get(identity)
        if comment is not None and comment.item_id == event.owner_id:
            progress.append(ReportEvent(comment.item_id, event.event_date, 'comment',
                                        comment.body, event.id))
    hidden = [i for i in snapshot.items.values() if not i.completed
              and snapshot.categories[i.category_id].name not in hidden_names
              and d.visibility(snapshot, i.id, d.instant_datetime(now if now is not None else end), hidden_names).own_hidden]
    return finished, progress, hidden


class _Evidence:
    """Reuse already exhausted endpoint evidence during sync reconciliation."""
    def __init__(self, adapter, completed, activities):
        self.adapter, self.done, self.events = adapter, completed, activities
        self.own = {}

    def completed(self, start, end, scope=None):
        records = tuple(r for r in self.done.records
            if _within(r.occurrence.completed_at, start, end)
            and (scope is None or r.item.category_id == scope['project_id']))
        return Retrieval(records, self.done.pages, start, end)

    def activities(self, start, end, scope=None):
        records = tuple(e for e in self.events.records if _within(e.event_date, start, end)
            and (scope is None or (e.object_type == scope['object_type'] and e.object_id == scope['object_id'])))
        return Retrieval(records, self.events.pages, start, end)

    def comments(self, owner):
        if owner not in self.own:
            self.own[owner] = self.adapter.comments(owner)
        return self.own[owner]


class Reporter:
    def __init__(self, transport, store=None, *, clock=None, streams=None):
        self.transport = transport
        self.store = StateStore() if store is None else store
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.streams = streams or OriginalStreams.current()

    def run(self, request=()):
        if not hasattr(request, 'options'):
            request = parse(['report', *request])
        if request.command != 'report':
            raise UsageError('report', 'expected report request')
        options = dict(request.options)
        # Normalize combinations even for programmatically constructed requests.
        flags = [name for name in ('final', 'show-cursor', 'set-cursor') if name in options]
        if len(flags) > 1 or (flags and any(k in options for k in ('since', 'until'))) or ('yes' in options and 'set-cursor' not in options):
            raise UsageError('report', 'incompatible report options')
        # Boundary syntax is checked before attempting the exclusive lock. Reload
        # timezone/config/cursor under it; no pre-lock value authorizes output.
        if any(k in options for k in ('since', 'until', 'set-cursor')):
            syntax_now = self.clock()
            for name in ('since', 'until', 'set-cursor'):
                if name in options:
                    # UTC establishes grammar without touching protected state.
                    # Account-local calendar/DST resolution is repeated under lock.
                    self._boundary(options[name], syntax_now, 'UTC')
        with exclusive_lock('report', self.store.root):
            config = load_config(self.store.root)
            binding = self.store.load_binding()
            if options.get('show-cursor'):
                deliver(render_report_cursor(self.store.load_cursor(), binding.last_synced_account_timezone),
                        config, self.streams, 'report-show-cursor')
                return ReportResult()
            if 'set-cursor' in options:
                return self._set(options, config, binding)
            return self._online(options, config)

    @staticmethod
    def _boundary(text, now, zone):
        try:
            return d.parse_boundary(text, d.instant_datetime(now), zone)
        except d.DomainError as error:
            raise UsageError('report', str(error), text) from error

    def _set(self, options, config, binding):
        now = self.clock()
        proposed = self._boundary(options['set-cursor'], now, binding.last_synced_account_timezone)
        if d.instant_key(proposed) > d.instant_key(now):
            raise LocalError('report cursor cannot be in the future')
        path = self.store.root / 'report-cursor'
        old, label = None, 'none'
        if regular(path, missing=True) is not None:
            read_bytes(path)  # Safety/readability failures cannot become corruption.
            try:
                old = self.store.load_cursor()
                label = d.instant_text(old)
            except LocalError:
                label = 'corrupted'
        if old is not None and d.instant_key(old) == d.instant_key(proposed):
            raise LocalError('report cursor is already at the supplied instant')
        warning = ('Moving backward can repeat work; moving forward can skip work.' if old is not None else
                   'The chosen boundary may repeat or skip work because the old boundary is unknown.')
        deliver(Document(f'Previous report cursor: {label}\nProposed report cursor: {d.instant_text(proposed)}\n',
                         'todo: warning: ' + warning + '\n'), config, self.streams, 'report-set-cursor')
        if not options.get('yes'):
            answer = prompt('Set report cursor? [y/N] ', stdin=self.streams.stdin,
                stdout=self.streams.stdout, stderr=self.streams.stderr, default='n')
            if answer.lower() not in ('y', 'yes'):
                raise Cancelled('cursor unchanged')
        self.store.write_cursor(proposed)
        deliver(render_report_cursor(proposed, binding.last_synced_account_timezone),
                config, self.streams, 'report-set-cursor')
        return ReportResult(end=proposed)

    def _online(self, options, config):
        state = self.store.load_consistent_state(require_cache=False)
        try:
            state = self.store.load_consistent_state()
        except LocalError:
            pass  # Only disposable cache content may be rebuilt.
        now = self.clock()
        # Freeze the command time immediately before retrieval; calendar inputs
        # are resolved only after synchronization supplies the account timezone.
        snapshot, pending, binding, start, end = self._prepare(state, config, options, now)
        finished, progress, hidden = _select(snapshot, self.completed, self.activities,
                                           start, end, config.hidden_from_now, now=now)
        document = render_report(snapshot, start, end, finished=finished, progress=progress, hidden=hidden)
        limit = snapshot.account.capabilities.history_limit
        if limit > 0 and config.warn_limited_history:
            document = replace(document, stderr=history_warning(limit).stderr + document.stderr)
        final = bool(options.get('final'))
        deliver(document, config, self.streams, 'report-final' if final else 'report-preview')
        if not final:
            return ReportResult(start, end)
        self.store.write_cursor(end)
        warnings = ()
        try:
            cleaned = prune_history(pending, end, output_finalized=True, saved_cursor=end)
            self.store.save_history(cleaned, binding=binding)
        except (LocalError, d.DomainError, OSError) as error:
            warnings = ('todo: warning: report output and cursor saved; history cleanup failed; extra retained data is safe: ' + str(error),)
            # A diagnostic failure cannot roll back the already successful final.
            try:
                self.streams.stderr.write(warnings[0] + '\n')
                self.streams.stderr.flush()
            except (OSError, ValueError):
                pass
        return ReportResult(start, end, True, warnings)

    def _prepare(self, state, config, options, now):
        phase, before = 'current retrieval', None
        sync = Synchronizer(self.transport, self.store)
        try:
            known = _known(state)
            # A full current read avoids seeding retained archived metadata into
            # an incremental Sync view and then mistaking it for current evidence.
            current = retrieve(self.transport, known.binding, prior=known, sync_token=state.sync_token,
                replace=True, hidden_names=config.hidden_from_now)
            zone = current.account.timezone
            start = self._boundary(options['since'], now, zone) if 'since' in options else state.cursor
            end = self._boundary(options['until'], now, zone) if 'until' in options else now
            if d.instant_key(start) > d.instant_key(end):
                raise LocalError('report start exceeds end')
            if d.instant_key(end) > d.instant_key(now):
                raise LocalError('report end cannot be in the future')
            caps = current.account.capabilities
            if not caps.activity_history:
                raise LocalError('activity history is unavailable')
            if caps.history_limit == 0:
                raise LocalError('no activity history is retained')
            if caps.history_limit is None:
                raise LocalError('activity retention capability is unavailable')
            # Retention is elapsed UTC days; keep the precise fractional endpoint.
            if caps.history_limit > 0 and d.instant_key(start) < d.instant_key(now) - caps.history_limit * 86400:
                raise LocalError('report start is earlier than retained activity history')
            phase = 'report history retrieval'
            lower = min((start, state.cursor, state.synced_at or state.cursor), key=d.instant_key)
            adapter = HistoryAdapter(self.transport,
                timezone=current.account.timezone, stderr=self.streams.stderr)
            records, pages = [], []
            for category in sorted(current.snapshot.categories):
                result = adapter.completed(lower, now, {'project_id': category})
                records.extend(result.records)
                pages.extend(result.pages)
            self.completed = Retrieval(tuple(records), tuple(pages), lower, now)
            self.activities = adapter.activities(lower, now)
            evidence = _Evidence(adapter, self.completed, self.activities)
            snapshot, pending = _reconcile(current, known, state.history, evidence,
                lower, now, state.cursor, config.hidden_from_now)
            removed = set(current.deleted_ids | current.departed_ids)
            all_items = {**known.items, **{r.item.id: r.item for r in records}, **snapshot.items}
            while True:
                expanded = removed | {i.id for i in all_items.values() if i.parent_id in removed}
                if expanded == removed:
                    break
                removed = expanded
            records = tuple(r for r in records if r.item.id not in removed
                            and r.item.category_id in snapshot.categories and not r.deleted)
            self.completed = replace(self.completed, records=records)
            # Global activity retrieval preserves events from before a currently
            # managed object entered scope. Unknown archived owners are relevant
            # only with managed-project evidence (or absent scope metadata).
            owners = set(current.snapshot.items) | {r.item.id for r in records}
            activities = replace(self.activities, records=tuple(e for e in self.activities.records
                if e.owner_id not in removed and (e.owner_id in owners or e.owner_id in known.items
                    or e.project_id is None or e.project_id in snapshot.categories
                    or e.project_id == snapshot.root.id)))
            for event in activities.records:
                if (event.object_type == 'item' and event.event_type == 'completed'
                        and event.object_id not in owners
                        and _within(event.event_date, start, end)):
                    raise LocalError('unresolved archived owner/parent ' + event.object_id +
                                     '; completed/current evidence is insufficient')
            qualifying = replace(activities, records=tuple(e for e in activities.records
                if _within(e.event_date, start, end)))
            comments = adapter.required_comments(current.snapshot.items, self.completed, qualifying)
            items = dict(comments.owners)
            snapshot = d.validate(replace(snapshot, items=items, comments=comments.comments,
                reminders={k: v for k, v in snapshot.reminders.items() if v.item_id in items},
                occurrences={k: v for k, v in snapshot.occurrences.items() if v.item_id in items}), config.hidden_from_now)
            incoming = History(snapshot, {k: now for k in items})
            pending = merge_history(pending, incoming,
                removed_comment_ids={k for k, c in pending.snapshot.comments.items()
                    if c.item_id in items and k not in snapshot.comments})
            phase = 'candidate preparation'
            candidates = prepare_candidates(snapshot, pending, account_display=state.binding.account_display,
                sync_token=current.sync_token, synced_at=now, hidden_names=config.hidden_from_now)
            before = sync._bytes(('cache.json', 'history.json', 'binding.json'))
            phase = 'local publication'
            self.store.publish_snapshot(candidates)
            return snapshot, pending, self.store.load_binding(), start, end
        except (LocalError, d.DomainError, HTTPFailure, OSError, KeyboardInterrupt) as error:
            started = before is not None and sync._bytes(before.keys()) != before
            failure = SyncError(phase, error, publication_started=started,
                                refresh_permitted=not started)
            if isinstance(error, KeyboardInterrupt):
                raise SyncInterrupted(failure) from None
            raise failure from error


def report(transport=None, request=(), *, store=None, clock=None, streams=None):
    return Reporter(transport, store, clock=clock, streams=streams).run(request)
