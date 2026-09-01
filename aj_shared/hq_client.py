"""Framework-neutral, fail-closed HTTP client for the AJ HQ contract."""

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Optional

import requests

logger = logging.getLogger(__name__)

MAX_JSON_RESPONSE_BYTES = 2 * 1024 * 1024

# AJ Core v1 read/write contracts (see AJOperations/aj-hq's Core Candidate
# Schema implementation). A hard version prefix, unlike the rest of HQ's
# legacy routes — a breaking change there lands at /api/core/v2/, not here.
CORE_API_PREFIX = "/api/core/v1"

# Scopes a service credential (people_service_access on the HQ side) can be
# granted for Core reads/writes, via the X-AJ-Service / X-AJ-Service-Key
# headers. Documentation, not enforcement — HQ is the sole authority on what
# a given credential is actually allowed to do. Every Core *read* route also
# accepts the ambient PLATFORM_SECRET (X-AJ-Key), same as HQ's existing
# routes, so HQClient's default constructor already works for reads with no
# extra setup. Core *writes* (Vendor/Project Series creation) deliberately do
# not accept PLATFORM_SECRET — pass service_id/service_key to the
# constructor for those.
CORE_SERVICE_SCOPES = frozenset({
    "core.person.read",
    "core.client.read",
    "core.pricing_role.read",
    "core.discipline.read",
    "core.vendor.read",
    "core.vendor.write",
    "core.series.read",
    "core.series.write",
})


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
        service_id: Optional[str] = None,
        service_key: Optional[str] = None,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("HQ base URL must be absolute HTTP(S)")
        if not platform_secret:
            raise ValueError("PLATFORM_SECRET is required")
        self.base_url = base_url.rstrip("/")
        self.platform_secret = platform_secret
        self.timeout = timeout
        self.session = session or requests.Session()
        # Optional scoped Core service credential (see CORE_SERVICE_SCOPES).
        # Sent alongside X-AJ-Key on every request when both are supplied —
        # harmless on routes that only check the platform secret, and
        # required on the Core write routes that deliberately don't accept
        # PLATFORM_SECRET at all.
        self.service_id = service_id
        self.service_key = service_key

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
        if self.service_id and self.service_key:
            headers["X-AJ-Service"] = self.service_id
            headers["X-AJ-Service-Key"] = self.service_key
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

    # -----------------------------------------------------------------
    # AJ Core v1 — thin path/param wrappers over get_json/post_json.
    #
    # Deliberately as thin as the rest of this client: no per-entity
    # dataclasses, no unwrapping into None on failure/404. Callers get the
    # same HQResponse(status_code, body) shape as everything else here, so a
    # 502 "HQ temporarily unavailable" (Core down) stays distinguishable
    # from a 404 (no such entity) — collapsing those into one sentinel would
    # lose information a caller may need to degrade gracefully per
    # AJOperations/aj-hq's Core Candidate Schema resilience requirement.
    # -----------------------------------------------------------------

    @staticmethod
    def _list_params(
        limit: Optional[int] = None, cursor: Optional[str] = None, **extra: Any
    ) -> dict[str, str]:
        params: dict[str, str] = {}
        if limit is not None:
            params["limit"] = str(limit)
        if cursor:
            params["cursor"] = cursor
        for key, value in extra.items():
            if value:
                params[key] = str(value)
        return params

    def get_core_person(self, core_person_id: str) -> HQResponse:
        return self.get_json(f"{CORE_API_PREFIX}/people/{core_person_id}")

    def list_core_people(
        self, limit: Optional[int] = None, cursor: Optional[str] = None
    ) -> HQResponse:
        return self.get_json(f"{CORE_API_PREFIX}/people", self._list_params(limit, cursor))

    def get_core_client(self, core_client_id: str) -> HQResponse:
        return self.get_json(f"{CORE_API_PREFIX}/clients/{core_client_id}")

    def list_core_clients(
        self, limit: Optional[int] = None, cursor: Optional[str] = None
    ) -> HQResponse:
        return self.get_json(f"{CORE_API_PREFIX}/clients", self._list_params(limit, cursor))

    def get_core_pricing_role(self, core_pricing_role_id: str) -> HQResponse:
        return self.get_json(f"{CORE_API_PREFIX}/pricing-roles/{core_pricing_role_id}")

    def list_core_pricing_roles(self) -> HQResponse:
        return self.get_json(f"{CORE_API_PREFIX}/pricing-roles")

    def list_core_disciplines(self) -> HQResponse:
        return self.get_json(f"{CORE_API_PREFIX}/disciplines")

    def get_core_vendor(self, core_vendor_id: str) -> HQResponse:
        return self.get_json(f"{CORE_API_PREFIX}/vendors/{core_vendor_id}")

    def list_core_vendors(
        self, q: Optional[str] = None, limit: Optional[int] = None, cursor: Optional[str] = None
    ) -> HQResponse:
        return self.get_json(f"{CORE_API_PREFIX}/vendors", self._list_params(limit, cursor, q=q))

    def create_core_vendor(self, display_name: str, notes: Optional[str] = None) -> HQResponse:
        """Requires a service credential with core.vendor.write — pass
        service_id/service_key to the constructor. PLATFORM_SECRET alone is
        not accepted by this route. Never de-duplicates by display_name: per
        Decisions, Vendor identity must never be inferred from free text, so
        calling this twice with the same name creates two distinct vendors."""
        payload: dict[str, Any] = {"display_name": display_name}
        if notes is not None:
            payload["notes"] = notes
        return self.post_json(f"{CORE_API_PREFIX}/vendors", payload)

    def get_core_project_series(self, project_series_id: str) -> HQResponse:
        return self.get_json(f"{CORE_API_PREFIX}/project-series/{project_series_id}")

    def list_core_project_series(
        self,
        core_client_id: Optional[str] = None,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> HQResponse:
        return self.get_json(
            f"{CORE_API_PREFIX}/project-series",
            self._list_params(limit, cursor, core_client_id=core_client_id),
        )

    def create_core_project_series(
        self, core_client_id: str, series_name: str, series_type: Optional[str] = None
    ) -> HQResponse:
        """Requires a service credential with core.series.write — same
        auth note as create_core_vendor. Per Decisions, Project Series is
        never inferred from a Job's end_date/year or fuzzy name matching;
        every call here should come from an exact-key source (e.g. a
        HubSpot Signature Event value) or an explicit human action."""
        payload: dict[str, Any] = {"core_client_id": core_client_id, "series_name": series_name}
        if series_type is not None:
            payload["series_type"] = series_type
        return self.post_json(f"{CORE_API_PREFIX}/project-series", payload)
