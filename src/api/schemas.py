"""
API Request/Response Schemas
Pydantic models for all API endpoints.
"""

from typing import List, Optional
from pydantic import BaseModel, Field
class ColdStartInput(BaseModel):
    """Static / demographic features — available at customer onboarding."""
    age:                int   = Field(..., ge=18, le=100, description="Applicant age (years)")
    employment_status:  str   = Field(..., description="Salaried | Self-Employed | Business | Daily Wage | Retired")
    education_level:    str   = Field(..., description="No Formal Education | Primary | Secondary | High School | Graduate | Postgraduate")
    monthly_income:     float = Field(..., ge=0,  description="Monthly income (INR)")
    credit_limit:       Optional[float] = Field(None, ge=0, description="Assigned credit limit (INR). Max ₹1,00,000. Estimated from income if omitted.")
    city_tier:          str   = Field(..., description="Tier-1 | Tier-2 | Tier-3")
    dependents:         int   = Field(..., ge=0, le=10, description="Number of financial dependents")
    residence_type:     str   = Field(..., description="Owned | Rented | Family-Owned")
    account_age_months: int   = Field(..., ge=0, description="Account age in months (0 = brand new)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "age": 30,
                "employment_status": "Salaried",
                "education_level": "Graduate",
                "monthly_income": 50000.0,
                "credit_limit": 80000.0,
                "city_tier": "Tier-1",
                "dependents": 1,
                "residence_type": "Rented",
                "account_age_months": 0,
            }
        }
    }


class FullModelInput(ColdStartInput):
    """All features including 3-month behavioral signals — for established accounts."""
    # Basic 3-month aggregates
    util_avg_3m:           float = Field(..., description="Avg credit utilization (last 3 months)")
    payment_ratio_avg_3m:  float = Field(..., description="Avg payment ratio (last 3 months)")
    max_outstanding_3m:    float = Field(..., ge=0, description="Max outstanding balance (last 3 months, INR)")
    avg_txn_amt_3m:        float = Field(..., ge=0, description="Avg transaction amount (last 3 months, INR)")
    avg_txn_count_3m:      float = Field(..., ge=0, description="Avg transaction count (last 3 months)")
    late_payments_3m:      int   = Field(..., ge=0, le=3, description="Late payments in last 3 months")
    missed_due_count_3m:   int   = Field(..., ge=0, le=3, description="Missed due dates in last 3 months")
    # Recency
    missed_due_last_1m:    int   = Field(..., ge=0, le=1, description="Missed due last month (0/1)")
    payment_ratio_last_1m: float = Field(..., ge=0, le=1, description="Payment ratio last month")
    outstanding_delta_3m:  float = Field(..., description="Change in outstanding balance over 3 months (INR)")
    bnpl_active_last_1m:   int   = Field(..., ge=0, le=1, description="Had transactions last month (0/1)")
    # Risk signals
    consecutive_missed_due:    int   = Field(..., ge=0, le=3, description="Consecutive months with missed due")
    payment_ratio_min_3m:      float = Field(..., ge=0, le=1, description="Worst (min) payment ratio over 3 months")
    worst_util_3m:             float = Field(..., ge=0, le=1, description="Peak utilization over 3 months")
    ever_defaulted:            int   = Field(..., ge=0, le=1, description="Has ever defaulted (0/1)")
    default_count_history:     int   = Field(..., ge=0, description="Total historical defaults")
    months_since_last_default: int   = Field(..., ge=0, description="Months since last default (0 if never)")
    # Affordability
    outstanding_to_income_pct: float = Field(..., description="Outstanding / monthly income (%)")
    outstanding_to_limit_pct:  float = Field(..., description="Outstanding / credit limit (%)")
    income_affordability_score: float = Field(..., description="Income / max outstanding ratio")
    debt_burden_category:      int   = Field(..., ge=0, le=3, description="Debt burden tier (0=Low … 3=Critical)")
    # Trends
    payment_ratio_trend:    float = Field(..., description="Change in payment ratio over window (+ve = improving)")
    utilization_trend:      float = Field(..., description="Change in utilization over window (+ve = worsening)")
    outstanding_growth_rate: float = Field(..., description="Growth rate of outstanding balance")
    is_deteriorating:       int   = Field(..., ge=0, le=1, description="Deteriorating flag (0/1)")
    # Engagement
    active_months_3m:      int   = Field(..., ge=0, le=3, description="Active months in last 3")
    avg_util_when_active:  float = Field(..., ge=0, le=1, description="Avg utilization in active months")
    snapshot_account_age:  int   = Field(..., ge=0, description="Dynamic account age at snapshot (months)")
    account_age_bucket:    int   = Field(..., ge=0, le=2, description="Account maturity bucket (0=New, 1=Established, 2=Mature)")
    risk_score:            float = Field(..., ge=0, le=100, description="Composite risk score (0–100)")
    snapshot_month:        int   = Field(..., ge=1, le=12, description="Calendar month of snapshot")

    model_config = {
        "json_schema_extra": {
            "example": {
                "age": 35, "employment_status": "Salaried", "education_level": "Graduate",
                "monthly_income": 80000.0, "credit_limit": 100000.0,
                "city_tier": "Tier-1", "dependents": 2, "residence_type": "Owned",
                "account_age_months": 24,
                "util_avg_3m": 0.35, "payment_ratio_avg_3m": 0.95,
                "max_outstanding_3m": 15000.0, "avg_txn_amt_3m": 2500.0,
                "avg_txn_count_3m": 5.0, "late_payments_3m": 0,
                "missed_due_count_3m": 0, "missed_due_last_1m": 0,
                "payment_ratio_last_1m": 1.0, "outstanding_delta_3m": 200.0,
                "bnpl_active_last_1m": 1, "consecutive_missed_due": 0,
                "payment_ratio_min_3m": 0.9, "worst_util_3m": 0.4,
                "ever_defaulted": 0, "default_count_history": 0,
                "months_since_last_default": 0, "outstanding_to_income_pct": 18.5,
                "outstanding_to_limit_pct": 10.0, "income_affordability_score": 5.3,
                "debt_burden_category": 1, "payment_ratio_trend": 0.05,
                "utilization_trend": -0.02, "outstanding_growth_rate": 0.01,
                "is_deteriorating": 0, "active_months_3m": 3,
                "avg_util_when_active": 0.35, "snapshot_account_age": 24,
                "account_age_bucket": 1, "risk_score": 15.0, "snapshot_month": 6,
            }
        }
    }

class PredictionRequest(BaseModel):
    """Simple request payload containing only the customer_id."""
    customer_id: int = Field(..., description="The unique ID of the customer (BIGINT)")

class ScoringResponse(BaseModel):
    model_type:         str
    customer_tier:      int
    tier_description:   str
    account_age_months: int
    default_probability: float
    credit_score:       int
    decision:           str
    max_credit_limit:   int
    model_used:         str
    recommendation:     Optional[str] = None
    risk_warnings:      List[str] = []
    note:               Optional[str] = None

class CustomerCreate(BaseModel):
    """New customer profile to store in Supabase."""
    customer_id:        int
    age:                int   = Field(..., ge=18, le=100)
    employment_status:  str
    education_level:    str
    monthly_income:     int   = Field(..., ge=0)
    credit_limit:       Optional[int] = Field(
        None, ge=0, le=1_00_000,
        description="Leave blank — backend auto-calculates from income, employment, education, and age."
    )
    city_tier:          str
    dependents:         int   = Field(..., ge=0, le=10)
    residence_type:     str
    registered_at:      Optional[str] = Field(
        None,
        description="ISO timestamp of account registration. Defaults to now() if omitted."
    )
    # Legacy field — kept for backward compatibility with existing data.
    # account_age_months is now computed dynamically from registered_at.
    account_age_months: int   = Field(0, ge=0, description="Set to 0 for new customers — auto-calculated at scoring time.")



class BehaviorCreate(BaseModel):
    """Monthly behavioral record to store in Supabase."""
    month:                 int   = Field(..., ge=1, le=12)
    year:                  int   = Field(..., ge=2020, le=2100)
    credit_utilization:    float = Field(..., ge=0.0, le=1.0)
    late_payment:          int   = Field(..., ge=0, le=1)
    payment_ratio:         float = Field(..., ge=0.0, le=1.0)
    outstanding_balance:   float = Field(..., ge=0)
    default_event:         int   = Field(..., ge=0, le=1)
    num_transactions:      int   = Field(..., ge=0)
    avg_transaction_amount: float = Field(..., ge=0)
    missed_due_flag:       int   = Field(..., ge=0, le=1)
