from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings
from app.dao.account_dao import _from_dynamodb_item, _to_dynamodb_item
from app.models.organisation import Membership, Organisation


class OrganisationDAO:

    def __init__(
        self,
        client: Any,
        organisations_table_name: str,
        memberships_table_name: str,
        requests_table_name: str,
        accounts_table_name: str,
    ) -> None:
        self._client = client
        self._organisations_table_name = organisations_table_name
        self._memberships_table_name = memberships_table_name
        self._requests_table_name = requests_table_name
        self._accounts_table_name = accounts_table_name

    def get_organisation(
        self,
        organisation_id: str,
    ) -> Organisation | None:
        response = self._client.get_item(
            TableName=self._organisations_table_name,
            Key={"organisation_id": {"S": organisation_id}},
            ConsistentRead=True,
        )
        item = response.get("Item")
        return Organisation.model_validate(
            _from_dynamodb_item(item)
        ) if item else None

    def get_membership(
        self,
        account_id: str,
        organisation_id: str,
    ) -> Membership | None:
        response = self._client.get_item(
            TableName=self._memberships_table_name,
            Key={
                "account_id": {"S": account_id},
                "organisation_id": {"S": organisation_id},
            },
            ConsistentRead=True,
        )
        item = response.get("Item")
        return Membership.model_validate(
            _from_dynamodb_item(item)
        ) if item else None

    def list_memberships(
        self,
        account_id: str,
    ) -> list[Membership]:
        memberships = []
        request = {
            "TableName": self._memberships_table_name,
            "KeyConditionExpression": "account_id = :account_id",
            "ExpressionAttributeValues": {
                ":account_id": {"S": account_id},
            },
            "ConsistentRead": True,
        }
        while True:
            response = self._client.query(**request)
            memberships.extend(
                Membership.model_validate(_from_dynamodb_item(item))
                for item in response.get("Items", [])
            )
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                return memberships
            request["ExclusiveStartKey"] = last_key

    def get_creation_request(
        self,
        request_id: str,
    ) -> dict | None:
        response = self._client.get_item(
            TableName=self._requests_table_name,
            Key={"request_id": {"S": request_id}},
            ConsistentRead=True,
        )
        item = response.get("Item")
        return _from_dynamodb_item(item) if item else None

    def create_organisation(
        self,
        organisation: Organisation,
        membership: Membership,
        request_id: str,
        fingerprint: str,
    ) -> None:
        self._client.transact_write_items(
            TransactItems=[
                {
                    "ConditionCheck": {
                        "TableName": self._accounts_table_name,
                        "Key": {"id": {"S": membership.account_id}},
                        "ConditionExpression": "#status = :active",
                        "ExpressionAttributeNames": {"#status": "status"},
                        "ExpressionAttributeValues": {":active": {"S": "active"}},
                    },
                },
                {
                    "Put": {
                        "TableName": self._organisations_table_name,
                        "Item": _to_dynamodb_item(organisation.model_dump()),
                        "ConditionExpression": "attribute_not_exists(organisation_id)",
                    },
                },
                {
                    "Put": {
                        "TableName": self._memberships_table_name,
                        "Item": _to_dynamodb_item(membership.model_dump()),
                        "ConditionExpression": "attribute_not_exists(account_id)",
                    },
                },
                {
                    "Put": {
                        "TableName": self._requests_table_name,
                        "Item": _to_dynamodb_item({
                            "request_id": request_id,
                            "organisation_id": organisation.organisation_id,
                            "fingerprint": fingerprint,
                        }),
                        "ConditionExpression": "attribute_not_exists(request_id)",
                    },
                },
            ],
        )

    def ensure_tables(self) -> None:
        tables = [
            (self._organisations_table_name, "organisation_id", None),
            (self._memberships_table_name, "account_id", "organisation_id"),
            (self._requests_table_name, "request_id", None),
        ]
        for table_name, partition_key, sort_key in tables:
            try:
                self._client.describe_table(TableName=table_name)
                continue
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "ResourceNotFoundException":
                    raise
            keys = [{"AttributeName": partition_key, "KeyType": "HASH"}]
            attributes = [{"AttributeName": partition_key, "AttributeType": "S"}]
            if sort_key:
                keys.append({"AttributeName": sort_key, "KeyType": "RANGE"})
                attributes.append({"AttributeName": sort_key, "AttributeType": "S"})
            self._client.create_table(
                TableName=table_name,
                KeySchema=keys,
                AttributeDefinitions=attributes,
                BillingMode="PAY_PER_REQUEST",
            )
            self._client.get_waiter("table_exists").wait(TableName=table_name)


@lru_cache
def get_organisation_dao() -> OrganisationDAO:
    settings: Settings = get_settings()
    client = boto3.client(
        "dynamodb",
        region_name=settings.aws_region,
        endpoint_url=settings.dynamodb_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    return OrganisationDAO(
        client=client,
        organisations_table_name=settings.dynamodb_organisations_table_name,
        memberships_table_name=settings.dynamodb_memberships_table_name,
        requests_table_name=settings.dynamodb_organisation_requests_table_name,
        accounts_table_name=settings.dynamodb_accounts_table_name,
    )
