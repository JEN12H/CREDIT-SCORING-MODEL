"""
Modules:
    generate_customers — Generates synthetic customer demographic profiles
    generate_behavior  — Generates monthly credit behaviour records
    feature_pipeline   — Runs the snap pipeline: raw data → model-ready features
"""
from src.data.generate_customers import generate_customers, assign_credit_limit
from src.data.generate_behavior import generate_monthly_behavior

__all__ = ["generate_customers", "assign_credit_limit", "generate_monthly_behavior"]
