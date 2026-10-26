"""Cache-first read commands and reusable, title-only selection scopes.

ReadWorkflow.execute accepts syntax.CommandRequest (or argv) and returns a
ReadResult. It performs no output unless delivery is requested or a terminal
chooser is needed. Local/sync errors propagate unchanged. Selection errors carry
status 1 and a complete document, so launchers can report them without guessing
whether a failed population load meant no match. Mutation callers may use the
pure candidate helpers and choose() with their already synchronized snapshot.
"""
from dataclasses import dataclass, replace
import json
import unicodedata

from todo_lib import domain as d
from todo_lib import presentation as p
from todo_lib.local import LocalError, load_config
from todo_lib.syntax import parse
from todo_lib.syntax.input import interactive, prompt


def _fold(text):
    return unicodedata.normalize('NFC', unicodedata.normalize('NFC', text).casefold())


def terms(query):
    """A string is one phrase; a sequence preserves parser argument boundaries."""
    return (query,) if isinstance(query, str) else tuple(query)


def matches(field, query):
    needles = tuple(_fold(term) for term in terms(query) if term)
    return bool(needles) and all(term in _fold(field) for term in needles)


def query_text(query):
    # JSON quoting preserves spaces, literal punctuation and argument boundaries.
    return ' '.join(json.dumps(term, ensure_ascii=False) for term in terms(query))


class SelectionError(Exception):
    status = 1

    def __init__(self, message, document=None):
        super().__init__(message)
        self.document = document or p.document(warnings='todo: ' + message)


class NoMatch(SelectionError):
    pass


class AmbiguityError(SelectionError):
    def __init__(self, query, candidates, document):
        self.candidates = tuple(candidates)
        super().__init__('multiple items match ' + query_text(query), document)


def _candidate_key(snapshot, item):
    return (snapshot.categories[item.category_id].name.lower(),
            tuple(a.title.lower() for a in d.ancestors(snapshot, item.id)),
            item.title.lower(), item.id)


def title_candidates(snapshot, query, *, target='item', parent_id=None):
    """Open titles only. parent_id restricts to immediate children by stable ID."""
    return tuple(sorted((item for item in snapshot.items.values()
        if not item.completed and (target == 'item' or item.role == target)
        and (parent_id is None or item.parent_id == parent_id)
        and matches(item.title, query)), key=lambda i: _candidate_key(snapshot, i)))


def move_destination_candidates(snapshot, query, *, kind='positional'):
    """Typed categories and open items; promotion is the explicit empty scope."""
    if kind == 'promotion':
        return ()
    categories = tuple(sorted((c for c in snapshot.categories.values()
                              if matches(c.name, query)), key=lambda c: (c.name.lower(), c.id)))
    if kind == 'category':
        return categories
    items = title_candidates(snapshot, query)
    if kind in ('parent', 'task', 'item'):
        return items  # --task is a parent destination, which may itself be a step.
    if kind != 'positional':
        raise ValueError('unknown move destination kind: ' + kind)
    return categories + items


def recent_candidates(snapshot, query, cursor, now, *, operation='reopen', target='item'):
    """Return exact lifecycle facts, including only the latest recurring undo."""
    if operation == 'reopen':
        population = d.recent_reopen_candidates(snapshot, cursor, now)
    elif operation == 'delete':
        population = d.completed_deletion_candidates(snapshot, cursor, now)
    else:
        raise ValueError('unknown lifecycle operation: ' + operation)
    return tuple(c for c in population if matches(snapshot.items[c.item_id].title, query)
                 and (target == 'item' or snapshot.items[c.item_id].role == target))


def deletion_candidates(snapshot, query, cursor, now, *, target='item'):
    """Ordinary open deletion plus bounded, currently completed nonrecurrence."""
    return title_candidates(snapshot, query, target=target) + recent_candidates(
        snapshot, query, cursor, now, operation='delete', target=target)


def choose(snapshot, query, candidates, now, *, streams=None, color=p.Color()):
    """Shared exact chooser. Return the original stable object, not display data."""
    candidates = tuple(candidates)
    if not candidates:
        raise NoMatch('no matching item for selector ' + query_text(query))
    if len(candidates) == 1:
        return candidates[0]
    streams = streams or p.OriginalStreams.current()
    displays = tuple(replace(snapshot.items[c.item_id], completed=True,
                            completed_at=c.completed_at)
                     if isinstance(c, d.LifecycleCandidate) else c for c in candidates)
    # One-term queries keep the template's unquoted heading. Multi-term headings
    # quote arguments separately to distinguish a phrase from several terms.
    heading = terms(query)[0] if len(terms(query)) == 1 else query_text(query)
    document = p.render_ambiguity(snapshot, heading, displays,
                                  d.instant_datetime(now), interactive=False, color=color)
    if not interactive(streams.stdin, streams.stdout):
        raise AmbiguityError(query, candidates, document)
    streams.stdout.write(document.stdout + '\n')
    streams.stdout.flush()

    def selection(answer):
        if answer == '':
            from todo_lib.syntax.input import Cancelled
            raise Cancelled('selection cancelled')
        if not answer.isascii() or not answer.isdecimal() or not 1 <= int(answer) <= len(candidates):
            raise ValueError(p.invalid_selection(len(candidates)).stdout.rstrip('\n'))
        return candidates[int(answer) - 1]

    return prompt(f'Select 1-{len(candidates)}, or q to cancel:\n',
                  stdin=streams.stdin, stdout=streams.stdout, stderr=streams.stderr,
                  validate=selection)


def select_title(snapshot, query, now, *, target='item', streams=None, color=p.Color()):
    return choose(snapshot, query, title_candidates(snapshot, query, target=target),
                  now, streams=streams, color=color)


def select_child(snapshot, parent_query, child_query, now, *, streams=None, color=p.Color()):
    """Resolve a task OR step parent before filtering its direct open children."""
    parent = select_title(snapshot, parent_query, now, streams=streams, color=color)
    return choose(snapshot, child_query,
                  title_candidates(snapshot, child_query, target='step', parent_id=parent.id),
                  now, streams=streams, color=color)


def combined_snapshot(result):
    """Merge compatible retained context once; current owner collections win."""
    current, history = result.snapshot, result.history.snapshot
    if current is None:
        raise LocalError('missing saved snapshot; use todo --refresh now')
    if current.binding != history.binding or current.account != history.account or current.categories != history.categories:
        raise LocalError('incompatible retained history; restore a consistent saved set')
    collections = {}
    for name in ('comments', 'reminders'):
        collections[name] = {k: v for k, v in getattr(history, name).items()
                             if v.item_id not in current.items}
        collections[name].update(getattr(current, name))
    return replace(current, items={**history.items, **current.items},
                   occurrences={**history.occurrences, **current.occurrences}, **collections)


def search_candidates(snapshot, query, *, all_items=False):
    comments = {}
    for comment in snapshot.comments.values():
        comments.setdefault(comment.item_id, []).append(comment.body)
    result = []
    for item in snapshot.items.values():
        if item.completed and not all_items:
            continue
        ordinary, reason = d.split_waiting(item.description)
        fields = (item.title, ordinary, reason or '', *comments.get(item.id, ()))
        if any(matches(field, query) for field in fields):
            result.append(item)
    return tuple(result)


@dataclass(frozen=True)
class ReadResult:
    document: p.Document
    snapshot: d.Snapshot
    now: object
    selected: object = None
    status: int = 0


class ReadWorkflow:
    def __init__(self, synchronizer, *, settings=None, streams=None):
        self.synchronizer = synchronizer
        self.settings = settings
        self.streams = streams

    def execute(self, request, *, deliver=False):
        if isinstance(request, (list, tuple)):
            request = parse(request)
        command = request.command
        if command not in ('now', 'waiting', 'someday', 'task', 'step', 'category', 'search', 'lookup', 'comment'):
            raise ValueError('not a read command: ' + command)
        if command == 'comment' and (request.groups or request.option('edit')):
            raise ValueError('comment mutation is not a read command')
        if request.option('clear-cache') and not request.option('refresh'):
            raise ValueError('--clear-cache requires --refresh')
        settings = self.settings or load_config(self.synchronizer.store.root)
        # Never catch a population-loading failure and reclassify it as no-match.
        result = (self.synchronizer.refresh(clear_cache=bool(request.option('clear-cache')))
                  if request.option('refresh') else self.synchronizer.read_local())
        snapshot = combined_snapshot(result)
        d.validate(snapshot, settings.hidden_from_now)
        now = d.instant_datetime(result.now)
        streams = self.streams or p.OriginalStreams.current()
        color = p.Color.for_stdout(streams.stdout, request.option('color', 'auto'), slots=settings.colors)
        selected = None
        if command == 'now':
            category = request.option('category')
            category_id = d.lookup_category(snapshot, category).id if category is not None else None
            document = p.render_now(snapshot, now, hidden_names=settings.hidden_from_now,
                                    all_items=bool(request.option('all')), category_id=category_id, color=color)
        elif command == 'waiting':
            document = p.render_waiting(snapshot, now, hidden_names=settings.hidden_from_now)
        elif command == 'someday':
            document = p.render_someday(snapshot, hidden_names=settings.hidden_from_now)
        elif command == 'category':
            document = p.render_categories(snapshot)
        elif command == 'search':
            all_items = bool(request.option('all'))
            completed = [i.completed_at for i in snapshot.items.values() if i.completed]
            completed.extend(o.completed_at for o in snapshot.occurrences.values() if not o.undone)
            document = p.render_search(snapshot, search_candidates(snapshot, request.selector, all_items=all_items),
                all_items=all_items, earliest_completion=min(completed, key=d.instant_key, default=None))
        else:
            target = command if command in ('task', 'step') else request.target
            if request.parent:
                selected = select_child(snapshot, request.parent, request.selector, now, streams=streams, color=color)
            else:
                selected = select_title(snapshot, request.selector, now, target=target, streams=streams, color=color)
            document = (p.render_comments(snapshot, selected) if command == 'comment'
                        else p.render_detail(snapshot, selected, now, color=color))
        if result.warnings:
            document = p.document(document.stdout, '\n'.join(filter(None,
                (document.stderr, *('todo: ' + w for w in result.warnings)))))
        if deliver:
            view_kind = selected.role if command == 'lookup' else command
            p.deliver(document, settings, streams, view_kind=view_kind)
        return ReadResult(document, snapshot, result.now, selected)


def execute(request, synchronizer, **kwargs):
    """Convenience public entry point; see ReadWorkflow.execute."""
    delivery = kwargs.pop('deliver', False)
    return ReadWorkflow(synchronizer, **kwargs).execute(request, deliver=delivery)
