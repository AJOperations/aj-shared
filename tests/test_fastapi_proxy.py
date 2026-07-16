import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aj_shared.fastapi_integration import FastAPIHQ
from aj_shared.hq_client import HQResponse


USER = {"id": "u1", "role": "staff", "tags": []}


class FakeHQClient:
    def __init__(self):
        self.user = USER
        self.calls = []
        self.result = HQResponse(200, {"upstream": True})

    def validate(self, token=None):
        self.calls.append(("validate", token))
        return self.user if token == "valid" else None

    def get_json(self, path, params=None):
        self.calls.append(("get", path, dict(params or {})))
        return self.result

    def post_json(self, path, payload, cookies=None):
        self.calls.append(("post_json", path, dict(payload), dict(cookies or {})))
        return self.result

    def post_multipart(self, path, data, files):
        self.calls.append(("post_multipart", path, dict(data), dict(files or {})))
        return self.result


def make_client(*, role="staff"):
    fake = FakeHQClient()
    fake.user = {**USER, "role": role}
    app = FastAPI()
    hq = FastAPIHQ(
        app_name="Estimate Engine",
        hq_base="https://hq.example",
        app_base_url="https://engine.example",
        app_secret_key="app-secret",
        platform_secret="platform-secret",
        production=False,
        client=fake,
    )
    hq.install(app)
    hq.install_standard_routes(app)
    client = TestClient(app)
    client.get("/?token=valid", follow_redirects=False)
    fake.calls.clear()
    return client, fake


@pytest.mark.parametrize(
    ("route", "upstream_path", "params"),
    [
        ("/api/users", "/api/users", {}),
        ("/api/rates", "/api/rates", {}),
        ("/api/rates?client=Acme", "/api/rates", {"client": "Acme"}),
        ("/api/rates/lookup?role=Producer", "/api/rates/lookup", {"role": "Producer"}),
        ("/api/people?item_type=staff", "/api/people", {"item_type": "staff"}),
        ("/api/codes", "/api/codes", {}),
        ("/api/codes/fees", "/api/codes/fees", {}),
        ("/api/codes/expenses", "/api/codes/expenses", {}),
        ("/api/jobs?client=Acme", "/api/jobs", {"client": "Acme"}),
        ("/api/jobs/J-100", "/api/jobs/J-100", {}),
        ("/api/clients?active=1", "/api/clients", {"active": "1"}),
        ("/api/contracts?client=Acme", "/api/contracts", {"client": "Acme"}),
        ("/api/dropbox/list?path=%2FJobs", "/api/dropbox/list", {"path": "/Jobs"}),
    ],
)
def test_get_routes_preserve_shape_and_query(route, upstream_path, params):
    client, fake = make_client()

    response = client.get(route)

    assert response.status_code == 200
    assert response.json() == {"upstream": True}
    assert fake.calls == [("get", upstream_path, params)]


def test_apps_forwards_cached_role_and_apps_all_requires_admin():
    client, fake = make_client()

    apps = client.get("/api/apps")
    denied = client.get("/api/apps/all")

    assert apps.status_code == 200
    assert fake.calls == [("get", "/api/apps", {"role": "staff"})]
    assert denied.status_code == 403

    admin, admin_fake = make_client(role="admin")
    allowed = admin.get("/api/apps/all")
    assert allowed.status_code == 200
    assert admin_fake.calls == [("get", "/api/apps/all", {})]


def test_json_routes_return_401_instead_of_browser_redirect():
    client, _ = make_client()
    client.cookies.clear()

    response = client.get("/api/users", follow_redirects=False)

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


def test_auth_validate_uses_cache_then_forwards_token_without_cache():
    client, fake = make_client()
    cached = client.get("/auth/validate")
    assert cached.json() == {"valid": True, "user": USER}
    assert fake.calls == []

    client.cookies.clear()
    fake.result = HQResponse(401, {"valid": False})
    forwarded = client.get("/auth/validate?token=bad")
    assert forwarded.status_code == 401
    assert forwarded.json() == {"valid": False}
    assert fake.calls == [("get", "/auth/validate", {"token": "bad"})]


def test_logout_clears_local_session():
    client, _ = make_client()

    response = client.post("/auth/logout")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert client.get("/api/users").status_code == 401


@pytest.mark.parametrize(
    ("route", "payload", "upstream"),
    [
        ("/api/users/me/password", {"password": "new"}, "/api/users/me/password"),
        ("/api/email/send", {"to": "ada@example.com"}, "/api/email/send"),
    ],
)
def test_json_mutations_forward_payload_and_require_csrf(route, payload, upstream):
    client, fake = make_client()

    denied = client.post(route, json=payload)
    accepted = client.post(
        route,
        json=payload,
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert denied.status_code == 403
    assert accepted.status_code == 200
    assert fake.calls[0][0:3] == ("post_json", upstream, payload)


@pytest.mark.parametrize(
    ("route", "file_field"),
    [("/api/feedback", "screenshot"), ("/api/dropbox/upload", "file")],
)
def test_multipart_mutations_forward_fields_and_files(route, file_field):
    client, fake = make_client()

    response = client.post(
        route,
        data={"note": "hello"},
        files={file_field: ("note.txt", b"content", "text/plain")},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 200
    kind, path, data, files = fake.calls[0]
    assert (kind, path) == ("post_multipart", route)
    assert data == {"note": "hello"}
    assert file_field in files
    filename, stream, content_type = files[file_field]
    assert filename == "note.txt"
    assert stream.read() == b"content"
    assert content_type == "text/plain"


def test_upstream_status_and_generic_failure_body_are_preserved():
    client, fake = make_client()
    fake.result = HQResponse(502, {"error": "HQ temporarily unavailable"})

    response = client.get("/api/users")

    assert response.status_code == 502
    assert response.json() == {"error": "HQ temporarily unavailable"}


def test_contract_requires_constant_platform_key_and_reports_versions():
    client, fake = make_client()

    missing = client.get("/api/contract")
    wrong = client.get("/api/contract", headers={"X-AJ-Key": "wrong"})
    valid = client.get(
        "/api/contract", headers={"X-AJ-Key": "platform-secret"}
    )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert valid.status_code == 200
    assert valid.json()["app_name"] == "Estimate Engine"
    assert valid.json()["contract_version"] == "1.0.0"
    assert "aj_shared_version" in valid.json()
    assert fake.calls == []
