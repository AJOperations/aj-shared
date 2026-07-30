from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from aj_shared.fastapi_integration import FastAPIHQ


USER = {"id": "u1", "role": "staff", "tags": []}


class FakeHQClient:
    def validate(self, token=None):
        return USER if token == "valid" else None


def make_client():
    app = FastAPI()
    hq = FastAPIHQ(
        app_name="Estimate Engine",
        hq_base="https://hq.example",
        app_base_url="https://engine.example",
        app_secret_key="app-secret",
        platform_secret="platform-secret",
        production=False,
        client=FakeHQClient(),
    )
    hq.install(app, public_paths=("/public-mutate",))

    @app.get("/csrf")
    def csrf(request: Request):
        return {"token": hq.csrf_token(request)}

    @app.api_route(
        "/mutate",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        dependencies=[Depends(hq.require_csrf)],
    )
    async def mutate(request: Request):
        return {"ok": True}

    @app.post("/public-mutate", dependencies=[Depends(hq.require_csrf)])
    async def public_mutate():
        return {"ok": True}

    return TestClient(app)


def authenticate(client):
    response = client.get("/csrf?token=valid", follow_redirects=False)
    assert response.status_code == 307
    return client.get("/csrf").json()["token"]


def test_post_without_header_or_form_token_is_forbidden():
    client = make_client()
    authenticate(client)

    response = client.post("/mutate", data={"value": "x"})

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}


def test_fetch_header_is_accepted_for_json():
    client = make_client()
    authenticate(client)

    response = client.post(
        "/mutate",
        json={"value": "x"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 200


def test_signed_form_nonce_is_accepted():
    client = make_client()
    token = authenticate(client)

    response = client.post("/mutate", data={"value": "x", "_csrf": token})

    assert response.status_code == 200


def test_signed_multipart_nonce_is_accepted():
    client = make_client()
    token = authenticate(client)

    response = client.post(
        "/mutate",
        data={"_csrf": token},
        files={"attachment": ("note.txt", b"safe")},
    )

    assert response.status_code == 200


def test_wrong_nonce_is_forbidden():
    client = make_client()
    authenticate(client)

    response = client.post("/mutate", data={"_csrf": "wrong"})

    assert response.status_code == 403


def test_wrong_header_values_are_forbidden():
    client = make_client()
    authenticate(client)

    lowercase_value = client.post(
        "/mutate", headers={"X-Requested-With": "xmlhttprequest"}
    )
    wrong_value = client.post(
        "/mutate", headers={"X-Requested-With": "fetch"}
    )

    assert lowercase_value.status_code == 403
    assert wrong_value.status_code == 403


def test_missing_session_is_forbidden_even_on_public_route():
    client = make_client()

    response = client.post(
        "/public-mutate", headers={"X-Requested-With": "XMLHttpRequest"}
    )

    assert response.status_code == 403


def test_safe_method_does_not_require_csrf_proof():
    client = make_client()
    authenticate(client)

    response = client.get("/mutate")

    assert response.status_code == 200
