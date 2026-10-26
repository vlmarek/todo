"""Ordered capture, scalar and scheduling workflows over synchronized state.

Preflight constructs and validates the whole proposed batch. The execution plan
uses symbolic create IDs until the gateway supplies operation-attributable IDs.
Every accepted operation crosses the synchronizer's publication boundary before
another mutation. Failure receipts retain remote classification without replay.
"""
from dataclasses import dataclass, field, replace
from todo_lib import domain as d, presentation as p
from todo_lib.adapter.commands import Gateway, Operation, due_arguments
from todo_lib.adapter.current import Current
from todo_lib.adapter.transport import HTTPFailure, Replay
from todo_lib.local import exclusive_lock, load_config, LocalError
from todo_lib.syntax import parse
from .reads import select_title, select_child
from .sync import SyncError, SyncInterrupted
from .scheduling import propose, validate_proposals, offsets, offset_text


@dataclass(frozen=True)
class OperationOutcome:
    operation: str
    title: str
    outcome: str
    target_id: str | None = None
    actual: object = None
    issues: tuple[str, ...] = ()
    receipt: object = None


@dataclass(frozen=True)
class CaptureResult:
    snapshot: d.Snapshot
    outcomes: tuple[OperationOutcome, ...]
    document: p.Document
    status: int = 0
    failure: object = None


@dataclass
class _Action:
    method: str
    target: str
    title: str
    kwargs: dict = field(default_factory=dict)
    expected: object = None
    retained: tuple[int, ...] | None = None


def _same_item(left, right, zone):
    return (left.title, left.priority, left.description, left.labels) == (
        right.title, right.priority, right.description, right.labels) and d.same_attention(
        left.attention, right.attention, zone)


def _require_waiting_label(transport):
    """Read label resources only when adding policy; never provision implicitly.

    Sync's documented full response followed by freshness delta supplies label
    existence, which Snapshot deliberately does not model. Item labels are names.
    """
    labels, token = {}, '*'
    for full in (True, False):
        response = transport.request('POST', '/sync', replay=Replay.READ,
            form={'sync_token': token, 'resource_types': '["labels"]'})
        if (not isinstance(response, dict) or response.get('full_sync') is not full
                or not isinstance(response.get('sync_token'), str)
                or not response['sync_token'] or response['sync_token'] == '*'
                or not isinstance(response.get('labels', [] if not full else None), list)):
            raise d.DomainError('invalid waiting label resource response')
        token = response['sync_token']
        for label in response.get('labels', []):
            if (not isinstance(label, dict) or not isinstance(label.get('id'), str)
                    or not label['id'] or type(label.get('is_deleted', False)) is not bool):
                raise d.DomainError('invalid waiting label resource')
            if label.get('is_deleted', False):
                labels.pop(label['id'], None)
            else:
                if not isinstance(label.get('name'), str) or not label['name']:
                    raise d.DomainError('invalid waiting label name')
                labels[label['id']] = label['name']
    if 'waiting' not in labels.values():
        raise d.DomainError('waiting label is missing; run todo init before adding hiding')


class CaptureWorkflow:
    def __init__(self, synchronizer, *, gateway=None, settings=None, streams=None):
        self.synchronizer = synchronizer
        self.gateway = gateway or Gateway(synchronizer.transport)
        self.settings = settings
        self.streams = streams

    def execute(self, request, *, deliver=False):
        if isinstance(request, (list, tuple)):
            request = parse(request)
        if request.command not in ('add', 'priority', 'rename', 'schedule', 'hide', 'unhide'):
            raise ValueError('not a capture/scalar/scheduling command: ' + request.command)
        settings = self.settings or load_config(self.synchronizer.store.root)
        with exclusive_lock('capture', self.synchronizer.store.root):
            synchronized = self.synchronizer.refresh_locked()
            snapshot = synchronized.snapshot
            now = d.instant_datetime(synchronized.now)
            d.validate(snapshot, settings.hidden_from_now)
            actions, adding_hiding = self._plan(request, snapshot, now, settings.hidden_from_now)
            if adding_hiding:
                _require_waiting_label(self.synchronizer.transport)
            result = self._run(actions, synchronized, settings.hidden_from_now, now)
        if deliver:
            streams = self.streams or p.OriginalStreams.current()
            p.deliver(result.document, settings, streams, view_kind='mutation')
        return result

    def _plan(self, request, snapshot, now, hidden):
        actions, proposals = [], []
        adding_hiding = False
        options = dict(request.options)
        if request.command == 'add' and request.target == 'category':
            name = d.validate_title(options['name'])
            if any(d.title_key(c.name) == d.title_key(name) for c in snapshot.categories.values()):
                raise d.DomainError('category already exists: ' + name)
            return [_Action('provision_category', snapshot.root.id, name, {'name': name})], False
        if request.command == 'add':
            titles = [d.validate_title(v) for g in request.groups if g.kind == ('step' if request.target == 'step' else 'title') for v in g.values]
            inline = [d.validate_title(v) for g in request.groups if g.kind == 'step' for v in g.values] if request.target == 'task' else []
            if not titles:
                raise d.DomainError('creation requires titles')
            if inline and len(titles) != 1:
                raise d.DomainError('inline steps require exactly one new task')
            parent = None
            if request.target == 'step':
                parent = select_title(snapshot, request.parent, now, streams=self.streams)
                if d.hierarchy_depths(snapshot)[parent.id] >= 4:
                    raise d.DomainError('parent at depth 4 cannot receive another step')
                category_id = parent.category_id
                priority = d.creation_priority(snapshot, parent.id)
                if 'priority' in options:
                    raise d.DomainError('step creation has no priority option')
            else:
                category_id = d.lookup_category(snapshot, options['category']).id
                priority = int(str(options.get('priority', 'P2')).lower().removeprefix('p'))
            if options.get('done') and any(k in options for k in ('at', 'hide', 'reason', 'reminder')):
                raise d.DomainError('completed creation cannot have scheduling or hiding')
            # Validate all original active sibling sets together, including inline children.
            items = dict(snapshot.items)
            for index, title in enumerate(titles):
                key = self._temporary(items, index)
                item = d.Item(key, category_id, title, parent.id if parent else None, priority=priority)
                items[key] = item
                context = replace(snapshot, items=items)
                proposal = propose(request, context, item, now)
                proposals.append(proposal)
                adding_hiding |= proposal.item.waiting
                actions.append(_Action('create_task', key, title, dict(category_id=category_id,
                    title=title, parent_id=item.parent_id, priority=priority,
                    attention=proposal.item.attention, labels=proposal.item.labels,
                    description=proposal.item.description), proposal.item, ()))
                self._reminders(actions, context, key, title, proposal.reminders)
                for j, child_title in enumerate(inline):
                    child_key = self._temporary(items, f'{index}-{j}')
                    child = d.Item(child_key, category_id, child_title, key, priority=priority)
                    items[child_key] = child
                    actions.append(_Action('create_task', child_key, child_title,
                        dict(category_id=category_id, title=child_title, parent_id=key,
                             priority=priority), child, ()))
                    if options.get('done'):
                        actions.append(_Action('complete', child_key, child_title))
                if options.get('done'):
                    actions.append(_Action('complete', key, title))
            validate_proposals(replace(snapshot, items=items), proposals, hidden)
        else:
            item = (select_child(snapshot, request.parent, request.selector, now, streams=self.streams)
                    if request.parent else select_title(snapshot, request.selector, now,
                        target=request.target, streams=self.streams))
            d.require_editable(item)
            if request.command in ('priority', 'rename'):
                kwargs = ({'priority': int(str(options['priority']).lower().removeprefix('p'))}
                          if request.command == 'priority' else {'title': d.validate_title(' '.join(request.destination))})
                updated = replace(item, **kwargs)
                if updated == item:
                    raise d.DomainError(f'unchanged {request.command}: ' + str(next(iter(kwargs.values()))))
                d.validate(replace(snapshot, items={**snapshot.items, item.id: updated}), hidden)
                actions.append(_Action('update_task', item.id, item.title, kwargs, updated, offsets(snapshot, item.id)))
            else:
                proposal = propose(request, snapshot, item, now)
                if _same_item(item, proposal.item, snapshot.account.timezone) and set(offsets(snapshot, item.id)) == set(proposal.reminders):
                    raise d.DomainError('unchanged attention, hiding and reminders (complete no-op)')
                validate_proposals(snapshot, [proposal], hidden)
                adding_hiding = proposal.item.waiting and not item.waiting
                kwargs = {}
                for name in ('attention', 'labels', 'description'):
                    old, new = getattr(item, name), getattr(proposal.item, name)
                    same = d.same_attention(old, new, snapshot.account.timezone) if name == 'attention' else old == new
                    if not same:
                        kwargs[name] = new
                # Explicit clear may remove reminders before changing to date-only/none.
                markers = 'reminder' in options or options.get('clear')
                if markers and set(offsets(snapshot, item.id)) != set(proposal.reminders):
                    self._reminders(actions, snapshot, item.id, item.title, (), delete_only=True)
                if kwargs:
                    actions.append(_Action('update_task', item.id, item.title, kwargs, proposal.item,
                        offsets(snapshot, item.id) if not markers or set(offsets(snapshot, item.id)) == set(proposal.reminders) else ()))
                if markers and set(offsets(snapshot, item.id)) != set(proposal.reminders):
                    self._reminders(actions, replace(snapshot, reminders={}), item.id, item.title, proposal.reminders)
        return actions, adding_hiding

    @staticmethod
    def _temporary(items, suffix):
        key = 'capture-proposal-' + str(suffix)
        while key in items:
            key += '-new'
        return key

    @staticmethod
    def _reminders(actions, snapshot, item_id, title, values, delete_only=False):
        for reminder in snapshot.reminders.values():
            if reminder.item_id == item_id:
                actions.append(_Action('delete_reminder', reminder.id, title))
        if not delete_only:
            for minutes in values:
                actions.append(_Action('create_reminder', item_id, title, {'minutes': minutes}))

    def _run(self, actions, synchronized, hidden, now):
        snapshot = synchronized.snapshot
        ids, outcomes, documents = {}, [], []
        failure = None
        status = 0
        for action in actions:
            target = ids.get(action.target, action.target)
            kwargs = dict(action.kwargs)
            if kwargs.get('parent_id') in ids:
                kwargs['parent_id'] = ids[kwargs['parent_id']]
            before = Current(snapshot, synchronized.state.sync_token)
            old = snapshot.items.get(target)
            receipt = None
            rendered = False
            try:
                method = getattr(self.gateway, action.method)
                if action.method == 'create_task':
                    receipt = method(**kwargs, before=before)
                elif (action.method == 'update_task' and kwargs.get('attention') is not None
                      and kwargs['attention'].kind == 'date' and old.recurring and old.attention.zone is not None):
                    # update_task retains the previous zone unconditionally. A date-only
                    # occurrence cannot carry that timed zone (Due dates contract).
                    # Submit the validated semantic update through the same gateway.
                    attention = kwargs['attention']
                    args = {'id': target, 'due': due_arguments(attention, old.attention)}
                    args['due']['timezone'] = None
                    args.update({k: list(v) if k == 'labels' else v for k, v in kwargs.items() if k != 'attention'})
                    receipt = self.gateway.execute(Operation('item_update', args,
                        expected_attention=attention), before=before)
                else:
                    receipt = method(target, **kwargs, before=before)
                outcome = receipt.outcome.value
                issues = list(receipt.issues)
                actual = receipt.actual
                # Record acceptance before reconciliation: publication cannot undo it.
                outcomes.append(OperationOutcome(action.method, action.title, outcome,
                    receipt.target_id, actual, tuple(issues), receipt))
                if not receipt.accepted:
                    failure = '; '.join(issues) or ('remote outcome ' + outcome)
                    status = 1
                    break
                if action.method == 'create_task':
                    ids[action.target] = receipt.target_id
                    target = receipt.target_id
                synchronized = self.synchronizer.reconcile_accepted_locked()
                snapshot = synchronized.snapshot
                d.validate(snapshot, hidden)
                actual = (snapshot.categories.get(receipt.target_id) if action.method == 'provision_category'
                          else snapshot.reminders.get(receipt.target_id) if action.method in ('create_reminder', 'delete_reminder')
                          else snapshot.items.get(target))
                if action.expected is not None:
                    expected = action.expected
                    if actual is None:
                        issues.append('accepted item is absent from reconciled state')
                    else:
                        attention = expected.attention
                        if attention is not None and attention.kind == 'unresolved':
                            valid_due = actual.attention is not None
                        else:
                            compare = d.reconciles_attention if 'attention' in kwargs else d.same_attention
                            valid_due = compare(attention, actual.attention, snapshot.account.timezone)
                        if not valid_due:
                            issues.append(f'accepted attention differs: requested {attention!r}; actual {actual.attention!r}')
                        if (expected.title, expected.priority, expected.labels, expected.description) != (actual.title, actual.priority, actual.labels, actual.description):
                            issues.append('accepted scalar state differs from proposed title/priority/hiding/reason')
                        if (actual.parent_id != ids.get(expected.parent_id, expected.parent_id)
                                or actual.category_id != expected.category_id):
                            issues.append('accepted item has unexpected parent/category')
                if action.method == 'create_reminder':
                    if actual is None or (actual.item_id, actual.minutes) != (target, kwargs['minutes']):
                        issues.append('accepted reminder differs from reconciled owner/offset')
                elif action.method == 'delete_reminder' and target in snapshot.reminders:
                    issues.append('accepted reminder deletion remains in reconciled state')
                elif action.method == 'complete' and (actual is None or not actual.completed):
                    issues.append('accepted ordinary completion is absent from reconciled lifecycle state')
                if action.method in ('create_reminder', 'delete_reminder'):
                    owner_id = target if action.method == 'create_reminder' else before.snapshot.reminders[target].item_id
                    owner_before = before.snapshot.items[owner_id]
                    owner_after = snapshot.items.get(owner_id)
                    if owner_after is None or not _same_item(owner_before, owner_after, snapshot.account.timezone):
                        issues.append('reminder operation changed the owner attention/scalar state')
                if action.method == 'provision_category':
                    if actual is None or (actual.name, actual.parent_id) != (kwargs['name'], target):
                        issues.append('accepted category differs from reconciled name/parent')
                if action.retained is not None and set(offsets(snapshot, target)) != set(action.retained):
                    issues.append('accepted attention changed the preserved reminder set')
                outcomes[-1] = replace(outcomes[-1], actual=actual, issues=tuple(issues))
                documents.append(self._document(action, old, actual, snapshot, now, before.snapshot))
                rendered = True
                if issues:
                    failure = '; '.join(issues) + '. Read-only recovery: todo --refresh now; do not replay the mutation.'
                    status = 1
                    break
            except (SyncError, SyncInterrupted, d.DomainError, LocalError, HTTPFailure, OSError, KeyboardInterrupt) as error:
                failure = error
                status = 130 if isinstance(error, KeyboardInterrupt) else 1
                if receipt is None:
                    outcomes.append(OperationOutcome(action.method, action.title, 'unknown', target,
                        issues=(str(error),)))
                elif receipt.accepted:
                    if not rendered and receipt.actual is not None and receipt.after is not None:
                        try:
                            documents.append(self._document(action, old, receipt.actual,
                                receipt.after.snapshot, now, before.snapshot))
                        except Exception as rendering_error:
                            # A secondary display failure must not erase accepted
                            # remote work or prevent the ordered recovery receipt.
                            outcomes[-1] = replace(outcomes[-1], issues=(
                                *outcomes[-1].issues, 'accepted receipt rendering failed: ' + str(rendering_error)))
                            documents.append(p.document(warnings='Accepted receipt rendering failed: ' + str(rendering_error)))
                    outcomes[-1] = replace(outcomes[-1], issues=(*outcomes[-1].issues, str(error)))
                break
        if failure is not None:
            for action in actions[len(outcomes):]:
                outcomes.append(OperationOutcome(action.method, action.title, 'unattempted'))
            labels = {'rejected': 'Failed', 'unattempted': 'Not attempted'}
            lines = [f"{labels.get(o.outcome, o.outcome.capitalize())}: {o.operation.replace('_', ' ')} {o.title}"
                     for o in outcomes]
            lines.append(str(failure))
            if any(o.outcome == 'unknown' for o in outcomes):
                lines.append('Read-only recovery: todo --refresh now; do not replay an unknown mutation.')
            documents.append(p.document(warnings='\n'.join(lines)))
        return CaptureResult(snapshot, tuple(outcomes), p.render_receipts(documents), status, failure)

    @staticmethod
    def _document(action, old, actual, snapshot, now, before_snapshot):
        if action.method == 'provision_category':
            return p.render_created_category(actual) if actual else p.document()
        if action.method in ('create_reminder', 'delete_reminder'):
            reminder = actual if action.method == 'create_reminder' else before_snapshot.reminders.get(action.target)
            owner = snapshot.items.get(reminder.item_id) if reminder else None
            if owner is None:
                return p.document()
            return p.render_mutation(snapshot, owner, changes=(('Reminders',
                offset_text(offsets(before_snapshot, owner.id)), offset_text(offsets(snapshot, owner.id))),))
        if actual is None:
            return p.document()
        if action.method == 'create_task':
            return p.render_mutation(snapshot, actual, 'Created', attention=actual.attention,
                changes=(('Hiding', False, actual.waiting),))
        if action.method == 'complete':
            # Completion may archive the owner (and its ancestors) out of active
            # Sync. Keep pre-completion ancestry as display context, with the
            # authoritative completed owner taking precedence.
            context = replace(snapshot, items={**before_snapshot.items,
                                               **snapshot.items, actual.id: actual})
            return p.render_mutation(context, actual, 'Completed')
        changes = [('Title', old.title, actual.title),
                   ('Priority', f'P{old.priority}', f'P{actual.priority}'),
                   ('Hiding', old.waiting, actual.waiting),
                   ('Reason', d.split_waiting(old.description)[1], d.split_waiting(actual.description)[1])]
        zone = snapshot.account.timezone
        if not d.same_attention(old.attention, actual.attention, zone):
            previous_due = p.actual_due(old.attention, zone) if old.attention else None
            actual_due = p.actual_due(actual.attention, zone) if actual.attention else None
            if previous_due == actual_due:
                # Whole-second display must not erase a real explicit fractional change.
                previous_due = due_arguments(old.attention)['date']
                actual_due = due_arguments(actual.attention)['date']
            changes.append(('Due', previous_due, actual_due))
        document = p.render_mutation(snapshot, actual, changes=changes)
        if not document.stdout and 'attention' in action.kwargs:
            document = p.document(f'Accepted scheduling for {actual.role}: {actual.title}\n'
                                  '  Due: ' + p.actual_due(actual.attention, zone))
        extra = []
        if action.retained:
            extra.append('  Reminders retained: ' + offset_text(action.retained))
        if old.waiting and not actual.waiting and d.visibility(snapshot, actual.id, now).ancestor_hidden:
            extra.append('  Still hidden by an ancestor policy.')
        return p.render_receipts((document, p.document('\n'.join(extra))))


def execute(request, synchronizer, **kwargs):
    delivery = kwargs.pop('deliver', False)
    return CaptureWorkflow(synchronizer, **kwargs).execute(request, deliver=delivery)
