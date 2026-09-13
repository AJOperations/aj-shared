"""Opt-in dependency budgets; one transport per app/dependency, no retry stack.

A daemon worker bounds caller elapsed time even for stalled DNS/custom adapters.
Timed-out workers retain their capacity slot until they exit; there is no queue
or unbounded thread growth. Reuse the transport, do not construct per request.
"""

import json
import math
import threading
import time
from dataclasses import dataclass
from queue import Queue, Empty
from urllib.parse import urlsplit
from .suite import operation_reference


@dataclass(frozen=True)
class TransportPolicy:
    connect: float = 1.0
    read: float = 2.0
    total: float = 4.0
    max_bytes: int = 2 * 1024 * 1024
    capacity: int = 4

    def __post_init__(self):
        for value in (self.connect, self.read, self.total):
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or not 0 < value <= 300
            ):
                raise ValueError("Invalid timeout")
        if (
            type(self.max_bytes) is not int
            or not 1 <= self.max_bytes <= 16 * 1024 * 1024
        ):
            raise ValueError("Invalid size bound")
        if type(self.capacity) is not int or not 1 <= self.capacity <= 32:
            raise ValueError("Invalid capacity")


@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    body: dict


class BoundedTransport:
    def __init__(self, policy=None):
        self.policy = policy or TransportPolicy()
        self._slots = threading.BoundedSemaphore(self.policy.capacity)

    def request(self, session, method, url, *, reference=None, **kwargs):
        ref = operation_reference(
            reference or kwargs.get("headers", {}).get("X-AJ-Operation-Reference")
        )
        method = method.upper()
        write = method not in ("GET", "HEAD", "OPTIONS")

        def failure(code, status=502, ambiguous=False):
            return TransportResponse(
                status,
                dict(
                    error="Dependency request did not complete",
                    failure_code=code,
                    reference_id=ref,
                    retryable=not write
                    and code in ("timeout", "capacity", "unavailable", "rate_limited"),
                    outcome_unknown=bool(write and ambiguous),
                ),
            )

        parsed = urlsplit(url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            return failure("invalid_destination")
        if not self._slots.acquire(blocking=False):
            return failure("capacity")
        result = Queue(maxsize=1)
        deadline = time.monotonic() + self.policy.total
        headers = dict(kwargs.pop("headers", {}))
        headers["X-AJ-Operation-Reference"] = ref
        # Callers cannot override configured bounds or redirect policy.
        for key in ("timeout", "stream", "allow_redirects"):
            kwargs.pop(key, None)

        def run():
            response = None
            try:
                response = session.request(
                    method,
                    url,
                    headers=headers,
                    timeout=(
                        min(self.policy.connect, self.policy.total),
                        min(self.policy.read, self.policy.total),
                    ),
                    stream=True,
                    allow_redirects=False,
                    **kwargs,
                )
                code = response.status_code
                if 300 <= code < 400:
                    result.put(failure("redirect"))
                    return
                if code in (401, 403, 429) or code >= 500:
                    reason = {
                        401: "unauthenticated",
                        403: "forbidden",
                        429: "rate_limited",
                    }.get(code, "unavailable")
                    result.put(failure(reason, code, code >= 500))
                    return
                declared = response.headers.get("Content-Length")
                if declared is not None and (
                    not str(declared).isdigit() or int(declared) > self.policy.max_bytes
                ):
                    result.put(failure("oversized", ambiguous=write))
                    return
                raw = bytearray()
                for chunk in response.iter_content(chunk_size=16384):
                    if time.monotonic() >= deadline:
                        result.put(failure("timeout", ambiguous=write))
                        return
                    if len(raw) + len(chunk) > self.policy.max_bytes:
                        result.put(failure("oversized", ambiguous=write))
                        return
                    raw.extend(chunk)
                body = (
                    {} if code == 204 and not raw else json.loads(raw.decode("utf-8"))
                )
                if type(body) is not dict:
                    raise ValueError("Invalid JSON shape")
                if code >= 400:
                    result.put(failure("rejected", code))
                    return
                result.put(TransportResponse(code, body))
            except (TimeoutError,):
                result.put(failure("timeout", ambiguous=write))
            except Exception as exc:
                import requests

                result.put(
                    failure(
                        (
                            "timeout"
                            if isinstance(exc, requests.exceptions.Timeout)
                            else "invalid_response"
                        ),
                        ambiguous=write,
                    )
                )
            finally:
                if response is not None:
                    try:
                        response.close()
                    except Exception:
                        pass
                self._slots.release()

        threading.Thread(target=run, daemon=True, name="aj-dependency").start()
        try:
            return result.get(timeout=max(0, deadline - time.monotonic()))
        except Empty:
            return failure("timeout", ambiguous=write)
