from decimal import Decimal
from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.core.config import get_settings
from app.dao.account_dao import _from_dynamodb_item, _to_dynamodb_item
from app.models.property import Property


def _property_from_storage(data: dict) -> dict:
    data = dict(data)
    # boto3 deserialises all DynamoDB numbers as Decimal. Restore integer
    # fields at this storage boundary without weakening strict API validation.
    for name in ("max_guests", "version"):
        value = data.get(name)
        if isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value():
            data[name] = int(value)
    return data


class PropertyDAO:

    def __init__(
        self, client: Any, table_name: str, requests_table_name: str,
        accounts_table_name: str, organisations_table_name: str,
        memberships_table_name: str,
    ) -> None:
        self._client = client
        self._table_name = table_name
        self._requests_table_name = requests_table_name
        self._accounts_table_name = accounts_table_name
        self._organisations_table_name = organisations_table_name
        self._memberships_table_name = memberships_table_name

    def get_property(self, organisation_id: str, property_id: str) -> Property | None:
        response = self._client.get_item(
            TableName=self._table_name,
            Key=self._key(organisation_id, property_id),
            ConsistentRead=True,
        )
        item = response.get("Item")
        return Property.model_validate(_property_from_storage(_from_dynamodb_item(item))) if item else None

    def list_properties(
        self, organisation_id: str, limit: int, after: str | None,
    ) -> tuple[list[Property], str | None]:
        request = {
            "TableName": self._table_name,
            "KeyConditionExpression": "organisation_id = :organisation_id",
            "ExpressionAttributeValues": {":organisation_id": {"S": organisation_id}},
            "ConsistentRead": True,
            "Limit": limit,
        }
        if after:
            request["ExclusiveStartKey"] = self._key(organisation_id, after)
        response = self._client.query(**request)
        items = [Property.model_validate(_property_from_storage(_from_dynamodb_item(item)))
                 for item in response.get("Items", [])]
        last_key = response.get("LastEvaluatedKey")
        return items, last_key["property_id"]["S"] if last_key else None

    def get_creation_request(self, request_id: str) -> dict | None:
        response = self._client.get_item(
            TableName=self._requests_table_name,
            Key={"request_id": {"S": request_id}},
            ConsistentRead=True,
        )
        item = response.get("Item")
        if not item:
            return None
        record = _from_dynamodb_item(item)
        record["property"] = _property_from_storage(record["property"])
        return record

    def create_property(
        self, property: Property, account_id: str, request_id: str, fingerprint: str,
    ) -> None:
        self._client.transact_write_items(TransactItems=[
            *self._permission_checks(account_id, property.organisation_id),
            {"Put": {
                "TableName": self._table_name,
                "Item": _to_dynamodb_item(property.model_dump(mode="json")),
                "ConditionExpression": "attribute_not_exists(property_id)",
            }},
            {"Put": {
                "TableName": self._requests_table_name,
                "Item": _to_dynamodb_item({
                    "request_id": request_id,
                    "fingerprint": fingerprint,
                    "property": property.model_dump(mode="json"),
                }),
                "ConditionExpression": "attribute_not_exists(request_id)",
            }},
        ])

    def replace_property(self, property: Property, account_id: str, expected_version: int) -> None:
        self._client.transact_write_items(TransactItems=[
            *self._permission_checks(account_id, property.organisation_id),
            {"Put": {
                "TableName": self._table_name,
                "Item": _to_dynamodb_item(property.model_dump(mode="json")),
                "ConditionExpression": "attribute_exists(property_id) AND #version = :version AND #status = :draft",
                "ExpressionAttributeNames": {"#version": "version", "#status": "status"},
                "ExpressionAttributeValues": {
                    ":version": {"N": str(expected_version)},
                    ":draft": {"S": "DRAFT"},
                },
            }},
        ])

    @staticmethod
    def _deletion_key(organisation_id: str, property_id: str) -> str:
        return f"deleted:{organisation_id}:{property_id}"

    def is_deleted(self, organisation_id: str, property_id: str) -> bool:
        response = self._client.get_item(
            TableName=self._requests_table_name,
            Key={"request_id": {"S": self._deletion_key(organisation_id, property_id)}},
            ConsistentRead=True,
        )
        return "Item" in response

    def delete_draft(self, property: Property, account_id: str, expected_version: int) -> None:
        self._client.transact_write_items(TransactItems=[
            *self._permission_checks(account_id, property.organisation_id),
            {"Delete": {
                "TableName": self._table_name,
                "Key": self._key(property.organisation_id, property.property_id),
                "ConditionExpression": (
                    "attribute_exists(property_id) AND #version = :version "
                    "AND (#status = :draft OR #status = :archived) "
                    "AND attribute_not_exists(published_at) "
                    "AND (attribute_not_exists(has_booking_history) OR has_booking_history = :false)"
                ),
                "ExpressionAttributeNames": {"#version": "version", "#status": "status"},
                "ExpressionAttributeValues": {
                    ":version": {"N": str(expected_version)}, ":draft": {"S": "DRAFT"},
                    ":archived": {"S": "ARCHIVED"}, ":false": {"BOOL": False},
                },
            }},
            {"Put": {
                "TableName": self._requests_table_name,
                "Item": _to_dynamodb_item({
                    "request_id": self._deletion_key(property.organisation_id, property.property_id),
                    "organisation_id": property.organisation_id,
                    "property_id": property.property_id, "status": "DELETED",
                }),
                "ConditionExpression": "attribute_not_exists(request_id)",
            }},
        ])

    def _permission_checks(self, account_id: str, organisation_id: str) -> list[dict]:
        # Recheck authorisation atomically with every mutation, including revocation races.
        checks = [
            (self._accounts_table_name, {"id": {"S": account_id}}),
            (self._organisations_table_name, {"organisation_id": {"S": organisation_id}}),
            (self._memberships_table_name, {
                "account_id": {"S": account_id},
                "organisation_id": {"S": organisation_id},
            }),
        ]
        result = []
        for table, key in checks:
            check = {
                "TableName": table, "Key": key,
                "ConditionExpression": "#status = :active",
                "ExpressionAttributeNames": {"#status": "status"},
                "ExpressionAttributeValues": {":active": {"S": "active"}},
            }
            if table == self._memberships_table_name:
                check["ConditionExpression"] += " AND #role = :admin"
                check["ExpressionAttributeNames"]["#role"] = "role"
                check["ExpressionAttributeValues"][":admin"] = {"S": "admin"}
            result.append({"ConditionCheck": check})
        return result

    @staticmethod
    def _key(organisation_id: str, property_id: str) -> dict:
        return {"organisation_id": {"S": organisation_id}, "property_id": {"S": property_id}}

    def ensure_tables(self) -> None:
        for table, keys in (
            (self._table_name, ["organisation_id", "property_id"]),
            (self._requests_table_name, ["request_id"]),
        ):
            try:
                self._client.describe_table(TableName=table)
                continue
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "ResourceNotFoundException":
                    raise
            self._client.create_table(
                TableName=table,
                KeySchema=[{"AttributeName": key, "KeyType": "HASH" if i == 0 else "RANGE"}
                           for i, key in enumerate(keys)],
                AttributeDefinitions=[{"AttributeName": key, "AttributeType": "S"} for key in keys],
                BillingMode="PAY_PER_REQUEST",
            )
            self._client.get_waiter("table_exists").wait(TableName=table)


@lru_cache
def get_property_dao() -> PropertyDAO:
    settings = get_settings()
    client = boto3.client(
        "dynamodb", region_name=settings.aws_region,
        endpoint_url=settings.dynamodb_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    return PropertyDAO(
        client, settings.dynamodb_properties_table_name,
        settings.dynamodb_property_requests_table_name,
        settings.dynamodb_accounts_table_name,
        settings.dynamodb_organisations_table_name,
        settings.dynamodb_memberships_table_name,
    )
