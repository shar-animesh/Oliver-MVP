"""Health & readiness probes."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok", "service": "oliver-mvp", "version": "0.1.0"}
