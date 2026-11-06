from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import uuid4

from botocore.exceptions import ClientError
from fastapi import Depends

from app.dao.organisation_dao import OrganisationDAO, get_organisation_dao
from app.models.organisation import (
    Membership,
    MembershipStatus,
    Organisation,
    OrganisationContext,
    OrganisationCreate,
    OrganisationRole,
    OrganisationStatus,
)


class OrganisationPermissionError(ValueError):
    pass


class OrganisationConflictError(ValueError):
    pass


class OrganisationService:

    def __init__(self, organisation_dao: OrganisationDAO) -> None:
        self._organisation_dao = organisation_dao

    def get_context(
        self,
        account_id: str,
        organisation_id: str,
    ) -> OrganisationContext:
        membership = self._organisation_dao.get_membership(
            account_id, organisation_id,
        )
        if (
            membership is None
            or membership.status != MembershipStatus.ACTIVE
            or membership.account_id != account_id
            or membership.organisation_id != organisation_id
        ):
            raise OrganisationPermissionError("Organisation access denied")

        organisation = self._organisation_dao.get_organisation(organisation_id)
        if (
            organisation is None
            or organisation.status != OrganisationStatus.ACTIVE
        ):
            raise OrganisationPermissionError("Organisation access denied")

        return OrganisationContext(
            organisation=organisation,
            membership=membership,
        )

    def list_contexts(self, account_id: str) -> list[OrganisationContext]:
        contexts = []
        for membership in self._organisation_dao.list_memberships(account_id):
            try:
                contexts.append(self.get_context(
                    account_id, membership.organisation_id,
                ))
            except OrganisationPermissionError:
                continue
        return contexts

    def create(
        self,
        account_id: str,
        payload: OrganisationCreate,
        idempotency_key: str,
    ) -> OrganisationContext:
        request_id = sha256(json.dumps(
            [account_id, idempotency_key],
        ).encode()).hexdigest()
        fingerprint = sha256(payload.model_dump_json().encode()).hexdigest()
        existing = self._organisation_dao.get_creation_request(request_id)
        if existing:
            return self._replay(account_id, existing, fingerprint)

        now = datetime.now(timezone.utc)
        organisation = Organisation(
            organisation_id=str(uuid4()),
            name=payload.name,
            status=OrganisationStatus.ACTIVE,
            created_by=account_id,
            created_at=now,
            updated_at=now,
        )
        membership = Membership(
            organisation_id=organisation.organisation_id,
            account_id=account_id,
            role=OrganisationRole.ADMIN,
            status=MembershipStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        try:
            self._organisation_dao.create_organisation(
                organisation, membership, request_id, fingerprint,
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "TransactionCanceledException":
                raise
            reasons = exc.response.get("CancellationReasons", [])
            if not reasons or any(
                reason.get("Code", "None") not in (
                    "None", "ConditionalCheckFailed", "TransactionConflict",
                ) for reason in reasons
            ):
                raise
            existing = self._organisation_dao.get_creation_request(request_id)
            if existing:
                return self._replay(account_id, existing, fingerprint)
            raise OrganisationConflictError(
                "Creation could not complete; retry with the same Idempotency-Key"
            ) from exc

        return OrganisationContext(organisation=organisation, membership=membership)

    def _replay(
        self,
        account_id: str,
        existing: dict,
        fingerprint: str,
    ) -> OrganisationContext:
        if existing["fingerprint"] != fingerprint:
            raise OrganisationConflictError(
                "Idempotency-Key was already used with different details"
            )
        return self.get_context(account_id, existing["organisation_id"])


def get_organisation_service(
    organisation_dao: OrganisationDAO = Depends(get_organisation_dao),
) -> OrganisationService:
    return OrganisationService(organisation_dao=organisation_dao)
