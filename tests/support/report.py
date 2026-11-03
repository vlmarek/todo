"""Reusable synthetic report fixtures; no executable test cases."""
from io import StringIO
from todo_lib import domain as d
from todo_lib.presentation import OriginalStreams
from todo_lib.workflows.report import Reporter
from todo_lib.workflows.sync import SyncError
from tests.support.sync import SyncSupport, NOW, CURSOR, CREATED, completed_b
from tests.support.current import full, delta, item
from tests.support.history import Expected


START = '2026-10-22T12:00:00.123456789012341Z'
FIRST = '2026-10-22T12:00:00.123456789012344Z'
LAST = '2026-10-22T12:00:00.123456789012349Z'
END = '2026-10-22T12:00:00.123456789012350Z'
NEWER = '2026-10-22T12:00:00.123456789012351Z'


def event(identity, at, kind='updated', owner='B', obj='own', typ='note'):
    return dict(id=identity, object_type=typ, object_id=obj, event_type=kind,
                event_date=at, parent_item_id=owner, parent_project_id='cat',
                extra_data={'content': 'annotation is not current text'})


def limits(access=True, days=-1):
    return dict(current=dict(activity_log=access, activity_log_limit=days, reminders=False))


class ReportSupport:
    setUp = SyncSupport.setUp
    put = SyncSupport.put
    sync = SyncSupport.sync
    boundary = SyncSupport.boundary

    def streams(self, out=None):
        return OriginalStreams(StringIO(), out or StringIO(), StringIO())

    def requests(self, *, events=(), rows=(), days=-1, access=True, comments=None,
                 cursor=CURSOR, now=NOW, current_items=None, current_notes=None):
        lower = min((cursor, self.store.load_consistent_state().synced_at), key=d.instant_key)
        lo = d.instant_text(d.instant_datetime(lower).replace(microsecond=0))
        hi = '2026-10-22T12:00:01Z'
        cq = [('project_id', 'cat'), ('since', lo), ('until', hi), ('limit', '200')]
        aq = [('date_from', lo), ('date_to', hi),
              ('limit', '200')]
        aq += [('object_event_types', '["item:completed", "item:uncompleted", "item:deleted", "note:added", "note:updated", "note:deleted"]')]
        active = current_items if current_items is not None else [item('A'), item('B', parent_id='A')]
        own = comments if comments is not None else [dict(id='own', content='Current post-boundary text', posted_at=CREATED, is_deleted=False)]
        notes = current_notes if current_notes is not None else [dict(c, item_id='B') for c in own if any(i['id'] == 'B' for i in active)]
        token = self.store.load_consistent_state().sync_token
        steps = [self.sync(token, full(items=active, notes=notes, user_plan_limits=limits(access, days))),
                 self.sync('full-token', delta())]
        if access and days != 0:
            steps += [(Expected('/tasks/completed/by_completion_date', cq), {'items': list(rows)}),
                      (Expected('/activities', aq), {'results': list(events), 'next_cursor': None})]
            # Reconciliation needs all missing known owners. Only uncovered owners
            # have REST expectations; active notes above are complete Sync evidence.
            missing = (set(self.store.load_consistent_state().snapshot.items) | set(self.store.load_history().snapshot.items)) - {i['id'] for i in active}
            archived = {r['id'] for r in rows if r.get('checked')} - {i['id'] for i in active}
            for owner in sorted(missing | archived):
                steps.append((Expected('/comments', [('task_id', owner), ('limit', '200')]),
                    {'results': own if owner == 'B' else [], 'next_cursor': None}))
        return steps

    def run_report(self, steps, args=(), streams=None, now=NOW):
        transport, self.last_http = self.boundary(steps)
        streams = streams or self.streams()
        result = Reporter(transport, self.store, clock=lambda: now, streams=streams).run(args)
        return result, streams
