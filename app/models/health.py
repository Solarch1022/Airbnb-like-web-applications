"""Schemas for health-check responses."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response body for the health-check endpoint."""

    status: str = "ok"
    environment: str
    version: str
