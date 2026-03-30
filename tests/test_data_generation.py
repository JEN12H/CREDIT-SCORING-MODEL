"""
Unit tests for data generation — validates output schema and distributions.
"""

import os
import sys
import pytest
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.data.generate_customers import generate_customers, assign_credit_limit
from src.data.generate_behavior import generate_monthly_behavior


class TestGenerateCustomers:
    """Test customer profile generation."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.output_path = str(tmp_path / "customers.csv")
        generate_customers(n_customers=50, output_path=self.output_path)
        self.df = pd.read_csv(self.output_path)

    def test_correct_row_count(self):
        assert len(self.df) == 50

    def test_unique_customer_ids(self):
        assert self.df["customer_id"].nunique() == 50

    def test_required_columns_present(self):
        required = ["customer_id", "age", "employment_status", "education_level",
                     "monthly_income", "credit_limit", "city_tier", "dependents",
                     "residence_type", "account_age_months"]
        for col in required:
            assert col in self.df.columns, f"Missing column: {col}"

    def test_age_range(self):
        assert self.df["age"].between(21, 75).all()

    def test_income_positive(self):
        assert (self.df["monthly_income"] > 0).all()

    def test_credit_limit_cap(self):
        """No customer should have credit_limit > ₹1,00,000."""
        assert (self.df["credit_limit"] <= 1_00_000).all(), \
            f"Max limit found: {self.df['credit_limit'].max()}"

    def test_credit_limit_minimum(self):
        assert (self.df["credit_limit"] >= 5_000).all()

    def test_dependents_range(self):
        assert self.df["dependents"].between(0, 5).all()

    def test_valid_employment_statuses(self):
        valid = {"Salaried", "Self-Employed", "Business", "Daily Wage", "Retired"}
        assert set(self.df["employment_status"].unique()).issubset(valid)


class TestCreditLimitAssignment:
    """Test the credit limit assignment function directly."""

    def test_cap_at_100000(self):
        """Even very high income should be capped at ₹1,00,000."""
        limit = assign_credit_limit("Salaried", 5_00_000, "Postgraduate", 40)
        assert limit <= 1_00_000

    def test_minimum_5000(self):
        limit = assign_credit_limit("Daily Wage", 5_000, "Primary", 55)
        assert limit >= 5_000

    def test_rounded_to_500(self):
        limit = assign_credit_limit("Salaried", 50_000, "Graduate", 30)
        assert limit % 500 == 0


class TestGenerateBehavior:
    """Test monthly behavioral data generation."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        # First generate customers
        self.customers_path = str(tmp_path / "customers.csv")
        self.behavior_path = str(tmp_path / "behavior.csv")
        generate_customers(n_customers=20, output_path=self.customers_path)
        generate_monthly_behavior(
            customers_path=self.customers_path,
            output_path=self.behavior_path,
            n_months=6,
        )
        self.df = pd.read_csv(self.behavior_path)

    def test_records_generated(self):
        assert len(self.df) > 0

    def test_12_months_per_customer(self):
        """Each customer should have exactly n_months records."""
        counts = self.df.groupby("customer_id").size()
        assert (counts == 6).all()

    def test_utilization_range(self):
        assert self.df["credit_utilization"].between(0, 1).all()

    def test_payment_ratio_allows_zero(self):
        """After the fix, payment_ratio should allow 0.0 (complete non-payment)."""
        assert self.df["payment_ratio"].min() >= 0.0
        assert self.df["payment_ratio"].max() <= 1.0

    def test_default_event_binary(self):
        assert self.df["default_event"].isin([0, 1]).all()

    def test_missed_due_binary(self):
        assert self.df["missed_due_flag"].isin([0, 1]).all()

    def test_late_payment_binary(self):
        assert self.df["late_payment"].isin([0, 1]).all()

    def test_outstanding_non_negative(self):
        assert (self.df["outstanding_balance"] >= 0).all()
