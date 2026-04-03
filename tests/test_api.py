"""
Unit tests for API endpoints — validates correct HTTP responses.
Uses FastAPI TestClient (no real model loading or DB needed).
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Ensure project root is importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture
def client():
    """Create a TestClient with mocked dependencies."""
    # Mock the DB and scheduler imports before importing app
    with patch("src.db.turso.ping", return_value=False), \
         patch("src.db.turso.seed_from_csv", return_value={}), \
         patch("src.scheduler.retraining.start_scheduler"), \
         patch("src.scheduler.retraining.stop_scheduler"), \
         patch("src.core.handler.ColdStartHandler.__init__", side_effect=FileNotFoundError("mock")):
        from src.api.app import app
        # Ensure handler is None (models not loaded)
        import src.api.app as app_module
        app_module.handler = None
        # Also ensure route modules have no handler
        from src.api.routes import scoring, admin
        scoring._handler = None
        admin._handler = None
        with TestClient(app) as c:
            yield c


class TestHealthEndpoints:
    """Test root and health check endpoints."""

    def test_root_returns_200(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        assert "models" in data
        assert "endpoints" in data

    def test_root_shows_max_limit(self, client):
        response = client.get("/")
        data = response.json()
        assert "1,00,000" in data.get("max_credit_limit", "")

    def test_health_returns_503_when_no_models(self, client):
        """Health should return 503 if handler is not initialized."""
        response = client.get("/health")
        assert response.status_code == 503


class TestScoringValidation:
    """Test input validation on scoring endpoints."""

    def test_predict_auto_missing_fields_returns_422(self, client):
        response = client.post("/api/v1/predict/auto", json={"age": 30})
        assert response.status_code == 422

    def test_predict_cold_start_missing_fields_returns_422(self, client):
        response = client.post("/api/v1/predict/cold-start", json={})
        assert response.status_code == 422

    def test_predict_full_missing_fields_returns_422(self, client):
        response = client.post("/api/v1/predict/full", json={"age": 25})
        assert response.status_code == 422

    def test_predict_auto_invalid_age_returns_422(self, client):
        """Age must be between 18-100."""
        payload = {
            "age": 5,  # invalid
            "employment_status": "Salaried",
            "education_level": "Graduate",
            "monthly_income": 50000.0,
            "credit_limit": 80000.0,
            "city_tier": "Tier-1",
            "dependents": 1,
            "residence_type": "Rented",
            "account_age_months": 0,
            # behavioral fields with defaults
            "util_avg_3m": 0, "payment_ratio_avg_3m": 1.0,
            "max_outstanding_3m": 0, "avg_txn_amt_3m": 0,
            "avg_txn_count_3m": 0, "late_payments_3m": 0,
            "missed_due_count_3m": 0, "missed_due_last_1m": 0,
            "payment_ratio_last_1m": 1.0, "outstanding_delta_3m": 0,
            "bnpl_active_last_1m": 0, "consecutive_missed_due": 0,
            "payment_ratio_min_3m": 1.0, "worst_util_3m": 0,
            "ever_defaulted": 0, "default_count_history": 0,
            "months_since_last_default": 0, "outstanding_to_income_pct": 0,
            "outstanding_to_limit_pct": 0, "income_affordability_score": 1.0,
            "debt_burden_category": 0, "payment_ratio_trend": 0,
            "utilization_trend": 0, "outstanding_growth_rate": 0,
            "is_deteriorating": 0, "active_months_3m": 0,
            "avg_util_when_active": 0, "snapshot_account_age": 0,
            "account_age_bucket": 0, "risk_score": 0, "snapshot_month": 1,
        }
        response = client.post("/api/v1/predict/auto", json=payload)
        assert response.status_code == 422

    def test_predict_auto_returns_503_no_handler(self, client):
        """With no trained models, valid input should return 503."""
        payload = {"customer_id": 1}
        response = client.post("/api/v1/predict/auto", json=payload)
        assert response.status_code == 503


class TestCustomerEndpoints:
    """Test customer CRUD validation."""

    def test_create_customer_credit_limit_validation(self, client):
        """Credit limit should not exceed ₹1,00,000."""
        payload = {
            "customer_id": 1,
            "age": 30,
            "employment_status": "Salaried",
            "education_level": "Graduate",
            "monthly_income": 80_000,
            "credit_limit": 2_00_000,  # exceeds ₹1L cap
            "city_tier": "Tier-1",
            "dependents": 1,
            "residence_type": "Rented",
            "account_age_months": 0,
        }
        response = client.post("/api/v1/customers/", json=payload)
        assert response.status_code == 422
