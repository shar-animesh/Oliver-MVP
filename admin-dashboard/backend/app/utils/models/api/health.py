# Path: app/utils/models/api/health.py
# Description: Request and response models for health endpoints.

from typing import Literal

from pydantic import BaseModel


# GET /health
class HealthResponse(BaseModel):
    """Health status returned by the backend readiness endpoint."""

    status: Literal["healthy"]
