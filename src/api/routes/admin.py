"""
Admin Routes
Model retraining, diagnostics, and version management endpoints.
"""
import logging
import os
import sys
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.db.turso import get_retraining_log
from src.scheduler.retraining import run_retraining_job
from src.core.versioning import list_model_versions, rollback_model, get_current_version
from src.core.monitoring import prediction_tracker

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")

router = APIRouter(prefix="/admin", tags=["Admin"])

# Handler reference — set by app.py at startup
_handler = None

def set_handler(handler):
    global _handler
    _handler = handler

@router.post("/retrain")
def trigger_retraining():
    """
    Manually trigger a full model retraining cycle.
    Steps: Turso export → snap pipeline → retrain both models → hot-reload.
    This normally runs automatically on the 1st of every month at 02:00 AM.
    """
    result = run_retraining_job(trigger="manual", handler=_handler)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=f"Retraining failed: {result['message']}")

    if result.get("cold_start_auc") and result.get("full_model_auc"):
        prediction_tracker.update_auc(result["cold_start_auc"], result["full_model_auc"])
    return result

@router.get("/retraining-log")
def retraining_log(limit: int = 20):
    """
    View the history of model retraining runs (stored in Turso).
    """
    try:
        log = get_retraining_log(limit=limit)
        return {"count": len(log), "entries": log}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@router.get("/model-versions/{model_name}")
def get_model_versions(model_name: str):
    """
    List all saved versions of a model.
    """
    if model_name not in ("cold_start_model", "credit_score_model"):
        raise HTTPException(status_code=400, detail="model_name must be 'cold_start_model' or 'credit_score_model'")

    versions = list_model_versions(model_name, MODELS_DIR)
    current = get_current_version(model_name, MODELS_DIR)
    return {
        "model_name": model_name,
        "current_version": current,
        "total_versions": len(versions),
        "versions": versions,
    }

class RollbackRequest(BaseModel):
    version: str

@router.post("/model-versions/{model_name}/rollback")
def rollback_to_version(model_name: str, body: RollbackRequest):
    """
    Roll back a model to a specific version.
    """
    if model_name not in ("cold_start_model", "credit_score_model"):
        raise HTTPException(status_code=400, detail="model_name must be 'cold_start_model' or 'credit_score_model'")

    success = rollback_model(model_name, body.version, MODELS_DIR)
    if not success:
        raise HTTPException(status_code=404, detail=f"Version '{body.version}' not found for {model_name}")

    # Hot-reload the handler
    if _handler is not None:
        _handler.reload_models(
            cold_start_model_path=os.path.join(MODELS_DIR, "cold_start_model.pkl"),
            full_model_path=os.path.join(MODELS_DIR, "credit_score_model.pkl"),
            feature_config_path=os.path.join(MODELS_DIR, "feature_config.pkl"),
        )

    return {
        "status": "rolled_back",
        "model_name": model_name,
        "version": body.version,
        "handler_reloaded": _handler is not None,
    }

