"""Request-scoped correlation context used by structured logging."""

from contextvars import ContextVar
from typing import Dict, Optional
from uuid import uuid4

_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_endpoint: ContextVar[Optional[str]] = ContextVar("endpoint", default=None)
_method: ContextVar[Optional[str]] = ContextVar("method", default=None)


def set_request_context(
    request_id: Optional[str] = None,
    endpoint: Optional[str] = None,
    method: Optional[str] = None,
) -> str:
    """Set request-scoped context and return the active request ID."""
    active_request_id = request_id or f"req_{uuid4().hex[:16]}"
    _request_id.set(active_request_id)
    if endpoint:
        _endpoint.set(endpoint)
    if method:
        _method.set(method)
    return active_request_id


def get_request_context() -> Dict[str, str]:
    """Return the populated request context fields."""
    context: Dict[str, str] = {}
    if request_id := _request_id.get():
        context["request_id"] = request_id
    if endpoint := _endpoint.get():
        context["endpoint"] = endpoint
    if method := _method.get():
        context["method"] = method
    return context


def clear_request_context() -> None:
    """Clear all request-scoped values at the end of a request."""
    _request_id.set(None)
    _endpoint.set(None)
    _method.set(None)
