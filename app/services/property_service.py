import base64
from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import uuid4

from pydantic import ValidationError

from botocore.exceptions import ClientError
from fastapi import Depends

from app.dao.property_dao import PropertyDAO, get_property_dao
from app.models.property import Property, PropertyCreate, PropertyPage, PropertyStatus, PropertyUpdate, PropertyReadiness, ReadinessIssue, PublicProperty, PublicPropertyPage


class PropertyNotFoundError(ValueError):
    pass


class PropertyConflictError(ValueError):
    pass


class PropertyPermissionError(ValueError):
    pass


class PropertyDeletedError(ValueError):
    pass


class PropertyReadinessError(ValueError):
    def __init__(self, issues: list[ReadinessIssue]) -> None:
        self.issues = issues
        super().__init__("Property configuration is incomplete or invalid")


PROVISIONING_FIELDS = {"public_location", "min_nights", "max_nights", "preparation_nights", "blocked_dates"}
SUPPORTED_CURRENCIES = {"AUD", "USD", "EUR", "GBP", "NZD"}


class PropertyCursorError(ValueError):
    pass


class PropertyService:

    def __init__(self, property_dao: PropertyDAO) -> None:
        self._property_dao = property_dao

    def get(self, organisation_id: str, property_id: str) -> Property:
        property = self._property_dao.get_property(organisation_id, property_id)
        if property is None or property.organisation_id != organisation_id or property.property_id != property_id:
            raise PropertyNotFoundError("Property not found")
        return property

    def list(self, organisation_id: str, limit: int, cursor: str | None) -> PropertyPage:
        after = None
        if cursor:
            try:
                data = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
                if (not isinstance(data, dict) or set(data) != {"organisation_id", "property_id"}
                    or data["organisation_id"] != organisation_id
                    or not isinstance(data["property_id"], str) or not 1 <= len(data["property_id"]) <= 128):
                    raise ValueError()
                after = data["property_id"]
            except (ValueError, TypeError, UnicodeError) as exc:
                raise PropertyCursorError("Invalid pagination cursor for this organisation") from exc
        items, last_id = self._property_dao.list_properties(organisation_id, limit, after)
        next_cursor = None
        if last_id:
            next_cursor = base64.urlsafe_b64encode(json.dumps({
                "organisation_id": organisation_id, "property_id": last_id,
            }).encode()).decode()
        return PropertyPage(items=items, next_cursor=next_cursor)

    def create(
        self, organisation_id: str, account_id: str, payload: PropertyCreate, idempotency_key: str,
    ) -> Property:
        request_id = sha256(json.dumps([account_id, organisation_id, idempotency_key]).encode()).hexdigest()
        fingerprint = sha256(payload.model_dump_json().encode()).hexdigest()
        legacy_fingerprint = None
        if all(getattr(payload, field) in (None, []) for field in PROVISIONING_FIELDS):
            legacy_fingerprint = sha256(payload.model_dump_json(exclude=PROVISIONING_FIELDS).encode()).hexdigest()
        existing = self._property_dao.get_creation_request(request_id)
        if existing:
            return self._replay(existing, fingerprint, legacy_fingerprint)
        now = datetime.now(timezone.utc)
        property = Property(
            **payload.model_dump(), property_id=str(uuid4()), organisation_id=organisation_id,
            created_by=account_id, status=PropertyStatus.DRAFT,
            created_at=now, updated_at=now, version=1,
        )
        try:
            self._property_dao.create_property(property, account_id, request_id, fingerprint)
        except ClientError as exc:
            self._check_transaction_error(exc)
            existing = self._property_dao.get_creation_request(request_id)
            if existing:
                return self._replay(existing, fingerprint, legacy_fingerprint)
            raise PropertyConflictError("Creation conflicted; retry with the same Idempotency-Key") from exc
        return property

    def update(self, property: Property, account_id: str, payload: PropertyUpdate) -> Property:
        self._check_version(property, payload.expected_version)
        if property.status == PropertyStatus.ARCHIVED:
            raise PropertyConflictError("Archived properties cannot be edited")
        data = property.model_dump()
        data.update(payload.model_dump(exclude_unset=True, exclude={"expected_version"}))
        data.update(updated_at=datetime.now(timezone.utc), version=property.version + 1)
        try:
            updated = Property.model_validate(data)
        except ValidationError as exc:
            raise PropertyReadinessError([ReadinessIssue(field="stay_rules", message="Maximum nights must be at least minimum nights")]) from exc
        # Calendar allocation changes need booking conflict checks in later phases.
        # Fail closed until that workflow exists rather than overwriting reserved nights.
        if property.has_booking_history and any(
            getattr(updated, field) != getattr(property, field)
            for field in ("blocked_dates", "preparation_nights")
        ):
            raise PropertyConflictError("Calendar changes on properties with booking history require booking conflict checks")
        if updated.status == PropertyStatus.ACTIVE:
            self._require_ready(updated)
        self._replace(updated, account_id, property.version, property.status)
        return updated

    def archive(self, property: Property, account_id: str, expected_version: int) -> Property:
        self._check_version(property, expected_version)
        if property.status == PropertyStatus.ARCHIVED:
            return property
        archived = property.model_copy(update={
            "status": PropertyStatus.ARCHIVED, "version": property.version + 1,
            "updated_at": datetime.now(timezone.utc),
        })
        self._replace(archived, account_id, property.version, property.status)
        return archived

    def delete_draft(self, property: Property, account_id: str, expected_version: int) -> None:
        self._check_version(property, expected_version)
        if (property.status not in (PropertyStatus.DRAFT, PropertyStatus.ARCHIVED)
            or property.published_at is not None or property.has_booking_history):
            raise PropertyConflictError("Only never-published drafts without booking history can be deleted")
        try:
            self._property_dao.delete_draft(property, account_id, expected_version)
        except ClientError as exc:
            self._check_transaction_error(exc)
            raise PropertyConflictError("Property changed or is no longer eligible for deletion; reload before retrying") from exc

    def readiness(self, property: Property) -> PropertyReadiness:
        issues = []
        required = {
            "title": "Add a title", "description": "Add a description", "address": "Add the private property address",
            "public_location": "Add a public city or area", "property_type": "Add a property type",
            "price_per_night": "Set a positive nightly price", "currency": "Choose a currency",
            "max_guests": "Set guest capacity", "images": "Add at least one HTTP/HTTPS image URL",
            "booking_mode": "Explicitly choose INSTANT or REQUEST", "min_nights": "Set minimum stay nights",
            "max_nights": "Set maximum stay nights", "preparation_nights": "Set preparation nights (0 is allowed)",
        }
        for field, message in required.items():
            value = getattr(property, field)
            if value is None or value == [] or value == "":
                issues.append(ReadinessIssue(field=field, message=message))
        if property.currency and property.currency not in SUPPORTED_CURRENCIES:
            issues.append(ReadinessIssue(field="currency", message="Supported currencies: AUD, USD, EUR, GBP, NZD"))
        ready = not issues
        return PropertyReadiness(
            ready=ready, can_publish=ready and property.status in (PropertyStatus.DRAFT, PropertyStatus.INACTIVE),
            version=property.version, status=property.status, issues=issues,
        )

    def _require_ready(self, property: Property) -> None:
        readiness = self.readiness(property)
        if not readiness.ready:
            raise PropertyReadinessError(readiness.issues)

    def publish(self, property: Property, account_id: str, expected_version: int) -> Property:
        self._check_version(property, expected_version)
        if property.status == PropertyStatus.ARCHIVED:
            raise PropertyConflictError("Archived properties cannot be published")
        self._require_ready(property)
        if property.status == PropertyStatus.ACTIVE:
            return property
        now = datetime.now(timezone.utc)
        published = property.model_copy(update={
            "status": PropertyStatus.ACTIVE, "published_at": property.published_at or now,
            "updated_at": now, "version": property.version + 1,
        })
        self._replace(published, account_id, property.version, property.status)
        return published

    def deactivate(self, property: Property, account_id: str, expected_version: int) -> Property:
        self._check_version(property, expected_version)
        if property.status == PropertyStatus.INACTIVE:
            return property
        if property.status != PropertyStatus.ACTIVE:
            raise PropertyConflictError("Only active properties can be taken offline")
        inactive = property.model_copy(update={
            "status": PropertyStatus.INACTIVE, "updated_at": datetime.now(timezone.utc), "version": property.version + 1,
        })
        self._replace(inactive, account_id, property.version, property.status)
        return inactive

    def public_property(self, property: Property) -> PublicProperty:
        if property.status != PropertyStatus.ACTIVE or not self.readiness(property).ready:
            raise PropertyNotFoundError("Listing not found")
        return PublicProperty.model_validate(property.model_dump())

    def list_public(self, organisation_id: str, limit: int, cursor: str | None) -> PublicPropertyPage:
        page = self.list(organisation_id, limit, cursor)
        items = [self.public_property(property) for property in page.items
                 if property.status == PropertyStatus.ACTIVE and self.readiness(property).ready]
        # Preserve the physical query cursor even on an empty filtered page.
        return PublicPropertyPage(items=items, next_cursor=page.next_cursor)

    def _replace(self, property: Property, account_id: str, version: int, expected_status: str = "DRAFT") -> None:
        try:
            self._property_dao.replace_property(property, account_id, version, expected_status)
        except ClientError as exc:
            self._check_transaction_error(exc)
            raise PropertyConflictError("Property changed; reload before retrying") from exc

    @staticmethod
    def _check_version(property: Property, expected_version: int) -> None:
        if property.version != expected_version:
            raise PropertyConflictError("Property changed; reload before retrying")

    def _replay(self, existing: dict, fingerprint: str, legacy_fingerprint: str | None = None) -> Property:
        if existing["fingerprint"] != fingerprint and (legacy_fingerprint is None or existing["fingerprint"] != legacy_fingerprint):
            raise PropertyConflictError("Idempotency-Key was already used with different details")
        # Return the original creation response even if the listing has since been edited/archived.
        property = Property.model_validate(existing["property"])
        if self._property_dao.is_deleted(property.organisation_id, property.property_id):
            raise PropertyDeletedError("This property was permanently deleted; use a new Idempotency-Key for a new draft")
        return property

    @staticmethod
    def _check_transaction_error(exc: ClientError) -> None:
        if exc.response["Error"]["Code"] != "TransactionCanceledException":
            raise exc
        reasons = exc.response.get("CancellationReasons", [])
        if not reasons or any(reason.get("Code", "None") not in (
            "None", "ConditionalCheckFailed", "TransactionConflict",
        ) for reason in reasons):
            raise exc
        if any(reason.get("Code") == "ConditionalCheckFailed" for reason in reasons[:3]):
            raise PropertyPermissionError("Property management access denied") from exc


def get_property_service(
    property_dao: PropertyDAO = Depends(get_property_dao),
) -> PropertyService:
    return PropertyService(property_dao)
