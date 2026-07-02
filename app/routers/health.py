"""Health-check endpoints."""

from fastapi import APIRouter, Depends

from app import __version__
from app.core.config import Settings, get_settings
from app.models.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Return service health and basic metadata."""
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        version=__version__,
    )
