from flask import Flask

import aj_shared


def test_existing_public_exports_remain_available():
    expected = {
        "require_auth",
        "require_auth_by_default",
        "get_current_user",
        "has_tag",
        "require_env_secret",
        "configure_session_security",
        "register_error_handlers",
        "csrf_protect",
        "rate_limited",
        "register_proxy",
        "build_set_clause",
        "configure_cors",
        "AJ_FLEET_ORIGINS",
        "CONTRACT_VERSION",
        "register_contract_route",
        "get_aj_shared_version",
        "get_runtime_identity",
    }
    assert expected <= set(aj_shared.__all__)


def test_existing_flask_contract_route_shape(monkeypatch):
    monkeypatch.setenv("PLATFORM_SECRET", "test-platform-secret")
    app = Flask(__name__)
    app.secret_key = "test-session-secret"
    aj_shared.register_contract_route(app, "Compatibility App")
    response = app.test_client().get(
        "/api/contract", headers={"X-AJ-Key": "test-platform-secret"}
    )
    assert response.status_code == 200
    assert response.get_json()["app_name"] == "Compatibility App"
    assert response.get_json()["contract_version"] == "1.0.0"
