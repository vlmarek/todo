"""Reusable synthetic sync fixtures; no executable test cases."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from todo_lib import domain as d
from todo_lib.adapter.current import retrieve
from todo_lib.adapter.transport import Transport
from todo_lib.local import StateStore, empty_history, prepare_candidates, exclusive_lock
from todo_lib.workflows import Synchronizer
from tests.support.current import BINDING, RESOURCES, full, delta, item, note
from tests.support.history import Expected
from tests.support.http import ControlledHTTP, ExpectedRequest, Response
from tests.support.fixture import Fixture


CREATED = '2026-10-20T12:00:00.123456789012345Z'
DONE = '2026-10-21T12:00:00.123456789012349Z'
COMMENT = '2026-10-21T12:00:00.123456789012348Z'
NOW = d.instant_from_wire('2026-10-22T12:00:00.123456789012350Z')
INITIAL = d.instant_from_wire('2026-10-20T13:00:00Z')
CURSOR = d.instant_from_wire('2026-10-20T00:00:00Z')
COMPLETED_QUERY = [('project_id', 'cat'), ('since', '2026-10-20T00:00:00Z'),
                   ('until', '2026-10-22T12:00:01Z'), ('limit', '200')]


def open_tree(**changes):
    return full(items=[item('A', added_at=CREATED),
                       item('B', parent_id='A', added_at=CREATED)],
                notes=[note('own', 'B', posted_at=CREATED)], **changes)


def completed_b(**changes):
    return item('B', parent_id='A', checked=True, completed_at=DONE,
                added_at=CREATED, **changes)


class SyncSupport:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / '.todo'
        self.root.mkdir(mode=0o700)
        self.store = StateStore(self.root)
        self.put('config', b'[main]\nproject=root\ndefault_sections=cat\nhidden_from_now=\n')
        # Observe the open tree through real adapter mapping. No completed seed.
        transport, _ = self.boundary([self.sync('*', open_tree()),
                                     self.sync('full-token', delta())])
        observed = retrieve(transport, BINDING)
        with exclusive_lock('init', self.root):
            self.store.publish_snapshot(prepare_candidates(observed.snapshot,
                empty_history(observed.snapshot), account_display='Person',
                waiting_label_ids=observed.waiting_label_ids, current_snapshot=observed.snapshot, sync_token=observed.sync_token, synced_at=INITIAL, initial_cursor=CURSOR))

    def put(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        path.chmod(0o600)

    def sync(self, token, data):
        return (ExpectedRequest('POST', '/sync', 'secret', form={
            'sync_token': token, 'resource_types': RESOURCES}), data)

    def completed(self, rows):
        return (Expected('/tasks/completed/by_completion_date', COMPLETED_QUERY), {'items': rows})

    def comments(self, body='Surviving own comment', **changes):
        raw = dict(id='own', content=body, posted_at=COMMENT,
                   is_deleted=False, file_attachment=None, **changes)
        return (Expected('/comments', [('task_id', 'B'), ('limit', '200')]),
                {'results': [raw], 'next_cursor': None})

    def boundary(self, steps):
        http = ControlledHTTP([(request, value if isinstance(value, (Response, Exception))
                     else Response(json.dumps(value).encode())) for request, value in steps])
        self.addCleanup(http.assert_done)
        return Transport('secret', opener=http, sleep=lambda _: None), http

    def workflow(self, steps=(), now=NOW):
        transport, http = self.boundary(steps)
        return Synchronizer(transport, self.store, clock=lambda: now), http

    def external(self):
        return [self.sync('delta-token', full(items=[item('A', added_at=CREATED)])),
                self.sync('full-token', delta()), self.completed([completed_b()]), self.comments()]

    def retained(self, *, c=False):
        steps = [self.completed([]), self.comments()]
        if c:
            steps.append((Expected('/comments', [('task_id', 'C'), ('limit', '200')]),
                          {'results': [], 'next_cursor': None}))
        return steps

    def bytes(self):
        return {name: (self.root / name).read_bytes() for name in
                ('cache.json', 'history.json', 'binding.json', 'report-cursor')}

    def child_process(self, mixed=False):
        # Separate interpreter uses the public workflow/store. Any HTTP is fatal.
        script = '''
import json, sys
from todo_lib.workflows import Synchronizer
from todo_lib.local import StateStore, LocalError
from todo_lib.domain import instant_from_wire, instant_text, instant_key
class NoHTTP:
    def request(self, *a, **k):
        raise AssertionError('offline HTTP')
w = Synchronizer(NoHTTP(), StateStore(sys.argv[1]), clock=lambda: instant_from_wire('2026-10-24T12:00:00Z'))
try:
    r = w.read_local()
except LocalError as error:
    if sys.argv[2] != 'mixed': raise
    assert 'mixed' in str(error) or 'required history' in str(error), str(error)
    print('refused mixed set with zero HTTP')
else:
    assert sys.argv[2] != 'mixed'
    b = r.history.snapshot.items['B']
    c = r.history.snapshot.comments['own']
    assert b.parent_id == 'A' and b.completed
    assert instant_text(b.added_at) == sys.argv[3]
    assert instant_key(b.added_at) == instant_key(instant_from_wire(sys.argv[3]))
    assert instant_text(b.completed_at) == sys.argv[4]
    assert instant_text(c.added_at) == sys.argv[5]
    assert c.body == 'Surviving own comment' and c.item_id == 'B'
    assert r.warnings
    print('coherent precise state with zero HTTP')
'''
        result = subprocess.run([sys.executable, '-B', '-c', script, str(self.root),
                'mixed' if mixed else 'coherent', CREATED, DONE, COMMENT],
                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def assert_precise(self):
        state = StateStore(self.root).load_consistent_state()
        for s in (state.snapshot, state.history.snapshot):
            self.assertEqual(set(s.items), {'A', 'B'})
            b, c = s.items['B'], s.comments['own']
            self.assertFalse(s.items['A'].completed)
            self.assertTrue(b.completed)
            self.assertEqual(b.parent_id, 'A')
            for value, expected in ((b.added_at, CREATED), (b.completed_at, DONE),
                                    (c.added_at, COMMENT)):
                self.assertEqual(d.instant_text(value), expected)
                self.assertEqual(d.instant_key(value), d.instant_key(d.instant_from_wire(expected)))
            self.assertEqual(c.body, 'Surviving own comment')
        return state

    def reminder_hydration(self, final, *, resolved=True):
        # Synthetic Sync NotificationSyncView due shapes from pinned upstream
        # api-v1.openapi.json. C is absent from current and not yet scope-resolved.
        from tests.support.reminders import absolute
        first = absolute('historical', item_id='C')
        conflicting = absolute('historical', {'date': '2025-02-12T10:00:00',
            'lang': 'en', 'timezone': 'Europe/Madrid'}, item_id='C')
        steps = [self.sync('delta-token', delta(items=[item('entrant')],
                    reminders=[first, conflicting])),
                 self.sync('*', full(items=[item('A', added_at=CREATED), item('entrant')],
                                      reminders=final)),
                 self.sync('full-token', delta()),
                 self.completed([completed_b()] + ([item('C', checked=True,
                    completed_at=DONE, added_at=CREATED)] if resolved else [])),
                 self.comments()]
        if resolved:
            steps.append((Expected('/comments', [('task_id', 'C'), ('limit', '200')]),
                          {'results': [], 'next_cursor': None}))
        return steps


class SyncFixture(SyncSupport, Fixture):
    """Standalone fixture with cleanup owned by its calling test."""
