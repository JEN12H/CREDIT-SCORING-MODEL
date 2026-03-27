"""
src.api — FastAPI Application Layer
Exposes the FastAPI application and all route groups.
Modules:
    app     — Application factory, middleware, startup/shutdown events
    schemas — Pydantic request/response models (shared across routes)
    routes  — Scoring, customer CRUD, and admin endpoints
"""

from src.api.app import app

__all__ = ["app"]
