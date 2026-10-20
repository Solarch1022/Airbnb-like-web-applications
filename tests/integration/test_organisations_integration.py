from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

from botocore.exceptions import ClientError
import pytest

from app.dao.organisation_dao import OrganisationDAO
from app.models.organisation import OrganisationCreate
from app.services.organisation_service import OrganisationConflictError, OrganisationService


pytestmark = pytest.mark.integration


@pytest.fixture
def organisation_context(ddb_client):
    prefix = "org_test_" + uuid4().hex
    names = [prefix + suffix for suffix in ("_orgs", "_members", "_requests", "_accounts")]
    dao = OrganisationDAO(ddb_client, *names)
    try:
        dao.ensure_tables()
        ddb_client.create_table(
            TableName=names[3],
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        ddb_client.get_waiter("table_exists").wait(TableName=names[3])
        ddb_client.put_item(TableName=names[3], Item={"id": {"S": "alice"}, "status": {"S": "active"}})
        yield dao, OrganisationService(dao), ddb_client, names
    finally:
        for name in names:
            try:
                ddb_client.delete_table(TableName=name)
            except ddb_client.exceptions.ResourceNotFoundException:
                pass


def test_real_transaction_roundtrip_and_replay(organisation_context):
    dao, service, _, _ = organisation_context
    payload = OrganisationCreate(name="Integration Organisation")
    first = service.create("alice", payload, "same-key")
    assert service.create("alice", payload, "same-key") == first
    assert service.list_contexts("alice") == [first]
    assert service.list_contexts("bob") == []


def test_real_transaction_rolls_back_for_inactive_account(organisation_context):
    dao, service, client, names = organisation_context
    client.put_item(TableName=names[3], Item={"id": {"S": "alice"}, "status": {"S": "deactivated"}})
    with pytest.raises(OrganisationConflictError):
        service.create("alice", OrganisationCreate(name="Denied"), "failed-key")
    for name in names[:3]:
        assert client.scan(TableName=name, ConsistentRead=True)["Items"] == []


def test_concurrent_retries_create_one_organisation(organisation_context):
    dao, service, client, names = organisation_context
    payload = OrganisationCreate(name="Concurrent Organisation")
    def submit(_):
        try:
            return service.create("alice", payload, "concurrent-key")
        except OrganisationConflictError:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(submit, range(4)))
    final = service.create("alice", payload, "concurrent-key")
    assert all(result is None or result == final for result in results)
    for name in names[:3]:
        assert len(client.scan(TableName=name, ConsistentRead=True)["Items"]) == 1
