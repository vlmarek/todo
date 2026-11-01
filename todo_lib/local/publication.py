"""Observe publication facts without rollback or workflow recovery policy."""
from dataclasses import dataclass

from .safety import LocalError, read_bytes, regular


DESTINATIONS = ('cache.json', 'history.json', 'binding.json')


def destination_bytes(root, names):
    result = {}
    for name in names:
        try:
            path = root / name
            result[name] = read_bytes(path) if regular(path, missing=True) else None
        except (LocalError, OSError):
            # A fresh marker on each observation makes unknown bytes unequal.
            result[name] = object()
    return result


@dataclass(frozen=True)
class PublicationFacts:
    changed_destinations: tuple[str, ...]
    required_state_usable: bool
    saved_snapshot_available: bool

    @property
    def started(self):
        return bool(self.changed_destinations)


class PublicationObserver:
    def __init__(self, store, names=DESTINATIONS):
        self.store, self.names, self.before = store, tuple(names), None

    def capture(self):
        self.before = destination_bytes(self.store.root, self.names)

    def changed_destinations(self):
        if self.before is None:
            return ()
        try:
            after = destination_bytes(self.store.root, self.names)
            return tuple(name for name, content in self.before.items() if after[name] != content)
        except (Exception, KeyboardInterrupt):
            # Diagnostics cannot erase the original failure or prove preservation.
            return self.names

    @property
    def started(self):
        return bool(self.changed_destinations())

    def failure_facts(self, *, preflight=None):
        def usable(require_cache):
            try:
                if preflight is not None:
                    preflight()
                self.store.load_consistent_state(require_cache=require_cache)
                return True
            except (Exception, KeyboardInterrupt):
                return False
        return PublicationFacts(self.changed_destinations(), usable(False), usable(True))
