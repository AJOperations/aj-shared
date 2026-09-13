import threading
import time
import pytest
from aj_shared.transport import BoundedTransport, TransportPolicy
from aj_shared.hq_client import HQClient
from tests.test_hq_client import FakeSession, FakeResponse


def test_total_budget_and_capacity_isolation():
    release = threading.Event()

    class Slow:
        def request(self, *a, **kw):
            release.wait(2)
            return FakeResponse(200, {})

    transport = BoundedTransport(
        TransportPolicy(total=0.04, connect=0.01, read=0.02, capacity=1)
    )
    start = time.monotonic()
    try:
        result = transport.request(Slow(), "GET", "https://synthetic.example/read")
        assert result.body["failure_code"] == "timeout"
        assert time.monotonic() - start < 0.3
        assert (
            transport.request(Slow(), "GET", "https://synthetic.example/read").body[
                "failure_code"
            ]
            == "capacity"
        )
        assert (
            BoundedTransport()
            .request(
                FakeSession(FakeResponse(200, {})),
                "GET",
                "https://synthetic.example/read",
            )
            .status_code
            == 200
        )
    finally:
        release.set()


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "unauthenticated"),
        (403, "forbidden"),
        (429, "rate_limited"),
        (503, "unavailable"),
        (302, "redirect"),
    ],
)
def test_failure_mapping_redacts_bodies(status, code):
    result = BoundedTransport().request(
        FakeSession(FakeResponse(status, {"secret": "private"})),
        "GET",
        "https://synthetic.example/read",
        reference="synthetic-123",
    )
    assert result.body["failure_code"] == code
    assert result.body["reference_id"] == "synthetic-123"
    assert "private" not in str(result)


def test_write_ambiguity_no_retry_and_correlation():
    fake = FakeSession(error=TimeoutError("private"))
    result = BoundedTransport().request(fake, "POST", "https://synthetic.example/write")
    assert result.body["outcome_unknown"] is True
    assert len(fake.calls) == 1
    assert (
        fake.calls[0][2]["headers"]["X-AJ-Operation-Reference"]
        == result.body["reference_id"]
    )


def test_hq_opt_in_uses_budget_without_breaking_legacy_defaults():
    fake = FakeSession(FakeResponse(200, {}))
    client = HQClient(
        "https://synthetic.example",
        "synthetic-key",
        session=fake,
        transport_policy=TransportPolicy(),
    )
    assert client.get_json("/api/apps").status_code == 200
    assert fake.calls[0][2]["headers"]["X-AJ-Key"] == "synthetic-key"


@pytest.mark.parametrize(
    "body,headers,code",
    [
        (b"bad", {}, "invalid_response"),
        (b"x" * 10, {}, "oversized"),
        (b"{}", {"Content-Length": "-1"}, "oversized"),
    ],
)
def test_malformed_and_size_failures(body, headers, code):
    response = FakeResponse(200, body, headers)
    result = BoundedTransport(TransportPolicy(max_bytes=5)).request(
        FakeSession(response),
        "GET",
        "https://synthetic.example/read",
        headers={"X-AJ-Operation-Reference": "forwarded-123"},
    )
    assert result.body["failure_code"] == code
    assert result.body["reference_id"] == "forwarded-123"
    assert response.closed
