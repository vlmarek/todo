"""Reusable synthetic current fixtures; no executable test cases."""
import json
from todo_lib.adapter.current import retrieve
from todo_lib.adapter.transport import Transport
from todo_lib.domain import Binding
from tests.support.http import ControlledHTTP, ExpectedRequest, Response


BINDING = Binding('u', 'root', frozenset({'cat'}))
STAMP = '2026-10-20T12:00:00.123456789Z'
MISSING = object()
RESOURCES = '["user","user_plan_limits","projects","items","labels","notes","reminders"]'


def project(identity='cat', parent='root', **changes):
    obj = dict(id=identity, name=identity, parent_id=parent, is_shared=False,
               is_archived=False, is_deleted=False)
    obj.update(changes)
    return obj


def due(value='2026-11-12T15:00:00.123456789Z', **changes):
    obj = dict(date=value, timezone='Europe/Prague', string='every day at 16',
               lang='en', is_recurring=False)
    obj.update(changes)
    return obj


def item(identity='task', **changes):
    obj = dict(id=identity, project_id='cat', parent_id=None, content=identity,
               priority=4, checked=False, labels=[], due=None, added_at=STAMP,
               completed_at=None, is_deleted=False)
    obj.update(changes)
    return obj


def note(identity='note', owner='task', **changes):
    obj = dict(id=identity, item_id=owner, content='own note', posted_at=STAMP,
               is_deleted=False, file_attachment=None)
    obj.update(changes)
    return obj


def reminder(identity='reminder', owner='task', **changes):
    obj = dict(id=identity, item_id=owner, type='relative', minute_offset=0,
               is_deleted=False)
    obj.update(changes)
    return obj


def full(**changes):
    obj = dict(full_sync=True, sync_token='full-token',
        user={'id': 'u', 'tz_info': {'timezone': 'Europe/Prague'}},
        user_plan_limits={'current': {'activity_log': False,
            'activity_log_limit': 0, 'reminders': True}},
        projects=[project('root', None), project()], labels=[],
        items=[item()], notes=[], reminders=[])
    obj.update(changes)
    return obj


def delta(**changes):
    obj = dict(full_sync=False, sync_token='delta-token')
    obj.update(changes)
    return obj


class CurrentSupport:
    def boundary(self, steps):
        script = []
        for token, response in steps:
            if not isinstance(response, (Response, Exception)):
                response = Response(json.dumps(response).encode())
            script.append((ExpectedRequest('POST', '/sync', 'secret', form={
                'sync_token': token, 'resource_types': RESOURCES}), response))
        http = ControlledHTTP(script)
        self.addCleanup(http.assert_done)
        return Transport('secret', opener=http, sleep=lambda _: None), http

    def initial(self, response=None, freshness=None):
        transport, _ = self.boundary([('*', full() if response is None else response),
            ('full-token', delta() if freshness is None else freshness)])
        return retrieve(transport, BINDING)

    def changed(self, prior, response):
        transport, _ = self.boundary([(prior.sync_token, response)])
        return retrieve(transport, prior.binding, prior=prior.snapshot,
                        sync_token=prior.sync_token)
