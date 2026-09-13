"""Additive suite v1 wire contracts. No storage, recipient authority or domain rules.

Callers establish authorization before constructing a projection. Validation
cannot turn a browser supplied recipient, actor or correlation ID into authority.
"""

import copy
import re
import uuid
from datetime import datetime, timezone, date
from urllib.parse import urlsplit, unquote
from zoneinfo import ZoneInfo

from .status import validate_status


class ContractError(ValueError):
    pass


def fields(value, required, optional=()):
    if (
        type(value) is not dict
        or not set(required) <= value.keys()
        or value.keys() - set(required) - set(optional)
    ):
        raise ContractError("Invalid contract fields")
    return copy.deepcopy(value)


def text(value, limit=200):
    if (
        type(value) is not str
        or not value.strip()
        or len(value) > limit
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise ContractError("Invalid bounded text")
    return value


def identifier(value):
    text(value, 128)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", value):
        raise ContractError("Invalid identifier")
    return value


def timestamp(value, nullable=False):
    if value is None and nullable:
        return None
    # Reuse the existing strict timestamp contract, including unknown-offset rejection.
    validate_status(
        dict(status="ok", qualifiers=["stale"], retryable=False, as_of=value)
    )
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def destination(value, allowed_origin):
    text(value, 1024)
    decoded = unquote(value)
    if any(c in decoded for c in ("\\", "?", "#")) or any(ord(c) < 32 for c in decoded):
        raise ContractError("Destination must not carry query, fragment or controls")
    parsed, origin = urlsplit(value), urlsplit(allowed_origin)
    if (
        origin.scheme != "https"
        or not origin.netloc
        or origin.username
        or origin.password
        or origin.path not in ("", "/")
        or origin.query
        or origin.fragment
    ):
        raise ContractError("Expected a configured HTTPS origin")
    if value.startswith("/") and not decoded.startswith("//") and not parsed.netloc:
        return value
    if (
        parsed.scheme != "https"
        or parsed.netloc != origin.netloc
        or parsed.username
        or parsed.password
    ):
        raise ContractError("Destination outside configured origin")
    return value


def validate_provenance(value, *, allowed_origin=None):
    result = fields(
        value,
        ("source_id", "source_label", "observed_at", "fetched_at"),
        ("destination",),
    )
    identifier(result["source_id"])
    text(result["source_label"])
    observed = timestamp(result["observed_at"], True)
    fetched = timestamp(result["fetched_at"])
    if observed and observed > fetched:
        raise ContractError("Source observation cannot follow fetch")
    if "destination" in result:
        if allowed_origin is None:
            raise ContractError("Destination needs configured origin")
        destination(result["destination"], allowed_origin)
    return result


def validate_attention(value, *, allowed_origin, max_items=100):
    result = fields(
        value, ("schema_version", "status", "provenance", "complete", "items")
    )
    if type(result["schema_version"]) is not int or result["schema_version"] != 1:
        raise ContractError("Unsupported attention schema")
    status = validate_status(result["status"])
    validate_provenance(result["provenance"], allowed_origin=allowed_origin)
    items = result["items"]
    if (
        type(result["complete"]) is not bool
        or type(items) is not list
        or len(items) > max_items
    ):
        raise ContractError("Invalid bounded snapshot")
    outcome = status["status"]
    if outcome == "empty" and (items or not result["complete"]):
        raise ContractError("Empty requires complete successful snapshot")
    if outcome not in ("ok", "empty") and (items or result["complete"]):
        raise ContractError("Unavailable/denied/unknown results cannot expose items")
    if (
        outcome == "ok"
        and not result["complete"]
        and "partial" not in status["qualifiers"]
    ):
        raise ContractError("Incomplete success requires partial status")
    if result["complete"] and "partial" in status["qualifiers"]:
        raise ContractError("Partial cannot claim completeness")
    seen = set()
    for item in items:
        fields(
            item,
            (
                "signal_id",
                "source_app_id",
                "signal_type",
                "kind",
                "source_record",
                "title",
                "reason",
                "destination",
                "state",
                "updated_at",
                "revision",
            ),
            ("action_label", "expires_at", "dates", "urgency"),
        )
        for key in ("signal_id", "source_app_id", "signal_type", "revision"):
            identifier(item[key])
        if item["source_app_id"] != result["provenance"]["source_id"]:
            raise ContractError("Producer mismatch")
        key = (item["source_app_id"], item["signal_id"])
        if key in seen:
            raise ContractError("Duplicate signal identity")
        seen.add(key)
        if item["kind"] not in ("action", "date", "assignment", "update") or item[
            "state"
        ] not in ("active", "resolved"):
            raise ContractError("Invalid signal vocabulary")
        fields(item["source_record"], ("entity_type", "id"))
        for val in item["source_record"].values():
            identifier(val)
        for key in ("title", "reason"):
            text(item[key], 300)
        if item["kind"] == "action" and "action_label" not in item:
            raise ContractError("Action needs copy")
        if "action_label" in item:
            text(item["action_label"], 80)
        destination(item["destination"], allowed_origin)
        timestamp(item["updated_at"])
        if "expires_at" in item:
            timestamp(item["expires_at"])
        if "urgency" in item:
            fields(item["urgency"], ("level", "reason"))
            if item["urgency"]["level"] not in ("normal", "soon", "urgent"):
                raise ContractError("Invalid urgency")
            text(item["urgency"]["reason"], 300)
        dates = item.get("dates", [])
        if type(dates) is not list or len(dates) > 10:
            raise ContractError("Invalid dates")
        names = set()
        for entry in dates:
            fields(entry, ("name", "value", "timezone"))
            identifier(entry["name"])
            if entry["name"] in names:
                raise ContractError("Duplicate date name")
            names.add(entry["name"])
            try:
                ZoneInfo(text(entry["timezone"], 100))
            except (KeyError, ValueError):
                raise ContractError("Unknown timezone") from None
            if type(entry["value"]) is str and re.fullmatch(
                r"\d{4}-\d{2}-\d{2}", entry["value"]
            ):
                date.fromisoformat(entry["value"])
            else:
                timestamp(entry["value"])
    return result


def operation_reference(value=None):
    if type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{5,63}", value):
        return value
    return uuid.uuid4().hex[:12]


def validate_diagnostic(value):
    result = fields(
        value,
        (
            "schema_version",
            "app",
            "environment",
            "event_code",
            "route_template",
            "operation_reference",
            "outcome",
            "duration_ms",
        ),
        ("dependency_id",),
    )
    if type(result["schema_version"]) is not int or result["schema_version"] != 1:
        raise ContractError("Unsupported diagnostic schema")
    for key in ("app", "environment", "event_code", "outcome", "dependency_id"):
        if key in result:
            identifier(result[key])
    route = text(result["route_template"], 200)
    if not re.fullmatch(r"/[A-Za-z0-9_/:<>.-]*", route):
        raise ContractError("Expected safe route template")
    if (
        operation_reference(result["operation_reference"])
        != result["operation_reference"]
    ):
        raise ContractError("Invalid reference")
    if (
        type(result["duration_ms"]) not in (int, float)
        or not 0 <= result["duration_ms"] <= 86400000
    ):
        raise ContractError("Invalid duration")
    return result


def emit_diagnostic(value, sink):
    event = validate_diagnostic(value)
    try:
        sink(event)
    except Exception:
        return False
    return True


def protected_read(reader, *, authorized):
    if authorized is not True:
        raise PermissionError("Access denied")
    return reader()


def record_audited_write(transaction, write, audit_sink, *, actor, event):
    """Own a local transaction: sink must use this SAME transaction, never commit.

    The adapter must implement commit/rollback context management. Do not use
    inside an already active transaction; external operations are unsupported.
    """
    if getattr(transaction, "in_transaction", False):
        raise ContractError("Audit helper requires a fresh owned transaction")
    identifier(actor)
    record = fields(
        event, ("action", "target", "outcome", "operation_reference"), ("reason_code",)
    )
    for key in ("action", "target", "reason_code"):
        if key in record:
            identifier(record[key])
    if record["outcome"] != "succeeded":
        raise ContractError("Committed write must record success")
    if (
        operation_reference(record["operation_reference"])
        != record["operation_reference"]
    ):
        raise ContractError("Invalid reference")
    record.update(
        schema_version=1,
        event_id=uuid.uuid4().hex,
        actor=actor,
        occurred_at=datetime.now(timezone.utc).isoformat(),
    )
    with transaction:
        result = write(transaction)
        audit_sink(transaction, record)  # Any failure rolls back the governed write.
    return result


def validate_job(value):
    result = fields(
        value,
        (
            "schema_version",
            "run_id",
            "operation_reference",
            "job_type",
            "attempt",
            "state",
            "started_at",
            "finished_at",
            "last_success_at",
            "counts",
            "recovery_reference",
        ),
    )
    if type(result["schema_version"]) is not int or result["schema_version"] != 1:
        raise ContractError("Unsupported job schema")
    for key in ("run_id", "job_type"):
        identifier(result[key])
    for key in ("operation_reference", "recovery_reference"):
        if operation_reference(result[key]) != result[key]:
            raise ContractError("Invalid reference")
    if type(result["attempt"]) is not int or not 1 <= result["attempt"] <= 10000:
        raise ContractError("Invalid attempt")
    state = result["state"]
    if state not in (
        "queued",
        "running",
        "succeeded",
        "partial",
        "failed",
        "cancelled",
        "interrupted",
    ):
        raise ContractError("Invalid job state")
    start = timestamp(result["started_at"], state == "queued")
    finish = timestamp(result["finished_at"], True)
    success = timestamp(result["last_success_at"], True)
    if state in ("queued", "running"):
        if finish is not None:
            raise ContractError("Unfinished job has finish")
    elif start is None or finish is None or finish < start:
        raise ContractError("Invalid job interval")
    if state == "succeeded" and success != finish:
        raise ContractError("Success freshness must match completion")
    if state != "succeeded" and success and start and success >= start:
        raise ContractError("Failure cannot advance freshness")
    counts = result["counts"]
    if type(counts) is not dict or len(counts) > 20:
        raise ContractError("Invalid counts")
    for key, val in counts.items():
        identifier(key)
        if type(val) is not int or not 0 <= val <= 2**53 - 1:
            raise ContractError("Invalid count")
    return result


def start_job(job_type, *, reference, attempt=1, last_success_at=None, now=None):
    """A retry keeps the logical operation reference but gets a fresh run ID."""
    stamp = now or datetime.now(timezone.utc).isoformat()
    return validate_job(
        dict(
            schema_version=1,
            run_id=uuid.uuid4().hex,
            operation_reference=reference,
            job_type=job_type,
            attempt=attempt,
            state="running",
            started_at=stamp,
            finished_at=None,
            last_success_at=last_success_at,
            counts={},
            recovery_reference=reference,
        )
    )


def finish_job(value, state, *, counts, now=None):
    current = validate_job(value)
    if current["state"] != "running" or state not in (
        "succeeded",
        "partial",
        "failed",
        "cancelled",
        "interrupted",
    ):
        raise ContractError("Invalid job transition")
    stamp = now or datetime.now(timezone.utc).isoformat()
    current.update(state=state, finished_at=stamp, counts=counts)
    if state == "succeeded":
        current["last_success_at"] = stamp
    return validate_job(current)


def interrupt_stale_job(value, *, now, stale_after_seconds):
    current = validate_job(value)
    if (
        type(stale_after_seconds) not in (int, float)
        or not 0 < stale_after_seconds <= 86400
    ):
        raise ContractError("Invalid interruption threshold")
    if (
        current["state"] == "running"
        and (timestamp(now) - timestamp(current["started_at"])).total_seconds()
        > stale_after_seconds
    ):
        return finish_job(current, "interrupted", counts=current["counts"], now=now)
    return current
