from datetime import datetime, timezone
from hashlib import sha256
from unittest.mock import Mock

from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
import pytest

from app.dao.organisation_dao import get_organisation_dao
from app.dependencies.auth import require_authenticated_user
from app.models.auth import CurrentUser
from app.models.organisation import MembershipStatus, OrganisationRole, OrganisationStatus
from app.models.property import PropertyCreate, PropertyStatus, PropertyUpdate
from app.services.property_service import PROVISIONING_FIELDS, PropertyConflictError
from tests.test_property import property_context, create, transaction_error


def complete_payload(mode="REQUEST"):
    return {
        "title": "Perth apartment", "description": "Sunny apartment near the city", "address": "Private street address",
        "public_location": "Perth, WA", "property_type": "Apartment", "price_per_night": "120.50",
        "currency": "AUD", "max_guests": 2, "images": ["https://example.com/apartment.jpg"],
        "booking_mode": mode, "min_nights": 1, "max_nights": 14, "preparation_nights": 0,
        "blocked_dates": ["2026-12-25", "2026-12-24"],
    }


@pytest.fixture
def provision_context(property_context):
    dao, org_dao, service, client, base, other = property_context
    client.app.dependency_overrides[get_organisation_dao] = lambda: org_dao
    return property_context


def public_base(base):
    return "/public" + base


def publish(client, path, version):
    return client.post(path + "/publish", json={"expected_version": version})


def test_incomplete_draft_shows_actionable_readiness_and_cannot_publish(provision_context):
    _, _, _, client, base, _ = provision_context
    first = create(client, base).json()
    path = base + "/" + first["property_id"]
    readiness = client.get(path + "/readiness").json()
    assert readiness["ready"] is False and readiness["can_publish"] is False
    missing = {issue["field"] for issue in readiness["issues"]}
    assert {"description", "images", "booking_mode", "min_nights", "max_nights", "preparation_nights", "public_location"} <= missing
    assert publish(client, path, 1).status_code == 422
    assert client.get(path).json() == first
    assert client.get(public_base(base) + "/" + first["property_id"]).status_code == 404


@pytest.mark.parametrize("mode", ["INSTANT", "REQUEST"])
def test_configure_publish_public_projection_deactivate_republish_and_archive(provision_context, mode):
    _, _, _, client, base, _ = provision_context
    first = create(client, base, complete_payload(mode)).json()
    path = base + "/" + first["property_id"]
    assert first["blocked_dates"] == ["2026-12-24", "2026-12-25"]
    assert client.get(path + "/readiness").json()["can_publish"]
    active = publish(client, path, 1)
    assert active.status_code == 200
    active = active.json()
    assert active["status"] == "ACTIVE" and active["published_at"] and active["version"] == 2
    assert publish(client, path, 2).json() == active
    assert publish(client, path, 1).status_code == 409
    listing = client.get(public_base(base) + "/" + first["property_id"])
    assert listing.status_code == 200
    public = listing.json()
    assert public["booking_mode"] == mode and public["price_per_night"] == "120.50"
    assert not {"address", "created_by", "version", "status", "published_at", "has_booking_history", "blocked_dates", "preparation_nights", "organisation_id"} & public.keys()
    assert client.get(public_base(base)).json()["items"] == [public]
    assert client.delete(path + "/draft", params={"expected_version": 2}).status_code == 409
    inactive = client.post(path + "/deactivate", json={"expected_version": 2}).json()
    assert inactive["status"] == "INACTIVE" and inactive["version"] == 3
    assert inactive["published_at"] == active["published_at"]
    assert client.get(public_base(base)).json()["items"] == []
    assert client.get(public_base(base) + "/" + first["property_id"]).status_code == 404
    assert client.post(path + "/deactivate", json={"expected_version": 3}).json() == inactive
    reactivated = publish(client, path, 3).json()
    assert reactivated["status"] == "ACTIVE" and reactivated["published_at"] == active["published_at"]
    archived = client.delete(path, params={"expected_version": 4}).json()
    assert archived["status"] == "ARCHIVED" and archived["published_at"] == active["published_at"]
    assert publish(client, path, 5).status_code == 409
    assert client.delete(path + "/draft", params={"expected_version": 5}).status_code == 409
    assert client.get(public_base(base)).json()["items"] == []


def test_active_mode_price_changes_preserve_identity_and_readiness(provision_context):
    _, _, _, client, base, _ = provision_context
    first = create(client, base, complete_payload()).json()
    path = base + "/" + first["property_id"]
    active = publish(client, path, 1).json()
    changed = client.patch(path, json={"booking_mode": "INSTANT", "price_per_night": "150.00", "expected_version": 2})
    assert changed.status_code == 200
    assert changed.json()["published_at"] == active["published_at"]
    assert changed.json()["status"] == "ACTIVE" and changed.json()["version"] == 3
    assert client.patch(path, json={"images": [], "expected_version": 3}).status_code == 422
    assert client.patch(path, json={"booking_mode": None, "expected_version": 3}).status_code == 422
    assert client.get(path).json() == changed.json()


def test_calendar_changes_fail_closed_if_booking_history_exists(provision_context):
    dao, _, _, client, base, _ = provision_context
    first = create(client, base, complete_payload()).json()
    property = dao.properties[(first["organisation_id"], first["property_id"])]
    property.has_booking_history = True
    path = base + "/" + first["property_id"]
    assert client.patch(path, json={"blocked_dates": [], "expected_version": 1}).status_code == 409
    assert client.patch(path, json={"preparation_nights": 1, "expected_version": 1}).status_code == 409
    assert client.patch(path, json={"booking_mode": "INSTANT", "expected_version": 1}).status_code == 200
    assert client.get(path).json()["has_booking_history"] is True


@pytest.mark.parametrize("patch", [
    {"min_nights": 0}, {"max_nights": 91}, {"preparation_nights": -1}, {"preparation_nights": 8},
    {"min_nights": True}, {"max_nights": 2.5}, {"min_nights": "2"},
    {"min_nights": 5, "max_nights": 2}, {"blocked_dates": ["invalid"]}, {"blocked_dates": [0]}, {"blocked_dates": ["2026-12-01T00:00:00Z"]},
    {"blocked_dates": ["2026-12-01", "2026-12-01"]}, {"blocked_dates": None},
    {"booking_mode": "invalid"}, {"public_location": "   "},
])
def test_invalid_configuration_is_rejected_without_writes(provision_context, patch):
    _, _, _, client, base, _ = provision_context
    first = create(client, base, complete_payload()).json()
    path = base + "/" + first["property_id"]
    response = client.patch(path, json={**patch, "expected_version": 1})
    assert response.status_code == 422
    assert client.get(path).json() == first


def test_partial_stay_patch_validates_against_saved_limits(provision_context):
    _, _, _, client, base, _ = provision_context
    first = create(client, base, complete_payload()).json()
    path = base + "/" + first["property_id"]
    assert client.patch(path, json={"min_nights": 15, "expected_version": 1}).status_code == 422
    assert client.get(path).json()["min_nights"] == 1


def test_unsupported_currency_draft_saves_but_cannot_publish(provision_context):
    _, _, _, client, base, _ = provision_context
    payload = complete_payload(); payload["currency"] = "XYZ"
    first = create(client, base, payload).json()
    path = base + "/" + first["property_id"]
    assert client.get(path + "/readiness").json()["issues"][0]["field"] == "currency"
    assert publish(client, path, 1).status_code == 422


def test_member_reads_readiness_but_cannot_change_mode_or_lifecycle(provision_context):
    _, org_dao, _, client, base, _ = provision_context
    first = create(client, base, complete_payload()).json()
    path = base + "/" + first["property_id"]
    org_dao.memberships[("alice", first["organisation_id"])].role = OrganisationRole.MEMBER
    assert client.get(path + "/readiness").status_code == 200
    assert publish(client, path, 1).status_code == 403
    assert client.post(path + "/deactivate", json={"expected_version": 1}).status_code == 403
    assert client.patch(path, json={"booking_mode": "INSTANT", "expected_version": 1}).status_code == 403


@pytest.mark.parametrize("action", ["publish", "deactivate"])
def test_lifecycle_requires_identity_and_cannot_inject_fields(provision_context, action):
    _, _, _, client, base, _ = provision_context
    first = create(client, base, complete_payload()).json()
    path = base + "/" + first["property_id"] + "/" + action
    assert client.post(path, json={"expected_version": 1, "status": "ACTIVE"}).status_code == 422
    assert client.post(path, json={"expected_version": True}).status_code == 422
    from app.services.authentication_service import get_authentication_service
    client.app.dependency_overrides.pop(require_authenticated_user)
    client.app.dependency_overrides[get_authentication_service] = lambda: Mock()
    assert client.post(path, json={"expected_version": 1}).status_code == 401


def test_public_visibility_is_anonymous_and_follows_organisation_status(provision_context):
    _, org_dao, _, client, base, other = provision_context
    first = create(client, base, complete_payload()).json()
    path = base + "/" + first["property_id"]
    assert publish(client, path, 1).status_code == 200
    client.app.dependency_overrides.pop(require_authenticated_user)
    assert client.get(public_base(base)).status_code == 200
    assert client.get(public_base(base) + "/" + first["property_id"]).status_code == 200
    assert client.get(f"/public/organisations/{other}/properties/{first['property_id']}").status_code == 404
    org_dao.organisations[first["organisation_id"]].status = OrganisationStatus.INACTIVE
    assert client.get(public_base(base)).status_code == 404
    assert client.get(public_base(base) + "/" + first["property_id"]).status_code == 404
    assert client.get("/public/organisations/missing/properties").status_code == 404


def test_public_pagination_retains_cursor_across_empty_filtered_pages(provision_context):
    dao, _, _, client, base, _ = provision_context
    first = create(client, base, complete_payload()).json()
    second = create(client, base, complete_payload(), key="two").json()
    ordered = sorted([first, second], key=lambda item: item["property_id"])
    assert publish(client, base + "/" + ordered[1]["property_id"], 1).status_code == 200
    page = client.get(public_base(base), params={"limit": 1}).json()
    assert page["items"] == [] and page["next_cursor"]
    next_page = client.get(public_base(base), params={"limit": 1, "cursor": page["next_cursor"]}).json()
    assert next_page["items"][0]["property_id"] == ordered[1]["property_id"]
    assert next_page["next_cursor"] is None


def test_legacy_creation_fingerprint_still_replays_without_new_config(provision_context):
    dao, _, service, client, base, _ = provision_context
    first = create(client, base).json()
    record = next(iter(dao.requests.values()))
    payload = PropertyCreate(title="First property")
    record["fingerprint"] = sha256(payload.model_dump_json(exclude=PROVISIONING_FIELDS).encode()).hexdigest()
    for field in PROVISIONING_FIELDS:
        record["property"].pop(field, None)
    assert create(client, base).json() == first
    assert create(client, base, {"title": "First property", "preparation_nights": 0}).status_code == 409


def test_publish_rechecks_permission_at_write_and_keeps_draft_on_failure(provision_context):
    dao, _, _, client, base, _ = provision_context
    first = create(client, base, complete_payload()).json()
    dao.replace_property = Mock(side_effect=transaction_error(["None", "None", "ConditionalCheckFailed", "None"]))
    assert publish(client, base + "/" + first["property_id"], 1).status_code == 403
    assert client.get(base + "/" + first["property_id"]).json() == first
