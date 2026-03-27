"""
Shared pytest fixtures for BAAKI Credit Scoring tests.
"""

import os
import sys
import pytest

# Ensure project root is importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture
def sample_new_customer():
    """Tier 1: brand-new customer (0-3 months)."""
    return {
        "age": 30,
        "employment_status": "Salaried",
        "education_level": "Graduate",
        "monthly_income": 50_000,
        "credit_limit": 80_000,
        "city_tier": "Tier-1",
        "dependents": 1,
        "residence_type": "Rented",
        "account_age_months": 1,
    }


@pytest.fixture
def sample_building_customer():
    """Tier 2: building history (3-6 months)."""
    return {
        "age": 35,
        "employment_status": "Salaried",
        "education_level": "Graduate",
        "monthly_income": 60_000,
        "credit_limit": 90_000,
        "city_tier": "Tier-2",
        "dependents": 0,
        "residence_type": "Owned",
        "account_age_months": 5,
        "payment_ratio_avg_3m": 0.95,
        "missed_due_count_3m": 0,
    }


@pytest.fixture
def sample_established_customer():
    """Tier 3: established customer (6+ months) with full behavioral data."""
    return {
        "age": 40,
        "employment_status": "Business",
        "education_level": "Postgraduate",
        "monthly_income": 80_000,
        "credit_limit": 1_00_000,
        "city_tier": "Tier-1",
        "dependents": 2,
        "residence_type": "Owned",
        "account_age_months": 12,
        "snapshot_month": 6,
        "util_avg_3m": 0.30,
        "payment_ratio_avg_3m": 0.92,
        "max_outstanding_3m": 15_000,
        "avg_txn_amt_3m": 2_500,
        "avg_txn_count_3m": 5,
        "late_payments_3m": 0,
        "missed_due_count_3m": 0,
        "missed_due_last_1m": 0,
        "payment_ratio_last_1m": 1.0,
        "outstanding_delta_3m": 200,
        "bnpl_active_last_1m": 1,
        "consecutive_missed_due": 0,
        "payment_ratio_min_3m": 0.88,
        "worst_util_3m": 0.40,
        "ever_defaulted": 0,
        "default_count_history": 0,
        "months_since_last_default": 0,
        "outstanding_to_income_pct": 18.5,
        "outstanding_to_limit_pct": 10.0,
        "income_affordability_score": 5.3,
        "debt_burden_category": 1,
        "payment_ratio_trend": 0.05,
        "utilization_trend": -0.02,
        "outstanding_growth_rate": 0.01,
        "is_deteriorating": 0,
        "active_months_3m": 3,
        "avg_util_when_active": 0.30,
        "snapshot_account_age": 12,
        "account_age_bucket": 1,
        "risk_score": 10.0,
    }


@pytest.fixture
def sample_high_risk_customer():
    """High-risk: low income, daily wage, many dependents."""
    return {
        "age": 28,
        "employment_status": "Daily Wage",
        "education_level": "Primary",
        "monthly_income": 12_000,
        "credit_limit": 8_000,
        "city_tier": "Tier-3",
        "dependents": 4,
        "residence_type": "Rented",
        "account_age_months": 0,
    }
