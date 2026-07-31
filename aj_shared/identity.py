"""Framework-neutral identity defaults and claim normalization."""

import json
from typing import Any


DEFAULT_SESSION_TTL_SECONDS = 20 * 60


def normalize_tags(raw: Any) -> list[Any]:
    """Return a validated tag list; malformed or wrong-shaped claims fail closed."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return []
    return raw if isinstance(raw, list) else []


def identity_has_tag(user: Any, tag: str) -> bool:
    """Check a functional tag without accepting mapping or tuple membership."""
    if not isinstance(user, dict):
        return False
    return tag in normalize_tags(user.get("tags"))
