import unittest
from unittest import mock

from flask import Flask, jsonify, session

from aj_shared.aj_auth import (
    _SESSION_TTL_SECONDS,
    _get_or_validate_user,
    csrf_protect,
    has_tag,
    require_auth,
    require_auth_by_default,
)


class AuthSecurityTests(unittest.TestCase):
    def make_app(self):
        app = Flask(__name__)
        app.secret_key = "test-secret"
        app.config.update(TESTING=True)

        @app.post("/mutate")
        @csrf_protect
        def mutate():
            return jsonify({"ok": True})

        @app.get("/protected")
        @require_auth
        def protected():
            return jsonify({"ok": True})

        @app.post("/protected-post")
        @require_auth
        def protected_post():
            return jsonify({"ok": True})

        @app.get("/protected-json")
        @require_auth(json=True)
        def protected_json():
            return jsonify({"ok": True})

        @app.get("/tag/<tag>")
        def tag(tag):
            return jsonify({"present": has_tag(tag)})

        return app

    def test_csrf_requires_exact_proof_header(self):
        client = self.make_app().test_client()

        self.assertEqual(client.post("/mutate").status_code, 403)
        self.assertEqual(
            client.post(
                "/mutate",
                headers={"X-Requested-With": "anything"},
            ).status_code,
            403,
        )
        self.assertEqual(
            client.post(
                "/mutate",
                headers={"X-Requested-With": "XMLHttpRequest"},
            ).status_code,
            200,
        )

    @mock.patch(
        "aj_shared.aj_auth._validate_with_hq",
        return_value={"id": "u1", "name": "Test User", "role": "staff", "tags": "[]"},
    )
    def test_page_auth_strips_token_and_preserves_other_query_values(self, _validate):
        client = self.make_app().test_client()

        response = client.get(
            "/protected?token=one-time-secret&view=full&token=second-secret&view=compact",
            base_url="https://tools.example",
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"],
            "https://tools.example/protected?view=full&view=compact",
        )
        self.assertNotIn("token", response.headers["Location"])
        self.assertEqual(
            client.get(response.headers["Location"]).status_code,
            200,
        )

    @mock.patch(
        "aj_shared.aj_auth._validate_with_hq",
        return_value={"id": "u1", "name": "Test User", "role": "staff", "tags": "[]"},
    )
    def test_json_and_post_routes_do_not_redirect_or_drop_request_body(self, _validate):
        app = self.make_app()

        json_response = app.test_client().get(
            "/protected-json?token=one-time-secret",
        )
        post_response = app.test_client().post(
            "/protected-post?token=one-time-secret",
        )

        self.assertEqual(json_response.status_code, 200)
        self.assertEqual(post_response.status_code, 200)

    @mock.patch(
        "aj_shared.aj_auth._validate_with_hq",
        return_value={"id": "u1", "name": "Test User", "role": "staff", "tags": "[]"},
    )
    def test_default_deny_auth_also_strips_token_from_safe_page_get(self, _validate):
        app = Flask(__name__)
        app.secret_key = "test-secret"
        app.config.update(TESTING=True)

        @app.get("/protected")
        def protected():
            return jsonify({"ok": True})

        require_auth_by_default(app)
        response = app.test_client().get(
            "/protected?token=one-time-secret&tab=home",
            base_url="https://app.example",
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"],
            "https://app.example/protected?tab=home",
        )

    def test_flask_session_expires_at_same_1200_second_boundary_as_fastapi(self):
        app = self.make_app()
        user = {
            "id": "u1",
            "role": "staff",
            "tags": [],
        }

        self.assertEqual(_SESSION_TTL_SECONDS, 1_200)
        with app.test_request_context("/protected"):
            session["_aj_user"] = user
            session["_aj_user_cached_at"] = 1_000.0
            with mock.patch("aj_shared.aj_auth.time.time", return_value=2_199.0):
                self.assertEqual(_get_or_validate_user(), user)

        with app.test_request_context("/protected"):
            session["_aj_user"] = user
            session["_aj_user_cached_at"] = 1_000.0
            with mock.patch("aj_shared.aj_auth.time.time", return_value=2_200.0):
                self.assertIsNone(_get_or_validate_user())
            self.assertNotIn("_aj_user", session)
            self.assertNotIn("_aj_user_cached_at", session)

    def test_flask_has_tag_matches_fastapi_list_only_contract(self):
        cases = (
            (["estimating"], "estimating", True),
            ('["finance"]', "finance", True),
            ("not-json", "finance", False),
            ({"finance": True}, "finance", False),
            (("finance",), "finance", False),
            (None, "finance", False),
        )

        for tags, requested, expected in cases:
            with self.subTest(tags=tags):
                client = self.make_app().test_client()
                with client.session_transaction() as local_session:
                    local_session["_aj_user"] = {
                        "id": "u1",
                        "role": "staff",
                        "tags": tags,
                    }
                    local_session["_aj_user_cached_at"] = 9_999_999_999.0
                response = client.get(f"/tag/{requested}")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.get_json(),
                    {"present": expected},
                )

    def test_flask_has_tag_returns_false_without_a_session(self):
        response = self.make_app().test_client().get("/tag/finance")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"present": False})


if __name__ == "__main__":
    unittest.main()
