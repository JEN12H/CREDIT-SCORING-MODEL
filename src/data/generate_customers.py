"""
Customer Profile Generator
===========================
Generates 10,000 synthetic customer profiles with realistic
Indian lending market demographics and proper credit limits.

Key improvements over legacy version:
- Credit limit assigned per customer (income × employment multiplier)
- Income distribution is employment-correlated
- Dependents are realistically weighted
- All fields validated before save
"""

import random
import numpy as np
import pandas as pd
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────
N_CUSTOMERS = 10_000
OUTPUT_PATH = "data/customers.csv"

EMPLOYMENT_TYPES   = ["Salaried", "Self-Employed", "Business", "Daily Wage"]
EMPLOYMENT_WEIGHTS = [0.45,        0.25,            0.15,       0.15]

EDUCATION_LEVELS   = ["No Formal Education", "Primary", "Secondary", "High School", "Graduate", "Postgraduate"]
EDUCATION_WEIGHTS  = [0.08,                   0.12,      0.22,        0.26,          0.22,       0.10]

CITY_TIERS   = ["Tier-1", "Tier-2", "Tier-3"]
CITY_WEIGHTS = [0.25,      0.45,     0.30]

RESIDENCE_TYPES   = ["Owned", "Rented", "Family-Owned"]
RESIDENCE_WEIGHTS = [0.35,    0.50,     0.15]

# Dependents: 0-1 most common in BNPL customer base
DEPENDENT_COUNTS   = [0, 1, 2, 3, 4]
DEPENDENT_WEIGHTS  = [0.30, 0.30, 0.22, 0.12, 0.06]


# ──────────────────────────────────────────────────────────────────────
# INCOME GENERATION (long-tail per employment type)
# ──────────────────────────────────────────────────────────────────────
def generate_income(employment_status: str, rng: float) -> int:
    """Return monthly income (INR) with realistic skew per employment type."""
    if employment_status == "Daily Wage":
        return random.randint(8_000, 25_000)
    elif employment_status == "Salaried":
        if rng < 0.70:   return random.randint(20_000, 60_000)
        elif rng < 0.93: return random.randint(60_000, 1_00_000)
        else:            return random.randint(1_00_000, 2_00_000)
    elif employment_status == "Self-Employed":
        if rng < 0.60:   return random.randint(25_000, 60_000)
        elif rng < 0.88: return random.randint(60_000, 1_20_000)
        else:            return random.randint(1_20_000, 2_50_000)
    elif employment_status == "Business":
        if rng < 0.45:   return random.randint(30_000, 80_000)
        elif rng < 0.78: return random.randint(80_000, 1_50_000)
        else:            return random.randint(1_50_000, 2_50_000)
    else:  # Retired
        return random.randint(15_000, 60_000)


# ──────────────────────────────────────────────────────────────────────
# CREDIT LIMIT ASSIGNMENT
# ──────────────────────────────────────────────────────────────────────
def assign_credit_limit(
    employment_status: str,
    monthly_income: int,
    education_level: str,
    age: int,
) -> int:
    """
    Assign a credit limit using fixed, deterministic lender underwriting logic:
    - Base = income × fixed employment-stability multiplier
    - Education adjustment (higher education → slightly higher limit)
    - Age adjustment (very young or very old → conservative)
    - Rounded to nearest ₹500, clamped to [₹5,000 – ₹1,00,000]

    Fixed multipliers (no randomness) — same customer always gets same limit.
    """
    # Fixed multiplier per employment type (deterministic — production safe)
    fixed_multipliers = {
        "Salaried":      2.0,   # Stable salary — max 2× income
        "Business":      1.5,   # Revenue can vary — moderate
        "Self-Employed": 1.2,   # Unpredictable — conservative
        "Retired":       0.8,   # Fixed pension — limited growth
        "Daily Wage":    0.4,   # Irregular income — most conservative
    }
    multiplier = fixed_multipliers.get(employment_status, 1.0)
    base_limit = int(monthly_income * multiplier)

    edu_factor = {
        "Postgraduate":        1.20,
        "Graduate":            1.10,
        "High School":         1.00,
        "Secondary":           0.90,
        "Primary":             0.80,
        "No Formal Education": 0.70,
    }
    base_limit = int(base_limit * edu_factor.get(education_level, 1.0))

    if age < 25 or age > 65:
        base_limit = int(base_limit * 0.75)

    # Round to nearest ₹500 and clamp
    base_limit = max(5_000, min(1_00_000, round(base_limit / 500) * 500))
    return base_limit


# ──────────────────────────────────────────────────────────────────────
# MAIN GENERATION FUNCTION
# ──────────────────────────────────────────────────────────────────────
def generate_customers(
    n_customers: int = N_CUSTOMERS,
    output_path: str = OUTPUT_PATH,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate synthetic customer profiles and save to CSV.

    Returns:
        DataFrame of generated customer profiles.
    """
    random.seed(seed)
    np.random.seed(seed)

    logger.info(f"Generating {n_customers:,} customer profiles...")
    customers = []

    for cid in range(1, n_customers + 1):
        age = random.randint(21, 75)

        # Retired if age >= 62
        employment_status = (
            "Retired"
            if age >= 62
            else random.choices(EMPLOYMENT_TYPES, weights=EMPLOYMENT_WEIGHTS)[0]
        )

        education_level = random.choices(EDUCATION_LEVELS,  weights=EDUCATION_WEIGHTS)[0]
        city_tier        = random.choices(CITY_TIERS,        weights=CITY_WEIGHTS)[0]
        dependents       = random.choices(DEPENDENT_COUNTS,  weights=DEPENDENT_WEIGHTS)[0]
        residence_type   = random.choices(RESIDENCE_TYPES,   weights=RESIDENCE_WEIGHTS)[0]

        # Account age AT START of window (0 = brand-new account)
        account_age_months = random.randint(0, 60)

        income_rng     = random.random()
        monthly_income = generate_income(employment_status, income_rng)
        credit_limit   = assign_credit_limit(employment_status, monthly_income, education_level, age)

        customers.append({
            "customer_id":        cid,
            "age":                age,
            "employment_status":  employment_status,
            "education_level":    education_level,
            "monthly_income":     monthly_income,
            "credit_limit":       credit_limit,
            "city_tier":          city_tier,
            "dependents":         dependents,
            "residence_type":     residence_type,
            "account_age_months": account_age_months,
        })

    df = pd.DataFrame(customers)

    # ── Validation ──────────────────────────────────────────────────
    assert df["customer_id"].nunique() == n_customers, "Duplicate customer IDs!"
    assert df["monthly_income"].min() > 0,             "Non-positive income detected!"
    assert df["credit_limit"].min() >= 5_000,          "Credit limit below minimum!"
    assert df["age"].between(21, 75).all(),            "Age out of range!"

    # ── Save ────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    df.to_csv(output_path, index=False)

    logger.info(f"✅ {output_path} saved ({n_customers:,} customers, {df.shape[1]} columns)")
    logger.info(f"   Income range:       ₹{df.monthly_income.min():>10,} – ₹{df.monthly_income.max():>10,}")
    logger.info(f"   Credit limit range: ₹{df.credit_limit.min():>10,} – ₹{df.credit_limit.max():>10,}")
    logger.info(f"   Employment mix:\n{df.employment_status.value_counts(normalize=True).mul(100).round(1).to_string()}")

    return df


# ──────────────────────────────────────────────────────────────────────
# ENTRY POINT — safe to import without triggering generation
# ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    generate_customers()
