# Path: app/main.py
# Description: FastAPI application for the Oliver admin dashboard backend.

import time
import tomllib
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Callable

import anyio
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings
from app.logger import get_logger
from app.routers import email_threads, health
from app.utils import request_context

# Get the settings
settings = get_settings()

# Get the logger
logger = get_logger()

with (Path(__file__).resolve().parent.parent / "pyproject.toml").open("rb") as file:
    project = tomllib.load(file)["project"]


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Configure process-wide runtime limits before accepting requests."""
    limiter = anyio.to_thread.current_default_thread_limiter()
    limiter.total_tokens = settings.ANYIO_THREAD_POOL_TOKENS
    logger.info(f"AnyIO thread pool capacity set to {limiter.total_tokens}")
    yield


app = FastAPI(
    title=project["name"],
    description=project["description"],
    version=project["version"],
    lifespan=lifespan,
    openapi_url="/api/openapi.json" if settings.ENV == "development" else None,
    docs_url="/api/docs" if settings.ENV == "development" else None,
    redoc_url="/api/redoc" if settings.ENV == "development" else None,
)


class CustomMiddleware(BaseHTTPMiddleware):
    """Add request correlation, timing headers, and one completion log per request."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request_context.set_request_context(endpoint=request.url.path, method=request.method)
        try:
            started_at = time.perf_counter()
            response: Response = await call_next(request)
            process_time = time.perf_counter() - started_at

            response.headers["X-Oliver-Process-Time"] = str(process_time)
            response.headers["X-Oliver-Request-Id"] = request_id
            logger.info(f"Request completed: {request.method} {request.url.path} - Status: {response.status_code} - Time: {process_time:.3f}s")
            return response
        finally:
            request_context.clear_request_context()


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CustomMiddleware)

app.include_router(health.router)
app.include_router(email_threads.router)
