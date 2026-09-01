"""AJ Core v1 convenience methods on HQClient.

Thin path/param wrappers only — no per-entity dataclasses, no collapsing a
502 (Core unavailable) and a 404 (no such entity) into one sentinel value,
matching the rest of this client's existing style.
"""
from aj_shared.hq_client import CORE_API_PREFIX, CORE_SERVICE_SCOPES, HQClient
from tests.test_hq_client import FakeResponse, FakeSession


def _client(session, **kwargs):
    return HQClient("https://hq.example", "platform", session=session, **kwargs)


def test_core_api_prefix_is_versioned():
    assert CORE_API_PREFIX == "/api/core/v1"


def test_core_service_scopes_cover_every_read_and_write_scope():
    assert CORE_SERVICE_SCOPES == {
        "core.person.read", "core.client.read",
        "core.pricing_role.read", "core.discipline.read",
        "core.vendor.read", "core.vendor.write",
        "core.series.read", "core.series.write",
    }


def test_get_core_person_builds_the_correct_path():
    session = FakeSession(FakeResponse(200, {"core_person_id": "p_1"}))
    response = _client(session).get_core_person("p_1")

    assert response.status_code == 200
    assert response.body == {"core_person_id": "p_1"}
    method, url, _ = session.calls[0]
    assert (method, url) == ("GET", "https://hq.example/api/core/v1/people/p_1")


def test_list_core_people_forwards_limit_and_cursor():
    session = FakeSession(FakeResponse(200, {"items": [], "next_cursor": None}))
    _client(session).list_core_people(limit=25, cursor="abc123")

    _, url, kwargs = session.calls[0]
    assert url == "https://hq.example/api/core/v1/people"
    assert kwargs["params"] == {"limit": "25", "cursor": "abc123"}


def test_list_core_people_omits_absent_params():
    session = FakeSession(FakeResponse(200, {"items": []}))
    _client(session).list_core_people()

    _, _, kwargs = session.calls[0]
    assert kwargs["params"] == {}


def test_get_core_client_builds_the_correct_path():
    session = FakeSession(FakeResponse(200, {"core_client_id": "cl_1"}))
    response = _client(session).get_core_client("cl_1")

    assert response.status_code == 200
    _, url, _ = session.calls[0]
    assert url == "https://hq.example/api/core/v1/clients/cl_1"


def test_get_core_pricing_role_and_list():
    session = FakeSession(FakeResponse(200, {"role_title": "Producer"}))
    _client(session).get_core_pricing_role("producer")
    _, url, _ = session.calls[0]
    assert url == "https://hq.example/api/core/v1/pricing-roles/producer"

    session2 = FakeSession(FakeResponse(200, {"items": []}))
    _client(session2).list_core_pricing_roles()
    _, url2, _ = session2.calls[0]
    assert url2 == "https://hq.example/api/core/v1/pricing-roles"


def test_list_core_disciplines():
    session = FakeSession(FakeResponse(200, {"items": [{"discipline_id": "creative"}]}))
    response = _client(session).list_core_disciplines()

    assert response.body == {"items": [{"discipline_id": "creative"}]}
    _, url, _ = session.calls[0]
    assert url == "https://hq.example/api/core/v1/disciplines"


def test_list_core_vendors_forwards_search_query():
    session = FakeSession(FakeResponse(200, {"items": []}))
    _client(session).list_core_vendors(q="Acme")

    _, url, kwargs = session.calls[0]
    assert url == "https://hq.example/api/core/v1/vendors"
    assert kwargs["params"] == {"q": "Acme"}


def test_create_core_vendor_sends_display_name_and_notes():
    session = FakeSession(FakeResponse(201, {"core_vendor_id": "v_1"}))
    response = _client(session).create_core_vendor("Acme Rentals", notes="AV house")

    assert response.status_code == 201
    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url == "https://hq.example/api/core/v1/vendors"
    assert kwargs["json"] == {"display_name": "Acme Rentals", "notes": "AV house"}


def test_create_core_vendor_omits_notes_when_absent():
    session = FakeSession(FakeResponse(201, {"core_vendor_id": "v_2"}))
    _client(session).create_core_vendor("Acme Rentals")

    _, _, kwargs = session.calls[0]
    assert kwargs["json"] == {"display_name": "Acme Rentals"}


def test_create_core_vendor_attaches_scoped_service_credential_when_configured():
    session = FakeSession(FakeResponse(201, {"core_vendor_id": "v_3"}))
    client = _client(session, service_id="my-app", service_key="secret-key")
    client.create_core_vendor("Acme Rentals")

    _, _, kwargs = session.calls[0]
    assert kwargs["headers"]["X-AJ-Service"] == "my-app"
    assert kwargs["headers"]["X-AJ-Service-Key"] == "secret-key"
    # PLATFORM_SECRET still travels alongside it — harmless on routes that
    # only check one or the other.
    assert kwargs["headers"]["X-AJ-Key"] == "platform"


def test_no_service_headers_are_sent_when_not_configured():
    session = FakeSession(FakeResponse(200, {"items": []}))
    _client(session).list_core_vendors()

    _, _, kwargs = session.calls[0]
    assert "X-AJ-Service" not in kwargs["headers"]
    assert "X-AJ-Service-Key" not in kwargs["headers"]


def test_get_core_project_series_and_filtered_list():
    session = FakeSession(FakeResponse(200, {"project_series_id": "ps_1"}))
    _client(session).get_core_project_series("ps_1")
    _, url, _ = session.calls[0]
    assert url == "https://hq.example/api/core/v1/project-series/ps_1"

    session2 = FakeSession(FakeResponse(200, {"items": []}))
    _client(session2).list_core_project_series(core_client_id="cl_1", limit=10)
    _, url2, kwargs2 = session2.calls[0]
    assert url2 == "https://hq.example/api/core/v1/project-series"
    assert kwargs2["params"] == {"limit": "10", "core_client_id": "cl_1"}


def test_create_core_project_series_sends_required_and_optional_fields():
    session = FakeSession(FakeResponse(201, {"project_series_id": "ps_2"}))
    response = _client(session).create_core_project_series(
        "cl_1", "Annual Signature Event", series_type="event"
    )

    assert response.status_code == 201
    _, url, kwargs = session.calls[0]
    assert url == "https://hq.example/api/core/v1/project-series"
    assert kwargs["json"] == {
        "core_client_id": "cl_1",
        "series_name": "Annual Signature Event",
        "series_type": "event",
    }


def test_core_calls_degrade_to_a_typed_unavailable_response_on_failure():
    session = FakeSession(error=TimeoutError("upstream detail"))
    response = _client(session).get_core_person("p_1")

    assert response.status_code == 502
    assert response.body["error"] == "HQ temporarily unavailable"
    assert "upstream detail" not in str(response.body)
