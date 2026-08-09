"""Oliver MVP — FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

import os
from app.routers import submissions, health, ingest, audit

app = FastAPI(
    title="Oliver Assessment API",
    version="0.1.0",
    description="Mock assessment pipeline for the Oliver AI Pilot Lifecycle Mesh.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("OLIVER_CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(submissions.router, prefix="/api/v1")
app.include_router(ingest.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")

# Serve built frontend if it exists (production / Docker)
_static = Path(__file__).resolve().parent.parent / "static"
if _static.is_dir():
    app.mount("/", StaticFiles(directory=str(_static), html=True), name="frontend")
