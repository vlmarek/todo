"""Safe, field-oriented domain diagnostics."""


class DomainError(ValueError):
    """Invalid managed value; messages identify invariants, not remote payloads."""
