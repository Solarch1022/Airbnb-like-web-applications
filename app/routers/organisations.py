from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import HTMLResponse

from app.dependencies.auth import get_current_user
from app.dependencies.organisation import require_org_admin, require_org_member
from app.models.auth import CurrentUser
from app.models.organisation import OrganisationContext, OrganisationCreate
from app.services.organisation_service import (
    OrganisationConflictError,
    OrganisationPermissionError,
    OrganisationService,
    get_organisation_service,
)


router = APIRouter(tags=["organisations"])


@router.get("/me/organisations", response_model=list[OrganisationContext])
def list_my_organisations(
    current_user: CurrentUser = Depends(get_current_user),
    service: OrganisationService = Depends(get_organisation_service),
) -> list[OrganisationContext]:
    return service.list_contexts(current_user.account_id)


@router.post(
    "/organisations",
    response_model=OrganisationContext,
    status_code=status.HTTP_201_CREATED,
)
def create_organisation(
    payload: OrganisationCreate,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
    current_user: CurrentUser = Depends(get_current_user),
    service: OrganisationService = Depends(get_organisation_service),
) -> OrganisationContext:
    try:
        return service.create(current_user.account_id, payload, idempotency_key)
    except OrganisationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OrganisationPermissionError as exc:
        raise HTTPException(status_code=403, detail="Organisation access denied") from exc


@router.get("/organisations/{organisation_id}", response_model=OrganisationContext)
def get_organisation(
    context: OrganisationContext = Depends(require_org_member),
) -> OrganisationContext:
    return context


@router.get(
    "/organisations/{organisation_id}/admin",
    response_model=OrganisationContext,
)
def get_organisation_admin_context(
    context: OrganisationContext = Depends(require_org_admin),
) -> OrganisationContext:
    return context


@router.get("/management", response_class=HTMLResponse, include_in_schema=False)
def management_dashboard() -> HTMLResponse:
    page = Path(__file__).resolve().parents[1] / "templates" / "management.html"
    return HTMLResponse(page.read_text(encoding="utf-8"))
