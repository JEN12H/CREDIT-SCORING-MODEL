"""
Monthly Behavioral Data Generator
===================================
Generates 12 months of credit behavior per customer.

Key improvements:
- Bill amounts are proportional to each customer's credit limit
- Payment ratios are income/employment-correlated (higher income = better payer)
- Payment behavior has autocorrelation (momentum effect — real-world behavior)
- Credit utilization = outstanding_balance / credit_limit (correct formula)
- Outstanding balance capped at 2× credit limit
- Default probability is income-correlated in addition to behavioral signals
- Requires customers.csv to exist (run generate_data.py first)
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
N_MONTHS       = 12
CUSTOMERS_PATH = "data/customers.csv"
OUTPUT_PATH    = "data/credit_behavior_monthly.csv"


# ──────────────────────────────────────────────────────────────────────
# PAYMENT PROFILE (income + employment → behavioral baseline)
# ──────────────────────────────────────────────────────────────────────
def get_payment_profile(income: int, employment: str) -> tuple:
    """
    Returns (base_payment_ratio, payment_std, active_prob).

    Higher income / stable employment → better payment discipline.
    Active probability: richer customers use credit more often.
    """
    if   income >= 1_00_000: base_pr, std = 0.93, 0.05
    elif income >=   60_000: base_pr, std = 0.87, 0.07
    elif income >=   30_000: base_pr, std = 0.78, 0.09
    elif income >=   15_000: base_pr, std = 0.68, 0.11
    else:                    base_pr, std = 0.55, 0.13

    emp_adj = {
        "Salaried":      +0.04,
        "Business":      +0.01,
        "Self-Employed":  0.00,
        "Retired":       +0.03,
        "Daily Wage":    -0.07,
    }
    base_pr = float(np.clip(base_pr + emp_adj.get(employment, 0.0), 0.30, 0.99))

    # More active = more frequent transactions (not just higher income)
    active_prob = float(np.clip(0.50 + income / 6_00_000, 0.40, 0.90))

    return base_pr, std, active_prob


# ──────────────────────────────────────────────────────────────────────
# MAIN GENERATION FUNCTION
# ──────────────────────────────────────────────────────────────────────
def generate_monthly_behavior(
    customers_path: str = CUSTOMERS_PATH,
    output_path: str = OUTPUT_PATH,
    n_months: int = N_MONTHS,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate 12 months of behavioral credit data for all customers.

    Args:
        customers_path: Path to customers.csv (must exist — run generate_data.py first).
        output_path:    Destination CSV path.
        n_months:       Number of months to simulate per customer.
        seed:           Random seed for reproducibility.

    Returns:
        DataFrame of behavioral rows.
    """
    random.seed(seed)
    np.random.seed(seed)

    if not os.path.exists(customers_path):
        raise FileNotFoundError(
            f"'{customers_path}' not found. Run generate_data.py first."
        )

    customers_df     = pd.read_csv(customers_path)
    customers_lookup = customers_df.set_index("customer_id").to_dict("index")
    customer_ids     = customers_df["customer_id"].tolist()
    n_customers      = len(customer_ids)
    logger.info(f"Loaded {n_customers:,} customer profiles from {customers_path}")

    # ── Behavioral Data Generation ────────────────────────────────────
    logger.info(f"Generating {n_months} months of behavioral data for {n_customers:,} customers...")
    rows = []

    for cid in customer_ids:
        profile      = customers_lookup[cid]
        income       = profile["monthly_income"]
        credit_limit = profile["credit_limit"]
        employment   = profile["employment_status"]

        base_pr, pr_std, active_prob = get_payment_profile(income, employment)

        outstanding_balance   = 0.0
        prev_payment_ratio    = base_pr   # initialise autocorrelation

        for month in range(1, n_months + 1):

            active = random.random() < active_prob

            if not active:
                # Inactive month: no new bill, no payment, outstanding carries over
                rows.append({
                    "customer_id":          cid,
                    "month":                month,
                    "credit_utilization":   round(min(1.0, outstanding_balance / credit_limit), 4),
                    "late_payment":         0,
                    "payment_ratio":        1.0,   # no obligation → treated as paid
                    "outstanding_balance":  round(outstanding_balance, 2),
                    "default_event":        0,     # placeholder
                    "num_transactions":     0,
                    "avg_transaction_amount": 0.0,
                    "missed_due_flag":      0,
                })
                continue

            # ── Bill amount: 10–80% of credit limit (realistic usage) ──────
            util_target  = random.uniform(0.10, 0.80)
            bill_amount  = round(credit_limit * util_target)
            bill_amount  = max(500, min(bill_amount, credit_limit))

            # ── Payment ratio: autocorrelated momentum + income baseline ───
            momentum     = 0.45 * prev_payment_ratio + 0.55 * base_pr
            raw_pr       = random.gauss(momentum, pr_std)
            payment_ratio = round(float(np.clip(raw_pr, 0.0, 1.00)), 2)
            prev_payment_ratio = payment_ratio

            paid_amount   = round(bill_amount * payment_ratio, 2)
            unpaid_amount = round(bill_amount - paid_amount, 2)

            # Accumulate unpaid, cap at 2× credit limit
            outstanding_balance = round(
                min(outstanding_balance + unpaid_amount, credit_limit * 2.0), 2
            )

            # ── Flags ──────────────────────────────────────────────────────
            missed_due_flag = 1 if payment_ratio < 0.80 else 0
            late_payment    = 1 if unpaid_amount > 0 else 0

            # ── Real utilization (outstanding / assigned limit) ─────────────
            credit_utilization = round(min(1.0, outstanding_balance / credit_limit), 4)

            num_transactions    = random.randint(1, 8)
            avg_txn_amt         = round(bill_amount / num_transactions, 2)

            rows.append({
                "customer_id":            cid,
                "month":                  month,
                "credit_utilization":     credit_utilization,
                "late_payment":           late_payment,
                "payment_ratio":          payment_ratio,
                "outstanding_balance":    outstanding_balance,
                "default_event":          0,   # placeholder — filled in next step
                "num_transactions":       num_transactions,
                "avg_transaction_amount": avg_txn_amt,
                "missed_due_flag":        missed_due_flag,
            })

    df = pd.DataFrame(rows)
    logger.info(f"  Generated {len(df):,} behavioral rows")

    # ── Default Event Generation (income-correlated, lagged signals) ──
    logger.info("Calibrating default events...")
    df["default_event"] = 0

    for cid in df["customer_id"].unique():
        profile      = customers_lookup[cid]
        income       = profile["monthly_income"]
        credit_limit = profile["credit_limit"]

        # Structural income risk modifier
        if   income >= 1_00_000: income_risk = -0.012
        elif income >=   60_000: income_risk =  0.000
        elif income >=   30_000: income_risk = +0.010
        elif income >=   15_000: income_risk = +0.025
        else:                    income_risk = +0.042

        user_idx = df.index[df["customer_id"] == cid].tolist()
        user_df  = df.loc[user_idx].sort_values("month")

        for i in range(1, len(user_df)):
            row  = user_df.iloc[i]
            prev = user_df.iloc[i - 1]

            p_default = (
                0.012                                                              # base rate
                + income_risk                                                      # income structure
                + 0.22  * prev["missed_due_flag"]                                  # strongest signal
                + 0.12  * (1.0 - prev["payment_ratio"])                            # payment stress
                + 0.08  * min(prev["outstanding_balance"] / max(credit_limit, 1), 1.0)  # utilization load
                + 0.04  * prev["late_payment"]                                     # recency flag
            )
            # Mild stochastic noise (real-world unpredictability)
            p_default += random.uniform(-0.008, 0.008)
            p_default  = float(np.clip(p_default, 0.002, 0.50))

            df.at[row.name, "default_event"] = int(random.random() < p_default)

    # ── Validation ────────────────────────────────────────────────────
    assert df["credit_utilization"].between(0, 1).all(),    "Utilization out of [0,1]!"
    assert df["payment_ratio"].between(0.0, 1.0).all(),    "Payment ratio out of range!"
    assert df["default_event"].isin([0, 1]).all(),          "Default event must be 0 or 1!"
    assert df["missed_due_flag"].isin([0, 1]).all(),        "Missed due must be 0 or 1!"

    # ── Save & Report ─────────────────────────────────────────────────
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    df.to_csv(output_path, index=False)

    overall_dr = df["default_event"].mean()
    logger.info(f"✅ {output_path} saved ({len(df):,} rows, {df.shape[1]} columns)")
    logger.info(f"   Overall default rate: {overall_dr:.4f} ({overall_dr*100:.2f}%)")

    logger.info("\nDefault rate by missed_due_flag:")
    logger.info(df.groupby("missed_due_flag")["default_event"].mean().round(4).to_string())

    df["util_bucket"] = pd.qcut(
        df["credit_utilization"], q=4, labels=["Q1-Low", "Q2", "Q3", "Q4-High"],
        duplicates="drop"
    )
    logger.info("\nDefault rate by utilization quartile:")
    logger.info(df.groupby("util_bucket")["default_event"].mean().round(4).to_string())

    return df


# ──────────────────────────────────────────────────────────────────────
# ENTRY POINT — safe to import without triggering generation
# ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    generate_monthly_behavior()