"""Ordered capture, scalar and scheduling workflows over validated saved state.

Preflight constructs and validates the whole proposed batch. The execution plan
uses symbolic create IDs until the gateway supplies operation-attributable IDs.
Every accepted operation crosses the synchronizer's publication boundary before
another mutation. Failure receipts retain remote classification without replay.
"""
from dataclasses import dataclass, field, replace
from todo_lib import domain as d, presentation as p
from todo_lib.adapter.commands import Gateway, due_arguments, _UnsubmittedOperation
from todo_lib.adapter.current import Current
from todo_lib.adapter.transport import HTTPFailure
from todo_lib.local import exclusive_lock, load_config, LocalError
from todo_lib.syntax import parse
from todo_lib.syntax.input import prompt, InputError
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
    creating_owner: bool = False


def reminder_values(snapshot, owner_id):
    """Accepted receipt scalar, preserving each reminder's schedule context."""
    from todo_lib.presentation.formatting import reminders_text
    reminders = [r for r in snapshot.reminders.values() if r.item_id == owner_id]
    relative = sorted(r.minutes for r in reminders if r.type == 'relative')
    absolute = [r for r in reminders if r.type == 'absolute']
    return ', '.join(v for v in (offset_text(relative), reminders_text(absolute, snapshot.account.timezone, schedule_zone=True)) if v) or None


def _same_item(left, right, zone):
    return (left.title, left.priority, left.description, left.labels) == (
        right.title, right.priority, right.description, right.labels) and d.same_attention(
        d.rebase_attention(left.attention, zone), d.attention_prediction(right.attention, zone), zone)


def _require_waiting_label(state):
    if state.waiting_label_ids is None:
        raise LocalError('saved waiting-label context is missing; run todo --refresh now then retry')
    if not state.waiting_label_ids:
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
            synchronized = (self.synchronizer.refresh_locked() if request.command == 'add' and request.target == 'category'
                            else self.synchronizer.read_local())
            snapshot = synchronized.snapshot
            now = d.instant_datetime(synchronized.now)
            d.validate(snapshot, settings.hidden_from_now)
            actions, adding_hiding = self._plan(request, snapshot, now, settings.hidden_from_now,
                p.Color.for_stdout((self.streams or p.OriginalStreams.current()).stdout,
                    request.option('color', 'auto'), slots=settings.colors))
            if self.previews:
                streams = self.streams or p.OriginalStreams.current()
                for preview in self.previews:
                    streams.stdout.write(preview.stdout + '\n')
                streams.stdout.flush()
                try:
                    answer = prompt('Replace reminders and remove the listed existing reminders? [y/N]:',
                        stdin=streams.stdin, stdout=streams.stdout, stderr=streams.stderr, default='n')
                    if answer.lower() not in ('y', 'yes'):
                        raise InputError('reminder replacement cancelled')
                except InputError as error:
                    result = CaptureResult(snapshot, (), p.document(warnings=str(error)), error.status, error)
                    if deliver:
                        p.deliver(result.document, settings, streams, view_kind='mutation')
                    return result
            if adding_hiding:
                _require_waiting_label(synchronized.state)
            result = self._run(actions, synchronized, settings.hidden_from_now, now)
        if deliver:
            streams = self.streams or p.OriginalStreams.current()
            p.deliver(result.document, settings, streams, view_kind='mutation')
        return result

    def _plan(self, request, snapshot, now, hidden, color=p.Color()):
        self.previews = []
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
                parent = select_title(snapshot, request.parent, now, streams=self.streams, color=color)
                if d.hierarchy_depths(snapshot)[parent.id] >= 4:
                    raise d.DomainError('parent at depth 4 cannot receive another step')
                category_id = parent.category_id
                priority = d.creation_priority(snapshot, parent.id)
                if 'priority' in options:
                    raise d.DomainError('step creation has no priority option')
            else:
                category_id = d.lookup_category(snapshot, options['category']).id
                priority = int(str(options.get('priority', 'P2')).lower().removeprefix('p'))
            if options.get('done') and any(k in options for k in ('at', 'hide', 'reason', 'reminder', 'reminder-at')):
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
                self._reminders(actions, key, title, proposal.additions, creating_owner=True)
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
            d.validate_sibling_uniqueness(items.values(), snapshot.items.values())
            validate_proposals(replace(snapshot, items=items), proposals, hidden)
        else:
            item = (select_child(snapshot, request.parent, request.selector, now, streams=self.streams, color=color)
                    if request.parent else select_title(snapshot, request.selector, now,
                        target=request.target, streams=self.streams, color=color))
            d.require_editable(item)
            if request.command in ('priority', 'rename'):
                kwargs = ({'priority': int(str(options['priority']).lower().removeprefix('p'))}
                          if request.command == 'priority' else {'title': d.validate_title(' '.join(request.destination))})
                updated = replace(item, **kwargs)
                if updated == item:
                    raise d.DomainError(f'unchanged {request.command}: ' + d.scalar_title(str(next(iter(kwargs.values())))))
                d.validate_sibling_uniqueness(({**snapshot.items, item.id: updated}).values(), snapshot.items.values())
                d.validate(replace(snapshot, items={**snapshot.items, item.id: updated}), hidden)
                actions.append(_Action('update_task', item.id, item.title, kwargs, updated, offsets(snapshot, item.id)))
            else:
                proposal = propose(request, snapshot, item, now)
                if _same_item(item, proposal.item, snapshot.account.timezone) and not proposal.removals and not proposal.additions:
                    raise d.DomainError('unchanged attention, hiding and reminders (complete no-op)')
                validate_proposals(snapshot, [proposal], hidden)
                adding_hiding = proposal.item.waiting and not item.waiting
                kwargs = {}
                for name in ('attention', 'labels', 'description'):
                    old, new = getattr(item, name), getattr(proposal.item, name)
                    same = d.same_attention(old, d.attention_prediction(new, snapshot.account.timezone), snapshot.account.timezone) if name == 'attention' else old == new
                    if not same:
                        kwargs[name] = new
                if proposal.removals and not options.get('clear') and options.get('reminder') != ('clear',):
                    self.previews.append(p.render_reminder_replacement(snapshot, item,
                        proposal.removals, proposal.additions))
                for reminder in proposal.removals:
                    actions.append(_Action('delete_reminder', reminder.id, item.title))
                if kwargs:
                    actions.append(_Action('update_task', item.id, item.title, kwargs, proposal.item,
                        tuple(r.minutes for r in proposal.retained if r.type == 'relative')))
                self._reminders(actions, item.id, item.title, proposal.additions)
        return actions, adding_hiding

    @staticmethod
    def _temporary(items, suffix):
        key = 'capture-proposal-' + str(suffix)
        while key in items:
            key += '-new'
        return key

    @staticmethod
    def _reminders(actions, item_id, title, values, *, creating_owner=False):
        for reminder in values:
            kwargs = {'minutes': reminder.minutes} if reminder.type == 'relative' else {'due': reminder.due}
            actions.append(_Action('create_reminder', item_id, title, kwargs, creating_owner=creating_owner))

    def _run(self, actions, synchronized, hidden, now):
        snapshot = synchronized.snapshot
        selected_owners = dict(snapshot.items)
        selected_reminders = dict(snapshot.reminders)
        ids, outcomes, documents = {}, [], []
        failure = None
        status = 0
        for action in actions:
            target = ids.get(action.target, action.target)
            kwargs = dict(action.kwargs)
            if kwargs.get('parent_id') in ids:
                kwargs['parent_id'] = ids[kwargs['parent_id']]
            before = Current(snapshot, synchronized.state.sync_token, current_snapshot=synchronized.state.current_snapshot,
                waiting_label_ids=synchronized.state.waiting_label_ids, reminder_ids=synchronized.state.current_reminder_ids)
            old = snapshot.items.get(target) or selected_owners.get(target)
            receipt = None
            rendered = False
            try:
                method = getattr(self.gateway, action.method)
                if action.method == 'create_task':
                    receipt = method(**kwargs, before=before, known_owners=selected_owners, known_reminders=selected_reminders, start=synchronized.state.cursor)
                else:
                    receipt = method(target, **kwargs, before=before, known_owners=selected_owners, known_reminders=selected_reminders, start=synchronized.state.cursor)
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
                synchronized = (self.synchronizer.reconcile_accepted_locked() if action.method == 'provision_category'
                                else self.synchronizer.reconcile_accepted_locked(receipt))
                snapshot = synchronized.snapshot
                if action.method == 'create_task' and target in snapshot.items:
                    selected_owners[target] = snapshot.items[target]
                d.validate(snapshot, hidden)
                actual = (snapshot.categories.get(receipt.target_id) if action.method == 'provision_category'
                          else snapshot.reminders.get(receipt.target_id) if action.method in ('create_reminder', 'delete_reminder')
                          else snapshot.items.get(target))
                if action.expected is not None:
                    expected = action.expected
                    if actual is None:
                        issues.append('accepted item is absent from reconciled state')
                    else:
                        creating = action.method == 'create_task'
                        if creating or 'attention' in kwargs:
                            attention = d.attention_prediction(expected.attention, snapshot.account.timezone)
                            valid_due = d.reconciles_attention(attention, actual.attention, snapshot.account.timezone)
                            if not valid_due:
                                issues.append(f'accepted attention differs: requested {attention!r}; actual {actual.attention!r}')
                        if any(getattr(expected, name) != getattr(actual, name)
                               for name in ('title', 'priority', 'labels', 'description')
                               if creating or name in kwargs):
                            issues.append('accepted scalar state differs from proposed title/priority/hiding/reason')
                        if creating and (actual.parent_id != ids.get(expected.parent_id, expected.parent_id)
                                or actual.category_id != expected.category_id):
                            issues.append('accepted item has unexpected parent/category')
                reminder_issue_start = len(issues)
                if action.method == 'create_reminder':
                    if actual is None or actual.item_id != target:
                        issues.append('accepted reminder differs from reconciled owner')
                    elif 'minutes' in kwargs:
                        if actual.type != 'relative' or actual.minutes != kwargs['minutes']:
                            issues.append('accepted reminder differs from reconciled offset')
                    elif actual.type != 'absolute' or not actual.due.exact or not d.reconciles_attention(d.attention_prediction(kwargs['due'], snapshot.account.timezone), actual.due, snapshot.account.timezone):
                        from todo_lib.domain.reminder_context import safe
                        requested = due_arguments(kwargs['due'])
                        summary = ', '.join(k + '=' + safe(requested[k])
                            for k in ('date', 'timezone', 'string') if k in requested)
                        issues.append('accepted absolute reminder differs from requested exact schedule: '
                            f'requested {summary}; account timezone {safe(snapshot.account.timezone)}')
                elif action.method == 'delete_reminder' and target in snapshot.reminders:
                    issues.append('accepted reminder deletion remains in reconciled state')
                elif action.method == 'complete' and (actual is None or not actual.completed):
                    issues.append('accepted ordinary completion is absent from reconciled lifecycle state')
                if action.method == 'provision_category':
                    if actual is None or (actual.name, actual.parent_id) != (kwargs['name'], target):
                        issues.append('accepted category differs from reconciled name/parent')
                if action.method in ('create_reminder', 'delete_reminder'):
                    from todo_lib.domain.reminder_context import context, ReminderDiagnostic
                    value = actual or before.snapshot.reminders.get(receipt.target_id)
                    if value is None:
                        value = dict(receipt.operation.args, id=receipt.target_id)
                    detail = context(value, {**before.snapshot.items, **snapshot.items}, snapshot.categories,
                        cached=actual is None and action.method == 'delete_reminder')
                    issues[reminder_issue_start:] = [ReminderDiagnostic(issue + ' [' + detail + ']')
                                                     for issue in issues[reminder_issue_start:]]
                outcomes[-1] = replace(outcomes[-1], actual=actual, issues=tuple(issues))
                if not issues:
                    documents.append(self._document(action, old, actual, snapshot, now, before.snapshot))
                rendered = True
                if issues:
                    from todo_lib.domain.reminder_context import repair_guidance
                    failure = '; '.join(issues) + '. ' + repair_guidance(issues)
                    status = 1
                    break
            except (SyncError, SyncInterrupted, d.DomainError, LocalError, HTTPFailure, OSError, KeyboardInterrupt) as error:
                failure = error
                status = 130 if isinstance(error, KeyboardInterrupt) else 1
                if receipt is None:
                    # Only the gateway's explicit pre-dispatch refusal proves
                    # that this operation was never submitted. Other failures
                    # without a receipt remain conservatively unknown.
                    outcome = 'unattempted' if isinstance(error, _UnsubmittedOperation) else 'unknown'
                    outcomes.append(OperationOutcome(action.method, action.title, outcome, target,
                        issues=(str(error),)))
                elif receipt.accepted:
                    if not rendered and not receipt.issues and receipt.actual is not None and receipt.after is not None:
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
            lines = [f"{labels.get(o.outcome, o.outcome.capitalize())}: {o.operation.replace('_', ' ')} {d.scalar_title(o.title)}"
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
            if action.method == 'create_reminder' and action.creating_owner:
                return p.document('  Reminders: ' + reminder_values(snapshot, owner.id))
            return p.render_mutation(snapshot, owner, changes=(('Reminders',
                reminder_values(before_snapshot, owner.id), reminder_values(snapshot, owner.id)),))
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
                   ('Hiding', ('inactive' if old.waiting and old.attention is None else old.waiting), ('inactive' if actual.waiting and actual.attention is None else actual.waiting)),
                   ('Reason', d.item_description(old)[1], d.item_description(actual)[1])]
        zone = snapshot.account.timezone
        if not d.same_attention(old.attention, actual.attention, zone):
            previous_due = p.actual_due(old.attention, zone, schedule_zone=True) if old.attention else None
            actual_due = p.actual_due(actual.attention, zone, schedule_zone=True) if actual.attention else None
            if previous_due == actual_due:
                # Whole-second display must not erase a real explicit fractional change.
                previous_due = due_arguments(old.attention)['date']
                actual_due = due_arguments(actual.attention)['date']
            changes.append(('Due', previous_due, actual_due))
        document = p.render_mutation(snapshot, actual, changes=changes)
        if not document.stdout and 'attention' in action.kwargs:
            document = p.document(f'Accepted scheduling for {actual.role}: {d.scalar_title(actual.title)}\n'
                                  '  Due: ' + p.actual_due(actual.attention, zone, schedule_zone=True))
        extra = []
        if action.retained is not None and reminder_values(snapshot, actual.id):
            extra.append('  Reminders retained: ' + reminder_values(snapshot, actual.id))
        if old.waiting and not actual.waiting and d.visibility(snapshot, actual.id, now).ancestor_hidden:
            extra.append('  Still hidden by an ancestor policy.')
        return p.render_receipts((document, p.document('\n'.join(extra))))


def execute(request, synchronizer, **kwargs):
    delivery = kwargs.pop('deliver', False)
    return CaptureWorkflow(synchronizer, **kwargs).execute(request, deliver=delivery)
