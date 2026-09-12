"""Strict, additive request-status wire contract; no service or adapter logic."""

import re
from datetime import datetime
from typing import List, Literal, TypedDict, cast

RequestOutcome = Literal[
    "loading", "ok", "empty", "denied", "failed", "unavailable", "queued", "unknown"
]
DataQualifier = Literal["stale", "partial", "cached"]
REQUEST_OUTCOMES = ("loading", "ok", "empty", "denied", "failed", "unavailable", "queued", "unknown")
DATA_QUALIFIERS = ("stale", "partial", "cached")


class _RequiredStatus(TypedDict):
    status: RequestOutcome
    qualifiers: List[DataQualifier]
    retryable: bool


class StatusPayload(_RequiredStatus, total=False):
    as_of: str
    missing: List[str]
    retry_after: int


class StatusValidationError(ValueError):
    """Input does not satisfy the status wire contract; no fallback is emitted."""


_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
)
_FIELDS = {"status", "qualifiers", "retryable", "as_of", "missing", "retry_after"}


def validate_status(value: object) -> StatusPayload:
    """Validate a decoded JSON object and return an independent copy.

    Reject wrong types, unknown fields/identifiers and inconsistent metadata.
    Never normalize legacy values, infer meaning, or substitute a status.
    """
    if type(value) is not dict:
        raise StatusValidationError("status payload must be a JSON object")
    if set(value) - _FIELDS:
        raise StatusValidationError("status payload contains unknown fields")
    if not {"status", "qualifiers", "retryable"} <= set(value):
        raise StatusValidationError("status, qualifiers and retryable are required")
    if type(value["status"]) is not str or value["status"] not in REQUEST_OUTCOMES:
        raise StatusValidationError("status must be an approved request outcome")
    qualifiers = value["qualifiers"]
    if type(qualifiers) is not list or any(
        type(q) is not str or q not in DATA_QUALIFIERS for q in qualifiers
    ):
        raise StatusValidationError("qualifiers must be an array of approved qualifiers")
    if len(set(qualifiers)) != len(qualifiers):
        raise StatusValidationError("qualifiers must not contain duplicates")
    if type(value["retryable"]) is not bool:
        raise StatusValidationError("retryable must be a boolean")
    if ("stale" in qualifiers) != ("as_of" in value):
        raise StatusValidationError("as_of is required exactly when stale is present")
    if "as_of" in value:
        stamp = value["as_of"]
        if type(stamp) is not str or not _TIMESTAMP.fullmatch(stamp):
            raise StatusValidationError("as_of must be a timezone-qualified timestamp")
        if stamp.endswith("-00:00"):
            raise StatusValidationError("as_of must have a known UTC offset")
        try:
            datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            raise StatusValidationError("as_of must be a valid calendar timestamp") from None
    if ("partial" in qualifiers) != ("missing" in value):
        raise StatusValidationError("missing is required exactly when partial is present")
    if "missing" in value:
        missing = value["missing"]
        if type(missing) is not list or not missing or any(
            type(item) is not str or not item.strip() for item in missing
        ):
            raise StatusValidationError("missing must be a nonempty array of nonblank strings")
    if "retry_after" in value:
        delay = value["retry_after"]
        if not value["retryable"] or type(delay) is not int or not 0 <= delay <= 9007199254740991:
            raise StatusValidationError("retry_after requires retryable true and safe nonnegative integer seconds")
    result = dict(value)
    result["qualifiers"] = list(qualifiers)
    if "missing" in value:
        result["missing"] = list(value["missing"])
    return cast(StatusPayload, result)


def build_status(
    status: RequestOutcome, *, qualifiers: List[DataQualifier], retryable: bool, **metadata: object
) -> StatusPayload:
    """Build a JSON-ready object using the same strict validation as wire input."""
    return validate_status(dict(metadata, status=status, qualifiers=qualifiers, retryable=retryable))
