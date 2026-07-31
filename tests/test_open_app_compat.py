from unittest import mock

from flask import Flask

from aj_shared import register_proxy


class StubResponse:
    status_code = 200
    headers = {"Content-Type": "application/json"}

    def iter_content(self, chunk_size=65536):
        del chunk_size
        yield b'{"jobs": []}'

    def close(self):
        return None


def make_open_client():
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config.update(TESTING=True)
    register_proxy(
        app,
        app_name="Open Tool",
        hq_base="https://hq.example",
        configure_cors_now=False,
        open_app=True,
    )
    return app.test_client()


@mock.patch("requests.request")
def test_open_app_keeps_reads_ungated_and_auth_validation_stubbed(request):
    request.return_value = StubResponse()
    client = make_open_client()

    validation = client.get("/auth/validate")
    jobs = client.get("/api/jobs")

    assert validation.status_code == 200
    assert validation.get_json() == {"valid": False}
    assert jobs.status_code == 200
    assert jobs.get_json() == {"jobs": []}
    request.assert_called_once()


@mock.patch("requests.request")
def test_open_app_mutations_still_require_csrf_proof(request):
    response = make_open_client().post(
        "/api/feedback",
        data={"message": "Help"},
    )

    assert response.status_code == 403
    request.assert_not_called()
