import itertools
import json
from typing import get_args

import pytest

from aj_shared import (
    DATA_QUALIFIERS, REQUEST_OUTCOMES, DataQualifier, RequestOutcome,
    StatusPayload, StatusValidationError, build_status, validate_status,
)


def payload(**updates):
    return dict(status="unknown", qualifiers=[], retryable=False, **updates)


def test_exact_public_vocabulary():
    assert REQUEST_OUTCOMES == ("loading", "ok", "empty", "denied", "failed", "unavailable", "queued", "unknown")
    assert DATA_QUALIFIERS == ("stale", "partial", "cached")
    assert get_args(RequestOutcome) == REQUEST_OUTCOMES
    assert get_args(DataQualifier) == DATA_QUALIFIERS
    assert StatusPayload.__required_keys__ == {"status", "qualifiers", "retryable"}


@pytest.mark.parametrize("outcome", REQUEST_OUTCOMES)
@pytest.mark.parametrize("qualifiers", [list(q) for n in range(4) for q in itertools.combinations(DATA_QUALIFIERS, n)])
@pytest.mark.parametrize("retryable", [False, True])
def test_all_axes_round_trip(outcome, qualifiers, retryable):
    metadata = {}
    if "stale" in qualifiers:
        metadata["as_of"] = "2026-09-12T14:02:00Z"
    if "partial" in qualifiers:
        metadata["missing"] = ["source B has not responded"]
    if retryable:
        metadata["retry_after"] = 30
    value = build_status(outcome, qualifiers=qualifiers, retryable=retryable, **metadata)
    assert value == dict(status=outcome, qualifiers=qualifiers, retryable=retryable, **metadata)
    assert validate_status(json.loads(json.dumps(value))) == value


@pytest.mark.parametrize("stamp", ["2024-02-29T12:00:00Z", "2026-09-12T09:02:00-05:00", "2026-09-12T14:02:00.123456+00:00"])
def test_valid_timestamps(stamp):
    assert build_status("ok", qualifiers=["stale"], retryable=False, as_of=stamp)["as_of"] == stamp


@pytest.mark.parametrize("stamp", [None, 42, "", "yesterday", "2026-09-12", "2026-09-12T14:02:00", "2026-02-29T00:00:00Z", "2026-09-12T24:00:00Z", "2026-09-12T14:02:60Z", "2026-09-12T14:02:00+24:00", "2026-09-12T14:02:00-00:00", "2026-09-12T14:02:00.1234567Z"])
def test_invalid_timestamps(stamp):
    with pytest.raises(StatusValidationError):
        build_status("ok", qualifiers=["stale"], retryable=False, as_of=stamp)


@pytest.mark.parametrize("field", ["status", "qualifiers", "retryable"])
def test_required_fields(field):
    value = payload()
    del value[field]
    with pytest.raises(StatusValidationError):
        validate_status(value)


@pytest.mark.parametrize("value", [None, [], "ok", 1, True, (), '{"status":"ok"}'])
def test_wrong_top_level(value):
    with pytest.raises(StatusValidationError):
        validate_status(value)


@pytest.mark.parametrize("field,bad", [
    ("status", "success"), ("status", "partial"), ("status", "stale"),
    ("status", "positive"), ("status", "OK"), ("status", " ok "),
    ("status", None), ("status", []), ("status", 0),
    ("qualifiers", "stale"), ("qualifiers", ("cached",)), ("qualifiers", None),
    ("qualifiers", ["cached", "cached"]), ("qualifiers", ["retryable"]),
    ("qualifiers", [None]), ("qualifiers", [[]]),
    ("retryable", 0), ("retryable", 1), ("retryable", "false"), ("retryable", None),
    ("tone", "positive"), ("retry_after", 0), ("as_of", "2026-09-12T14:02:00Z"),
    ("missing", ["source B"]), (1, "unknown key"),
])
def test_invalid_wire_fields(field, bad):
    value = payload()
    value[field] = bad
    with pytest.raises(StatusValidationError):
        validate_status(value)


@pytest.mark.parametrize("qualifier", ["stale", "partial"])
def test_qualifier_requires_metadata(qualifier):
    with pytest.raises(StatusValidationError):
        build_status("unknown", qualifiers=[qualifier], retryable=False)


@pytest.mark.parametrize("missing", [None, [], "source B", [""], ["  "], [1], [[]]])
def test_partial_requires_missing_descriptions(missing):
    with pytest.raises(StatusValidationError):
        build_status("unknown", qualifiers=["partial"], retryable=False, missing=missing)


@pytest.mark.parametrize("delay", [None, True, False, -1, 1.5, "30", float("inf"), float("nan"), 9007199254740992])
def test_invalid_retry_delay(delay):
    with pytest.raises(StatusValidationError):
        build_status("failed", qualifiers=[], retryable=True, retry_after=delay)


@pytest.mark.parametrize("delay", [0, 1, 9007199254740991])
def test_retry_seconds_boundaries(delay):
    assert build_status("queued", qualifiers=[], retryable=True, retry_after=delay)["retry_after"] == delay


def test_retryability_does_not_require_delay_or_infer_outcome():
    for status in ("empty", "unavailable", "unknown"):
        assert build_status(status, qualifiers=[], retryable=True) == dict(status=status, qualifiers=[], retryable=True)


def test_no_mutation_or_shared_lists():
    source = dict(status="ok", qualifiers=["partial", "stale"], retryable=False,
                  missing=["source B"], as_of="2026-09-12T14:02:00Z")
    before = json.loads(json.dumps(source))
    result = validate_status(source)
    assert source == before
    result["qualifiers"].append("cached")
    result["missing"].append("source C")
    assert source == before
    bad = dict(source, retry_after=10)
    before_bad = json.loads(json.dumps(bad))
    with pytest.raises(StatusValidationError):
        validate_status(bad)
    assert bad == before_bad


def test_builder_rejects_unknown_metadata():
    with pytest.raises(StatusValidationError):
        build_status("ok", qualifiers=[], retryable=False, tone="positive")


def test_framework_serialization():
    from flask import Flask, jsonify
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    value = build_status("unavailable", qualifiers=["cached"], retryable=True)
    flask_app = Flask(__name__)
    with flask_app.app_context():
        assert jsonify(value).get_json() == value
    app = FastAPI()

    @app.get("/status")
    def status():
        return value

    assert TestClient(app).get("/status").json() == value
