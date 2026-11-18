from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status

from app.dependencies.organisation import require_org_admin, require_org_member
from app.dependencies.property import require_property_admin, require_property_read
from app.models.organisation import OrganisationContext
from app.models.property import Property, PropertyCreate, PropertyPage, PropertyUpdate, PropertyReadiness, PropertyVersionRequest
from app.services.property_service import (
    PropertyConflictError, PropertyCursorError, PropertyDeletedError, PropertyPermissionError, PropertyReadinessError,
    PropertyService, get_property_service,
)


router = APIRouter(prefix="/organisations/{organisation_id}/properties", tags=["properties"])


def _write_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=403 if isinstance(exc, PropertyPermissionError) else 409, detail=str(exc))


@router.post("", response_model=Property, status_code=status.HTTP_201_CREATED)
def create_property(
    payload: PropertyCreate,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"),
    context: OrganisationContext = Depends(require_org_admin),
    service: PropertyService = Depends(get_property_service),
) -> Property:
    try:
        return service.create(context.organisation.organisation_id, context.membership.account_id, payload, idempotency_key)
    except PropertyDeletedError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except (PropertyConflictError, PropertyPermissionError) as exc:
        raise _write_error(exc) from exc


@router.get("", response_model=PropertyPage)
def list_properties(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, min_length=1, max_length=1024),
    context: OrganisationContext = Depends(require_org_member),
    service: PropertyService = Depends(get_property_service),
) -> PropertyPage:
    try:
        return service.list(context.organisation.organisation_id, limit, cursor)
    except PropertyCursorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{property_id}", response_model=Property)
def get_property(property: Property = Depends(require_property_read)) -> Property:
    return property


@router.patch("/{property_id}", response_model=Property)
def update_property(
    payload: PropertyUpdate,
    property: Property = Depends(require_property_admin),
    context: OrganisationContext = Depends(require_org_admin),
    service: PropertyService = Depends(get_property_service),
) -> Property:
    try:
        return service.update(property, context.membership.account_id, payload)
    except PropertyReadinessError as exc:
        raise HTTPException(status_code=422, detail=[issue.model_dump() for issue in exc.issues]) from exc
    except (PropertyConflictError, PropertyPermissionError) as exc:
        raise _write_error(exc) from exc


@router.delete("/{property_id}", response_model=Property)
def archive_property(
    expected_version: int = Query(ge=1),
    property: Property = Depends(require_property_admin),
    context: OrganisationContext = Depends(require_org_admin),
    service: PropertyService = Depends(get_property_service),
) -> Property:
    try:
        return service.archive(property, context.membership.account_id, expected_version)
    except (PropertyConflictError, PropertyPermissionError) as exc:
        raise _write_error(exc) from exc



@router.delete("/{property_id}/draft", status_code=status.HTTP_204_NO_CONTENT)
def delete_property_draft(
    expected_version: int = Query(ge=1),
    property: Property = Depends(require_property_admin),
    context: OrganisationContext = Depends(require_org_admin),
    service: PropertyService = Depends(get_property_service),
) -> Response:
    try:
        service.delete_draft(property, context.membership.account_id, expected_version)
    except (PropertyConflictError, PropertyPermissionError) as exc:
        raise _write_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)



@router.get("/{property_id}/readiness", response_model=PropertyReadiness)
def get_property_readiness(
    property: Property = Depends(require_property_read),
    service: PropertyService = Depends(get_property_service),
) -> PropertyReadiness:
    return service.readiness(property)


@router.post("/{property_id}/publish", response_model=Property)
def publish_property(
    payload: PropertyVersionRequest,
    property: Property = Depends(require_property_admin),
    context: OrganisationContext = Depends(require_org_admin),
    service: PropertyService = Depends(get_property_service),
) -> Property:
    try:
        return service.publish(property, context.membership.account_id, payload.expected_version)
    except PropertyReadinessError as exc:
        raise HTTPException(status_code=422, detail=[issue.model_dump() for issue in exc.issues]) from exc
    except (PropertyConflictError, PropertyPermissionError) as exc:
        raise _write_error(exc) from exc


@router.post("/{property_id}/deactivate", response_model=Property)
def deactivate_property(
    payload: PropertyVersionRequest,
    property: Property = Depends(require_property_admin),
    context: OrganisationContext = Depends(require_org_admin),
    service: PropertyService = Depends(get_property_service),
) -> Property:
    try:
        return service.deactivate(property, context.membership.account_id, payload.expected_version)
    except (PropertyConflictError, PropertyPermissionError) as exc:
        raise _write_error(exc) from exc
