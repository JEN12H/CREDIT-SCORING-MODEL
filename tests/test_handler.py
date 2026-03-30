"""
Unit tests for ColdStartHandler — tier routing, scoring, and guardrails.
"""

import pytest
from src.core.handler import ColdStartHandler


class TestTierDetection:
    """Test get_customer_tier() routes to correct tiers."""

    def test_tier_1_brand_new(self):
        handler = ColdStartHandler.__new__(ColdStartHandler)
        tier, desc = handler.get_customer_tier(0)
        assert tier == 1
        assert "New" in desc or "Cold" in desc

    def test_tier_1_boundary(self):
        handler = ColdStartHandler.__new__(ColdStartHandler)
        tier, _ = handler.get_customer_tier(3)
        assert tier == 1

    def test_tier_2_building(self):
        handler = ColdStartHandler.__new__(ColdStartHandler)
        tier, _ = handler.get_customer_tier(4)
        assert tier == 2

    def test_tier_2_boundary(self):
        handler = ColdStartHandler.__new__(ColdStartHandler)
        tier, _ = handler.get_customer_tier(6)
        assert tier == 2

    def test_tier_3_established(self):
        handler = ColdStartHandler.__new__(ColdStartHandler)
        tier, _ = handler.get_customer_tier(7)
        assert tier == 3

    def test_tier_3_long_history(self):
        handler = ColdStartHandler.__new__(ColdStartHandler)
        tier, _ = handler.get_customer_tier(36)
        assert tier == 3


class TestScoringUtilities:
    """Test probability → score → decision conversions."""

    def test_prob_to_score_zero(self):
        assert ColdStartHandler._prob_to_score(0.0) == 900

    def test_prob_to_score_one(self):
        assert ColdStartHandler._prob_to_score(1.0) == 300

    def test_prob_to_score_midpoint(self):
        score = ColdStartHandler._prob_to_score(0.5)
        assert score == 600

    def test_prob_to_score_clamped_high(self):
        score = ColdStartHandler._prob_to_score(-0.5)
        assert score <= 900

    def test_prob_to_score_clamped_low(self):
        score = ColdStartHandler._prob_to_score(1.5)
        assert score >= 300

    def test_decision_approve_excellent(self):
        assert ColdStartHandler._score_to_decision(800) == "Approve_Excellent"

    def test_decision_approve_good(self):
        assert ColdStartHandler._score_to_decision(700) == "Approve_Good"

    def test_decision_conditional(self):
        assert ColdStartHandler._score_to_decision(600) == "Conditional"

    def test_decision_reject(self):
        assert ColdStartHandler._score_to_decision(400) == "Reject"

    def test_decision_boundary_750(self):
        assert ColdStartHandler._score_to_decision(750) == "Approve"

    def test_decision_boundary_650(self):
        assert ColdStartHandler._score_to_decision(650) == "Approve_Low_Limit"

    def test_decision_boundary_550(self):
        assert ColdStartHandler._score_to_decision(550) == "Conditional"

    def test_decision_boundary_800(self):
        assert ColdStartHandler._score_to_decision(800) == "Approve_Excellent"

    def test_decision_boundary_700(self):
        assert ColdStartHandler._score_to_decision(700) == "Approve_Good"


class TestProvisionalLimit:
    """Test provisional credit limit estimation."""

    def test_salaried_limit(self):
        limit = ColdStartHandler._estimate_provisional_limit(50_000, "Salaried")
        assert 5_000 <= limit <= 1_00_000

    def test_daily_wage_conservative(self):
        limit = ColdStartHandler._estimate_provisional_limit(15_000, "Daily Wage")
        assert limit <= 15_000  # should be conservative

    def test_max_cap_enforced(self):
        """Even high income should not exceed ₹1,00,000."""
        limit = ColdStartHandler._estimate_provisional_limit(5_00_000, "Salaried")
        assert limit <= 1_00_000

    def test_min_floor_enforced(self):
        limit = ColdStartHandler._estimate_provisional_limit(1_000, "Daily Wage")
        assert limit >= 5_000


class TestRiskGuardrails:
    """Test rule-based guardrails for cold start customers."""

    def setup_method(self):
        self.handler = ColdStartHandler.__new__(ColdStartHandler)

    def test_low_income_cap(self):
        customer = {"monthly_income": 10_000, "employment_status": "Salaried",
                     "dependents": 0, "age": 30}
        score, limit, decision, warnings = self.handler._apply_risk_guardrails(
            customer, 800, 50_000, 10_000
        )
        assert score <= 580
        assert limit <= 5_000
        assert any("low income" in w.lower() for w in warnings)

    def test_high_risk_employment(self):
        customer = {"monthly_income": 30_000, "employment_status": "Daily Wage",
                     "dependents": 0, "age": 30}
        score, limit, decision, warnings = self.handler._apply_risk_guardrails(
            customer, 800, 50_000, 10_000
        )
        assert score <= 540
        assert limit <= 3_000
        assert any("Daily Wage" in w for w in warnings)

    def test_young_borrower_cap(self):
        customer = {"monthly_income": 40_000, "employment_status": "Salaried",
                     "dependents": 0, "age": 21}
        score, limit, decision, warnings = self.handler._apply_risk_guardrails(
            customer, 800, 50_000, 15_000
        )
        assert limit <= 8_000
        assert any("Young" in w for w in warnings)

    def test_senior_borrower_cap(self):
        customer = {"monthly_income": 40_000, "employment_status": "Retired",
                     "dependents": 0, "age": 65}
        score, limit, decision, warnings = self.handler._apply_risk_guardrails(
            customer, 800, 50_000, 15_000
        )
        assert limit <= int(40_000 * 0.25)
        assert any("Senior" in w for w in warnings)

    def test_no_warnings_for_safe_customer(self):
        customer = {"monthly_income": 80_000, "employment_status": "Salaried",
                     "dependents": 1, "age": 35}
        score, limit, decision, warnings = self.handler._apply_risk_guardrails(
            customer, 800, 80_000, 10_000
        )
        assert len(warnings) == 0
        assert score == 800

    def test_tier_cap_respected(self):
        customer = {"monthly_income": 80_000, "employment_status": "Salaried",
                     "dependents": 0, "age": 35}
        _, limit, _, _ = self.handler._apply_risk_guardrails(
            customer, 800, 1_00_000, 10_000  # tier_cap = 10K
        )
        assert limit <= 10_000


class TestCreditLimitCap:
    """Verify the absolute ₹1,00,000 cap is enforced everywhere."""

    def test_max_limit_tier_1(self):
        assert ColdStartHandler.MAX_LIMIT_TIER_1 == 10_000

    def test_max_limit_tier_2(self):
        assert ColdStartHandler.MAX_LIMIT_TIER_2 == 25_000

    def test_max_limit_tier_3(self):
        assert ColdStartHandler.MAX_LIMIT_TIER_3 == 1_00_000

    def test_no_tier_exceeds_1L(self):
        assert ColdStartHandler.MAX_LIMIT_TIER_1 <= 1_00_000
        assert ColdStartHandler.MAX_LIMIT_TIER_2 <= 1_00_000
        assert ColdStartHandler.MAX_LIMIT_TIER_3 <= 1_00_000
