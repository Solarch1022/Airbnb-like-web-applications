from fastapi import Depends, HTTPException

from app.dependencies.organisation import require_org_admin, require_org_member
from app.models.organisation import OrganisationContext
from app.models.property import Property
from app.services.property_service import PropertyNotFoundError, PropertyService, get_property_service


def require_property_read(
    property_id: str,
    context: OrganisationContext = Depends(require_org_member),
    service: PropertyService = Depends(get_property_service),
) -> Property:
    try:
        return service.get(context.organisation.organisation_id, property_id)
    except PropertyNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Property not found") from exc


def require_property_admin(
    property: Property = Depends(require_property_read),
    context: OrganisationContext = Depends(require_org_admin),
) -> Property:
    return property
