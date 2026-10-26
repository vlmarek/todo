"""Text validation and the single canonical optional waiting-reason encoding.

Validation returns edge-normalized user input. Snapshot validation never rewrites
stored text. Unicode normalization is used only for matching.
"""
import unicodedata
from .errors import DomainError

START = '[todo waiting]'
END = '[/todo waiting]'


def _controls(value: str, multiline: bool) -> None:
    if not isinstance(value, str):
        raise DomainError('text must be a string')
    for char in value:
        n = ord(char)
        if (n < 32 or 127 <= n <= 159) and not (multiline and char in '\n\t'):
            raise DomainError('text contains a forbidden control character')


def validate_title(value: str) -> str:
    """Trim a nonempty single-line title, rejecting all C0/C1 controls."""
    _controls(value, False)
    if not value.strip():
        raise DomainError('title must be nonempty')
    return value.strip()


def validate_body(value: str) -> str:
    """Trim nonempty multiline user text; only LF and tab controls are allowed."""
    _controls(value, True)
    if not value.strip():
        raise DomainError('body must be nonempty')
    return value.strip()


def title_key(value: str) -> str:
    """Canonical Unicode/case-insensitive comparison, without changing storage."""
    return unicodedata.normalize('NFC', unicodedata.normalize('NFC', value.strip()).casefold())


def split_waiting(description: str) -> tuple[str, str | None]:
    """Return ordinary text and optional reason, rejecting noncanonical blocks.

    Empty description is valid. Exact marker *lines* are reserved; ordinary text
    containing a marker as part of a longer line is not a block.
    """
    _controls(description, True)
    lines = description.split('\n')
    starts = [i for i, line in enumerate(lines) if line == START]
    ends = [i for i, line in enumerate(lines) if line == END]
    if not starts and not ends:
        if description and not description.strip():
            raise DomainError('description must be empty or nonempty text')
        return description, None
    if len(starts) != 1 or len(ends) != 1:
        raise DomainError('waiting block must have exactly one marker pair')
    a, b = starts[0], ends[0]
    if b != len(lines) - 1 or b <= a + 1:
        raise DomainError('waiting block must be nonempty and trailing')
    reason = '\n'.join(lines[a + 1:b])
    if validate_body(reason) != reason:
        raise DomainError('waiting reason has noncanonical edge whitespace')
    ordinary = '\n'.join(lines[:a])
    if a:
        if a < 2 or lines[a - 1] != '' or lines[a - 2] == '':
            raise DomainError('waiting block requires one blank separator line')
        ordinary = '\n'.join(lines[:a - 1])
        if not ordinary.strip():
            raise DomainError('waiting block has empty ordinary text')
    return ordinary, reason


def with_waiting_reason(description: str, reason: str | None) -> str:
    """Replace/remove the optional reason; removal preserves ordinary text.

    Adding a block canonicalizes trailing LF separators to exactly one blank
    line. It never repairs an already malformed block.
    """
    ordinary, _ = split_waiting(description)
    if reason is None:
        return ordinary
    reason = validate_body(reason)
    if any(line in (START, END) for line in reason.split('\n')):
        raise DomainError('waiting reason contains a reserved marker line')
    ordinary = ordinary.rstrip('\n')
    return (ordinary + '\n\n' if ordinary else '') + START + '\n' + reason + '\n' + END
