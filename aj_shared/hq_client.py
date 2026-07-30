"""Framework-neutral, fail-closed HTTP client for the AJ HQ contract."""

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Optional

import requests

logger = logging.getLogger(__name__)

MAX_JSON_RESPONSE_BYTES = 2 * 1024 * 1024


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

    @staticmethod
    def _failure(*, exc: Optional[Exception] = None, detail: Optional[str] = None) -> HQResponse:
        reference_id = uuid.uuid4().hex[:12]
        fields = {"operation": "hq_request", "reference_id": reference_id}
        if exc is not None:
            fields["exception_type"] = type(exc).__name__
        if detail is not None:
            fields["detail"] = detail
        logger.error(
            "hq_client_failure %s",
            " ".join(f"{key}={value}" for key, value in fields.items()),
        )
        return HQResponse(
            502,
            {
                "error": "HQ temporarily unavailable",
                "reference_id": reference_id,
            },
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> HQResponse:
        headers = dict(kwargs.pop("headers", {}))
        headers["X-AJ-Key"] = self.platform_secret
        response = None
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                timeout=self.timeout,
                allow_redirects=False,
                stream=True,
                **kwargs,
            )
            if 300 <= response.status_code < 400:
                return self._failure(detail="unexpected_redirect")

            declared_length = response.headers.get("Content-Length")
            if declared_length:
                try:
                    if int(declared_length) > MAX_JSON_RESPONSE_BYTES:
                        return self._failure(detail="response_too_large")
                except (TypeError, ValueError):
                    return self._failure(detail="invalid_content_length")

            raw = bytearray()
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                raw.extend(chunk)
                if len(raw) > MAX_JSON_RESPONSE_BYTES:
                    return self._failure(detail="response_too_large")

            if response.status_code == 204 and not raw:
                return HQResponse(204, {})
            body = json.loads(raw.decode("utf-8"))
            if not isinstance(body, dict):
                return self._failure(detail="invalid_json_shape")
            return HQResponse(response.status_code, body)
        except Exception as exc:
            return self._failure(exc=exc)
        finally:
            if response is not None:
                response.close()

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
