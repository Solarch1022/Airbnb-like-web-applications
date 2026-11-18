from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.dao.organisation_dao import OrganisationDAO, get_organisation_dao
from app.models.organisation import OrganisationStatus
from app.models.property import PublicProperty, PublicPropertyPage
from app.services.property_service import PropertyCursorError, PropertyNotFoundError, PropertyService, get_property_service


router = APIRouter(tags=["public listings"])


def require_public_organisation(
    organisation_id: str,
    dao: OrganisationDAO = Depends(get_organisation_dao),
) -> str:
    organisation = dao.get_organisation(organisation_id)
    if organisation is None or organisation.status != OrganisationStatus.ACTIVE:
        raise HTTPException(status_code=404, detail="Listings not found")
    return organisation_id


@router.get("/public/organisations/{organisation_id}/properties", response_model=PublicPropertyPage)
def list_public_properties(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, min_length=1, max_length=1024),
    organisation_id: str = Depends(require_public_organisation),
    service: PropertyService = Depends(get_property_service),
) -> PublicPropertyPage:
    try:
        return service.list_public(organisation_id, limit, cursor)
    except PropertyCursorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/public/organisations/{organisation_id}/properties/{property_id}", response_model=PublicProperty)
def get_public_property(
    property_id: str,
    organisation_id: str = Depends(require_public_organisation),
    service: PropertyService = Depends(get_property_service),
) -> PublicProperty:
    try:
        return service.public_property(service.get(organisation_id, property_id))
    except PropertyNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Listing not found") from exc


@router.get("/listings", response_class=HTMLResponse, include_in_schema=False)
def listings_page() -> HTMLResponse:
    page = Path(__file__).resolve().parents[1] / "templates" / "listings.html"
    return HTMLResponse(page.read_text(encoding="utf-8"))
