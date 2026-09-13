"""Shared, fail-closed identity helpers for framework adapters."""

from __future__ import annotations

import json
from typing import Any, Mapping


# The local session cache is intentionally bounded because an application cannot
# observe a sign-out from HQ's separate cookie domain.
DEFAULT_SESSION_TTL_SECONDS = 20 * 60


def identity_has_tag(user: Mapping[str, Any] | None, tag: str) -> bool:
    """Return whether a validated user has *tag*, rejecting malformed claims.

    HQ may supply tags as a list or as a JSON-encoded list for compatibility
    with existing consumers. Every other shape fails closed; in particular,
    mappings and tuples must not become authorization grants through Python's
    membership rules.
    """
    if not isinstance(user, Mapping):
        return False

    tags = user.get("tags", [])
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except (TypeError, json.JSONDecodeError):
            return False
    return isinstance(tags, list) and tag in tags


def path_is_public(path, public_paths):
    """Only a trailing slash explicitly grants a directory subtree."""
    return any(path.startswith(p) if p.endswith('/') else path == p for p in public_paths)


def session_is_fresh(cached_at, ttl, now):
    try:
        return 0 <= now - float(cached_at) < ttl
    except (TypeError, ValueError):
        return False
