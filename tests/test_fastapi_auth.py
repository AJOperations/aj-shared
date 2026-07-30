import time
from urllib.parse import parse_qs, urlparse

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from aj_shared.fastapi_integration import FastAPIHQ


USER = {
    "id": "u1",
    "name": "Ada",
    "email": "ada@example.com",
    "role": "staff",
    "tags": ["estimating"],
}


class FakeHQClient:
    def __init__(self):
        self.valid_user = USER
        self.calls = []

    def validate(self, token=None):
        self.calls.append(token)
        return self.valid_user if token == "valid" else None


def make_client(*, production=False, ttl=1200, fake=None):
    fake = fake or FakeHQClient()
    app = FastAPI()
    hq = FastAPIHQ(
        app_name="Estimate Engine",
        hq_base="https://hq.example",
        app_base_url="https://engine.example",
        app_secret_key="app-secret",
        platform_secret="platform-secret",
        session_ttl_seconds=ttl,
        production=production,
        client=fake,
    )
    hq.install(app, public_paths=("/health", "/json", "/token-post"))

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/private")
    def private(request: Request):
        return hq.current_user(request)

    @app.get("/admin")
    def admin(user=Depends(hq.require_role("admin"))):
        return user

    @app.get("/json")
    def json_route(user=Depends(hq.require_user)):
        return user

    @app.post("/local-logout")
    def local_logout(request: Request):
        hq.clear_session(request)
        return {"ok": True}

    @app.post("/token-post")
    async def token_post(request: Request, user=Depends(hq.require_user)):
        return {"body": await request.json(), "user": user["id"]}

    return TestClient(app), fake


def login(client):
    response = client.get("/private?token=valid", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "https://engine.example/private"


def test_public_route_does_not_require_authentication():
    client, fake = make_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert fake.calls == []


def test_private_route_redirects_to_hq_login():
    client, _ = make_client()

    response = client.get("/private", follow_redirects=False)

    assert response.status_code == 307
    location = urlparse(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == "https://hq.example/login"
    assert parse_qs(location.query) == {"next": ["https://engine.example/private"]}


def test_valid_token_creates_session_and_removes_only_token():
    client, fake = make_client()

    response = client.get("/private?foo=1&token=valid&bar=2", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "https://engine.example/private?foo=1&bar=2"
    assert fake.calls == ["valid"]
    private = client.get("/private")
    assert private.status_code == 200
    assert private.json()["id"] == "u1"


def test_invalid_token_does_not_create_session():
    client, fake = make_client()

    response = client.get("/private?token=invalid", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].startswith("https://hq.example/login?")
    assert fake.calls == ["invalid"]
    assert client.get("/private", follow_redirects=False).status_code == 307


def test_valid_token_on_post_preserves_body_without_redirect():
    client, fake = make_client()

    response = client.post(
        "/token-post?token=valid",
        json={"value": "preserved"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert response.json() == {
        "body": {"value": "preserved"},
        "user": "u1",
    }
    assert "location" not in response.headers
    assert fake.calls == ["valid"]


def test_invalid_token_on_post_returns_json_unauthorized():
    client, fake = make_client()

    response = client.post(
        "/token-post?token=invalid",
        json={"value": "preserved"},
        follow_redirects=False,
    )

    assert response.status_code == 401
    assert response.json() == {"error": "Unauthorized"}
    assert "location" not in response.headers
    assert fake.calls == ["invalid"]


def test_json_dependency_returns_401_without_redirect():
    client, _ = make_client()

    response = client.get("/json", follow_redirects=False)

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


def test_role_dependency_denies_staff_and_allows_admin():
    client, fake = make_client()
    login(client)

    denied = client.get("/admin")
    assert denied.status_code == 403

    client.post("/local-logout")
    fake.valid_user = {**USER, "role": "admin"}
    login(client)
    allowed = client.get("/admin")
    assert allowed.status_code == 200
    assert allowed.json()["role"] == "admin"


def test_session_expires_at_ttl_boundary(monkeypatch):
    now = [1_000.0]
    monkeypatch.setattr(time, "time", lambda: now[0])
    client, _ = make_client(ttl=1200)
    login(client)

    now[0] = 2_199.0
    assert client.get("/private").status_code == 200
    now[0] = 2_200.0
    assert client.get("/private", follow_redirects=False).status_code == 307


def test_tampered_cookie_is_not_trusted():
    client, _ = make_client()
    login(client)
    cookie = client.cookies.get("aj_app_session")
    client.cookies.set("aj_app_session", f"{cookie}tampered")

    response = client.get("/private", follow_redirects=False)

    assert response.status_code == 307


def test_cookie_security_flags_follow_environment():
    local, _ = make_client(production=False)
    local_response = local.get("/private?token=valid", follow_redirects=False)
    assert "httponly" in local_response.headers["set-cookie"].lower()
    assert "samesite=lax" in local_response.headers["set-cookie"].lower()
    assert "secure" not in local_response.headers["set-cookie"].lower()

    production, _ = make_client(production=True)
    production_response = production.get("/private?token=valid", follow_redirects=False)
    assert "secure" in production_response.headers["set-cookie"].lower()


def test_has_tag_handles_lists_json_and_malformed_values():
    client, fake = make_client()
    login(client)
    app = client.app
    hq = app.state.aj_hq

    with client as active:
        request = None
        # Exercise through a temporary route so the real signed session is used.
        @app.get("/tag/{name}")
        def tag(name: str, req: Request):
            return {"present": hq.has_tag(req, name)}

        assert active.get("/tag/estimating").json() == {"present": True}

    client.post("/local-logout")
    fake.valid_user = {**USER, "tags": '["finance"]'}
    login(client)
    assert client.get("/tag/finance").json() == {"present": True}

    client.post("/local-logout")
    fake.valid_user = {**USER, "tags": "not-json"}
    login(client)
    assert client.get("/tag/finance").json() == {"present": False}
