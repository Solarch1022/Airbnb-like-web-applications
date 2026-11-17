from copy import deepcopy
from unittest.mock import Mock

from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
import pytest

from app.dependencies.auth import require_authenticated_user
from app.main import create_app
from app.models.auth import CurrentUser
from app.models.organisation import OrganisationCreate, OrganisationRole, OrganisationStatus, MembershipStatus
from app.models.property import PropertyCreate, PropertyUpdate
from app.services.organisation_service import OrganisationService, get_organisation_service
from app.services.property_service import PropertyConflictError, PropertyService, get_property_service
from tests.test_organisation import FakeOrganisationDAO


def transaction_error(codes):
    return ClientError({"Error": {"Code": "TransactionCanceledException"},
                        "CancellationReasons": [{"Code": code} for code in codes]}, "TransactWriteItems")


class FakePropertyDAO:
    def __init__(self):
        self.properties = {}
        self.requests = {}
        self.deleted = set()

    def get_property(self, org, id):
        value = self.properties.get((org, id))
        return value.model_copy(deep=True) if value else None

    def get_creation_request(self, request_id):
        return deepcopy(self.requests.get(request_id))

    def list_properties(self, org, limit, after):
        items = sorted((p for (o, _), p in self.properties.items() if o == org), key=lambda p: p.property_id)
        items = [p for p in items if after is None or p.property_id > after]
        page = items[:limit]
        return page, page[-1].property_id if len(items) > limit else None

    def create_property(self, property, account_id, request_id, fingerprint):
        if request_id in self.requests:
            raise transaction_error(["None"] * 4 + ["ConditionalCheckFailed"])
        self.properties[(property.organisation_id, property.property_id)] = property.model_copy(deep=True)
        self.requests[request_id] = {"fingerprint": fingerprint, "property": property.model_dump(mode="json")}

    def is_deleted(self, org, id):
        return (org, id) in self.deleted

    def delete_draft(self, property, account_id, expected_version):
        key = (property.organisation_id, property.property_id)
        existing = self.properties.get(key)
        if (existing is None or existing.version != expected_version
            or existing.status not in ("DRAFT", "ARCHIVED")
            or existing.published_at is not None or existing.has_booking_history):
            raise transaction_error(["None"] * 3 + ["ConditionalCheckFailed", "None"])
        self.deleted.add(key)
        del self.properties[key]

    def replace_property(self, property, account_id, expected_version):
        key = (property.organisation_id, property.property_id)
        existing = self.properties.get(key)
        if existing is None or existing.version != expected_version or existing.status != "DRAFT":
            raise transaction_error(["None"] * 3 + ["ConditionalCheckFailed"])
        self.properties[key] = property.model_copy(deep=True)


@pytest.fixture
def property_context():
    org_dao = FakeOrganisationDAO()
    org_service = OrganisationService(org_dao)
    org = org_service.create("alice", OrganisationCreate(name="Own"), "own").organisation.organisation_id
    other = org_service.create("bob", OrganisationCreate(name="Other"), "other").organisation.organisation_id
    dao = FakePropertyDAO()
    service = PropertyService(dao)
    app = create_app()
    app.dependency_overrides[require_authenticated_user] = lambda: CurrentUser(account_id="alice", session_id="session")
    app.dependency_overrides[get_organisation_service] = lambda: org_service
    app.dependency_overrides[get_property_service] = lambda: service
    return dao, org_dao, service, TestClient(app), f"/organisations/{org}/properties", other


def create(client, base, payload=None, key="create-1"):
    return client.post(base, json=payload or {"title": "First property"}, headers={"Idempotency-Key": key})


def test_create_read_edit_archive_and_history(property_context):
    dao, _, _, client, base, _ = property_context
    response = create(client, base, {"title": "  First property  ", "price_per_night": "12.50", "currency": "AUD", "images": ["https://example.com/image.jpg"]})
    assert response.status_code == 201
    first = response.json()
    assert first["title"] == "First property" and first["status"] == "DRAFT"
    assert first["created_by"] == "alice" and first["version"] == 1
    assert first["booking_mode"] is None and first["price_per_night"] == "12.50"
    path = base + "/" + first["property_id"]
    assert client.get(path).json() == first
    changed = client.patch(path, json={"title": "Edited", "expected_version": 1})
    assert changed.status_code == 200 and changed.json()["version"] == 2
    assert changed.json()["created_at"] == first["created_at"]
    archived = client.delete(path, params={"expected_version": 2})
    assert archived.status_code == 200 and archived.json()["status"] == "ARCHIVED"
    assert archived.json()["version"] == 3
    assert client.get(path).json() == archived.json()
    assert client.delete(path, params={"expected_version": 3}).json() == archived.json()
    assert client.patch(path, json={"title": "Forbidden", "expected_version": 3}).status_code == 409
    assert client.get(base).json()["items"] == [archived.json()]
    assert len(dao.properties) == 1


def test_create_retries_return_original_snapshot_even_after_edit(property_context):
    dao, _, _, client, base, _ = property_context
    first = create(client, base).json()
    client.patch(base + "/" + first["property_id"], json={"title": "Changed", "expected_version": 1})
    assert create(client, base).json() == first
    assert create(client, base, {"title": "Changed"}).status_code == 409
    assert len(dao.properties) == len(dao.requests) == 1


@pytest.mark.parametrize("payload", [
    {"title": ""}, {"title": "   "}, {"title": "x" * 101},
    {"title": "Test", "property_id": "injected"}, {"title": "Test", "organisation_id": "other"},
    {"title": "Test", "created_by": "bob"}, {"title": "Test", "owner_id": "bob"},
    {"title": "Test", "status": "ACTIVE"}, {"title": "Test", "version": 20},
    {"title": "Test", "price_per_night": "0"}, {"title": "Test", "price_per_night": "1.001"},
    {"title": "Test", "price_per_night": "NaN"}, {"title": "Test", "currency": "aud"},
    {"title": "Test", "max_guests": 0}, {"title": "Test", "max_guests": True},
    {"title": "Test", "max_guests": 1.5}, {"title": "Test", "booking_mode": "INVALID"},
    {"title": "Test", "images": ["javascript:alert(1)"]},
    {"title": "Test", "images": ["https://example.com/x"] * 21},
])
def test_invalid_create_has_no_writes(property_context, payload):
    dao, _, _, client, base, _ = property_context
    assert create(client, base, payload).status_code == 422
    assert not dao.properties and not dao.requests


@pytest.mark.parametrize("key", [None, "", "has spaces", "x" * 129])
def test_idempotency_key_required(property_context, key):
    _, _, _, client, base, _ = property_context
    headers = {} if key is None else {"Idempotency-Key": key}
    assert client.post(base, json={"title": "Test"}, headers=headers).status_code == 422


@pytest.mark.parametrize("payload", [
    {"expected_version": 1}, {"title": "Changed"}, {"title": None, "expected_version": 1},
    {"images": None, "expected_version": 1}, {"organisation_id": "other", "expected_version": 1},
    {"property_id": "other", "expected_version": 1}, {"created_by": "bob", "expected_version": 1},
    {"status": "ARCHIVED", "expected_version": 1}, {"version": 8, "expected_version": 1},
    {"title": "Changed", "expected_version": True},
])
def test_invalid_patch_is_rejected(property_context, payload):
    _, _, _, client, base, _ = property_context
    first = create(client, base).json()
    path = base + "/" + first["property_id"]
    assert client.patch(path, json=payload).status_code == 422
    assert client.get(path).json() == first


def test_omitted_fields_preserved_explicit_null_clears_optional_field(property_context):
    _, _, _, client, base, _ = property_context
    first = create(client, base, {"title": "Test", "description": "Details", "address": "Perth"}).json()
    updated = client.patch(base + "/" + first["property_id"], json={"description": None, "expected_version": 1}).json()
    assert updated["description"] is None and updated["address"] == "Perth"


@pytest.mark.parametrize("mode", ["INSTANT", "REQUEST"])
def test_both_modes_roundtrip(property_context, mode):
    _, _, _, client, base, _ = property_context
    first = create(client, base, {"title": "Test", "booking_mode": mode}).json()
    assert client.get(base + "/" + first["property_id"]).json()["booking_mode"] == mode


def test_stale_snapshot_cannot_overwrite_edit_or_archive(property_context):
    _, _, service, client, base, _ = property_context
    first = create(client, base).json()
    stale = service.get(first["organisation_id"], first["property_id"])
    path = base + "/" + first["property_id"]
    assert client.patch(path, json={"title": "Winner", "expected_version": 1}).status_code == 200
    assert client.patch(path, json={"title": "Loser", "expected_version": 1}).status_code == 409
    assert client.delete(path, params={"expected_version": 1}).status_code == 409
    with pytest.raises(PropertyConflictError):
        service.update(stale, "alice", PropertyUpdate(title="Loser", expected_version=1))
    assert client.get(path).json()["title"] == "Winner"


def test_cross_organisation_ids_never_expose_or_mutate(property_context):
    dao, org_dao, service, client, base, other = property_context
    other_property = service.create(other, "bob", PropertyCreate(title="Private"), "key")
    path = base + "/" + other_property.property_id
    assert client.get(path).status_code == 404
    assert client.patch(path, json={"title": "Stolen", "expected_version": 1}).status_code == 404
    assert client.delete(path, params={"expected_version": 1}).status_code == 404
    other_base = f"/organisations/{other}/properties"
    assert client.get(other_base).status_code == 403
    assert create(client, other_base).status_code == 403
    assert client.get(other_base + "/" + other_property.property_id).status_code == 403
    assert not client.get(base).json()["items"]


def test_member_reads_but_cannot_write_or_replay_create(property_context):
    _, org_dao, _, client, base, _ = property_context
    first = create(client, base).json()
    org_dao.memberships[("alice", first["organisation_id"])].role = OrganisationRole.MEMBER
    path = base + "/" + first["property_id"]
    assert client.get(base).status_code == client.get(path).status_code == 200
    assert create(client, base).status_code == 403
    assert client.patch(path, json={"title": "Denied", "expected_version": 1}).status_code == 403
    assert client.delete(path, params={"expected_version": 1}).status_code == 403


@pytest.mark.parametrize("state", ["inactive_org", "inactive_member", "removed_member"])
def test_revoked_context_denies_reads_and_retries(property_context, state):
    _, org_dao, _, client, base, _ = property_context
    first = create(client, base).json()
    org = first["organisation_id"]
    if state == "inactive_org":
        org_dao.organisations[org].status = OrganisationStatus.INACTIVE
    elif state == "inactive_member":
        org_dao.memberships[("alice", org)].status = MembershipStatus.INACTIVE
    else:
        org_dao.memberships.pop(("alice", org))
    assert client.get(base).status_code == create(client, base).status_code == 403


def test_pagination_is_scoped_and_rejects_invalid_cursor(property_context):
    _, _, _, client, base, other = property_context
    for index in range(3):
        create(client, base, key=str(index))
    ids = []
    cursor = None
    for _ in range(3):
        params = {"limit": 1}
        if cursor:
            params["cursor"] = cursor
        page = client.get(base, params=params).json()
        ids.extend(item["property_id"] for item in page["items"])
        cursor = page["next_cursor"]
    assert len(set(ids)) == 3 and cursor is None
    assert client.get(base, params={"cursor": "bad"}).status_code == 422
    assert client.get(base, params={"cursor": "bnVsbA=="}).status_code == 422
    assert client.get(base, params={"limit": 0}).status_code == 422
    assert client.get(base, params={"limit": 101}).status_code == 422


def test_operational_errors_propagate_and_permission_race_returns_403(property_context):
    dao, _, _, client, base, _ = property_context
    dao.create_property = Mock(side_effect=transaction_error(["None", "None", "ConditionalCheckFailed", "None", "None"]))
    assert create(client, base).status_code == 403
    dao.create_property = Mock(side_effect=ClientError({"Error": {"Code": "InternalServerError"}}, "TransactWriteItems"))
    with pytest.raises(ClientError):
        create(client, base)
    dao.create_property = Mock(side_effect=transaction_error(["None", "None", "None", "ProvisionedThroughputExceeded", "None"]))
    with pytest.raises(ClientError):
        create(client, base)


def test_racing_create_reads_winning_response(property_context):
    dao, _, service, client, base, _ = property_context
    first = create(client, base).json()
    record = next(iter(dao.requests.values()))
    dao.get_creation_request = Mock(side_effect=[None, record])
    dao.create_property = Mock(side_effect=transaction_error(["None"] * 4 + ["ConditionalCheckFailed"]))
    assert service.create(first["organisation_id"], "alice", PropertyCreate(title="First property"), "create-1").model_dump(mode="json") == first


@pytest.mark.parametrize("method,suffix", [("GET", ""), ("POST", ""), ("GET", "/id"), ("PATCH", "/id"), ("DELETE", "/id?expected_version=1")])
def test_all_property_routes_require_authentication(property_context, method, suffix):
    _, _, _, client, base, _ = property_context
    from app.services.authentication_service import get_authentication_service
    client.app.dependency_overrides.pop(require_authenticated_user)
    client.app.dependency_overrides[get_authentication_service] = lambda: Mock()
    assert client.request(method, base + suffix, json={"title": "Test", "expected_version": 1}, headers={"Idempotency-Key": "key"}).status_code == 401


def test_management_has_draft_form_and_scoped_list(property_context):
    _, _, _, client, _, _ = property_context
    page = client.get("/management")
    assert page.status_code == 200
    for id in ("property-form", "property-list", "more-properties", "reload-properties", "property-mode"):
        assert f'id="{id}"' in page.text
    assert "innerHTML" not in page.text and "localStorage" not in page.text


def test_normalised_price_and_whitespace_replay_same_creation(property_context):
    dao, _, _, client, base, _ = property_context
    first = create(client, base, {"title": "  Apartment ", "price_per_night": "12.5"})
    second = create(client, base, {"title": "Apartment", "price_per_night": "12.50"})
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert len(dao.properties) == 1


def test_same_key_is_scoped_to_both_actor_and_organisation(property_context):
    dao, org_dao, _, client, base, other = property_context
    first = create(client, base).json()
    org = first["organisation_id"]
    own_membership = org_dao.memberships[("alice", org)]
    org_dao.memberships[("alice", other)] = own_membership.model_copy(update={"organisation_id": other})
    second = create(client, f"/organisations/{other}/properties").json()
    org_dao.memberships[("bob", org)] = own_membership.model_copy(update={"account_id": "bob"})
    client.app.dependency_overrides[require_authenticated_user] = lambda: CurrentUser(account_id="bob", session_id="bob-session")
    third = create(client, base).json()
    assert len({p["property_id"] for p in (first, second, third)}) == 3
    assert third["created_by"] == "bob"
    assert len(dao.properties) == len(dao.requests) == 3


def test_pagination_cursor_cannot_be_reused_in_another_accessible_org(property_context):
    _, org_dao, _, client, base, other = property_context
    first = create(client, base).json()
    create(client, base, key="another")
    cursor = client.get(base, params={"limit": 1}).json()["next_cursor"]
    org_dao.memberships[("alice", other)] = org_dao.memberships[("alice", first["organisation_id"])].model_copy(update={"organisation_id": other})
    assert client.get(f"/organisations/{other}/properties", params={"cursor": cursor}).status_code == 422


def test_transaction_conflict_can_retry_with_original_key(property_context):
    dao, _, _, client, base, _ = property_context
    original = dao.create_property
    dao.create_property = Mock(side_effect=transaction_error(["None"] * 3 + ["TransactionConflict", "None"]))
    assert create(client, base).status_code == 409
    assert not dao.properties and not dao.requests
    dao.create_property = original
    assert create(client, base).status_code == 201
    assert len(dao.properties) == 1



@pytest.mark.parametrize("archived", [False, True])
def test_admin_permanently_deletes_draft_and_old_create_key_returns_gone(property_context, archived):
    dao, _, _, client, base, _ = property_context
    first = create(client, base).json()
    path = base + "/" + first["property_id"]
    current = client.delete(path, params={"expected_version": 1}).json() if archived else first
    response = client.delete(path + "/draft", params={"expected_version": current["version"]})
    assert response.status_code == 204 and not response.content
    assert client.get(path).status_code == 404
    assert client.get(base).json()["items"] == []
    assert create(client, base).status_code == 410
    assert not dao.properties and len(dao.requests) == len(dao.deleted) == 1
    assert client.delete(path + "/draft", params={"expected_version": current["version"]}).status_code == 404
    assert create(client, base, key="fresh-key").status_code == 201


def test_delete_draft_checks_version_before_removing(property_context):
    dao, _, service, client, base, _ = property_context
    first = create(client, base).json()
    stale = service.get(first["organisation_id"], first["property_id"])
    path = base + "/" + first["property_id"]
    assert client.patch(path, json={"title": "Updated", "expected_version": 1}).status_code == 200
    assert client.delete(path + "/draft", params={"expected_version": 1}).status_code == 409
    with pytest.raises(PropertyConflictError):
        service.delete_draft(stale, "alice", 1)
    assert not dao.deleted
    assert client.get(path).json()["title"] == "Updated"


@pytest.mark.parametrize("history", ["published_at", "has_booking_history"])
def test_published_or_booking_history_cannot_be_deleted(property_context, history):
    from datetime import datetime, timezone
    dao, _, _, client, base, _ = property_context
    first = create(client, base).json()
    property = dao.properties[(first["organisation_id"], first["property_id"])]
    setattr(property, history, datetime.now(timezone.utc) if history == "published_at" else True)
    path = base + "/" + first["property_id"]
    assert client.delete(path + "/draft", params={"expected_version": 1}).status_code == 409
    assert len(dao.properties) == 1 and not dao.deleted


@pytest.mark.parametrize("field,value", [("published_at", "2026-11-17T00:00:00Z"), ("has_booking_history", False)])
def test_history_guards_are_server_controlled(property_context, field, value):
    _, _, _, client, base, _ = property_context
    assert create(client, base, {"title": "Test", field: value}).status_code == 422
    first = create(client, base).json()
    assert client.patch(base + "/" + first["property_id"], json={field: value, "expected_version": 1}).status_code == 422


def test_member_cannot_delete_and_other_org_ids_are_hidden(property_context):
    dao, org_dao, _, client, base, other = property_context
    first = create(client, base).json()
    path = base + "/" + first["property_id"] + "/draft"
    org_dao.memberships[("alice", first["organisation_id"])].role = OrganisationRole.MEMBER
    assert client.delete(path, params={"expected_version": 1}).status_code == 403
    assert client.delete(f"/organisations/{other}/properties/{first['property_id']}/draft", params={"expected_version": 1}).status_code == 403
    org_dao.memberships[("alice", other)] = org_dao.memberships[("alice", first["organisation_id"])].model_copy(update={"organisation_id": other, "role": OrganisationRole.ADMIN})
    assert client.delete(f"/organisations/{other}/properties/{first['property_id']}/draft", params={"expected_version": 1}).status_code == 404
    assert len(dao.properties) == 1 and not dao.deleted


def test_delete_draft_requires_authentication_and_version(property_context):
    _, _, _, client, base, _ = property_context
    first = create(client, base).json()
    path = base + "/" + first["property_id"] + "/draft"
    assert client.delete(path).status_code == 422
    assert client.delete(path, params={"expected_version": 0}).status_code == 422
    from app.services.authentication_service import get_authentication_service
    client.app.dependency_overrides.pop(require_authenticated_user)
    client.app.dependency_overrides[get_authentication_service] = lambda: Mock()
    assert client.delete(path, params={"expected_version": 1}).status_code == 401
