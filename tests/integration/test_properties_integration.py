from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from app.dao.property_dao import PropertyDAO
from app.models.organisation import OrganisationCreate
from app.models.property import PropertyCreate, PropertyUpdate
from app.services.property_service import PropertyConflictError, PropertyPermissionError, PropertyService
from tests.integration.test_organisations_integration import organisation_context


pytestmark = pytest.mark.integration


@pytest.fixture
def property_context(organisation_context):
    _, org_service, client, org_tables = organisation_context
    org = org_service.create("alice", OrganisationCreate(name="Property Test"), "org").organisation.organisation_id
    prefix = "property_test_" + uuid4().hex
    tables = [prefix + "_properties", prefix + "_requests"]
    dao = PropertyDAO(client, *tables, org_tables[3], org_tables[0], org_tables[1])
    try:
        dao.ensure_tables()
        yield dao, PropertyService(dao), org, client, tables, org_tables
    finally:
        for name in tables:
            try:
                client.delete_table(TableName=name)
            except client.exceptions.ResourceNotFoundException:
                pass


def test_real_roundtrip_patch_clear_and_archive_preserves_record(property_context):
    dao, service, org, _, _, _ = property_context
    first = service.create(org, "alice", PropertyCreate(title="Test", price_per_night="12.50", max_guests=2, images=["https://example.com/image.jpg"], description="Clear me"), "key")
    assert dao.get_property(org, first.property_id) == first
    assert service.create(org, "alice", PropertyCreate(title="Test", price_per_night="12.50", max_guests=2, images=["https://example.com/image.jpg"], description="Clear me"), "key") == first
    changed = service.update(first, "alice", PropertyUpdate(description=None, expected_version=1))
    assert dao.get_property(org, first.property_id).description is None
    archived = service.archive(changed, "alice", 2)
    assert dao.get_property(org, first.property_id) == archived
    assert service.archive(archived, "alice", 3) == archived
    assert dao.get_property("other", first.property_id) is None


def test_real_duplicate_submissions_create_one_property(property_context):
    _, service, org, client, tables, _ = property_context
    payload = PropertyCreate(title="Concurrent")
    def submit(_):
        try:
            return service.create(org, "alice", payload, "same-key")
        except PropertyConflictError:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(submit, range(4)))
    final = service.create(org, "alice", payload, "same-key")
    assert all(value is None or value == final for value in results)
    for table in tables:
        assert len(client.scan(TableName=table, ConsistentRead=True)["Items"]) == 1


@pytest.mark.parametrize("revocation", ["account", "organisation", "membership"])
def test_real_create_rollback_on_revocation(property_context, revocation):
    _, service, org, client, tables, org_tables = property_context
    if revocation == "account":
        table, key = org_tables[3], {"id": {"S": "alice"}}
    elif revocation == "organisation":
        table, key = org_tables[0], {"organisation_id": {"S": org}}
    else:
        table, key = org_tables[1], {"account_id": {"S": "alice"}, "organisation_id": {"S": org}}
    client.update_item(TableName=table, Key=key, UpdateExpression="SET #status = :inactive",
                       ExpressionAttributeNames={"#status": "status"}, ExpressionAttributeValues={":inactive": {"S": "inactive"}})
    with pytest.raises(PropertyPermissionError):
        service.create(org, "alice", PropertyCreate(title="Denied"), "key")
    for table in tables:
        assert client.scan(TableName=table, ConsistentRead=True)["Items"] == []


def test_real_concurrent_edit_and_archive_allow_one_winner(property_context):
    dao, service, org, _, _, _ = property_context
    first = service.create(org, "alice", PropertyCreate(title="Concurrent"), "key")
    def submit(index):
        try:
            if index % 2:
                return service.archive(first, "alice", 1)
            return service.update(first, "alice", PropertyUpdate(title=f"Edit {index}", expected_version=1))
        except PropertyConflictError:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(submit, range(4)))
    winners = [value for value in results if value is not None]
    assert len(winners) == 1
    assert dao.get_property(org, first.property_id) == winners[0]
    assert winners[0].version == 2


def test_real_edit_rechecks_admin_after_dependency_snapshot(property_context):
    dao, service, org, client, _, org_tables = property_context
    first = service.create(org, "alice", PropertyCreate(title="Original"), "key")
    client.update_item(TableName=org_tables[1], Key={"account_id": {"S": "alice"}, "organisation_id": {"S": org}},
                       UpdateExpression="SET #role = :member", ExpressionAttributeNames={"#role": "role"},
                       ExpressionAttributeValues={":member": {"S": "member"}})
    with pytest.raises(PropertyPermissionError):
        service.update(first, "alice", PropertyUpdate(title="Denied", expected_version=1))
    assert dao.get_property(org, first.property_id) == first


def test_real_pagination_and_idempotency_are_organisation_scoped(property_context, organisation_context):
    dao, service, org, _, _, _ = property_context
    _, org_service, _, _ = organisation_context
    other = org_service.create("alice", OrganisationCreate(name="Other"), "other").organisation.organisation_id
    for index in range(3):
        service.create(org, "alice", PropertyCreate(title=f"Property {index}"), str(index))
    other_property = service.create(other, "alice", PropertyCreate(title="Other private"), "0")
    ids, cursor = [], None
    while True:
        page = service.list(org, 1, cursor)
        ids.extend(item.property_id for item in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert len(set(ids)) == 3 and other_property.property_id not in ids
    assert dao.list_properties(other, 20, None)[0] == [other_property]


def test_real_api_guest_capacity_create_list_edit_and_replay(property_context, organisation_context):
    from fastapi.testclient import TestClient
    from app.dependencies.auth import require_authenticated_user
    from app.main import create_app
    from app.models.auth import CurrentUser
    from app.services.organisation_service import get_organisation_service
    from app.services.property_service import get_property_service

    _, service, org, _, _, _ = property_context
    _, org_service, _, _ = organisation_context
    app = create_app()
    app.dependency_overrides[require_authenticated_user] = lambda: CurrentUser(account_id="alice", session_id="session")
    app.dependency_overrides[get_organisation_service] = lambda: org_service
    app.dependency_overrides[get_property_service] = lambda: service
    client = TestClient(app)
    base = f"/organisations/{org}/properties"
    payload = {"title": "Perth Test Apartment", "max_guests": 2, "price_per_night": "120.50", "currency": "AUD", "booking_mode": "REQUEST"}
    headers = {"Idempotency-Key": "guest-capacity-regression"}
    created = client.post(base, json=payload, headers=headers)
    assert created.status_code == 201
    first = created.json()
    assert first["status"] == "DRAFT" and first["max_guests"] == 2
    path = base + "/" + first["property_id"]
    assert client.get(path).json() == first
    assert client.get(base).json()["items"] == [first]
    assert client.post(base, json=payload, headers=headers).json() == first
    updated = client.patch(path, json={"max_guests": 4, "expected_version": 1})
    assert updated.status_code == 200
    assert client.get(path).json()["max_guests"] == 4
    assert client.get(base).json()["items"][0]["version"] == 2
    assert client.post(base, json=payload, headers=headers).json() == first



@pytest.mark.parametrize("archived", [False, True])
def test_real_delete_retains_tombstone_and_prevents_creation_replay(property_context, archived):
    from app.services.property_service import PropertyDeletedError
    dao, service, org, _, _, _ = property_context
    payload = PropertyCreate(title="Disposable draft", max_guests=2)
    first = service.create(org, "alice", payload, "delete-key")
    current = service.archive(first, "alice", 1) if archived else first
    service.delete_draft(current, "alice", current.version)
    assert dao.get_property(org, first.property_id) is None
    assert dao.list_properties(org, 20, None)[0] == []
    assert dao.is_deleted(org, first.property_id)
    with pytest.raises(PropertyDeletedError):
        service.create(org, "alice", payload, "delete-key")
    replacement = service.create(org, "alice", payload, "new-key")
    assert replacement.property_id != first.property_id


@pytest.mark.parametrize("guard", ["version", "published_at", "has_booking_history", "permission"])
def test_real_delete_rechecks_conditions_and_rolls_back_marker(property_context, guard):
    dao, service, org, client, tables, org_tables = property_context
    first = service.create(org, "alice", PropertyCreate(title="Preserve me"), "key")
    key = {"organisation_id": {"S": org}, "property_id": {"S": first.property_id}}
    if guard == "permission":
        client.update_item(TableName=org_tables[1], Key={"account_id": {"S": "alice"}, "organisation_id": {"S": org}},
                           UpdateExpression="SET #role = :value", ExpressionAttributeNames={"#role": "role"},
                           ExpressionAttributeValues={":value": {"S": "member"}})
    else:
        value = {"version": {"N": "2"}, "published_at": {"S": "2026-11-17T00:00:00+00:00"}, "has_booking_history": {"BOOL": True}}[guard]
        client.update_item(TableName=tables[0], Key=key, UpdateExpression="SET #guard = :value",
                           ExpressionAttributeNames={"#guard": guard}, ExpressionAttributeValues={":value": value})
    with pytest.raises(PropertyPermissionError if guard == "permission" else PropertyConflictError):
        service.delete_draft(first, "alice", 1)
    assert dao.get_property(org, first.property_id) is not None
    assert not dao.is_deleted(org, first.property_id)


def test_real_legacy_archived_draft_can_be_deleted_without_migration(property_context):
    dao, service, org, client, tables, _ = property_context
    first = service.create(org, "alice", PropertyCreate(title="Legacy draft"), "key")
    archived = service.archive(first, "alice", 1)
    client.update_item(TableName=tables[0], Key={"organisation_id": {"S": org}, "property_id": {"S": first.property_id}},
                       UpdateExpression="REMOVE has_booking_history")
    service.delete_draft(dao.get_property(org, first.property_id), "alice", archived.version)
    assert dao.get_property(org, first.property_id) is None and dao.is_deleted(org, first.property_id)


def test_real_concurrent_delete_and_edit_allow_one_winner(property_context):
    from threading import Barrier
    dao, service, org, _, _, _ = property_context
    first = service.create(org, "alice", PropertyCreate(title="Delete race"), "key")
    barrier = Barrier(2)
    def submit(index):
        barrier.wait()
        try:
            if index == 0:
                service.delete_draft(first, "alice", 1)
                return "deleted"
            service.update(first, "alice", PropertyUpdate(title="Edited", expected_version=1))
            return "edited"
        except PropertyConflictError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    winners = [result for result in results if result]
    assert len(winners) == 1
    current = dao.get_property(org, first.property_id)
    assert dao.is_deleted(org, first.property_id) == (winners[0] == "deleted")
    assert current is None if winners[0] == "deleted" else current.title == "Edited" and current.version == 2
