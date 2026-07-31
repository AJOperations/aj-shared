from flask import Flask

from aj_shared.contract import get_runtime_identity, register_contract_route


def test_runtime_identity_accepts_only_exact_build_metadata(monkeypatch):
    monkeypatch.setenv("AJ_APP_COMMIT", "a" * 40)
    monkeypatch.setenv("AJ_SHARED_COMMIT", "B" * 40)
    monkeypatch.setenv("AJ_RUNTIME_ENVIRONMENT", "Staging")

    assert get_runtime_identity() == {
        "app_commit": "a" * 40,
        "shared_commit": "b" * 40,
        "environment": "staging",
        "all_fields_supplied": True,
        "provenance": "externally_supplied_build_metadata",
    }


def test_runtime_identity_redacts_invalid_or_unapproved_values(monkeypatch):
    monkeypatch.setenv("AJ_APP_COMMIT", "not-a-commit")
    monkeypatch.setenv("AJ_SHARED_COMMIT", "secret=do-not-expose")
    monkeypatch.setenv("AJ_RUNTIME_ENVIRONMENT", "production\nSECRET=value")

    assert get_runtime_identity() == {
        "app_commit": None,
        "shared_commit": None,
        "environment": None,
        "all_fields_supplied": False,
        "provenance": "externally_supplied_build_metadata",
    }


def test_flask_contract_keeps_runtime_identity_behind_platform_key(monkeypatch):
    monkeypatch.setenv("PLATFORM_SECRET", "test-platform-secret")
    monkeypatch.setenv("AJ_APP_COMMIT", "1" * 40)
    monkeypatch.setenv("AJ_SHARED_COMMIT", "2" * 40)
    monkeypatch.setenv("AJ_RUNTIME_ENVIRONMENT", "testing")
    app = Flask(__name__)
    register_contract_route(app, "Compatibility App")
    client = app.test_client()

    denied = client.get("/api/contract")
    allowed = client.get(
        "/api/contract",
        headers={"X-AJ-Key": "test-platform-secret"},
    )

    assert denied.status_code == 401
    assert denied.get_json() == {"error": "Unauthorized"}
    assert allowed.status_code == 200
    assert allowed.get_json()["runtime_identity"] == {
        "app_commit": "1" * 40,
        "shared_commit": "2" * 40,
        "environment": "testing",
        "all_fields_supplied": True,
        "provenance": "externally_supplied_build_metadata",
    }
