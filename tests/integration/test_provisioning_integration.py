from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient
import pytest

from app.dao.organisation_dao import get_organisation_dao
from app.dependencies.auth import require_authenticated_user
from app.main import create_app
from app.models.auth import CurrentUser
from app.models.property import PropertyCreate, PropertyUpdate
from app.services.organisation_service import get_organisation_service
from app.services.property_service import PropertyConflictError, PropertyPermissionError, PropertyService, get_property_service
from tests.integration.test_properties_integration import property_context
from tests.integration.test_organisations_integration import organisation_context
from tests.test_property_provisioning import complete_payload


pytestmark = pytest.mark.integration


@pytest.mark.parametrize("mode", ["INSTANT", "REQUEST"])
def test_real_configuration_publication_and_public_api_roundtrip(property_context, organisation_context, mode):
    dao, service, org, _, _, _ = property_context
    org_dao, org_service, _, _ = organisation_context
    first = service.create(org, "alice", PropertyCreate(**complete_payload(mode)), "key")
    persisted = dao.get_property(org, first.property_id)
    assert persisted == first and type(persisted.preparation_nights) is int
    assert service.readiness(persisted).can_publish
    active = service.publish(persisted, "alice", 1)
    assert dao.get_property(org, first.property_id) == active
    app = create_app()
    app.dependency_overrides[get_organisation_dao] = lambda: org_dao
    app.dependency_overrides[get_property_service] = lambda: service
    client = TestClient(app)
    base = f"/public/organisations/{org}/properties"
    public = client.get(base).json()["items"][0]
    assert public["booking_mode"] == mode and public["max_guests"] == 2
    assert public["min_nights"] == 1 and public["max_nights"] == 14
    assert "address" not in public and "blocked_dates" not in public
    inactive = service.deactivate(active, "alice", 2)
    assert client.get(base).json()["items"] == []
    active_again = service.publish(inactive, "alice", 3)
    assert active_again.published_at == active.published_at
    edited = service.update(active_again, "alice", PropertyUpdate(booking_mode="INSTANT", expected_version=4))
    assert dao.get_property(org, first.property_id) == edited
    archived = service.archive(edited, "alice", 5)
    assert dao.get_property(org, first.property_id) == archived
    assert client.get(base + "/" + first.property_id).status_code == 404
    with pytest.raises(PropertyConflictError):
        service.delete_draft(archived, "alice", 6)


@pytest.mark.parametrize("revocation", ["organisation", "membership"])
def test_real_publish_rollback_after_access_revocation(property_context, revocation):
    dao, service, org, client, _, org_tables = property_context
    first = service.create(org, "alice", PropertyCreate(**complete_payload()), "key")
    table, key = (org_tables[0], {"organisation_id": {"S": org}}) if revocation == "organisation" else (org_tables[1], {"account_id": {"S": "alice"}, "organisation_id": {"S": org}})
    client.update_item(TableName=table, Key=key, UpdateExpression="SET #status = :inactive",
                       ExpressionAttributeNames={"#status": "status"}, ExpressionAttributeValues={":inactive": {"S": "inactive"}})
    with pytest.raises(PropertyPermissionError):
        service.publish(first, "alice", 1)
    assert dao.get_property(org, first.property_id) == first


@pytest.mark.parametrize("competing_action", ["edit", "delete", "publish"])
def test_real_publish_competing_with_mutation_has_one_winner(property_context, competing_action):
    dao, service, org, _, _, _ = property_context
    first = service.create(org, "alice", PropertyCreate(**complete_payload()), "key")
    barrier = Barrier(2)
    def submit(index):
        barrier.wait()
        try:
            if index == 0 or competing_action == "publish":
                service.publish(first, "alice", 1)
                return "publish"
            if competing_action == "delete":
                service.delete_draft(first, "alice", 1)
                return "delete"
            service.update(first, "alice", PropertyUpdate(title="Edited", expected_version=1))
            return "edit"
        except PropertyConflictError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert len([result for result in results if result]) == 1
    current = dao.get_property(org, first.property_id)
    if "delete" in results:
        assert current is None and dao.is_deleted(org, first.property_id)
    else:
        assert current.version == 2 and not dao.is_deleted(org, first.property_id)
        assert bool(current.published_at) == ("publish" in results)


def test_real_legacy_rows_load_with_optional_setup_defaults(property_context):
    dao, service, org, client, tables, _ = property_context
    first = service.create(org, "alice", PropertyCreate(title="Old draft"), "key")
    client.update_item(TableName=tables[0], Key={"organisation_id": {"S": org}, "property_id": {"S": first.property_id}},
                       UpdateExpression="REMOVE blocked_dates")
    legacy = dao.get_property(org, first.property_id)
    assert legacy.blocked_dates == [] and legacy.min_nights is None
    assert not service.readiness(legacy).ready
