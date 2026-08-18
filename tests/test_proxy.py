import io
import os
import unittest
from unittest import mock

from flask import Flask

from aj_shared import aj_proxy


class StubResponse:
    def __init__(self, body=b'{"ok": true}', status_code=200, headers=None):
        self.body = body
        self.status_code = status_code
        self.headers = headers or {}
        self.closed = False

    def iter_content(self, chunk_size=65536):
        del chunk_size
        yield self.body

    def close(self):
        self.closed = True


class ProxySecurityTests(unittest.TestCase):
    def make_client(self):
        app = Flask(__name__)
        app.secret_key = "test-secret"
        app.config.update(TESTING=True)
        aj_proxy.register_proxy(
            app,
            app_name="Test App",
            hq_base="https://hq.example",
            configure_cors_now=False,
        )
        client = app.test_client()
        with client.session_transaction() as session:
            session["_aj_user"] = {
                "id": "u1",
                "name": "Test User",
                "role": "admin",
                "tags": "[]",
            }
            session["_aj_user_cached_at"] = 9999999999
        return client

    def test_logout_requires_exact_csrf_proof_and_clears_session(self):
        client = self.make_client()

        self.assertEqual(client.post("/auth/logout").status_code, 403)
        self.assertEqual(
            client.post(
                "/auth/logout",
                headers={"X-Requested-With": "wrong"},
            ).status_code,
            403,
        )
        with client.session_transaction() as session:
            self.assertIn("_aj_user", session)

        response = client.post(
            "/auth/logout",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        self.assertEqual(response.status_code, 200)
        with client.session_transaction() as session:
            self.assertNotIn("_aj_user", session)
            self.assertNotIn("_aj_user_cached_at", session)

    @mock.patch("requests.request", side_effect=RuntimeError("secret=do-not-leak"))
    def test_network_failure_returns_generic_correlated_error(self, _request):
        response = self.make_client().get("/api/jobs")

        self.assertEqual(response.status_code, 502)
        body = response.get_json()
        self.assertEqual(
            body["error"],
            "HQ is temporarily unavailable. It is safe to retry.",
        )
        self.assertRegex(body["reference_id"], r"^[0-9a-f]{12}$")
        self.assertNotIn("secret", response.get_data(as_text=True))

    @mock.patch("requests.request")
    def test_non_json_upstream_response_is_not_reflected(self, request):
        request.return_value = StubResponse(b"<html>private upstream error</html>")

        response = self.make_client().get("/api/jobs")

        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private upstream", response.get_data(as_text=True))
        request.assert_called_once()
        self.assertEqual(request.call_args.args[0], "GET")
        self.assertFalse(request.call_args.kwargs["allow_redirects"])
        self.assertTrue(request.call_args.kwargs["stream"])

    @mock.patch("requests.request")
    def test_declared_oversize_upstream_response_is_rejected_before_read(self, request):
        response_obj = StubResponse(
            b'{"secret": "not read"}',
            headers={"Content-Length": str(aj_proxy._MAX_JSON_RESPONSE_BYTES + 1)},
        )
        request.return_value = response_obj

        response = self.make_client().get("/api/jobs")

        self.assertEqual(response.status_code, 502)
        self.assertTrue(response_obj.closed)
        self.assertNotIn("not read", response.get_data(as_text=True))

    @mock.patch("requests.request")
    def test_streamed_oversize_upstream_response_is_bounded(self, request):
        response_obj = StubResponse(
            b"x" * (aj_proxy._MAX_JSON_RESPONSE_BYTES + 1),
        )
        request.return_value = response_obj

        response = self.make_client().get("/api/jobs")

        self.assertEqual(response.status_code, 502)
        self.assertTrue(response_obj.closed)
        self.assertLess(len(response.get_data()), 512)

    @mock.patch("requests.request")
    def test_feedback_proxy_rejects_oversize_screenshot_before_hq(self, request):
        client = self.make_client()
        with mock.patch.object(aj_proxy, "_FEEDBACK_MAX_BYTES", 4):
            response = client.post(
                "/api/feedback",
                data={
                    "message": "Help",
                    "screenshot": (io.BytesIO(b"12345"), "screen.png"),
                },
                content_type="multipart/form-data",
                headers={"X-Requested-With": "XMLHttpRequest"},
            )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(
            response.get_json()["error"],
            "Screenshot must be 5 MB or smaller.",
        )
        request.assert_not_called()

    @mock.patch("requests.request")
    def test_monday_query_forwards_body_to_hq_with_platform_secret(self, request):
        request.return_value = StubResponse(b'{"data": {"boards": []}}')
        payload = {"query": "{ boards { id } }", "variables": {"limit": 1}}

        with mock.patch.dict(os.environ, {"PLATFORM_SECRET": "platform-secret"}):
            response = self.make_client().post(
                "/api/monday/query",
                json=payload,
                headers={"X-Requested-With": "XMLHttpRequest"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"data": {"boards": []}})
        method, url = request.call_args.args
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://hq.example/api/monday/query")
        self.assertEqual(
            request.call_args.kwargs["headers"]["X-AJ-Key"],
            "platform-secret",
        )
        self.assertEqual(request.call_args.kwargs["json"], payload)
        self.assertFalse(request.call_args.kwargs["allow_redirects"])
        self.assertTrue(request.call_args.kwargs["stream"])

    @mock.patch("requests.request")
    def test_monday_query_passes_hq_rejection_status_through(self, request):
        request.return_value = StubResponse(
            b'{"error": "\'query\' is required"}',
            status_code=400,
        )

        response = self.make_client().post(
            "/api/monday/query",
            json={},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "'query' is required"})

    @mock.patch("requests.request")
    def test_monday_query_requires_csrf_proof(self, request):
        response = self.make_client().post(
            "/api/monday/query",
            json={"query": "{ me { id } }"},
        )

        self.assertEqual(response.status_code, 403)
        request.assert_not_called()

    @mock.patch("requests.request")
    def test_monday_query_rejects_hq_redirect(self, request):
        response_obj = StubResponse(
            b'{"data": "not read"}',
            status_code=302,
            headers={"Location": "https://redirected.example"},
        )
        request.return_value = response_obj

        response = self.make_client().post(
            "/api/monday/query",
            json={"query": "{ me { id } }"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        self.assertEqual(response.status_code, 502)
        self.assertTrue(response_obj.closed)
        self.assertNotIn("redirected.example", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
