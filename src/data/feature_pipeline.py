"""
Snapshot Pipeline
==================
Joins customer profiles with 12-month behavioral data and engineers
the feature set used for model training.

Changes from legacy version:
- account_age is now DYNAMIC per snapshot (account_age_months + snapshot_month)
- credit_limit added to per-customer context for affordability ratios
- New feature: outstanding_to_limit_pct (utilization relative to assigned limit)
- All sanity checks updated to reflect new data contracts
"""

import pandas as pd
import numpy as np
import time
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# CONFIG
LOOKBACK_MONTHS = 3
MAX_SAVE_RETRIES = 3

# HELPER FUNCTIONS

def count_consecutive_missed(series: pd.Series) -> int:
    """Count consecutive missed due flags from the most recent month backwards."""
    streak = 0
    for val in reversed(series.values):
        if val == 1:
            streak += 1
        else:
            break
    return streak


def safe_divide(a, b, default: float = 0.0) -> float:
    """Division with zero/None guard."""
    if b is None or b == 0:
        return default
    return a / b


def categorize_debt_burden(pct: float) -> int:
    """Categorize outstanding-to-income percentage into risk tiers (0–3)."""
    if   pct < 10:  return 0  # Low
    elif pct < 30:  return 1  # Medium
    elif pct < 50:  return 2  # High
    else:           return 3  # Critical


def categorize_account_age(months: int) -> int:
    """Categorize account maturity into buckets (0=New, 1=Established, 2=Mature)."""
    if   months < 6:  return 0
    elif months < 24: return 1
    else:             return 2


def safe_save_csv(df: pd.DataFrame, filename: str, retries: int = 3) -> bool:
    """Save CSV with retry logic for file-lock issues (common on Windows)."""
    for attempt in range(retries):
        try:
            df.to_csv(filename, index=False)
            return True
        except PermissionError:
            logger.warning(f"File locked, retrying in 2s... ({attempt + 1}/{retries})")
            time.sleep(2)
    backup = filename.replace(".csv", "_backup.csv")
    df.to_csv(backup, index=False)
    logger.warning(f"Saved to backup: {backup}")
    return False


# ──────────────────────────────────────────────────────────────────────
# REAL-TIME FEATURE ENGINEERING (API ROUTE)
# ──────────────────────────────────────────────────────────────────────
def calculate_single_user_features(profile_data: dict, history_data: list) -> dict:
    """
    Calculate ML features dynamically for a single user during an API request.
    Takes the static profile_data and dynamic history_data and returns the final features dictionary.
    """
    if not profile_data:
        raise ValueError("Profile data is required.")
    
    # Check if history is raw transactions and handle it (mocking aggregation if needed)
    # For now, assuming history_data matches the monthly behavioral schema used downstream.
    if not history_data or len(history_data) < LOOKBACK_MONTHS + 1:
        # Fallback to cold start or empty 
        raise ValueError(f"Need at least {LOOKBACK_MONTHS + 1} months of history.")
        
    user_df = pd.DataFrame(history_data)
    if "month" in user_df.columns:
        user_df = user_df.sort_values(["year", "month"] if "year" in user_df.columns else ["month"]).reset_index(drop=True)

    monthly_income    = profile_data.get("monthly_income", 0)
    account_age_start = profile_data.get("account_age_months", 0)
    credit_limit      = profile_data.get("credit_limit", max(monthly_income * 2, 10_000))
    cid               = profile_data.get("customer_id")

    # Use the most recent month as 'current'
    t = len(user_df) - 1
    past    = user_df.iloc[t - LOOKBACK_MONTHS : t]
    last    = user_df.iloc[t - 1]
    current = user_df.iloc[t]

    prior_defaults = user_df.iloc[:t].get("default_event", pd.Series([0])).tolist()

    snapshot_account_age = account_age_start + int(current.get("month", 0))

    util_avg_3m            = float(past.get("credit_utilization", pd.Series([0.0])).mean())
    payment_ratio_avg_3m   = float(past.get("payment_ratio", pd.Series([1.0])).mean())
    max_outstanding_3m     = float(past.get("outstanding_balance", pd.Series([0.0])).max())
    avg_txn_amt_3m         = float(past.get("avg_transaction_amount", pd.Series([0.0])).mean())
    avg_txn_count_3m       = float(past.get("num_transactions", pd.Series([0.0])).mean())
    late_payments_3m       = int(past.get("late_payment", pd.Series([0])).sum())
    missed_due_count_3m    = int(past.get("missed_due_flag", pd.Series([0])).sum())

    missed_due_last_1m     = int(last.get("missed_due_flag", 0))
    payment_ratio_last_1m  = float(last.get("payment_ratio", 1.0))
    
    out_bal = past.get("outstanding_balance", pd.Series([0.0, 0.0]))
    outstanding_delta_3m   = float(out_bal.iloc[-1] - out_bal.iloc[0]) if len(out_bal) > 1 else 0.0
    bnpl_active_last_1m    = int(last.get("num_transactions", 0) > 0)

    consecutive_missed_due = count_consecutive_missed(past.get("missed_due_flag", pd.Series([0])))
    payment_ratio_min_3m   = float(past.get("payment_ratio", pd.Series([1.0])).min())
    worst_util_3m          = float(past.get("credit_utilization", pd.Series([0.0])).max())

    ever_defaulted          = 1 if sum(prior_defaults) > 0 else 0
    default_count_history   = int(sum(prior_defaults))

    months_since_last_default = 0
    if ever_defaulted:
        for i, d in enumerate(reversed(prior_defaults)):
            if d == 1:
                months_since_last_default = i
                break

    curr_bal = float(current.get("outstanding_balance", 0.0))
    outstanding_to_income_pct = safe_divide(curr_bal * 100, monthly_income, default=100.0)
    outstanding_to_limit_pct  = safe_divide(curr_bal * 100, credit_limit, default=100.0)
    income_affordability_score = safe_divide(monthly_income, max_outstanding_3m + 1, default=0.0)
    debt_burden_category = categorize_debt_burden(outstanding_to_income_pct)

    pr_series = past.get("payment_ratio", pd.Series([1.0, 1.0]))
    payment_ratio_trend = float(pr_series.iloc[-1] - pr_series.iloc[0]) if len(pr_series) > 1 else 0.0
    
    ut_series = past.get("credit_utilization", pd.Series([0.0, 0.0]))
    utilization_trend = float(ut_series.iloc[-1] - ut_series.iloc[0]) if len(ut_series) > 1 else 0.0
    
    outstanding_growth_rate = safe_divide(outstanding_delta_3m, out_bal.iloc[0] + 1, default=0.0) if len(out_bal) > 1 else 0.0
    is_deteriorating = int(payment_ratio_trend < 0 and utilization_trend > 0)

    txn_series = past.get("num_transactions", pd.Series([0]))
    active_months_3m = int((txn_series > 0).sum())
    active_mask = txn_series > 0
    avg_util_when_active = float(ut_series.loc[active_mask].mean()) if active_mask.any() else 0.0

    account_age_bucket = categorize_account_age(snapshot_account_age)

    risk_score = (
        missed_due_last_1m              * 25
        + consecutive_missed_due        * 15
        + (1 - payment_ratio_min_3m)    * 20
        + min(outstanding_to_limit_pct / 100, 1) * 15
        + is_deteriorating              * 10
        + (1 if payment_ratio_avg_3m < 0.70 else 0) * 10
        + ever_defaulted                * 5
    )
    risk_score = float(min(risk_score, 100.0))

    # Construct the FullModelInput dictionary
    features = {
        **profile_data,  # Contains age, monthly_income, etc.
        "util_avg_3m":               util_avg_3m,
        "payment_ratio_avg_3m":      payment_ratio_avg_3m,
        "max_outstanding_3m":        max_outstanding_3m,
        "avg_txn_amt_3m":            avg_txn_amt_3m,
        "avg_txn_count_3m":          avg_txn_count_3m,
        "late_payments_3m":          late_payments_3m,
        "missed_due_count_3m":       missed_due_count_3m,
        "missed_due_last_1m":        missed_due_last_1m,
        "payment_ratio_last_1m":     payment_ratio_last_1m,
        "outstanding_delta_3m":      outstanding_delta_3m,
        "bnpl_active_last_1m":       bnpl_active_last_1m,
        "consecutive_missed_due":    consecutive_missed_due,
        "payment_ratio_min_3m":      payment_ratio_min_3m,
        "worst_util_3m":             worst_util_3m,
        "ever_defaulted":            ever_defaulted,
        "default_count_history":     default_count_history,
        "months_since_last_default": months_since_last_default,
        "outstanding_to_income_pct": outstanding_to_income_pct,
        "outstanding_to_limit_pct":  outstanding_to_limit_pct,
        "income_affordability_score": income_affordability_score,
        "debt_burden_category":      debt_burden_category,
        "payment_ratio_trend":       payment_ratio_trend,
        "utilization_trend":         utilization_trend,
        "outstanding_growth_rate":   outstanding_growth_rate,
        "is_deteriorating":          is_deteriorating,
        "active_months_3m":          active_months_3m,
        "avg_util_when_active":      avg_util_when_active,
        "snapshot_account_age":      snapshot_account_age,
        "account_age_bucket":        account_age_bucket,
        "risk_score":                risk_score,
        "snapshot_month":            int(current.get("month", 0)),
    }
    return features


# ──────────────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ──────────────────────────────────────────────────────────────────────
def run_snap_pipeline(
    customers_path: str = "data/customers.csv",
    behavior_path:  str = "data/credit_behavior_monthly.csv",
    output_path:    str = "data/model_snapshots.csv",
) -> bool:

    # ── Load ──────────────────────────────────────────────────────────
    logger.info(f"Loading data from '{customers_path}' and '{behavior_path}'...")
    try:
        customers = pd.read_csv(customers_path)
        behavior  = pd.read_csv(behavior_path)
    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        return False

    # ── Sanity checks on inputs ────────────────────────────────────────
    for col in ["customer_id", "monthly_income", "account_age_months"]:
        assert col in customers.columns, f"customers.csv missing column: {col}"
    for col in ["customer_id", "month", "default_event", "missed_due_flag"]:
        assert col in behavior.columns, f"credit_behavior_monthly.csv missing column: {col}"

    has_credit_limit = "credit_limit" in customers.columns

    customer_lookup = customers.set_index("customer_id").to_dict("index")
    snapshots = []

    # ── Build snapshots ────────────────────────────────────────────────
    logger.info("Engineering snapshots...")
    for cid in behavior["customer_id"].unique():

        user_df = (
            behavior[behavior["customer_id"] == cid]
            .sort_values("month")
            .reset_index(drop=True)
        )

        profile           = customer_lookup.get(cid, {})
        monthly_income    = profile.get("monthly_income", 0)
        account_age_start = profile.get("account_age_months", 0)   # age at window start
        credit_limit      = profile.get("credit_limit", max(monthly_income * 2, 10_000))

        historical_defaults = []

        # Need at least LOOKBACK_MONTHS past + 1 current month
        for t in range(LOOKBACK_MONTHS, len(user_df)):

            past    = user_df.iloc[t - LOOKBACK_MONTHS : t]
            last    = user_df.iloc[t - 1]
            current = user_df.iloc[t]

            prior_defaults = user_df.iloc[:t]["default_event"].tolist()

            # ── DYNAMIC account age: starting age + months elapsed ─────
            snapshot_account_age = account_age_start + int(current["month"])

            # ──────────────────────────────────────────────────────────
            # BASIC AGGREGATES (3-month window)
            # ──────────────────────────────────────────────────────────
            util_avg_3m            = past["credit_utilization"].mean()
            payment_ratio_avg_3m   = past["payment_ratio"].mean()
            max_outstanding_3m     = past["outstanding_balance"].max()
            avg_txn_amt_3m         = past["avg_transaction_amount"].mean()
            avg_txn_count_3m       = past["num_transactions"].mean()
            late_payments_3m       = past["late_payment"].sum()
            missed_due_count_3m    = past["missed_due_flag"].sum()

            # ──────────────────────────────────────────────────────────
            # RECENCY / VELOCITY
            # ──────────────────────────────────────────────────────────
            missed_due_last_1m     = int(last["missed_due_flag"])
            payment_ratio_last_1m  = last["payment_ratio"]
            outstanding_delta_3m   = (
                past["outstanding_balance"].iloc[-1]
                - past["outstanding_balance"].iloc[0]
            )
            bnpl_active_last_1m    = int(last["num_transactions"] > 0)

            # ──────────────────────────────────────────────────────────
            # RISK SIGNALS
            # ──────────────────────────────────────────────────────────
            consecutive_missed_due  = count_consecutive_missed(past["missed_due_flag"])
            payment_ratio_min_3m    = past["payment_ratio"].min()
            worst_util_3m           = past["credit_utilization"].max()

            ever_defaulted          = 1 if sum(prior_defaults) > 0 else 0
            default_count_history   = int(sum(prior_defaults))

            months_since_last_default = 0
            if ever_defaulted:
                for i, d in enumerate(reversed(prior_defaults)):
                    if d == 1:
                        months_since_last_default = i
                        break

            # ──────────────────────────────────────────────────────────
            # AFFORDABILITY METRICS
            # ──────────────────────────────────────────────────────────
            outstanding_to_income_pct = safe_divide(
                current["outstanding_balance"] * 100, monthly_income, default=100.0
            )
            outstanding_to_limit_pct = safe_divide(
                current["outstanding_balance"] * 100, credit_limit, default=100.0
            )
            income_affordability_score = safe_divide(
                monthly_income, max_outstanding_3m + 1, default=0.0
            )
            debt_burden_category = categorize_debt_burden(outstanding_to_income_pct)

            # ──────────────────────────────────────────────────────────
            # BEHAVIORAL TRENDS
            # ──────────────────────────────────────────────────────────
            payment_ratio_trend     = past["payment_ratio"].iloc[-1] - past["payment_ratio"].iloc[0]
            utilization_trend       = past["credit_utilization"].iloc[-1] - past["credit_utilization"].iloc[0]
            outstanding_growth_rate = safe_divide(
                outstanding_delta_3m, past["outstanding_balance"].iloc[0] + 1, default=0.0
            )
            is_deteriorating = int(payment_ratio_trend < 0 and utilization_trend > 0)

            # ──────────────────────────────────────────────────────────
            # ENGAGEMENT & STABILITY
            # ──────────────────────────────────────────────────────────
            active_months_3m     = int((past["num_transactions"] > 0).sum())
            active_mask          = past["num_transactions"] > 0
            avg_util_when_active = (
                past.loc[active_mask, "credit_utilization"].mean()
                if active_mask.any() else 0.0
            )

            account_age_bucket = categorize_account_age(snapshot_account_age)

            # ──────────────────────────────────────────────────────────
            # COMPOSITE RISK SCORE (0–100)
            # ──────────────────────────────────────────────────────────
            risk_score = (
                missed_due_last_1m              * 25   # strongest recency signal
                + consecutive_missed_due        * 15
                + (1 - payment_ratio_min_3m)    * 20
                + min(outstanding_to_limit_pct / 100, 1) * 15   # vs limit, not income
                + is_deteriorating              * 10
                + (1 if payment_ratio_avg_3m < 0.70 else 0) * 10
                + ever_defaulted                * 5
            )
            risk_score = float(min(risk_score, 100.0))

            # ──────────────────────────────────────────────────────────
            # TARGET
            # ──────────────────────────────────────────────────────────
            default_next_1m = int(current["default_event"])

            snapshots.append({
                # Identifier
                "customer_id":               cid,
                "snapshot_month":            int(current["month"]),

                # Basic aggregates
                "util_avg_3m":               util_avg_3m,
                "payment_ratio_avg_3m":      payment_ratio_avg_3m,
                "max_outstanding_3m":        max_outstanding_3m,
                "avg_txn_amt_3m":            avg_txn_amt_3m,
                "avg_txn_count_3m":          avg_txn_count_3m,
                "late_payments_3m":          late_payments_3m,
                "missed_due_count_3m":       missed_due_count_3m,

                # Recency / velocity
                "missed_due_last_1m":        missed_due_last_1m,
                "payment_ratio_last_1m":     payment_ratio_last_1m,
                "outstanding_delta_3m":      outstanding_delta_3m,
                "bnpl_active_last_1m":       bnpl_active_last_1m,

                # Risk signals
                "consecutive_missed_due":    consecutive_missed_due,
                "payment_ratio_min_3m":      payment_ratio_min_3m,
                "worst_util_3m":             worst_util_3m,
                "ever_defaulted":            ever_defaulted,
                "default_count_history":     default_count_history,
                "months_since_last_default": months_since_last_default,

                # Affordability
                "outstanding_to_income_pct":   outstanding_to_income_pct,
                "outstanding_to_limit_pct":    outstanding_to_limit_pct,
                "income_affordability_score":  income_affordability_score,
                "debt_burden_category":        debt_burden_category,

                # Behavioral trends
                "payment_ratio_trend":         payment_ratio_trend,
                "utilization_trend":           utilization_trend,
                "outstanding_growth_rate":     outstanding_growth_rate,
                "is_deteriorating":            is_deteriorating,

                # Engagement & stability
                "active_months_3m":            active_months_3m,
                "avg_util_when_active":        avg_util_when_active,
                "snapshot_account_age":        snapshot_account_age,   # DYNAMIC
                "account_age_bucket":          account_age_bucket,

                # Composite risk
                "risk_score":                  risk_score,

                # Target
                "default_next_1m":             default_next_1m,
            })

    # ── Build DataFrame ────────────────────────────────────────────────
    snapshots_df = pd.DataFrame(snapshots)

    # ── Merge static customer features ────────────────────────────────
    snapshots_df = snapshots_df.merge(customers, on="customer_id", how="left")

    # ── Sanity checks on output ────────────────────────────────────────
    assert snapshots_df["missed_due_count_3m"].max()     <= LOOKBACK_MONTHS, "missed_due_count_3m overflow"
    assert snapshots_df["consecutive_missed_due"].max()  <= LOOKBACK_MONTHS, "consecutive overflow"
    assert snapshots_df["active_months_3m"].max()        <= LOOKBACK_MONTHS, "active_months overflow"
    assert snapshots_df["default_next_1m"].isin([0, 1]).all(), "target must be binary"
    assert snapshots_df["debt_burden_category"].isin([0, 1, 2, 3]).all(), "debt bucket out of range"
    assert snapshots_df["account_age_bucket"].isin([0, 1, 2]).all(),      "age bucket out of range"

    # ── Save ──────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    saved = safe_save_csv(snapshots_df, output_path)
    if saved:
        dr = snapshots_df["default_next_1m"].mean()
        logger.info(f"✅ {output_path} created ({snapshots_df.shape[0]:,} rows × {snapshots_df.shape[1]} features)")
        logger.info(f"   Default rate:         {dr:.4f} ({dr*100:.2f}%)")
        logger.info(f"   Snapshot account age: {snapshots_df['snapshot_account_age'].min()}–{snapshots_df['snapshot_account_age'].max()} months")

        logger.info("\n📊 Feature quality stats:")
        logger.info(f"  Consecutive missed due > 0 : {(snapshots_df['consecutive_missed_due'] > 0).mean():.2%}")
        logger.info(f"  Ever defaulted             : {snapshots_df['ever_defaulted'].mean():.2%}")
        logger.info(f"  Deteriorating behavior     : {snapshots_df['is_deteriorating'].mean():.2%}")
        logger.info(f"  Avg composite risk score   : {snapshots_df['risk_score'].mean():.1f}")
        logger.info(f"  High debt burden (>30%)    : {(snapshots_df['outstanding_to_income_pct'] > 30).mean():.2%}")
    else:
        logger.warning("⚠️ Failed to save primary output (backup may exist)")

    return saved


if __name__ == "__main__":
    run_snap_pipeline()
