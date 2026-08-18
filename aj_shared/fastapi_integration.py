"""FastAPI integration for AJ HQ authentication and signed local sessions."""

import json
import hmac
import secrets
import time
from typing import Any, Awaitable, Callable, Optional, Sequence
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse, RedirectResponse, Response

from .contract import CONTRACT_VERSION, get_aj_shared_version
from .hq_client import HQClient

_FEEDBACK_MAX_BYTES = 5 * 1024 * 1024


class FastAPIHQ:
    """Install HQ authentication and authorization helpers on a FastAPI app."""

    _ROLE_LEVELS = {"staff": 0, "leadership": 1, "admin": 2}
    _DEFAULT_PUBLIC_PATHS = (
        "/health",
        "/ready",
        "/static/",
        "/api/apps",
        "/auth/validate",
        "/auth/logout",
        "/api/contract",
    )

    def __init__(
        self,
        *,
        app_name: str,
        hq_base: str,
        app_base_url: str,
        app_secret_key: str,
        platform_secret: str,
        session_ttl_seconds: int = 1200,
        production: bool = True,
        client: Optional[HQClient] = None,
    ) -> None:
        self.app_name = app_name
        self.hq_base = self._absolute_url(hq_base, "HQ base URL").rstrip("/")
        self.app_base_url = self._absolute_url(
            app_base_url, "app base URL"
        ).rstrip("/")
        if not app_secret_key:
            raise ValueError("APP_SECRET_KEY is required")
        if not platform_secret:
            raise ValueError("PLATFORM_SECRET is required")
        if session_ttl_seconds <= 0:
            raise ValueError("session TTL must be positive")
        self.app_secret_key = app_secret_key
        self.platform_secret = platform_secret
        self.session_ttl_seconds = session_ttl_seconds
        self.production = production
        self.client = client or HQClient(self.hq_base, platform_secret)
        self.public_paths: tuple[str, ...] = self._DEFAULT_PUBLIC_PATHS

    @staticmethod
    def _absolute_url(value: str, label: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"{label} must be absolute HTTP(S)")
        return value

    def install(self, app: Any, *, public_paths: Sequence[str] = ()) -> None:
        """Attach middleware and expose this integration through ``app.state``."""
        self.public_paths = tuple(dict.fromkeys((*self._DEFAULT_PUBLIC_PATHS, *public_paths)))
        app.state.aj_hq = self

        @app.middleware("http")
        async def authenticate(
            request: Request,
            call_next: Callable[[Request], Awaitable[Response]],
        ) -> Response:
            token = request.query_params.get("token")
            if token is not None and request.url.path != "/auth/validate":
                user = self.client.validate(token)
                self.clear_session(request)
                clean_url = self._request_url(request, strip_token=True)
                if user is not None:
                    request.session["_aj_user"] = user
                    request.session["_aj_user_cached_at"] = time.time()
                    request.session["_aj_csrf"] = secrets.token_urlsafe(32)
                    if request.method in {"GET", "HEAD"}:
                        return RedirectResponse(clean_url, status_code=307)
                    return await call_next(request)
                if request.method in {"GET", "HEAD"}:
                    return self._login_redirect(clean_url)
                return JSONResponse({"error": "Unauthorized"}, status_code=401)

            if self._is_public(request.url.path):
                return await call_next(request)
            if self._session_user(request) is None:
                return self._login_redirect(self._request_url(request))
            return await call_next(request)

        # Added after the auth middleware so it wraps auth and makes request.session
        # available before authentication runs.
        app.add_middleware(
            SessionMiddleware,
            secret_key=self.app_secret_key,
            session_cookie="aj_app_session",
            max_age=self.session_ttl_seconds,
            same_site="lax",
            https_only=self.production,
        )

    def _is_public(self, path: str) -> bool:
        for public_path in self.public_paths:
            if public_path.endswith("/"):
                if path.startswith(public_path):
                    return True
            elif path == public_path:
                return True
        return False

    def _request_url(self, request: Request, *, strip_token: bool = False) -> str:
        query_items = list(request.query_params.multi_items())
        if strip_token:
            query_items = [(key, value) for key, value in query_items if key != "token"]
        url = f"{self.app_base_url}{request.url.path}"
        if query_items:
            url = f"{url}?{urlencode(query_items)}"
        return url

    def _login_redirect(self, next_url: str) -> RedirectResponse:
        return RedirectResponse(
            f"{self.hq_base}/login?{urlencode({'next': next_url})}",
            status_code=307,
        )

    def _session_user(self, request: Request) -> Optional[dict[str, Any]]:
        user = request.session.get("_aj_user")
        cached_at = request.session.get("_aj_user_cached_at")
        try:
            fresh = time.time() - float(cached_at) < self.session_ttl_seconds
        except (TypeError, ValueError):
            fresh = False
        if isinstance(user, dict) and fresh:
            return user
        self.clear_session(request)
        return None

    def current_user(self, request: Request) -> Optional[dict[str, Any]]:
        return self._session_user(request)

    async def require_user(self, request: Request) -> dict[str, Any]:
        user = self.current_user(request)
        if user is None:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return user

    def require_role(self, required_role: str) -> Callable[[Request], Awaitable[dict[str, Any]]]:
        if required_role not in self._ROLE_LEVELS:
            raise ValueError(f"unknown role: {required_role}")

        async def dependency(request: Request) -> dict[str, Any]:
            user = await self.require_user(request)
            role_level = self._ROLE_LEVELS.get(str(user.get("role")), -1)
            if role_level < self._ROLE_LEVELS[required_role]:
                raise HTTPException(status_code=403, detail="Forbidden")
            return user

        return dependency

    def has_tag(self, request: Request, tag: str) -> bool:
        user = self.current_user(request)
        if user is None:
            return False
        tags = user.get("tags", [])
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (TypeError, json.JSONDecodeError):
                return False
        return isinstance(tags, list) and tag in tags

    def csrf_token(self, request: Request) -> str:
        if self.current_user(request) is None:
            return ""
        token = request.session.get("_aj_csrf")
        return token if isinstance(token, str) else ""

    async def require_csrf(self, request: Request) -> None:
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return
        expected = self.csrf_token(request)
        if not expected:
            raise HTTPException(status_code=403, detail="Forbidden")
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return
        form = await request.form()
        supplied = form.get("_csrf", "")
        if not isinstance(supplied, str) or not hmac.compare_digest(
            supplied, expected
        ):
            raise HTTPException(status_code=403, detail="Forbidden")

    @staticmethod
    def _json_response(result: Any) -> JSONResponse:
        return JSONResponse(result.body, status_code=result.status_code)

    @staticmethod
    def _query_params(request: Request) -> dict[str, str]:
        return {key: value for key, value in request.query_params.multi_items()}

    async def _json_body(self, request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            return {}
        return body if isinstance(body, dict) else {}

    def install_standard_routes(self, app: Any) -> None:
        """Register the standard HQ proxy and package contract routes."""
        router = APIRouter()

        # These routes use dependencies for JSON 401/403 responses, so let
        # them pass through browser-oriented redirect middleware first.
        route_public_paths = (
            "/api/users",
            "/api/rates",
            "/api/rates/lookup",
            "/api/people",
            "/api/codes",
            "/api/codes/fees",
            "/api/codes/expenses",
            "/api/jobs",
            "/api/jobs/",
            "/api/clients",
            "/api/contracts",
            "/api/users/me/password",
            "/api/feedback",
            "/api/dropbox/list",
            "/api/dropbox/upload",
            "/api/email/send",
            "/api/monday/query",
            "/api/apps/all",
        )
        self.public_paths = tuple(
            dict.fromkeys((*self.public_paths, *route_public_paths))
        )

        @router.get("/api/apps")
        async def proxy_apps(
            user: dict[str, Any] = Depends(self.require_user),
        ) -> JSONResponse:
            result = self.client.get_json(
                "/api/apps", {"role": str(user.get("role", "staff"))}
            )
            return self._json_response(result)

        @router.get("/api/apps/all")
        async def proxy_apps_all(
            user: dict[str, Any] = Depends(self.require_role("admin")),
        ) -> JSONResponse:
            return self._json_response(self.client.get_json("/api/apps/all"))

        @router.get("/auth/validate")
        async def proxy_auth_validate(request: Request) -> JSONResponse:
            cached = self.current_user(request)
            if cached is not None:
                return JSONResponse({"valid": True, "user": cached})
            token = request.query_params.get("token")
            params = {"token": token} if token else {}
            return self._json_response(
                self.client.get_json("/auth/validate", params)
            )

        @router.post(
            "/auth/logout",
            dependencies=[Depends(self.require_csrf)],
        )
        async def proxy_auth_logout(request: Request) -> JSONResponse:
            self.clear_session(request)
            return JSONResponse({"ok": True})

        def get_proxy(upstream_path: str):
            async def proxy(
                request: Request,
                user: dict[str, Any] = Depends(self.require_user),
            ) -> JSONResponse:
                return self._json_response(
                    self.client.get_json(
                        upstream_path, self._query_params(request)
                    )
                )

            return proxy

        get_routes = (
            "/api/users",
            "/api/rates",
            "/api/rates/lookup",
            "/api/people",
            "/api/codes",
            "/api/codes/fees",
            "/api/codes/expenses",
            "/api/jobs",
            "/api/clients",
            "/api/contracts",
            "/api/dropbox/list",
        )
        for route in get_routes:
            router.add_api_route(
                route,
                get_proxy(route),
                methods=["GET"],
                name=f"aj_proxy_{route.strip('/').replace('/', '_')}",
            )

        @router.get("/api/jobs/{job_number}")
        async def proxy_job(
            job_number: str,
            user: dict[str, Any] = Depends(self.require_user),
        ) -> JSONResponse:
            return self._json_response(
                self.client.get_json(f"/api/jobs/{job_number}")
            )

        async def post_json(request: Request, upstream_path: str) -> JSONResponse:
            payload = await self._json_body(request)
            cookies = None
            if upstream_path == "/api/users/me/password":
                cookies = {"aj_session": request.cookies.get("aj_session", "")}
            return self._json_response(
                self.client.post_json(upstream_path, payload, cookies=cookies)
            )

        @router.post(
            "/api/users/me/password",
            dependencies=[Depends(self.require_user), Depends(self.require_csrf)],
        )
        async def proxy_password(request: Request) -> JSONResponse:
            return await post_json(request, "/api/users/me/password")

        @router.post(
            "/api/email/send",
            dependencies=[Depends(self.require_user), Depends(self.require_csrf)],
        )
        async def proxy_email(request: Request) -> JSONResponse:
            return await post_json(request, "/api/email/send")

        @router.post(
            "/api/monday/query",
            dependencies=[Depends(self.require_user), Depends(self.require_csrf)],
        )
        async def proxy_monday_query(request: Request) -> JSONResponse:
            return await post_json(request, "/api/monday/query")

        async def post_multipart(
            request: Request, upstream_path: str
        ) -> JSONResponse:
            form = await request.form()
            data: dict[str, Any] = {}
            files: dict[str, Any] = {}
            for key, value in form.multi_items():
                if hasattr(value, "filename"):
                    if value.filename:
                        if (
                            upstream_path == "/api/feedback"
                            and key == "screenshot"
                            and isinstance(getattr(value, "size", None), int)
                            and value.size > _FEEDBACK_MAX_BYTES
                        ):
                            return JSONResponse(
                                {"error": "Screenshot must be 5 MB or smaller."},
                                status_code=413,
                            )
                        files[key] = (
                            value.filename,
                            value.file,
                            value.content_type,
                        )
                else:
                    data[key] = value
            return self._json_response(
                self.client.post_multipart(upstream_path, data, files)
            )

        @router.post(
            "/api/feedback",
            dependencies=[Depends(self.require_user), Depends(self.require_csrf)],
        )
        async def proxy_feedback(request: Request) -> JSONResponse:
            return await post_multipart(request, "/api/feedback")

        @router.post(
            "/api/dropbox/upload",
            dependencies=[Depends(self.require_user), Depends(self.require_csrf)],
        )
        async def proxy_dropbox_upload(request: Request) -> JSONResponse:
            return await post_multipart(request, "/api/dropbox/upload")

        @router.get("/api/contract")
        async def contract(request: Request) -> JSONResponse:
            supplied = request.headers.get("X-AJ-Key", "")
            if not hmac.compare_digest(supplied, self.platform_secret):
                raise HTTPException(status_code=401, detail="Unauthorized")
            return JSONResponse(
                {
                    "app_name": self.app_name,
                    "contract_version": CONTRACT_VERSION,
                    "aj_shared_version": get_aj_shared_version(),
                }
            )

        app.include_router(router)

    def clear_session(self, request: Request) -> None:
        request.session.clear()
