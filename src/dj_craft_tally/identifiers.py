"""Identifier factories with compatibility across supported Python versions."""

import uuid
from importlib import import_module


def uuid7() -> uuid.UUID:
    """Return a time-sortable UUIDv7 on every supported Python version."""
    stdlib_uuid7 = getattr(uuid, "uuid7", None)
    if stdlib_uuid7 is not None:
        return stdlib_uuid7()
    return import_module("uuid6").uuid7()  # pragma: no cover
