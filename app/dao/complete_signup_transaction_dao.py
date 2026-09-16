from datetime import datetime, timezone

from functools import lru_cache
from typing import Any

import boto3

from app.core.config import Settings, get_settings


class CompleteSignupTransactionDAO:

    def __init__(
        self,
        client: Any,
        accounts_table_name: str,
        registration_tokens_table_name: str,
    ) -> None:
        self._client = client
        self._accounts_table_name = accounts_table_name
        self._registration_tokens_table_name = (
            registration_tokens_table_name
        )

    def complete_signup(
        self,
        account_id: str,
        registration_token_jti: str,
        first_name: str,
        last_name: str,
        password_hash: str,
    ) -> None:
        updated_at = datetime.now(timezone.utc).isoformat()

        self._client.transact_write_items(
            TransactItems=[
                {
                    "Update": {
                        "TableName": self._accounts_table_name,
                        "Key": {
                            "id": {
                                "S": account_id,
                            }
                        },
                        "ConditionExpression": (
                            "#status = :pending_setup"
                        ),
                        "UpdateExpression": (
                            "SET first_name = :first_name, "
                            "last_name = :last_name, "
                            "password_hash = :password_hash, "
                            "#status = :active, "
                            "updated_at = :updated_at"
                        ),
                        "ExpressionAttributeNames": {
                            "#status": "status",
                        },
                        "ExpressionAttributeValues": {
                            ":pending_setup": {
                                "S": "pending_setup",
                            },
                            ":first_name": {
                                "S": first_name,
                            },
                            ":last_name": {
                                "S": last_name,
                            },
                            ":password_hash": {
                                "S": password_hash,
                            },
                            ":active": {
                                "S": "active",
                            },
                            ":updated_at": {
                                "S": updated_at,
                            },
                        },
                    }
                },
                {
                    "Update": {
                        "TableName": (
                            self._registration_tokens_table_name
                        ),
                        "Key": {
                            "jti": {
                                "S": registration_token_jti,
                            }
                        },
                        "ConditionExpression": (
                            "#status = :active"
                        ),
                        "UpdateExpression": (
                            "SET #status = :consumed"
                        ),
                        "ExpressionAttributeNames": {
                            "#status": "status",
                        },
                        "ExpressionAttributeValues": {
                            ":active": {
                                "S": "active",
                            },
                            ":consumed": {
                                "S": "consumed",
                            },
                        },
                    }
                },
            ]
        )


@lru_cache
def get_complete_signup_transaction_dao(
) -> CompleteSignupTransactionDAO:
    settings: Settings = get_settings()

    client = boto3.client(
        "dynamodb",
        region_name=settings.aws_region,
        endpoint_url=settings.dynamodb_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=(
            settings.aws_secret_access_key
        ),
    )

    return CompleteSignupTransactionDAO(
        client=client,
        accounts_table_name=(
            settings.dynamodb_accounts_table_name
        ),
        registration_tokens_table_name=(
            settings.dynamodb_registration_tokens_table_name
        ),
    )