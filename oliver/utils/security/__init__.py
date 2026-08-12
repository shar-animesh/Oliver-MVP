"""Oliver service-to-service security dependencies."""

from .internal import require_internal_api_key

__all__ = ["require_internal_api_key"]
