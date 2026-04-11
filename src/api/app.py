"""
Credit Scoring API
Endpoints:
  GET  /              — API status & model health
  GET  /health        — Readiness probe (returns 503 if models not loaded)
  POST /predict/auto  — Auto-routes to correct model (RECOMMENDED)
  POST /predict/cold-start — Force cold start model (0–3 month accounts)
  POST /predict/full  — Force full model (established accounts)
"""
import logging
import os
import sys
import time
from typing import Optional
from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.handler import ColdStartHandler
from src.core.monitoring import prediction_tracker
from src.core.versioning import list_model_versions, get_current_version, rollback_model
from src.db.turso import ping, seed_from_csv
from src.scheduler.retraining import start_scheduler, stop_scheduler
from src.api.routes import scoring, data, admin

# ── Logging ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# APP INITIALIZATION
app = FastAPI(
    title="BAAKI Credit Scoring API",
    description=(
        "Production credit scoring API with intelligent model routing.\n\n"
        "- **Tier 1 (0–3 months)**: Cold start model + rule-based guardrails\n"
        "- **Tier 2 (3–6 months)**: Blended score (40% cold + 60% full)\n"
        "- **Tier 3 (6+ months)**: Full behavioral model\n\n"
        "Max credit limit: ₹1,00,000. Use `/api/v1/predict/auto` for production."
    ),
    version="4.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Rate Limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — configurable origins (default: locked to localhost)
allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

#API Key Auth for Admin endpoints
API_KEY = os.getenv("ADMIN_API_KEY", "")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)):
    """Require valid API key for admin endpoints (skip if ADMIN_API_KEY not set)."""
    if not API_KEY:  # no key configured = dev mode, allow all
        return
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")

# Register routers with /api/v1/ prefix 
app.include_router(scoring.router, prefix="/api/v1")
app.include_router(data.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])

# Request metrics tracking 
request_count = {"total": 0, "scoring": 0, "errors": 0}
latencies: list = []

@app.middleware("http")
async def track_metrics(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    request_count["total"] += 1
    if "/predict" in request.url.path:
        request_count["scoring"] += 1
    if response.status_code >= 400:
        request_count["errors"] += 1
    latencies.append(duration)
    if len(latencies) > 1000:  # keep last 1000
        latencies.pop(0)
    return response

#  Initialize handler, DB, and scheduler at startup 
handler: Optional[ColdStartHandler] = None

def _resolve_model_path(models_dir: str, base_name: str) -> str:
    """
    Resolve the path to the latest versioned model file.
    Reads `model_manifest.json` for the current_version and builds the
    versioned filename (e.g. cold_start_model_20260411_111055.pkl).
    Falls back to the canonical <base_name>.pkl if no versioned file is found.
    """
    version = get_current_version(base_name, models_dir)
    if version:
        versioned_filename = f"{base_name}_{version}.pkl"
        versioned_path = os.path.join(models_dir, versioned_filename)
        if os.path.exists(versioned_path):
            logger.info(f"🔍 Resolved '{base_name}' → {versioned_filename}")
            return versioned_path
        logger.warning(
            f"⚠️  Versioned file '{versioned_filename}' not found on disk; "
            f"falling back to {base_name}.pkl"
        )
    else:
        logger.info(f"ℹ️  No version entry in manifest for '{base_name}'; using {base_name}.pkl")
    return os.path.join(models_dir, f"{base_name}.pkl")

@app.on_event("startup")
async def startup_event():
    global handler
    models_dir = os.path.join(PROJECT_ROOT, "models")
    try:
        cold_start_path  = _resolve_model_path(models_dir, "cold_start_model")
        full_model_path  = _resolve_model_path(models_dir, "credit_score_model")
        feature_cfg_path = os.path.join(models_dir, "feature_config.pkl")

        handler = ColdStartHandler(
            cold_start_model_path=cold_start_path,
            full_model_path=full_model_path,
            feature_config_path=feature_cfg_path,
        )
        logger.info(
            f"✅ ColdStartHandler initialized — "
            f"cold_start={os.path.basename(cold_start_path)}, "
            f"full_model={os.path.basename(full_model_path)}"
        )
    except Exception as e:
        logger.error(f"❌ Failed to initialize handler: {e}")
        handler = None

    # Inject handler into route modules
    scoring.set_handler(handler)
    admin.set_handler(handler)

    # Seed Turso from existing CSVs (only if tables are empty)
    try:
        # TEMP: Skipping seed at startup to avoid slow boot times.
        # if ping():
        #     customers_csv = os.path.join(PROJECT_ROOT, "data", "customers.csv")
        #     behavior_csv  = os.path.join(PROJECT_ROOT, "data", "credit_behavior_monthly.csv")
        #     result = seed_from_csv(customers_csv, behavior_csv)
        #     logger.info(f"✅ Turso seeded: {result}")
        # else:
        #     logger.warning("Turso unreachable at startup — skipping seed (check .env credentials)")
        pass
    except Exception as e:
        logger.warning(f"Turso seed skipped: {e}")

    # Start monthly retraining scheduler
    try:
        scheduler = start_scheduler(handler=handler)
        if scheduler:
            logger.info("✅ APScheduler started (monthly retraining on 1st of every month at 02:00)")
        else:
            logger.info("ℹ️  Monthly scheduler disabled in this runtime")
    except Exception as e:
        logger.warning(f"Scheduler startup skipped: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    stop_scheduler()

# HEALTH ENDPOINTS
@app.get("/", tags=["Health"])
def root():
    """API status and model availability."""
    return {
        "status": "online",
        "version": "4.0.0",
        "max_credit_limit": "₹1,00,000",
        "handler_initialized": handler is not None,
        "models": {
            "cold_start": "Loaded" if handler and handler.cold_start_loaded else "Not Loaded",
            "full_model":  "Loaded" if handler and handler.full_model_loaded  else "Not Loaded",
        },
        "endpoints": {
            "auto":       "POST /api/v1/predict/auto    — recommended",
            "cold_start": "POST /api/v1/predict/cold-start",
            "full_model": "POST /api/v1/predict/full",
            "docs":       "GET  /docs",
            "metrics":    "GET  /metrics",
        },
    }

@app.get("/health", tags=["Health"])
def health_check():
    """Kubernetes/Docker readiness probe."""
    if handler is None:
        raise HTTPException(
            status_code=503,
            detail="Scoring handler not initialized. Ensure models are trained and restart the server.",
        )
    if not handler.cold_start_loaded or not handler.full_model_loaded:
        raise HTTPException(status_code=503, detail="One or more models not loaded")
    return {"status": "healthy"}

@app.get("/metrics", tags=["Monitoring"])
def metrics():
    """
    Prometheus-compatible metrics endpoint.
    Tracks request counts, latencies, model status, and prediction drift.
    """
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) > 20 else 0

    # Get model version info
    models_dir = os.path.join(PROJECT_ROOT, "models")
    cs_version = get_current_version("cold_start_model", models_dir)
    full_version = get_current_version("credit_score_model", models_dir)

    # Get drift metrics
    drift = prediction_tracker.get_drift_metrics()

    return {
        "requests_total":   request_count["total"],
        "requests_scoring": request_count["scoring"],
        "requests_errors":  request_count["errors"],
        "latency_avg_ms":   round(avg_latency * 1000, 2),
        "latency_p95_ms":   round(p95_latency * 1000, 2),
        "models_loaded":    handler is not None and handler.cold_start_loaded and handler.full_model_loaded,
        "cold_start_model": "loaded" if handler and handler.cold_start_loaded else "not_loaded",
        "full_model":       "loaded" if handler and handler.full_model_loaded else "not_loaded",
        "model_versions": {
            "cold_start": cs_version,
            "full_model": full_version,
        },
        "prediction_drift": drift,
    }

