"""Framework-neutral, fail-closed HTTP client for the AJ HQ contract."""

from dataclasses import dataclass
from typing import Any, Mapping, Optional

import requests


@dataclass(frozen=True)
class HQResponse:
    status_code: int
    body: dict[str, Any]


class HQClient:
    def __init__(
        self,
        base_url: str,
        platform_secret: str,
        *,
        timeout: int = 5,
        session: Any = None,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("HQ base URL must be absolute HTTP(S)")
        if not platform_secret:
            raise ValueError("PLATFORM_SECRET is required")
        self.base_url = base_url.rstrip("/")
        self.platform_secret = platform_secret
        self.timeout = timeout
        self.session = session or requests.Session()

    def _request(self, method: str, path: str, **kwargs: Any) -> HQResponse:
        headers = dict(kwargs.pop("headers", {}))
        headers["X-AJ-Key"] = self.platform_secret
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                timeout=self.timeout,
                **kwargs,
            )
            body = response.json()
            if not isinstance(body, dict):
                return HQResponse(502, {"error": "Invalid HQ response"})
            return HQResponse(response.status_code, body)
        except Exception:
            return HQResponse(502, {"error": "HQ temporarily unavailable"})

    def validate(self, token: Optional[str] = None) -> Optional[dict[str, Any]]:
        response = self._request(
            "GET", "/auth/validate", params={"token": token} if token else {}
        )
        if response.status_code == 200 and response.body.get("valid"):
            user = response.body.get("user")
            return user if isinstance(user, dict) else None
        return None

    def get_json(
        self, path: str, params: Optional[Mapping[str, str]] = None
    ) -> HQResponse:
        return self._request("GET", path, params=dict(params or {}))

    def post_json(
        self,
        path: str,
        payload: Mapping[str, Any],
        cookies: Optional[Mapping[str, str]] = None,
    ) -> HQResponse:
        return self._request(
            "POST", path, json=dict(payload), cookies=dict(cookies or {})
        )

    def post_multipart(
        self, path: str, data: Mapping[str, Any], files: Mapping[str, Any]
    ) -> HQResponse:
        return self._request("POST", path, data=dict(data), files=dict(files))
