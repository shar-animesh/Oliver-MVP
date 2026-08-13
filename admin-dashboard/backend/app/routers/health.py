# Path: app/routers/health.py
# Description: Backend health and readiness endpoint.

from fastapi import APIRouter

from app.utils.models.api import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, include_in_schema=False)
def health() -> HealthResponse:
    return HealthResponse(status="healthy")
