"""
Cold Start Handler — Production Module
"""
import logging
import warnings
from typing import Dict, List, Optional, Tuple
import joblib
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

class ColdStartHandler:
    # Account age tier boundaries (months)
    TIER_1_MAX_MONTHS = 3
    TIER_2_MAX_MONTHS = 6

    # Hard credit limit caps per tier (conservative risk management)
    MAX_LIMIT_TIER_1 = 10_000
    MAX_LIMIT_TIER_2 = 25_000
    MAX_LIMIT_TIER_3 = 1_00_000

    def __init__(self,cold_start_model_path: str = "models/cold_start_model.pkl",full_model_path:str = "models/credit_score_model.pkl",feature_config_path:str = "models/feature_config.pkl") -> None:
        self.cold_start_loaded = False
        self.full_model_loaded = False
        self.cold_start_model  = None
        self.full_model        = None
        self.feature_config    = {}
        self._load_model("cold_start", cold_start_model_path)
        self._load_model("full",       full_model_path)
        self._load_feature_config(feature_config_path)

    #Model loading
    def _load_model(self, name: str, path: str) -> None:
        try:
            model = joblib.load(path)
            if name == "cold_start":
                self.cold_start_model  = model
                self.cold_start_loaded = True
            else:
                self.full_model= model
                self.full_model_loaded = True
            logger.info(f"  Loaded {name} model: {path}")
        except FileNotFoundError:
            logger.error(f" Model not found: {path}  — run training first.")
        except Exception as e:
            logger.error(f" Failed to load {name} model ({path}): {e}")

    def _load_feature_config(self, path: str) -> None:
        try:
            self.feature_config = joblib.load(path)
            logger.info(f"Loaded feature config: {path}")
        except FileNotFoundError:
            logger.warning(f"feature_config.pkl not found at {path}, using defaults")
            self.feature_config = {
                "static_features": [
                    "age", "employment_status", "education_level",
                    "monthly_income", "credit_limit", "city_tier",
                    "dependents", "residence_type", "account_age_months",
                ],
                "all_features": None,
            }

    # Scoring utilities
    @staticmethod
    def _prob_to_score(prob: float) -> int:
        return int(max(300, min(900, 900 - prob * 600)))

    @staticmethod
    def _score_to_decision(score: int) -> str:
        # 6-band CIBIL-style scoring (300–900)
        if   score >= 800: return "Approve_Excellent"   # Prime: full limit, best terms
        elif score >= 750: return "Approve"              # Very Good: full limit
        elif score >= 700: return "Approve_Good"         # Good: 65% of limit
        elif score >= 650: return "Approve_Low_Limit"    # Fair: 45% of limit
        elif score >= 550: return "Conditional"          # Poor: micro-limit (10–20%)
        else:              return "Reject"               # Very Poor: 300–549

    @staticmethod
    def _estimate_provisional_limit(income: int, employment: str) -> int:
        mult = {"Salaried": 2.0, "Business": 1.5, "Self-Employed": 1.3,
                "Retired": 1.0, "Daily Wage": 0.6}.get(employment, 1.0)
        return max(5_000, min(1_00_000, round(income * mult / 500) * 500))

    def _apply_risk_guardrails(self,customer: Dict,score: int,credit_limit: int,tier_cap: int) -> Tuple[int, int, str, List[str]]:

        risk_warnings  = []
        adjusted_score = score
        assigned_limit = min(credit_limit, tier_cap)  # never exceed tier cap

        income      = customer.get("monthly_income", 0)
        employment  = customer.get("employment_status", "Unknown")
        dependents  = customer.get("dependents", 0)
        age         = customer.get("age", 30)

        # Rule 1: Very low income
        if income < 15_000:
            adjusted_score = min(adjusted_score, 580)
            assigned_limit = min(assigned_limit, 5_000)
            risk_warnings.append("Very low income — limit capped at ₹5,000")

        # Rule 2: High dependency ratio
        per_capita = income / (dependents + 1) if dependents >= 0 else income
        if per_capita < 12_000:
            adjusted_score = min(adjusted_score, 570)
            assigned_limit = min(assigned_limit, 5_000)
            risk_warnings.append("High dependency ratio — limit reduced")

        # Rule 3: High-risk employment
        if employment in ("Daily Wage", "Unemployed"):
            adjusted_score = min(adjusted_score, 540)
            assigned_limit = min(assigned_limit, 3_000)
            risk_warnings.append(f"High-risk employment ({employment}) — conservative limits applied")

        # Rule 4: Young borrower (<23)
        if age < 23:
            assigned_limit = min(assigned_limit, 8_000)
            risk_warnings.append("Young borrower — limit capped at ₹8,000")

        # Rule 5: Senior borrower (>62)
        if age > 62:
            senior_cap = int(income * 0.25)
            assigned_limit = min(assigned_limit, senior_cap)
            risk_warnings.append("Senior borrower — limit adjusted to 25% of income")

        decision = self._score_to_decision(adjusted_score)
        if decision == "Reject":
            assigned_limit = 0
            risk_warnings.append("Application rejected — credit limit set to ₹0")

        return adjusted_score, int(assigned_limit), decision, risk_warnings

    # Hot-reload models
    def reload_models(self,cold_start_model_path: str = "models/cold_start_model.pkl",full_model_path: str = "models/credit_score_model.pkl",feature_config_path: str = "models/feature_config.pkl") -> None:
        logger.info("Hot-reloading models...")
        self._load_model("cold_start", cold_start_model_path)
        self._load_model("full", full_model_path)
        self._load_feature_config(feature_config_path)
        logger.info("Hot-reload complete")

    # Tier detection
    def get_customer_tier(self, account_age_months: int) -> Tuple[int, str]:
        if   account_age_months <= self.TIER_1_MAX_MONTHS: return 1, "New Customer (Cold Start)"
        elif account_age_months <= self.TIER_2_MAX_MONTHS: return 2, "Building History"
        else:return 3, "Established Customer"

    # Tier-specific scoring
    def score_cold_start(self, customer: Dict) -> Dict:
        if not self.cold_start_loaded:
            raise RuntimeError(
                "Cold start model is not loaded."
            )

        static_features = self.feature_config.get("static_features", [])
        customer_df = pd.DataFrame([{k: customer.get(k) for k in static_features}])

        try:
            prob = float(self.cold_start_model.predict_proba(customer_df)[0, 1])
            ml_score = self._prob_to_score(prob)
        except Exception as e:
            logger.error(f"Cold start predict_proba failed: {e}")
            raise RuntimeError(f"Scoring failed: {e}") from e

        income = int(customer.get("monthly_income", 0))
        employment = customer.get("employment_status", "Unknown")
        credit_limit = int(
            customer.get("credit_limit") or self._estimate_provisional_limit(income, employment)
        )

        final_score, final_limit, decision, risk_warnings = self._apply_risk_guardrails(
            customer, ml_score, credit_limit, self.MAX_LIMIT_TIER_1
        )

        return {
            "ml_probability": round(prob, 4),
            "ml_score": ml_score,
            "final_score": final_score,
            "decision": decision,
            "max_credit_limit":final_limit,
            "risk_warnings": risk_warnings,
            "model_used": "cold_start_model + guardrails",
            "note": (
                "Cold start model uses demographic features only. "
                "Conservative limits applied until behavioral history builds."
            ),
        }

    def score_established(self, customer: Dict) -> Dict:
        if not self.full_model_loaded:
            raise RuntimeError(
                "Full model is not loaded."
            )

        all_features = self.feature_config.get("all_features") or []

        behavioral_defaults = {
            "snapshot_month": 6, "util_avg_3m": 0.0, "payment_ratio_avg_3m": 1.0,
            "max_outstanding_3m": 0.0, "avg_txn_amt_3m": 0.0, "avg_txn_count_3m": 0.0,
            "late_payments_3m": 0, "missed_due_count_3m": 0, "missed_due_last_1m": 0,
            "payment_ratio_last_1m": 1.0, "outstanding_delta_3m": 0.0,
            "bnpl_active_last_1m": 0, "consecutive_missed_due": 0,
            "payment_ratio_min_3m": 1.0, "worst_util_3m": 0.0, "ever_defaulted": 0,
            "default_count_history": 0, "months_since_last_default": 0,
            "outstanding_to_income_pct": 0.0, "outstanding_to_limit_pct": 0.0,
            "income_affordability_score": 1.0, "debt_burden_category": 0,
            "payment_ratio_trend": 0.0, "utilization_trend": 0.0,
            "outstanding_growth_rate": 0.0, "is_deteriorating": 0,
            "active_months_3m": 0, "avg_util_when_active": 0.0,
            "snapshot_account_age": 0, "account_age_bucket": 0, "risk_score": 0.0,
        }

        feature_dict = {**behavioral_defaults, **customer}

        if all_features:
            customer_df = pd.DataFrame([feature_dict])[all_features]
        else:
            customer_df = pd.DataFrame([feature_dict])

        try:
            prob  = float(self.full_model.predict_proba(customer_df)[0, 1])
            score = self._prob_to_score(prob)
        except Exception as e:
            logger.error(f"Full model predict_proba failed: {e}")
            raise RuntimeError(f"Scoring failed: {e}") from e

        decision = self._score_to_decision(score)

        income       = int(customer.get("monthly_income", 0))
        employment   = customer.get("employment_status", "Unknown")
        credit_limit = int(
            customer.get("credit_limit") or self._estimate_provisional_limit(income, employment)
        )

        # Graduated limit multipliers — smooth steps (aligned with 6-band decision)
        if   score >= 800: limit_mult = 1.00   # Excellent  → 100% of assigned limit
        elif score >= 750: limit_mult = 0.85   # Very Good  →  85%
        elif score >= 700: limit_mult = 0.65   # Good       →  65%
        elif score >= 650: limit_mult = 0.45   # Fair       →  45%
        elif score >= 600: limit_mult = 0.20   # Sub-Fair   →  20%
        elif score >= 550: limit_mult = 0.10   # Poor       →  10% (micro-credit watch)
        else:              limit_mult = 0.00   # Reject     →   0%

        max_limit = int(min(credit_limit * limit_mult, self.MAX_LIMIT_TIER_3))

        return {
            "ml_probability":   round(prob, 4),
            "final_score":      score,
            "decision":         decision,
            "max_credit_limit": max_limit,
            "model_used":       "full_model",
            "note": "Full behavioral model — reliable predictions with transaction history.",
        }
    # PUBLIC — Main entry point
    def score_customer(self, customer: Dict) -> Dict:
        """
        Auto-routes to the appropriate model based on account_age_months.
        """
        account_age = int(customer.get("account_age_months", 0))
        tier, tier_desc = self.get_customer_tier(account_age)

        result = {
            "customer_tier":      tier,
            "tier_description":   tier_desc,
            "account_age_months": account_age,
        }
        if tier == 1:
            scoring = self.score_cold_start(customer)
            result.update(scoring)
            result["recommendation"] = (
                "New customer — monitor closely. "
                "Consider limit increase after 3 months of on-time payments."
            )

        elif tier == 2:
            cs_result   = self.score_cold_start(customer)
            full_result = self.score_established(customer)
            blended_score = int(0.40 * cs_result["final_score"] + 0.60 * full_result["final_score"])
            blended_prob  = round(0.40 * cs_result["ml_probability"] + 0.60 * full_result["ml_probability"], 4)
            decision      = self._score_to_decision(blended_score)
            income       = int(customer.get("monthly_income", 0))
            employment   = customer.get("employment_status", "Unknown")
            credit_limit = int(
                customer.get("credit_limit") or self._estimate_provisional_limit(income, employment)
            )
            
            # Graduated limit multipliers for Blended Tier (aligned with 6-band decision)
            if   blended_score >= 800: limit_mult = 1.00
            elif blended_score >= 750: limit_mult = 0.85
            elif blended_score >= 700: limit_mult = 0.65
            elif blended_score >= 650: limit_mult = 0.45
            elif blended_score >= 600: limit_mult = 0.20
            elif blended_score >= 550: limit_mult = 0.10
            else:                      limit_mult = 0.00
            
            max_limit = int(min(credit_limit * 0.5 * limit_mult, self.MAX_LIMIT_TIER_2))

            result.update({
                "ml_probability":   blended_prob,
                "final_score":      blended_score,
                "decision":         decision,
                "max_credit_limit": max_limit,
                "model_used":       "blended (40% cold_start + 60% full)",
                "recommendation":   "Building credit history — good behavior will unlock higher limits.",
            })

        else:
            scoring = self.score_established(customer)
            result.update(scoring)
            result["recommendation"] = "Established customer — standard credit policies apply."

        return result
