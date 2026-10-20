from datetime import datetime, timezone
from unittest.mock import Mock

from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
import pytest

from app.dependencies.auth import get_current_user
from app.main import create_app
from app.models.auth import CurrentUser
from app.models.organisation import (
    Membership, MembershipStatus, OrganisationCreate,
    OrganisationRole, OrganisationStatus,
)
from app.services.organisation_service import (
    OrganisationConflictError, OrganisationPermissionError,
    OrganisationService, get_organisation_service,
)


class FakeOrganisationDAO:
    def __init__(self):
        self.organisations = {}
        self.memberships = {}
        self.requests = {}
        self.fail = False
        self.writes = 0

    def get_organisation(self, organisation_id):
        return self.organisations.get(organisation_id)

    def get_membership(self, account_id, organisation_id):
        return self.memberships.get((account_id, organisation_id))

    def list_memberships(self, account_id):
        return [m for (account, _), m in self.memberships.items() if account == account_id]

    def get_creation_request(self, request_id):
        return self.requests.get(request_id)

    def create_organisation(self, organisation, membership, request_id, fingerprint):
        if self.fail:
            raise ClientError({
                "Error": {"Code": "TransactionCanceledException"},
                "CancellationReasons": [{"Code": "ConditionalCheckFailed"}],
            }, "TransactWriteItems")
        self.writes += 1
        self.organisations[organisation.organisation_id] = organisation
        self.memberships[(membership.account_id, membership.organisation_id)] = membership
        self.requests[request_id] = {
            "organisation_id": organisation.organisation_id,
            "fingerprint": fingerprint,
        }


@pytest.fixture
def org_context():
    dao = FakeOrganisationDAO()
    service = OrganisationService(dao)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        account_id="alice", session_id="session",
    )
    app.dependency_overrides[get_organisation_service] = lambda: service
    return dao, service, TestClient(app)


def create(client, name="Test Organisation", key="request-1"):
    return client.post("/organisations", json={"name": name}, headers={"Idempotency-Key": key})


def test_create_bootstraps_admin_and_get_context(org_context):
    dao, _, client = org_context
    response = create(client)
    assert response.status_code == 201
    body = response.json()
    org_id = body["organisation"]["organisation_id"]
    assert body["organisation"]["created_by"] == "alice"
    assert body["membership"]["role"] == "admin"
    assert len(dao.organisations) == len(dao.memberships) == len(dao.requests) == 1
    assert client.get(f"/organisations/{org_id}").json() == body
    assert client.get(f"/organisations/{org_id}/admin").status_code == 200
    assert client.get("/me/organisations").json() == [body]


def test_retries_return_original_without_duplicate_writes(org_context):
    dao, _, client = org_context
    first = create(client)
    assert create(client).json() == first.json()
    assert dao.writes == 1


def test_reusing_key_with_changed_details_conflicts(org_context):
    dao, _, client = org_context
    create(client)
    assert create(client, name="Different").status_code == 409
    assert dao.writes == 1


def test_names_can_repeat_and_keys_are_scoped_to_caller(org_context):
    dao, service, client = org_context
    create(client)
    create(client, key="request-2")
    service.create("bob", OrganisationCreate(name="Test Organisation"), "request-1")
    assert len(dao.organisations) == 3
    assert len(service.list_contexts("alice")) == 2
    assert len(service.list_contexts("bob")) == 1


def test_failed_creation_has_no_partial_records(org_context):
    dao, _, client = org_context
    dao.fail = True
    assert create(client).status_code == 409
    assert not dao.organisations and not dao.memberships and not dao.requests
    dao.fail = False
    assert create(client).status_code == 201


@pytest.mark.parametrize("payload", [
    {"name": ""}, {"name": "   "}, {"name": "x" * 101},
    {"name": "Test", "role": "admin"},
    {"name": "Test", "organisation_id": "other"},
])
def test_invalid_or_privilege_injecting_payload_is_rejected(org_context, payload):
    dao, _, client = org_context
    response = client.post("/organisations", json=payload, headers={"Idempotency-Key": "test"})
    assert response.status_code == 422
    assert dao.writes == 0


@pytest.mark.parametrize("key", [None, "", " ", "x" * 129])
def test_requires_valid_idempotency_key(org_context, key):
    _, _, client = org_context
    headers = {} if key is None else {"Idempotency-Key": key}
    assert client.post("/organisations", json={"name": "Test"}, headers=headers).status_code == 422


@pytest.mark.parametrize("state", ["nonmember", "inactive_member", "inactive_org", "missing_org"])
def test_denies_inaccessible_organisations(org_context, state):
    dao, _, client = org_context
    org_id = create(client).json()["organisation"]["organisation_id"]
    if state == "nonmember":
        dao.memberships.clear()
    elif state == "inactive_member":
        dao.memberships[("alice", org_id)].status = MembershipStatus.INACTIVE
    elif state == "inactive_org":
        dao.organisations[org_id].status = OrganisationStatus.INACTIVE
    else:
        dao.organisations.clear()
    assert client.get(f"/organisations/{org_id}").status_code == 403
    assert client.get(f"/organisations/{org_id}/admin").status_code == 403
    assert client.get("/me/organisations").json() == []


def test_roles_are_scoped_to_each_organisation(org_context):
    dao, service, client = org_context
    own_id = create(client).json()["organisation"]["organisation_id"]
    other = service.create("bob", OrganisationCreate(name="Other"), "other")
    other_id = other.organisation.organisation_id
    assert client.get(f"/organisations/{other_id}").status_code == 403
    now = datetime.now(timezone.utc)
    dao.memberships[("alice", other_id)] = Membership(
        account_id="alice", organisation_id=other_id,
        role=OrganisationRole.MEMBER, status=MembershipStatus.ACTIVE,
        created_at=now, updated_at=now,
    )
    assert client.get(f"/organisations/{own_id}/admin").status_code == 200
    assert client.get(f"/organisations/{other_id}").status_code == 200
    assert client.get(f"/organisations/{other_id}/admin").status_code == 403


def test_replay_does_not_bypass_revoked_membership(org_context):
    dao, _, client = org_context
    create(client)
    dao.memberships.clear()
    assert create(client).status_code == 403


def test_racing_retry_reads_winning_transaction(org_context):
    dao, service, client = org_context
    first = create(client).json()
    dao.get_creation_request = Mock(side_effect=[None, next(iter(dao.requests.values()))])
    dao.fail = True
    replay = service.create("alice", OrganisationCreate(name="Test Organisation"), "request-1")
    assert replay.model_dump(mode="json") == first
    assert dao.writes == 1


def test_database_outage_is_not_reported_as_permission_error(org_context):
    dao, service, _ = org_context
    dao.create_organisation = Mock(side_effect=ClientError(
        {"Error": {"Code": "InternalServerError"}}, "TransactWriteItems",
    ))
    with pytest.raises(ClientError):
        service.create("alice", OrganisationCreate(name="Test"), "key")


@pytest.mark.parametrize("method,path", [
    ("GET", "/me/organisations"), ("POST", "/organisations"),
    ("GET", "/organisations/other"), ("GET", "/organisations/other/admin"),
])
def test_organisation_routes_require_authentication(org_context, method, path):
    _, _, client = org_context
    client.app.dependency_overrides.pop(get_current_user)
    # Override construction only; real bearer dependency still rejects the request.
    from app.services.authentication_service import get_authentication_service
    client.app.dependency_overrides[get_authentication_service] = lambda: Mock()
    assert client.request(method, path, json={"name": "Test"}, headers={"Idempotency-Key": "key"}).status_code == 401


def test_management_page_provides_signin_and_first_property_guidance(org_context):
    _, _, client = org_context
    response = client.get("/management")
    assert response.status_code == 200
    assert 'id="login-form"' in response.text
    assert "create your first property" in response.text
    assert "localStorage" not in response.text
