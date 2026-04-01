"""
Monthly Retraining Scheduler
retrain both credit scoring modelson the 1st of every month at 2:00 AM.
"""
import logging
import os
import sys
import traceback
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

logger = logging.getLogger(__name__)

# Paths used by the pipeline
CUSTOMERS_PATH = os.path.join(PROJECT_ROOT, "data", "customers.csv")
BEHAVIOR_PATH  = os.path.join(PROJECT_ROOT, "data", "credit_behavior_monthly.csv")
SNAPSHOTS_PATH = os.path.join(PROJECT_ROOT, "data", "model_snapshots.csv")
MODELS_DIR     = os.path.join(PROJECT_ROOT, "models")

# CORE RETRAINING JOB
def run_retraining_job(trigger: str = "scheduled", handler=None) -> dict:
    """
    Full retraining pipeline. Called by the scheduler OR the /admin/retrain endpoint.
    Steps:
      0. Aggregate raw_transactions → credit_behavior_monthly
      1. Export Supabase → CSV
      2. Feature engineering (snap pipeline)
      3. Train both models
      4. Hot-reload into live API
    """
    from src.db.supabase import export_to_csv, log_retraining
    from src.data.feature_pipeline import run_snap_pipeline
    from src.training.train import run_training

    logger.info(f"Retraining triggered [{trigger}] at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    result = {"success": False, "cold_start_auc": None, "full_model_auc": None, "message": ""}

    try:
        # Step 0 — Aggregate raw_transactions → credit_behavior_monthly
        logger.info("Step 0: Aggregating raw_transactions into monthly behavior records...")
        from src.data.aggregate_transactions import aggregate_raw_to_monthly
        aggregate_raw_to_monthly()
        logger.info("✅ Raw transaction aggregation complete")

        # Step 1 — Export Supabase → CSV
        logger.info("Exporting data from Supabase...")
        export_stats = export_to_csv(CUSTOMERS_PATH, BEHAVIOR_PATH)
        n_customers     = export_stats["n_customers"]
        n_behavior_rows = export_stats["n_behavior_rows"]
        logger.info(f"{n_customers:,} customers, {n_behavior_rows:,} behavior rows exported")

        # Step 2 — Feature engineering (snap pipeline)
        logger.info(" Running snap pipeline...")
        ok = run_snap_pipeline(CUSTOMERS_PATH, BEHAVIOR_PATH, SNAPSHOTS_PATH)
        if not ok:
            raise RuntimeError("Snap pipeline failed — check logs")

        # Step 3 — Train models
        logger.info(" Training models...")
        metrics = run_training(CUSTOMERS_PATH, BEHAVIOR_PATH)
        result["cold_start_auc"] = metrics.get("cold_start_auc")
        result["full_model_auc"] = metrics.get("full_model_auc")
        logger.info(f"Cold Start AUC={result['cold_start_auc']:.4f}  "
                    f"Full Model AUC={result['full_model_auc']:.4f}")

        # Step 4 — Hot-reload models into the live handler
        if handler is not None:
            logger.info("Hot-reloading models into running API...")
            handler.reload_models(
                cold_start_model_path=os.path.join(MODELS_DIR, "cold_start_model.pkl"),
                full_model_path=os.path.join(MODELS_DIR, "credit_score_model.pkl"),
                feature_config_path=os.path.join(MODELS_DIR, "feature_config.pkl"),
            )
            logger.info("Models hot-reloaded")
        else:
            logger.info("No live handler — models saved to disk only")

        result["success"] = True
        result["message"] = "Retraining completed successfully"

        # Log to Supabase
        log_retraining(
            trigger=trigger, success=True,
            cold_start_auc=result["cold_start_auc"],
            full_model_auc=result["full_model_auc"],
            n_customers=n_customers,
            n_behavior_rows=n_behavior_rows,
        )
        logger.info(f"Retraining [{trigger}] complete — results logged to Supabase")

    except Exception as e:
        err_msg = traceback.format_exc()
        logger.error(f"Retraining failed: {e}\n{err_msg}")
        result["message"] = str(e)

        try:
            log_retraining(trigger=trigger, success=False, notes=str(e))
        except Exception:
            logger.error("Also failed to write failure to retraining_log")

    return result

# SCHEDULER SETUP

_scheduler: BackgroundScheduler = None

def start_scheduler(handler=None) -> BackgroundScheduler:
    """
    Schedule: 1st of every month at 02:00 AM (server local time)
    """
    global _scheduler

    if _scheduler and _scheduler.running:
        logger.info("Scheduler already running — skipping start")
        return _scheduler

    _scheduler = BackgroundScheduler()

    _scheduler.add_job(
        func=run_retraining_job,
        trigger=CronTrigger(day=1, hour=2, minute=0),
        kwargs={"trigger": "scheduled", "handler": handler},
        id="monthly_retrain",
        name="Monthly Model Retraining",
        replace_existing=True,
        misfire_grace_time=3600,  # allow up to 1h late if server was down
    )
    _scheduler.start()
    logger.info("✅ APScheduler started — monthly retraining scheduled for 1st of every month at 02:00")
    return _scheduler

def stop_scheduler() -> None:
    """Gracefully stop the scheduler. Called at API shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")
