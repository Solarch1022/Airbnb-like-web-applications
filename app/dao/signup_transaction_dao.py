from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Any

import boto3

from app.core.config import Settings, get_settings
from app.models.account import AccountStatus
from app.models.auth import (
    VerificationPurpose,
    VerificationStatus,
)


class SignupTransactionDAO:

    def __init__(
        self,
        client: Any,
        accounts_table_name: str,
        otp_verifications_table_name: str,
    ) -> None:
        self._client = client
        self._accounts_table_name = accounts_table_name
        self._otp_verifications_table_name = (
            otp_verifications_table_name
        )

    def activate_account_and_consume_verification(
        self,
        account_id: str,
        identifier: str,
        purpose: VerificationPurpose,
        code_hash: str,
        updated_at: datetime,
    ) -> None:
        self._client.transact_write_items(
            TransactItems=[
                {
                    "Update": {
                        "TableName": self._accounts_table_name,
                        "Key": {
                            "id": {"S": account_id},
                        },
                        "UpdateExpression": (
                            "SET #status = :active, "
                            "updated_at = :updated_at"
                        ),
                        "ConditionExpression": (
                            "#status = :unverified"
                        ),
                        "ExpressionAttributeNames": {
                            "#status": "status",
                        },
                        "ExpressionAttributeValues": {
                            ":active": {
                                "S": AccountStatus.ACTIVE.value,
                            },
                            ":unverified": {
                                "S": AccountStatus.UNVERIFIED.value,
                            },
                            ":updated_at": {
                                "S": updated_at.isoformat(),
                            },
                        },
                    },
                },
                {
                    "Update": {
                        "TableName": self._otp_verifications_table_name,
                        "Key": {
                            "identifier": {"S": identifier},
                            "purpose": {"S": purpose.value},
                        },
                        "UpdateExpression": "SET #status = :consumed",
                        "ConditionExpression": (
                            "#status = :pending "
                            "AND code_hash = :code_hash "
                            "AND otp_expires_at > :now "
                            "AND session_expires_at > :now"
                        ),
                        "ExpressionAttributeNames": {
                            "#status": "status",
                        },
                        "ExpressionAttributeValues": {
                            ":consumed": {
                                "S": VerificationStatus.CONSUMED.value,
                            },
                            ":pending": {
                                "S": VerificationStatus.PENDING.value,
                            },
                            ":code_hash": {
                                "S": code_hash,
                            },
                            ":now": {
                                "S": updated_at.isoformat(),
                            },
                        },
                    },
                },
            ]
        )


@lru_cache
def get_signup_transaction_dao() -> SignupTransactionDAO:
    settings: Settings = get_settings()

    client = boto3.client(
        "dynamodb",
        region_name=settings.aws_region,
        endpoint_url=settings.dynamodb_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )

    return SignupTransactionDAO(
        client=client,
        accounts_table_name=settings.dynamodb_accounts_table_name,
        otp_verifications_table_name=(
            settings.dynamodb_otp_verifications_table_name
        ),
    )