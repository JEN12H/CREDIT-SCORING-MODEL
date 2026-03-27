"""
BAAKI Credit Scoring Model
An AI-powered product-lending credit scoring system for the Indian market.
Packages:
    src.api — FastAPI application, routes, and schemas
    src.core — Scoring handler, model versioning, drift monitoring
    src.data — Synthetic data generation and feature engineering
    src.db  — Supabase database layer (CRUD + seeding + export)
    src.training — Model training and evaluation pipelines
    src.scheduler — APScheduler-based monthly auto-retraining
    src.analysis — Analytical summaries and cold-start diagnostics
"""

__version__ = "1.0.0"
__author__  = "BAAKI"
