"""Independent provider fixtures from the pinned upstream location:

docs/design/external/todoist/upstream/api-v1.openapi.json.

NotificationSyncView.properties.due.examples[0] supplies MINIMAL unchanged.
Due dates tag supplies floating/fixed and recurrence shapes. FLOATING uses a
synthetic valid 2026 date: the tag's literal `2016-12-0` is malformed, so it is
not copied as an executable example. Recurrence wording is synthetic Spanish.
Sync Reminders and minute_offset description establish RELATIVE, including zero.
"""
from copy import deepcopy
import json
from todo_lib.adapter.current import retrieve
from todo_lib.adapter.transport import Transport
from tests.adapter.current.test_current import BINDING, RESOURCES, full, delta, item, due
from tests.support.http import ControlledHTTP, ExpectedRequest, Response

MINIMAL = {'date': '2025-02-12T09:00:00', 'lang': 'en', 'timezone': 'Europe/Madrid'}
FLOATING = {'date': '2026-10-30T09:00:00.123456789012345', 'timezone': None,
            'string': 'cada día a las 9', 'lang': 'es', 'is_recurring': True}
FIXED = {'date': '2026-10-30T08:00:00.123456789012345Z', 'timezone': 'Europe/Madrid',
         'string': 'cada día a las 9', 'lang': 'es', 'is_recurring': True}
RELATIVE = {'id': 'rel', 'item_id': 'timed', 'type': 'relative', 'minute_offset': 0,
            'due': {'unused': 'never interpreted'}, 'is_deleted': False,
            'notify_uid': 'recipient', 'is_urgent': False}


def absolute(identity='abs', schedule=None, **changes):
    result = dict(id=identity, item_id='undated', type='absolute',
                  due=deepcopy(MINIMAL if schedule is None else schedule),
                  is_deleted=False, notify_uid='recipient', is_urgent=True)
    result.update(changes)
    return result


def response():
    return full(items=[item('timed', due=due()), item('undated')],
        reminders=[deepcopy(RELATIVE), absolute(), absolute('floating', FLOATING),
                   absolute('fixed', FIXED)])


def boundary(case, steps):
    http = ControlledHTTP([(ExpectedRequest('POST', '/sync', 'secret', form={
        'sync_token': token, 'resource_types': RESOURCES}), Response(json.dumps(raw).encode()))
        for token, raw in steps])
    case.addCleanup(http.assert_done)
    return Transport('secret', opener=http, sleep=lambda _: None)


def observed(case, raw=None):
    return retrieve(boundary(case, [('*', response() if raw is None else raw),
                                   ('full-token', delta())]), BINDING)
