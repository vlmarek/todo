"""Compatible pending occurrence provenance, kept with the occurrence itself."""
from dataclasses import dataclass
from todo_lib import domain as d


@dataclass(frozen=True)
class ObservedOccurrence(d.Occurrence):
    activity_id: str | None = None
    source_order: int = 0
    completed_ids: tuple[str, ...] = ()
    undo_ids: tuple[str, ...] = ()
    activity_backed: bool = False

    def __post_init__(self):
        if (self.activity_id is not None and not isinstance(self.activity_id, str)
                or type(self.source_order) is not int or self.source_order < 0
                or type(self.activity_backed) is not bool):
            raise ValueError('invalid occurrence activity provenance')
        for field in ('completed_ids', 'undo_ids'):
            values = getattr(self, field)
            if not isinstance(values, (tuple, list)) or any(not isinstance(v, str) or not v for v in values):
                raise ValueError('invalid occurrence source identities')
            object.__setattr__(self, field, tuple(values))
