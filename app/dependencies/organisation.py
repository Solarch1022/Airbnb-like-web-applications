from fastapi import Depends, HTTPException, status

from app.dependencies.auth import get_current_user
from app.models.auth import CurrentUser
from app.models.organisation import OrganisationContext, OrganisationRole
from app.services.organisation_service import (
    OrganisationPermissionError,
    OrganisationService,
    get_organisation_service,
)


def require_org_member(
    organisation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    service: OrganisationService = Depends(get_organisation_service),
) -> OrganisationContext:
    try:
        return service.get_context(current_user.account_id, organisation_id)
    except OrganisationPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organisation access denied",
        ) from exc


def require_org_admin(
    context: OrganisationContext = Depends(require_org_member),
) -> OrganisationContext:
    if context.membership.role != OrganisationRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organisation admin role required",
        )
    return context
