"""Terminal setup and binding-last initialization.

All remote reads use the current adapter's Sync contract. Discovery responses are
transient: replaying them through retrieve applies the same managed mapping as a
normal refresh, without a second HTTP request or any history endpoint. Only
missing ancestors are supplied from validated pending context; active omission
is never evidence of deletion. No local recovery or remote rollback is implicit.
"""
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import configparser
import io
import os
from pathlib import Path
import stat
import sys

from todo_lib import domain as d
from todo_lib.adapter import current
from todo_lib.adapter.commands import Gateway, Operation, Outcome, _proof
from todo_lib.adapter.transport import Transport, HTTPFailure
from todo_lib.local import (StateStore, LocalError, ConfigState, History,
    check_paths, create_directory, wizard_mode_repairs, repair_wizard_modes,
    inspect_config, load_config, parse_config, write_config, resolve_credentials,
    exclusive_lock, empty_history, merge_history, prepare_candidates)
from todo_lib.local.safety import regular, read_bytes
from todo_lib.syntax.input import prompt, interactive, InputError, Cancelled, Interrupted


FRESH_START = ('For an explicit manual fresh start: stop todo processes, optionally back up wanted data, '
    'delete the entire ~/.todo directory and run todo init. This discards local configuration, binding, '
    'cache, pending history and report cursor, can lose unreported observations, and creates a new '
    'initial report boundary. Remote Todoist data is unchanged.')


@dataclass(frozen=True)
class Provision:
    kind: str
    name: str
    outcome: str
    target_id: str | None = None


@dataclass(frozen=True)
class InitResult:
    state: object
    config_path: Path
    config_saved: bool
    provisions: tuple[Provision, ...]
    message: str


class InitError(LocalError):
    status = 1

    def __init__(self, phase, cause, *, config_path=None, config_saved=False,
                 provisions=(), publication_started=False, local_changes=(), status=1):
        self.phase, self.status = phase, status
        self.config_saved, self.config_path = config_saved, config_path
        self.provisions = tuple(provisions)
        self.publication_started = publication_started
        self.local_changes = tuple(local_changes)
        message = f'{phase} failed: {cause}. Initialization did not succeed.'
        if config_saved:
            message += f' Configuration was saved at {config_path}; a normal rerun uses that configuration.'
        if self.local_changes:
            message += ' Local changes already made: ' + '; '.join(self.local_changes) + '.'
        for p in self.provisions:
            message += f' Remote {p.kind} {p.name!r}: {p.outcome}.'
        if self.provisions:
            message += ' Do not replay mutations to repair local files; an explicit init rerun rediscovers accepted creations.'
        if publication_started:
            message += (' Local files may be partially published and the saved snapshot may be unusable; '
                        'new observations may not all be saved. Preserve available bytes and restore a consistent set. ')
            message += FRESH_START
        elif phase == 'local validation':
            message += ' Repair the identified paths/state or restore a consistent set before retrying. '
            message += FRESH_START
        elif phase in ('preflight', 'post-provision validation'):
            message += ' Invalid remote fields or managed invariants require correction before rerunning.'
        if not publication_started:
            message += ' No snapshot destination was replaced; previous protected snapshot files were preserved.'
        super().__init__(message)


class _Replay:
    def __init__(self, responses):
        self.responses = iter(responses)

    def request(self, *args, **kwargs):
        return deepcopy(next(self.responses))


class _Receipts:
    """Keep command proof even if reconciliation is interrupted after acceptance."""
    def __init__(self, transport):
        self.transport, self.responses = transport, []

    def request(self, *args, **kwargs):
        result = self.transport.request(*args, **kwargs)
        if isinstance(result, dict):
            self.responses.append(result)
        return result


@dataclass
class _Catalogue:
    responses: tuple
    raw: dict
    account: d.Account
    display: str

    @property
    def projects(self):
        return {k: current._project(v) for k, v in self.raw['projects'].items()
                if v.get('is_deleted') is not True}


def _discover(transport, binding=None):
    """Full plus exactly one freshness read, including metadata validation."""
    first, token, full = current._read(transport, '*')
    if not full:
        raise d.DomainError('requested full Sync returned a delta')
    raw = {name: {} for name in current.RESOURCE_TYPES[2:]}
    current._merge(raw, first, True)
    user = current._required(first, 'user')
    limits = current._required(first, 'user_plan_limits')
    uid = current._id(current._required(user, 'id'), 'user.id')
    b = d.Binding(binding.account_id if binding else uid, binding.root_id if binding else 'discovery')
    account = current._account(user, limits, b)
    fresh, _, full = current._read(transport, token)
    if full:
        raise d.DomainError('freshness Sync returned another full response')
    current._merge(raw, fresh, False)
    user, limits = fresh.get('user', user), fresh.get('user_plan_limits', limits)
    account = current._account(user, limits, b)
    for value in raw['labels'].values():
        deleted = current._bool(current._required(value, 'is_deleted'), 'label.is_deleted')
        if not deleted:
            d.validate_title(current._required(value, 'name'))
    display = user.get('full_name') or user.get('email') or account.id
    if not isinstance(display, str):
        raise d.DomainError('user display must be text')
    return _Catalogue((first, fresh), raw, account, display)


def _root(catalogue, config, binding=None, selected=None):
    projects = catalogue.projects
    if binding is not None:
        root = projects.get(binding.root_id)
        if root is None:
            raise d.DomainError('bound root disappeared; a different root is not authorized')
        # Configuration names can outlive a rename, including after another
        # project takes the old name. Only an explicit identity selection can
        # conflict with the authoritative binding.
        if selected is not None and selected != root.id:
            raise d.DomainError('configured root differs from binding; full-directory fresh start required')
    else:
        matches = [p for p in projects.values()
                   if p.parent_id is None and not p.archived and p.name == config.project]
        if len(matches) > 1:
            raise d.DomainError('configured root name is ambiguous')
        root = matches[0] if matches else None
        if selected is not None and (root is None or root.id != selected):
            raise d.DomainError('selected root identity differs from configured root')
    if root is not None:
        d.bind_root(catalogue.account.id, [root], root.name)
    return root


def _timestamp(value, field, kind):
    try:
        return current._timestamp(value, field)
    except d.DomainError as error:
        raise d.DomainError(f'{kind} {value["id"]}.{field}: expected an aware RFC3339 timestamp or null; {error}') from None


def _pending(state):
    """Cache context can still be required even when absent from pending history."""
    history, cached = state.history, state.snapshot
    if cached is None:
        return history
    items = {**history.snapshot.items, **cached.items}
    comments = {**history.snapshot.comments, **cached.comments}
    reminders = {**history.snapshot.reminders, **cached.reminders}
    occurrences = {**history.snapshot.occurrences, **cached.occurrences}
    occurrences = {k: o for k, o in occurrences.items()
                   if items[o.item_id].completed or items[o.item_id].recurring}
    return replace(history, snapshot=d.validate(replace(cached, items=items,
        comments=comments, reminders=reminders, occurrences=occurrences)))


def _scope(catalogue, root, prior=None):
    # Validate stable bound IDs against the complete catalogue before filtering
    # current children or retiring history. A moved bound category is invalid;
    # an absent category containing known work cannot be silently replaced.
    binding = prior.binding if prior else d.Binding(catalogue.account.id, root.id)
    root, categories, b = current._projects(catalogue.raw, binding, prior.items if prior else {})
    # Also validate category case collisions before provisioning missing names.
    d.validate(d.Snapshot(b, catalogue.account, root, categories, {}))
    return categories


def _observe(catalogue, root, history, hidden, now):
    """Validate live state and join this read to pending history immediately."""
    old = history.snapshot if history else None
    categories = _scope(catalogue, root, old)
    raw = catalogue.raw
    removed = set()
    if old:
        for identity, item in old.items.items():
            value = raw['items'].get(identity)
            if ((value is None and item.category_id not in categories) or
                (value is not None and (value.get('is_deleted') is True or value.get('project_id') not in categories))):
                removed.add(identity)
    for value in raw['items'].values():
        if value.get('is_deleted') is not True and value.get('project_id') in categories:
            for field in ('added_at', 'completed_at'):
                _timestamp(value, field, 'item')
    # Explicit current promotion/move wins over an old parent association.
    parents = {k: v.parent_id for k, v in old.items.items()} if old else {}
    parents.update({k: v.get('parent_id') for k, v in raw['items'].items()
                    if v.get('is_deleted') is not True and v.get('project_id') in categories})
    while True:
        more = removed | {k for k, parent in parents.items() if parent in removed}
        if more == removed:
            break
        removed = more
    # Full live snapshots can omit known ancestors. Supply only the necessary
    # validated context, not every pending item, so the cache stays current.
    additions = {}
    if old:
        seed = current._seed(old)['items']
        def ancestor(identity):
            if identity is None or identity in raw['items'] or identity in additions or identity in removed:
                return
            item = old.items.get(identity)
            if item is not None and item.category_id in categories:
                additions[identity] = seed[identity]
                ancestor(item.parent_id)
        for value in raw['items'].values():
            if value.get('is_deleted') is not True and value.get('project_id') in categories:
                ancestor(value.get('parent_id'))
    responses = deepcopy(catalogue.responses)
    responses[0]['items'] = responses[0]['items'] + list(additions.values())
    binding = old.binding if old else d.Binding(catalogue.account.id, root.id)
    live = current.retrieve(_Replay(responses), binding, prior=old, replace=True,
                            hidden_names=hidden)
    snapshot = live.snapshot
    if history is None:
        history = empty_history(snapshot)
    # Rebase retained context to current account/scope authority, including the
    # original floating wall time under an authenticated timezone change.
    retained = {}
    for identity, item in history.snapshot.items.items():
        if identity in removed:
            continue
        if item.attention is not None and item.attention.kind == 'floating':
            item = replace(item, attention=d.resolve_remote_due(item.attention.raw_due, snapshot.account.timezone))
        retained[identity] = item
    retained.update(snapshot.items)
    comments = {k: c for k, c in history.snapshot.comments.items() if c.item_id in retained}
    removed_comments = set()
    for identity, value in raw['notes'].items():
        if value.get('is_deleted') is True:
            removed_comments.add(identity)
            comments.pop(identity, None)
            continue
        owner = current._id(current._required(value, 'item_id'), 'notes.item_id')
        if owner not in retained:
            removed_comments.add(identity)
            comments.pop(identity, None)
            continue  # discard unrelated unsupported data before own-field validation
        current._bool(current._required(value, 'is_deleted'), 'notes.is_deleted')
        if current._required(value, 'file_attachment') is not None:
            raise d.DomainError('managed comment attachments are unsupported')
        comments[identity] = d.Comment(identity, owner, current._required(value, 'content'),
                                       _timestamp(value, 'posted_at', 'note'))
    occurrences = {k: o for k, o in history.snapshot.occurrences.items()
                   if o.item_id in retained and (retained[o.item_id].completed or retained[o.item_id].recurring)}
    occurrences.update(snapshot.occurrences)
    reminders = {k: r for k, r in history.snapshot.reminders.items()
                 if r.item_id in retained and r.item_id not in snapshot.items}
    reminders.update(snapshot.reminders)
    joined = d.validate(replace(snapshot, items=retained, comments=comments,
                               reminders=reminders, occurrences=occurrences), hidden)
    # Both arguments to merge_history must already have complete ancestor context
    # and current timezone/scope; remove superseded lifecycle evidence explicitly.
    base = replace(history, snapshot=joined,
                   observations={k: v for k, v in history.observations.items() if k in retained})
    incoming = History(joined, {k: now for k in snapshot.items})
    pending = merge_history(base, incoming, removed_item_ids=removed,
                            removed_comment_ids=removed_comments)
    return live, pending


def _ini(project, categories, hidden, token=''):
    parser = configparser.ConfigParser(interpolation=None)
    parser['main'] = dict(project=project, default_sections=categories, hidden_from_now=hidden)
    parser['todoist'] = dict(token=token)
    output = io.StringIO()
    parser.write(output)
    content = output.getvalue().encode('utf-8')
    return content, parse_config(content)


def _validate_config_names(config):
    for field, names in (('project', (config.project,)),
                         ('default_sections', config.default_sections),
                         ('hidden_from_now', config.hidden_from_now)):
        for name in names:
            try:
                d.validate_title(name)
            except d.DomainError as error:
                raise LocalError(f'main.{field}: {error}') from None


class Initializer:
    """Dependency hooks are for controlled terminals/HTTP, never public options."""
    def __init__(self, transport=None, store=None, *, transport_factory=Transport,
                 clock=None, environ=None, stdin=None, stdout=None, stderr=None,
                 reader=None, hidden_reader=None):
        self.store = StateStore() if store is None else store
        self.transport, self.transport_factory = transport, transport_factory
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.environ = os.environ if environ is None else environ
        self.stdin = sys.stdin if stdin is None else stdin
        self.stdout = sys.stdout if stdout is None else stdout
        self.stderr = sys.stderr if stderr is None else stderr
        self.input = dict(stdin=self.stdin, stdout=self.stdout, stderr=self.stderr,
                          reader=reader, hidden_reader=hidden_reader)

    def _say(self, message):
        self.stdout.write(message + '\n')
        self.stdout.flush()

    def _ask(self, message, **kwargs):
        return prompt(message, **self.input, **kwargs)

    def _confirm(self, message):
        def answer(value):
            if value.lower() not in ('y', 'yes', 'n', 'no'):
                raise ValueError('Enter yes or no.')
            return value.lower() in ('y', 'yes')
        if not self._ask(message + ' [yes/no]: ', default=False, validate=answer):
            raise Cancelled('setup declined')

    def _local(self):
        check_paths(self.store.root)
        if regular(self.store.root / 'binding.json', missing=True):
            if regular(self.store.root / 'report-cursor', missing=True) is None:
                raise LocalError('missing report-cursor; use todo report --set-cursor to set an explicit boundary')
            return self.store.load_consistent_state(
                require_cache=regular(self.store.root / 'cache.json', missing=True) is not None)
        if any(regular(self.store.root / name, missing=True) is not None
               for name in ('cache.json', 'history.json', 'report-cursor')):
            raise LocalError('unbound partial initialization; preserve available bytes and restore a consistent set')
        return None

    def _wizard(self, credentials, transport, state):
        catalogue = _discover(transport, state.binding if state else None)
        roots = [p for p in catalogue.projects.values() if p.parent_id is None and
                 not (p.shared or p.workspace_id or p.archived or not p.personally_owned)]
        for number, p in enumerate(roots, 1):
            self._say(f'{number}. {p.name} (personal top-level project, choice {number})')
        self._say('Choose an existing root by number or enter a new root name. Suggested new name: Work.')
        def choose(value):
            if value.isascii() and value.isdecimal():
                n = int(value)
                if not 1 <= n <= len(roots):
                    raise ValueError('Choose a displayed number or enter a root name.')
                return roots[n-1].name, roots[n-1].id
            d.validate_title(value)
            if state:
                bound = catalogue.projects.get(state.binding.root_id)
                if value not in (state.binding.root_name, bound.name if bound else None):
                    raise ValueError('Root differs from binding; a full-directory fresh start is required.')
            return value, None
        default = (state.binding.root_name, state.binding.root_id) if state else ('Work', None)
        while True:
            name, selected = self._ask('Root [Work]: ', default=default, validate=choose)
            provisional = _ini(name, 'engineer, manager, someday', '')[1]
            root = _root(catalogue, provisional, state.binding if state else None, selected)
            categories = _scope(catalogue, root, _pending(state).snapshot if state else None) if root else {}
            suggested = ', '.join(p.name for p in categories.values()) or 'engineer, manager, someday'
            self._say('Work categories are direct-child projects under the root, not Todoist sections.')
            sections = self._ask(f'Categories [{suggested}]: ', default=suggested)
            self._say('hidden_from_now is local policy, with exact-case category matching; it creates no categories.')
            hidden = self._ask('Hidden categories [someday] (enter - for empty): ', default='someday')
            hidden = '' if hidden == '-' else hidden
            try:
                content, config = _ini(name, sections, hidden,
                    credentials.token() if credentials.source == 'wizard' else '')
                _validate_config_names(config)
            except (LocalError, d.DomainError) as error:
                self.stderr.write(str(error) + '\n')
                continue
            existing = {p.name.casefold() for p in categories.values()}
            # Reused categories keep their remote spelling; typed aliases do not
            # become effective names for the exact-case hidden policy.
            names = {p.name for p in categories.values()} | {
                value for value in config.default_sections if value.casefold() not in existing}
            for value in config.hidden_from_now:
                if value not in names:
                    self._say(f'Hidden name {value!r} matches no exact-case category; it has no effect and creates nothing.')
            self._say(f'Proposed configuration at {self.store.root / "config"}:')
            self._say(f'Root: {name} ({"existing" if root else "proposed new"})')
            self._say('Configured categories: ' + ', '.join(config.default_sections))
            for category in categories.values():
                self._say(f'Category: {category.name} (existing)')
            for value in config.default_sections:
                if value.casefold() not in existing:
                    self._say(f'Category: {value} (proposed new)')
            waiting_exists = any(v.get('is_deleted') is False and v.get('name') == 'waiting'
                                 for v in catalogue.raw['labels'].values())
            self._say(f'Label: waiting ({"existing" if waiting_exists else "proposed new"})')
            self._say('Hidden: ' + (', '.join(config.hidden_from_now) or '(empty)'))
            self._say('Credential source: ' + credentials.source + ' (token hidden).')
            self._confirm('Save configuration and continue Todoist initialization?')
            if inspect_config(self.store.root) == ConfigState.POPULATED:
                raise LocalError('config became populated during setup; refusing to overwrite')
            self._saving_config = True
            try:
                write_config(self.store.root, content)
            finally:
                # A signal can arrive after replacement but before the writer
                # returns. Report the actual complete saved config separately.
                if regular(self.store.root / 'config', missing=True):
                    self._config_saved = read_bytes(self.store.root / 'config') == content
            self._saving_config = False
            return config, catalogue, selected

    def run(self):
        root = self.store.root
        phase, saved, started = 'local validation', False, False
        provisions, changes = [], []
        credentials = None
        self._config_saved = self._saving_config = False
        try:
            # lstat only: populated config never enters the repair exception.
            try:
                directory_info = root.lstat()
            except FileNotFoundError:
                directory_info = None
            if directory_info is not None and (not stat.S_ISDIR(directory_info.st_mode)
                                               or directory_info.st_uid != os.getuid()):
                raise LocalError(f'{root}: requires an owned real directory, not a symlink')
            try:
                info = (root / 'config').lstat()
            except FileNotFoundError:
                info = None
            wizard = info is None or (stat.S_ISREG(info.st_mode) and info.st_size == 0)
            if wizard:
                if not interactive(self.stdin, self.stdout):
                    raise InputError('todo init setup must be rerun in a terminal (stdin and stdout)')
                repairs = wizard_mode_repairs(root)
                if repairs:
                    for path, old, required in repairs:
                        self._say(f'{path}: current mode {old:04o}; required mode {required:04o}')
                    self._confirm('Repair only these setup permissions?')
                    repair_wizard_modes(root, confirmed=True)
                    changes.extend(f'repaired mode of {path} to {required:04o}' for path, _, required in repairs)
                missing = not root.exists()
                create_directory(root)
                if missing:
                    changes.append(f'created protected directory {root}')
            else:
                check_paths(root)
            with exclusive_lock('init', root):
                state = self._local()
                if wizard:
                    phase = 'terminal setup'
                    if self.environ.get('TODOIST_TOKEN', ''):
                        credentials = resolve_credentials(environ=self.environ)
                    else:
                        self._say('A Todoist personal API token is required; input will be hidden.')
                        def token(value):
                            if not value or any(c.isspace() for c in value):
                                raise ValueError('nonempty token required')
                            return value
                        secret = self._ask('Personal API token: ', hidden=True, validate=token, cancel=())
                        credentials = resolve_credentials(environ=self.environ, wizard_token=secret)
                    transport = self.transport or self.transport_factory(credentials.token())
                    config, catalogue, selected = self._wizard(credentials, transport, state)
                    saved = True
                else:
                    config = load_config(root)
                    _validate_config_names(config)
                    credentials = config.resolve_credentials(self.environ)
                    transport = self.transport or self.transport_factory(credentials.token())
                    catalogue = selected = None
                phase = 'preflight'
                if catalogue is None:
                    catalogue = _discover(transport, state.binding if state else None)
                target = _root(catalogue, config, state.binding if state else None, selected)
                observation_time = self.clock()
                d.instant_key(observation_time)
                history = _pending(state) if state else None
                if target:
                    live, history = _observe(catalogue, target, history, config.hidden_from_now, observation_time)
                categories = live.snapshot.categories if target else {}
                plan = []
                if target is None:
                    plan.append(('root', config.project))
                for name in config.default_sections:
                    if not any(p.name.casefold() == name.casefold() for p in categories.values()):
                        plan.append(('category', name))
                labels = catalogue.raw['labels'].values()
                if not any(v.get('is_deleted') is False and v.get('name') == 'waiting' for v in labels):
                    plan.append(('label', 'waiting'))
                provisions = [Provision(kind, name, 'unattempted') for kind, name in plan]
                # Validate every authorized operation before the first mutation.
                for kind, name in plan:
                    d.validate_title(name)
                phase = 'provisioning'
                for index, (kind, name) in enumerate(plan):
                    args = {'name': name}
                    if kind != 'label':
                        args['parent_id'] = None if kind == 'root' else target.id
                    operation = Operation('label_add' if kind == 'label' else 'project_add', args)
                    provisions[index] = Provision(kind, name, 'unknown')
                    receipts = _Receipts(transport)
                    try:
                        result = Gateway(receipts).execute(operation)
                    except KeyboardInterrupt:
                        outcome, identity = _proof(operation, receipts.responses)
                        provisions[index] = Provision(kind, name, outcome.value, identity)
                        raise
                    provisions[index] = Provision(kind, name, result.outcome.value, result.target_id)
                    if result.outcome != Outcome.ACCEPTED or result.issues:
                        raise LocalError('; '.join(result.issues) or f'creation {result.outcome.value}')
                    if kind == 'root':
                        target = result.actual
                phase = 'post-provision validation'
                after = _discover(transport, d.Binding(catalogue.account.id, target.id))
                # Once chosen/created, stable identity cannot change during init.
                actual = after.projects.get(target.id)
                if actual is None:
                    raise d.DomainError('selected root disappeared after provisioning')
                now = self.clock()  # one binding instant, after the authoritative read
                d.instant_key(now)
                live, history = _observe(after, actual, history, config.hidden_from_now, now)
                for name in config.default_sections:
                    if not any(p.name.casefold() == name.casefold() for p in live.snapshot.categories.values()):
                        raise d.DomainError('configured category missing after provisioning')
                if not any(v.get('is_deleted') is False and v.get('name') == 'waiting'
                           for v in after.raw['labels'].values()):
                    raise d.DomainError('waiting label missing after provisioning')
                phase = 'candidate preparation'
                candidates = prepare_candidates(live.snapshot, history, account_display=after.display,
                    sync_token=live.sync_token, synced_at=now,
                    initial_cursor=None if state else now, hidden_names=config.hidden_from_now)
                phase = 'local publication'
                before = {name: read_bytes(root / name) if regular(root / name, missing=True) else None
                          for name in ('cache.json', 'history.json', 'report-cursor', 'binding.json')}
                try:
                    self.store.publish_snapshot(candidates)
                finally:
                    started = any((read_bytes(root / name) if regular(root / name, missing=True) else None) != value
                                  for name, value in before.items())
                state = self.store.load_consistent_state()
                message = (f'Configuration: {root / "config"}. Initialized {state.binding.root_name}; categories: '
                           f'{", ".join(state.binding.categories.values())}. Next: todo now')
                self._say(message)
                return InitResult(state, root / 'config', saved, tuple(provisions), message)
        except (LocalError, d.DomainError, HTTPFailure, InputError, OSError, ValueError, KeyboardInterrupt) as error:
            status = 130 if isinstance(error, (KeyboardInterrupt, Interrupted)) else 1
            cause = credentials.redact(error) if credentials else str(error)
            if self._saving_config:
                phase = 'configuration publication'
            raise InitError(phase, cause, config_path=root / 'config', config_saved=saved or self._config_saved,
                provisions=provisions, publication_started=started, local_changes=changes, status=status) from None


def initialize(transport=None, *, store=None, **kwargs):
    return Initializer(transport, store, **kwargs).run()
