"""Supported shared offline domain API.

Model types, traversal, validation, visibility, urgency and bounded lifecycle
predicates are exported here. Time parsers consume one original scalar, one aware
now and the authoritative account zone; they perform no CLI parsing or I/O.
See individual docstrings for ordering, absence and error contracts.
"""
from .errors import DomainError
from .text import validate_title, validate_body, title_key, split_waiting, with_waiting_reason
from .time import (
    Attention, account_timezone, require_aware, resolve_wall, exact_attention,
    parse_attention, parse_boundary, parse_reminder, validate_reminder_offsets,
    resolve_remote_due, attention_order, same_attention, reconciles_attention,
    retain_recurrence,
)
from .model import (
    Account, Capabilities, Binding, Project, Category, Item, Comment, Reminder,
    Occurrence, Snapshot, Visibility, Urgency, LifecycleCandidate,
    validate, hierarchy_depths, ancestors, root_task, ordered_siblings, subtree,
    subtree_depths, validate_sibling_uniqueness, lookup_category, bind_root,
    enroll_categories, effective_priority, creation_priority, effective_attention,
    visibility, validate_hiding, validate_hiding_enable, urgency, now_queue,
    validate_move_depth, completion_order, recent_reopen_candidates,
    completed_deletion_candidates, reopen_chain, require_editable,
)

__all__ = (
    'DomainError', 'validate_title', 'validate_body', 'title_key', 'split_waiting',
    'with_waiting_reason', 'Attention', 'account_timezone', 'require_aware',
    'resolve_wall', 'exact_attention', 'parse_attention', 'parse_boundary',
    'parse_reminder', 'validate_reminder_offsets', 'resolve_remote_due',
    'attention_order', 'same_attention', 'reconciles_attention', 'retain_recurrence',
    'Account', 'Capabilities', 'Binding', 'Project', 'Category', 'Item', 'Comment',
    'Reminder', 'Occurrence', 'Snapshot', 'Visibility', 'Urgency',
    'LifecycleCandidate', 'validate', 'hierarchy_depths', 'ancestors', 'root_task',
    'ordered_siblings', 'subtree', 'subtree_depths', 'validate_sibling_uniqueness',
    'lookup_category', 'bind_root', 'enroll_categories', 'effective_priority',
    'creation_priority', 'effective_attention', 'visibility', 'validate_hiding',
    'validate_hiding_enable', 'urgency', 'now_queue', 'validate_move_depth',
    'completion_order', 'recent_reopen_candidates', 'completed_deletion_candidates',
    'reopen_chain', 'require_editable',
)

from .time import ExactInstant, instant_from_wire, instant_key, instant_text, instant_datetime

__all__ += ("ExactInstant", "instant_from_wire", "instant_key", "instant_text", "instant_datetime")

from .text import incoming_text, scalar_title, item_description, convention_diagnostic
__all__ += ("incoming_text", "scalar_title", "item_description", "convention_diagnostic")
