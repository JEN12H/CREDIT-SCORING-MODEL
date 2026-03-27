"""
src.scheduler — Automated Monthly Retraining
=============================================
Uses APScheduler to retrain both credit scoring models on the 1st of
every month at 02:00 AM, without any manual intervention.

Retraining pipeline (run_retraining_job):
    1. Export latest data from Supabase → local CSVs
    2. Run snap pipeline → re-engineer all features
    3. Train cold start model + full behavioral model
    4. Hot-reload new .pkl files into the running API (zero downtime)
    5. Log AUC metrics to Supabase retraining_log table

Functions:
    start_scheduler(handler) — Start the background scheduler (called at API startup)
    stop_scheduler()         — Gracefully stop the scheduler (called at API shutdown)
    run_retraining_job()     — Trigger a full retrain manually or on schedule
"""

from src.scheduler.retraining import start_scheduler, stop_scheduler, run_retraining_job

__all__ = ["start_scheduler", "stop_scheduler", "run_retraining_job"]
