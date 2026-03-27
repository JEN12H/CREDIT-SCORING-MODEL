"""
src.api.routes — API Route Handlers
Routers:
    scoring  — POST /api/v1/predict/* (auto, cold-start, full model)
    data     — GET/POST /api/v1/customers/* (CRUD operations)
    admin    — POST /admin/retrain, GET /admin/retraining-log, GET /health/drift
"""
from src.api.routes import admin, data, scoring
__all__ = ["scoring", "data", "admin"]
