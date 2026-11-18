from datetime import datetime, timezone

import boto3
import pytest
from pydantic import ValidationError

from app.dao.account_dao import _to_dynamodb_item
from app.models.property import Property
from botocore.stub import Stubber

from app.dao.property_dao import PropertyDAO


def test_list_uses_scoped_query_and_dynamodb_pagination_key():
    client = boto3.client("dynamodb", region_name="us-east-1", aws_access_key_id="local", aws_secret_access_key="local")
    dao = PropertyDAO(client, "properties", "requests", "accounts", "organisations", "memberships")
    with Stubber(client) as stub:
        stub.add_response("query", {"Items": [], "LastEvaluatedKey": {
            "organisation_id": {"S": "org-a"}, "property_id": {"S": "last"},
        }}, {
            "TableName": "properties", "KeyConditionExpression": "organisation_id = :organisation_id",
            "ExpressionAttributeValues": {":organisation_id": {"S": "org-a"}},
            "ConsistentRead": True, "Limit": 10,
            "ExclusiveStartKey": {"organisation_id": {"S": "org-a"}, "property_id": {"S": "after"}},
        })
        assert dao.list_properties("org-a", 10, "after") == ([], "last")
        stub.assert_no_pending_responses()


def test_detail_uses_both_keys_and_consistent_read():
    client = boto3.client("dynamodb", region_name="us-east-1", aws_access_key_id="local", aws_secret_access_key="local")
    dao = PropertyDAO(client, "properties", "requests", "accounts", "organisations", "memberships")
    with Stubber(client) as stub:
        stub.add_response("get_item", {}, {"TableName": "properties", "Key": {
            "organisation_id": {"S": "org-a"}, "property_id": {"S": "id"},
        }, "ConsistentRead": True})
        assert dao.get_property("org-a", "id") is None
        stub.assert_no_pending_responses()


@pytest.mark.parametrize("read_path", ["detail", "list", "replay"])
def test_dynamodb_integer_numbers_are_restored_in_all_read_paths(read_path):
    now = datetime.now(timezone.utc)
    property = Property(title="Apartment", property_id="id", organisation_id="org-a",
                        created_by="alice", status="DRAFT", max_guests=2,
                        price_per_night="120.50", version=1, created_at=now, updated_at=now)
    stored = _to_dynamodb_item(property.model_dump(mode="json"))
    assert stored["max_guests"] == {"N": "2"}
    client = boto3.client("dynamodb", region_name="us-east-1", aws_access_key_id="local", aws_secret_access_key="local")
    dao = PropertyDAO(client, "properties", "requests", "accounts", "organisations", "memberships")
    with Stubber(client) as stub:
        if read_path == "detail":
            stub.add_response("get_item", {"Item": stored})
            result = dao.get_property("org-a", "id")
        elif read_path == "list":
            stub.add_response("query", {"Items": [stored]})
            result = dao.list_properties("org-a", 20, None)[0][0]
        else:
            stub.add_response("get_item", {"Item": _to_dynamodb_item({
                "request_id": "request", "fingerprint": "hash", "property": property.model_dump(mode="json"),
            })})
            result = Property.model_validate(dao.get_creation_request("request")["property"])
        assert result == property
        assert type(result.max_guests) is int
        assert str(result.price_per_night) == "120.50"


def test_fractional_stored_guest_count_is_rejected_without_truncation():
    now = datetime.now(timezone.utc)
    stored = _to_dynamodb_item({"title": "Apartment", "property_id": "id", "organisation_id": "org-a",
                                "created_by": "alice", "status": "DRAFT", "version": 1,
                                "created_at": now.isoformat(), "updated_at": now.isoformat()})
    stored["max_guests"] = {"N": "2.5"}
    client = boto3.client("dynamodb", region_name="us-east-1", aws_access_key_id="local", aws_secret_access_key="local")
    dao = PropertyDAO(client, "properties", "requests", "accounts", "organisations", "memberships")
    with Stubber(client) as stub:
        stub.add_response("get_item", {"Item": stored})
        with pytest.raises(ValidationError):
            dao.get_property("org-a", "id")
