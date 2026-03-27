"""
src.training — Model Training & Evaluation Pipeline
Trains and evaluates two production credit scoring models:
  1. Cold Start Model  — uses only static/demographic features (0–3 month accounts)
  2. Full Model        — uses all features including behavioral (6+ month accounts)

Modules:
    train  — run_training(): full training pipeline, callable by the scheduler
    evaluate — Model evaluation utilities and performance reporting
Usage:
    from src.training.train import run_training
    metrics = run_training()
    # Returns: {"cold_start_auc": 0.82, "full_model_auc": 0.91, ...}
"""
from src.training.train import run_training

__all__ = ["run_training"]
