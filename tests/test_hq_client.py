from aj_shared.hq_client import HQClient, MAX_JSON_RESPONSE_BYTES


class FakeResponse:
    def __init__(self, status_code, body, headers=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}
        self.closed = False

    def iter_content(self, chunk_size=65536):
        del chunk_size
        if isinstance(self._body, bytes):
            yield self._body
        else:
            import json

            yield json.dumps(self._body).encode("utf-8")

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.error:
            raise self.error
        return self.response


def test_validate_forwards_token_and_platform_key():
    session = FakeSession(FakeResponse(200, {"valid": True, "user": {"id": "u1"}}))
    client = HQClient("https://hq.example", "platform", session=session)

    assert client.validate("token-1") == {"id": "u1"}
    method, url, kwargs = session.calls[0]
    assert (method, url) == ("GET", "https://hq.example/auth/validate")
    assert kwargs["headers"] == {"X-AJ-Key": "platform"}
    assert kwargs["params"] == {"token": "token-1"}
    assert kwargs["timeout"] == 5
    assert kwargs["allow_redirects"] is False
    assert kwargs["stream"] is True


def test_validate_returns_none_for_invalid_or_malformed_user():
    invalid = FakeSession(FakeResponse(200, {"valid": False}))
    malformed = FakeSession(FakeResponse(200, {"valid": True, "user": "u1"}))

    assert HQClient("https://hq.example", "platform", session=invalid).validate() is None
    assert HQClient("https://hq.example", "platform", session=malformed).validate() is None


def test_dependency_failure_is_generic():
    session = FakeSession(error=TimeoutError("secret upstream detail"))

    response = HQClient("https://hq.example", "platform", session=session).get_json(
        "/api/apps"
    )

    assert response.status_code == 502
    assert response.body["error"] == "HQ temporarily unavailable"
    assert len(response.body["reference_id"]) == 12


def test_non_object_json_is_rejected():
    session = FakeSession(FakeResponse(200, ["not", "an", "object"]))

    response = HQClient("https://hq.example", "platform", session=session).get_json(
        "/api/apps"
    )

    assert response.status_code == 502
    assert response.body["error"] == "HQ temporarily unavailable"
    assert len(response.body["reference_id"]) == 12


def test_redirect_and_oversize_responses_are_rejected_and_closed():
    redirect = FakeResponse(302, {"secret": "redirect"})
    declared = FakeResponse(
        200,
        {"secret": "declared"},
        {"Content-Length": str(MAX_JSON_RESPONSE_BYTES + 1)},
    )
    streamed = FakeResponse(200, b"x" * (MAX_JSON_RESPONSE_BYTES + 1))

    for response in (redirect, declared, streamed):
        result = HQClient(
            "https://hq.example",
            "platform",
            session=FakeSession(response),
        ).get_json("/api/apps")
        assert result.status_code == 502
        assert result.body["error"] == "HQ temporarily unavailable"
        assert "secret" not in str(result.body)
        assert response.closed


def test_invalid_json_is_not_reflected():
    response = FakeResponse(500, b"<html>private upstream detail</html>")

    result = HQClient(
        "https://hq.example",
        "platform",
        session=FakeSession(response),
    ).get_json("/api/apps")

    assert result.status_code == 502
    assert result.body["error"] == "HQ temporarily unavailable"
    assert "private upstream" not in str(result.body)
    assert response.closed


def test_get_json_forwards_query_parameters():
    session = FakeSession(FakeResponse(200, {"apps": []}))
    client = HQClient("https://hq.example/", "platform", timeout=9, session=session)

    response = client.get_json("/api/apps", {"role": "staff"})

    assert response.status_code == 200
    assert response.body == {"apps": []}
    _, url, kwargs = session.calls[0]
    assert url == "https://hq.example/api/apps"
    assert kwargs["params"] == {"role": "staff"}
    assert kwargs["timeout"] == 9


def test_post_json_forwards_payload_and_cookies():
    session = FakeSession(FakeResponse(201, {"ok": True}))
    client = HQClient("https://hq.example", "platform", session=session)

    response = client.post_json(
        "/api/users/me/password", {"password": "replacement"}, cookies={"aj_session": "x"}
    )

    assert response.status_code == 201
    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["json"] == {"password": "replacement"}
    assert kwargs["cookies"] == {"aj_session": "x"}


def test_post_multipart_forwards_fields_and_files():
    session = FakeSession(FakeResponse(200, {"ok": True}))
    client = HQClient("https://hq.example", "platform", session=session)
    files = {"file": ("estimate.pdf", b"pdf", "application/pdf")}

    response = client.post_multipart("/api/dropbox/upload", {"path": "/x"}, files)

    assert response.status_code == 200
    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["data"] == {"path": "/x"}
    assert kwargs["files"] == files


def test_constructor_rejects_invalid_url_and_blank_secret():
    for invalid_url in ("", "/relative", "ftp://hq.example"):
        try:
            HQClient(invalid_url, "platform")
        except ValueError as exc:
            assert str(exc) == "HQ base URL must be absolute HTTP(S)"
        else:
            raise AssertionError(f"accepted invalid URL {invalid_url!r}")

    try:
        HQClient("https://hq.example", "")
    except ValueError as exc:
        assert str(exc) == "PLATFORM_SECRET is required"
    else:
        raise AssertionError("accepted blank PLATFORM_SECRET")
