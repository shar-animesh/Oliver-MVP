# Path: routes/health.py
# Description: Unversioned Oliver process-health route.

from typing import Dict

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health", include_in_schema=False)
def health() -> Dict[str, str]:
    """Report process health without invoking external dependencies."""
    return {"status": "healthy"}
