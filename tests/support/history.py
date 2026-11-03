"""Reusable synthetic history fixtures; no executable test cases."""
from dataclasses import replace
from todo_lib import domain as d
from todo_lib.local import History, merge_history, prepare_candidates
from todo_lib.workflows.completion import reconcile_completions
import json
from urllib.parse import parse_qsl, urlsplit
from todo_lib.adapter.history import HistoryAdapter
from todo_lib.adapter.transport import Transport
from todo_lib.domain import instant_from_wire as stamp
from tests.support.http import ControlledHTTP, Response


START = '2026-10-20T12:00:00.123456701Z'
END = '2026-10-20T12:00:00.123456709Z'
AFTER = '2026-10-20T12:00:00.123456710Z'
COMPLETED = '/tasks/completed/by_completion_date'
COMPLETED_QUERY = [('since', '2026-10-20T12:00:00Z'),
                   ('until', '2026-10-20T12:00:01Z'), ('limit', '200')]
ACTIVITY_QUERY = [('date_from', '2026-10-20T12:00:00Z'),
                  ('date_to', '2026-10-20T12:00:01Z'),
                  ('limit', '200'),
                  ('object_event_types', '["item:completed", "item:uncompleted", "item:deleted", "note:added", "note:updated", "note:deleted"]')]


def item(identity='task', at=END, **kw):
    raw = dict(id=identity, project_id='cat', parent_id=None, content='Title',
               priority=4, checked=True, labels=[], due=None, added_at=None,
               completed_at=at, is_deleted=False)
    raw.update(kw)
    return raw


def event(identity=1, at=END, **kw):
    raw = dict(id=identity, object_type='note', object_id='note',
               event_type='updated', event_date=at, parent_item_id='step',
               parent_project_id='cat', extra_data={'content': 'Observed old text', 'unknown': 123})
    raw.update(kw)
    return raw


def comment(identity='note', **kw):
    # No item_id: the scoped request supplies ownership.
    raw = dict(id=identity, content='Current text', posted_at=START,
               is_deleted=False, file_attachment=None)
    raw.update(kw)
    return raw


def comments_query(owner):
    return [('task_id', owner), ('limit', '200')]


class Expected:
    """Exact scalar fields and one JSON activity filter at the encoded boundary."""

    def __init__(self, path, query):
        self.path, self.query = path, list(query)

    def check(self, request, timeout):
        url = urlsplit(request.full_url)
        assert url.scheme == 'https' and url.netloc == 'api.todoist.com'
        assert url.path == '/api/v1' + self.path
        assert request.get_method() == 'GET' and request.data is None
        assert request.get_header('Authorization') == 'Bearer secret'
        assert timeout == 30
        actual = parse_qsl(url.query, keep_blank_values=True)
        if self.path == '/activities':
            # Independent retained parameter + x-codeSamples "Multiple event types".
            # Compare decoded JSON, never allow repeated scalar filter values.
            values = [v for k, v in actual if k == 'object_event_types']
            assert len(values) == 1, 'activity filter must have exactly one value'
            assert json.loads(values[0]) == [
                'item:completed', 'item:uncompleted', 'item:deleted', 'note:added', 'note:updated', 'note:deleted']
            actual = [(k, v) for k, v in actual if k != 'object_event_types']
            expected = [(k, v) for k, v in self.query if k != 'object_event_types']
        else:
            expected = self.query
        assert actual == expected, 'query drift or unsupported keys'


def retain_completed(synchronizer, result, hidden_names):
    """Seed saved lifecycle evidence before a command using public adapter/store APIs."""
    s = result.snapshot
    adapter = HistoryAdapter(synchronizer.transport, timezone=s.account.timezone)
    items, occurrences, latest = dict(s.items), dict(s.occurrences), {}
    records = []
    for category in sorted(s.categories):
        for record in adapter.completed(result.state.cursor, result.now,
                                        {'project_id': category}).records:
            at = record.occurrence.completed_at
            if not (d.instant_key(result.state.cursor) < d.instant_key(at) <= d.instant_key(result.now)):
                continue
            if record.item.category_id != category:
                continue
            records.append(record)
            old = latest.get(record.item.id)
            if old is None or d.instant_key(at) > d.instant_key(old.occurrence.completed_at):
                latest[record.item.id] = record
    for identity, record in latest.items():
        if record.deleted:
            continue
        if identity not in items and record.item.completed and not record.item.recurring:
            items[identity] = record.item
    occurrences = reconcile_completions(items, records, (), occurrences.values())
    snapshot = d.validate(replace(s, items=items, occurrences=occurrences), hidden_names)
    if snapshot != s:
        # These observations are needed even if selection is cancelled or a
        # different owner is deleted. Reconciliation reloads the store, so a
        # transient selection snapshot alone cannot protect the discoveries.
        comments = dict(snapshot.comments)
        for identity in sorted(items.keys() - s.items.keys()):
            for comment in adapter.comments(identity).records:
                if comment.item_id != identity or (comment.id in comments
                        and comments[comment.id].item_id != identity):
                    raise d.DomainError('incompatible historical comment ownership')
                comments[comment.id] = comment
        snapshot = d.validate(replace(snapshot, comments=comments), hidden_names)
        history = merge_history(result.history,
            History(snapshot, {identity: result.now for identity in latest if identity in items}))
        candidates = prepare_candidates(snapshot, replace(history, snapshot=snapshot),
            account_display=result.state.binding.account_display,
            sync_token=result.state.sync_token, synced_at=result.state.synced_at,
            current_snapshot=result.state.current_snapshot,
            waiting_label_ids=result.state.waiting_label_ids, current_reminder_ids=result.state.current_reminder_ids,
            hidden_names=hidden_names)
        synchronizer.store.publish_snapshot(candidates)
    return snapshot


class HistorySupport:
    def boundary(self, steps, stderr=None):
        http = ControlledHTTP([(Expected(path, query), response if isinstance(response, Response)
            else Response(json.dumps(response).encode())) for path, query, response in steps])
        self.addCleanup(http.assert_done)
        return HistoryAdapter(Transport('secret', opener=http), stderr=stderr), http
