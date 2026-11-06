from datetime import datetime, timezone
from unittest.mock import Mock

import boto3
from botocore.stub import Stubber
import pytest

from app.dao.account_dao import _to_dynamodb_item
from app.dao.organisation_dao import OrganisationDAO
from app.models.organisation import Membership, Organisation


@pytest.fixture
def dao_context():
    client = boto3.client("dynamodb", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test")
    dao = OrganisationDAO(client, "organisations", "memberships", "requests", "accounts")
    now = datetime.now(timezone.utc)
    org = Organisation(organisation_id="org-1", name="Org", status="active", created_by="alice", created_at=now, updated_at=now)
    member = Membership(organisation_id="org-1", account_id="alice", role="admin", status="active", created_at=now, updated_at=now)
    return dao, client, org, member


def test_creation_is_one_conditional_transaction(dao_context):
    dao, client, org, member = dao_context
    expected = {"TransactItems": [
        {"ConditionCheck": {"TableName": "accounts", "Key": {"id": {"S": "alice"}}, "ConditionExpression": "#status = :active", "ExpressionAttributeNames": {"#status": "status"}, "ExpressionAttributeValues": {":active": {"S": "active"}}}},
        {"Put": {"TableName": "organisations", "Item": _to_dynamodb_item(org.model_dump()), "ConditionExpression": "attribute_not_exists(organisation_id)"}},
        {"Put": {"TableName": "memberships", "Item": _to_dynamodb_item(member.model_dump()), "ConditionExpression": "attribute_not_exists(account_id)"}},
        {"Put": {"TableName": "requests", "Item": {"request_id": {"S": "key"}, "organisation_id": {"S": "org-1"}, "fingerprint": {"S": "hash"}}, "ConditionExpression": "attribute_not_exists(request_id)"}},
    ]}
    with Stubber(client) as stub:
        stub.add_response("transact_write_items", {}, expected)
        dao.create_organisation(org, member, "key", "hash")
        stub.assert_no_pending_responses()


def test_membership_reads_use_both_keys_and_consistent_read(dao_context):
    dao, client, _, member = dao_context
    with Stubber(client) as stub:
        stub.add_response("get_item", {"Item": _to_dynamodb_item(member.model_dump())}, {"TableName": "memberships", "Key": {"account_id": {"S": "alice"}, "organisation_id": {"S": "org-1"}}, "ConsistentRead": True})
        assert dao.get_membership("alice", "org-1") == member


def test_memberships_query_all_pages(dao_context):
    dao, client, _, member = dao_context
    query = {"TableName": "memberships", "KeyConditionExpression": "account_id = :account_id", "ExpressionAttributeValues": {":account_id": {"S": "alice"}}, "ConsistentRead": True}
    last = {"account_id": {"S": "alice"}, "organisation_id": {"S": "org-1"}}
    with Stubber(client) as stub:
        stub.add_response("query", {"Items": [_to_dynamodb_item(member.model_dump())], "LastEvaluatedKey": last}, query)
        stub.add_response("query", {"Items": []}, {**query, "ExclusiveStartKey": last})
        assert dao.list_memberships("alice") == [member]


def test_table_bootstrap_creates_composite_membership_key(dao_context):
    dao, _, _, _ = dao_context
    client = Mock()
    from botocore.exceptions import ClientError
    client.describe_table.side_effect = ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "DescribeTable")
    dao._client = client
    dao.ensure_tables()
    calls = client.create_table.call_args_list
    assert len(calls) == 3
    assert calls[1].kwargs["KeySchema"] == [
        {"AttributeName": "account_id", "KeyType": "HASH"},
        {"AttributeName": "organisation_id", "KeyType": "RANGE"},
    ]
