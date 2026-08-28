from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Any
from enum import Enum

import boto3
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings
from app.models.auth import OTPVerification, VerificationPurpose


_serializer = TypeSerializer()
_deserializer = TypeDeserializer()


def _prepare_value(value: Any) -> Any:

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, Enum):
        return value.value

    return value


def _to_dynamodb_item(data: dict[str, Any]) -> dict[str, Any]:

    return {
        key: _serializer.serialize(_prepare_value(value))
        for key, value in data.items()
        if value is not None
    }


def _from_dynamodb_item(item: dict[str, Any]) -> dict[str, Any]:

    return {
        key: _deserializer.deserialize(value)
        for key, value in item.items()
    }


class OTPVerificationDAO:

    def __init__(self, client: Any, table_name: str) -> None:
        self._client = client
        self._table_name = table_name

    def get_verification(
        self,
        identifier: str,
        purpose: VerificationPurpose,
    ) -> OTPVerification | None:
        response = self._client.get_item(
            TableName=self._table_name,
            Key={
                "identifier": {"S": identifier},
                "purpose": {"S": purpose.value},
            },
        )

        item = response.get("Item")

        if not item:
            return None

        return OTPVerification.model_validate(
            _from_dynamodb_item(item)
        )

    def put_verification(
        self,
        verification: OTPVerification,
    ) -> OTPVerification:
        self._client.put_item(
            TableName=self._table_name,
            Item=_to_dynamodb_item(
                verification.model_dump()
            ),
        )

        return verification

    def update_verification(
        self,
        verification: OTPVerification,
    ) -> OTPVerification:
        return self.put_verification(verification)

    def delete_verification(
        self,
        identifier: str,
        purpose: VerificationPurpose,
    ) -> bool:
        try:
            response = self._client.delete_item(
                TableName=self._table_name,
                Key={
                    "identifier": {"S": identifier},
                    "purpose": {"S": purpose.value},
                },
                ConditionExpression="attribute_exists(identifier)",
                ReturnValues="ALL_OLD",
            )

        except ClientError as exc:
            if (
                exc.response["Error"]["Code"]
                == "ConditionalCheckFailedException"
            ):
                return False
            
            raise

        return "Attributes" in response

    def ensure_table(self) -> None:
        try:
            self._client.describe_table(TableName=self._table_name)
            return
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ResourceNotFoundException":
                raise

        self._client.create_table(
            TableName=self._table_name,
            AttributeDefinitions=[
                {
                    "AttributeName": "identifier",
                    "AttributeType": "S",
                },
                {
                    "AttributeName": "purpose",
                    "AttributeType": "S",
                },
            ],
            KeySchema=[
                {
                    "AttributeName": "identifier",
                    "KeyType": "HASH",
                },
                {
                    "AttributeName": "purpose",
                    "KeyType": "RANGE",
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        self._client.get_waiter("table_exists").wait(
            TableName=self._table_name
        )


@lru_cache
def get_otp_verification_dao() -> OTPVerificationDAO:
    settings: Settings = get_settings()

    client = boto3.client(
        "dynamodb",
        region_name=settings.aws_region,
        endpoint_url=settings.dynamodb_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )

    return OTPVerificationDAO(
        client=client,
        table_name=settings.dynamodb_otp_verifications_table_name,
    )