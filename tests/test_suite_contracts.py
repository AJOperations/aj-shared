import copy
import pytest
from aj_shared.suite import (
    validate_attention,
    validate_provenance,
    operation_reference,
    validate_diagnostic,
    emit_diagnostic,
    record_audited_write,
    validate_job,
    protected_read,
)


def provenance():
    return dict(
        source_id="synthetic",
        source_label="Synthetic source",
        observed_at=None,
        fetched_at="2026-09-13T12:00:00Z",
    )


def snapshot():
    return dict(
        schema_version=1,
        status=dict(status="empty", qualifiers=[], retryable=False),
        provenance=provenance(),
        complete=True,
        items=[],
    )


def test_snapshot_separates_empty_unavailable_and_rejects_incompatibility():
    assert (
        validate_attention(snapshot(), allowed_origin="https://synthetic.example")
        == snapshot()
    )
    for change in [dict(schema_version=2), dict(complete=False), dict(items=[{}])]:
        with pytest.raises(ValueError):
            validate_attention(
                dict(snapshot(), **change), allowed_origin="https://synthetic.example"
            )
    value = snapshot()
    value.update(
        complete=False, status=dict(status="unavailable", qualifiers=[], retryable=True)
    )
    assert (
        validate_attention(value, allowed_origin="https://synthetic.example")[
            "provenance"
        ]["observed_at"]
        is None
    )


def test_provenance_no_freshness_inference_or_unknown_fields():
    assert validate_provenance(provenance())["observed_at"] is None
    for key, value in [
        ("cookies", "secret"),
        ("observed_at", "2026-03-08"),
        ("source_label", "x\nforged"),
    ]:
        with pytest.raises(ValueError):
            validate_provenance(dict(provenance(), **{key: value}))


def test_references_and_diagnostics_fail_safe():
    assert operation_reference("abc123") == "abc123"
    assert len(operation_reference("secret\nforged")) == 12
    event = dict(
        schema_version=1,
        app="synthetic",
        environment="test",
        event_code="dependency.failed",
        route_template="/api/items/:id",
        operation_reference="abc123",
        outcome="failed",
        duration_ms=1,
    )
    assert validate_diagnostic(event) == event
    for key, value in [
        ("headers", {}),
        ("route_template", "/api/private?token=secret"),
        ("event_code", "x\nforged"),
    ]:
        with pytest.raises(ValueError):
            validate_diagnostic(dict(event, **{key: value}))
    assert (
        emit_diagnostic(event, lambda _: (_ for _ in ()).throw(RuntimeError("secret")))
        is False
    )


def test_required_audit_failure_rolls_back_and_access_is_independent():
    import sqlite3

    db = sqlite3.connect(":memory:")
    db.execute("create table changes (value text)")
    event = dict(
        action="record.update",
        target="synthetic:1",
        outcome="succeeded",
        operation_reference="abc123",
    )
    with pytest.raises(RuntimeError):
        record_audited_write(
            db,
            lambda tx: tx.execute("insert into changes values ('synthetic')"),
            lambda tx, e: (_ for _ in ()).throw(RuntimeError("sink unavailable")),
            actor="verified-service",
            event=event,
        )
    assert db.execute("select count(*) from changes").fetchone()[0] == 0
    with pytest.raises(PermissionError):
        protected_read(lambda: ["secret"], authorized=False)


def test_failed_job_cannot_advance_freshness():
    value = dict(
        schema_version=1,
        run_id="run1",
        operation_reference="abc123",
        job_type="synthetic",
        attempt=1,
        state="failed",
        started_at="2026-09-13T12:00:00Z",
        finished_at="2026-09-13T12:01:00Z",
        last_success_at="2026-09-12T12:00:00Z",
        counts={"processed": 0},
        recovery_reference="abc123",
    )
    assert validate_job(value) == value
    with pytest.raises(ValueError):
        validate_job(dict(value, last_success_at=value["finished_at"]))


def test_installed_adoption_fixture_and_deliberate_mismatch():
    from aj_shared.adoption import check_compatibility

    assert check_compatibility()["synthetic_items"] == 4
    with pytest.raises(ValueError):
        check_compatibility(2)


def test_signal_identity_resolution_safe_destination_and_dates():
    import json
    from pathlib import Path

    value = json.loads(
        (Path(__file__).parents[1] / "aj_shared/fixtures/attention-v1.json").read_text()
    )
    baseline = validate_attention(value, allowed_origin="https://synthetic.example")
    changed = copy.deepcopy(value)
    changed["items"][0]["state"] = "resolved"
    changed["items"][0]["dates"][0]["value"] = "2026-11-01"
    result = validate_attention(changed, allowed_origin="https://synthetic.example")
    assert result["items"][0]["signal_id"] == baseline["items"][0]["signal_id"]
    for target in [
        "//other.example/private",
        "javascript:alert(1)",
        "/records/1?token=secret",
        "/%2fother.example",
        "/x%0aforged",
    ]:
        changed = copy.deepcopy(value)
        changed["items"][0]["destination"] = target
        with pytest.raises(ValueError):
            validate_attention(changed, allowed_origin="https://synthetic.example")
    changed = copy.deepcopy(value)
    changed["items"].append(copy.deepcopy(value["items"][0]))
    with pytest.raises(ValueError):
        validate_attention(changed, allowed_origin="https://synthetic.example")
    changed = copy.deepcopy(value)
    changed["items"][0]["dates"][0]["value"] = "2026-02-30"
    with pytest.raises(ValueError):
        validate_attention(changed, allowed_origin="https://synthetic.example")


def test_audience_gate_never_invokes_reader_without_verified_authority():
    calls = []
    with pytest.raises(PermissionError):
        protected_read(lambda: calls.append("private"), authorized=None)
    assert calls == []
    assert protected_read(
        lambda: ["synthetic recipient-filtered result"], authorized=True
    )


def test_runtime_identity_never_exposes_internal_fields_in_safe_subset():
    from aj_shared.runtime_identity import validate_runtime, support_identity

    value = dict(
        schema_version=1,
        app_id="synthetic",
        environment="test",
        source_revision="a" * 40,
        artifact_digest="Unknown",
        build_time="Unknown",
        shared_version="2.2.0",
        shared_checksum="Unknown",
        ui_version="Unknown",
        ui_checksum="Unknown",
        support_owner="Unknown",
    )
    assert set(support_identity(value)) == {"schema_version", "app_id", "support_owner"}
    assert support_identity(value, privileged=True)["source_revision"] == "a" * 40
    with pytest.raises(ValueError):
        validate_runtime(dict(value, environment_variables={"secret": "secret"}))


def test_interrupted_jobs_stay_visible_and_retry_keeps_logical_identity():
    from aj_shared.suite import start_job, finish_job, interrupt_stale_job

    first = start_job(
        "synthetic",
        reference="logical-123",
        last_success_at="2026-09-12T12:00:00Z",
        now="2026-09-13T12:00:00Z",
    )
    interrupted = interrupt_stale_job(
        first, now="2026-09-13T12:10:00Z", stale_after_seconds=60
    )
    assert interrupted["state"] == "interrupted"
    assert interrupted["last_success_at"] == first["last_success_at"]
    retry = start_job(
        "synthetic",
        reference=first["operation_reference"],
        attempt=2,
        last_success_at=first["last_success_at"],
        now="2026-09-13T12:11:00Z",
    )
    assert (
        retry["run_id"] != first["run_id"]
        and retry["operation_reference"] == first["operation_reference"]
    )
    done = finish_job(
        retry, "succeeded", counts={"processed": 1}, now="2026-09-13T12:12:00Z"
    )
    assert done["last_success_at"] == done["finished_at"]
    with pytest.raises(ValueError):
        finish_job(done, "failed", counts={})
