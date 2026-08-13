# Path: routes/__init__.py
# Description: Aggregate router for every Oliver API route.

from fastapi import APIRouter

from .email import router as email_router
from .health import router as health_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(email_router)

main_router = APIRouter()
main_router.include_router(health_router)
main_router.include_router(api_router)

__all__ = ["main_router"]
