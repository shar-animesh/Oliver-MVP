"""Shared-secret authentication for Logic App calls to Oliver."""

import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from config import get_settings

settings = get_settings()


def require_internal_api_key(api_key: str = Security(APIKeyHeader(name="X-Internal-Api-Key"))) -> None:  # noqa: B008
    """Allow calls carrying the shared Logic App service credential."""
    if not secrets.compare_digest(api_key, settings.INTERNAL_API_KEY.get_secret_value()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal API key")
