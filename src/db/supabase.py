"""
Database Layer — Supabase (Hosted PostgreSQL)
==============================================

HOW SUPABASE WORKS:
  1. Go to https://supabase.com → create a free project
  2. Go to Settings → API → copy your Project URL and anon/public Key
  3. Paste them into your .env file as SUPABASE_URL and SUPABASE_KEY
  4. Run the SQL in docs/supabase_schema.sql once from the Supabase SQL editor
     to create the three tables
  5. Done — this module connects automatically on import

WHY SUPABASE:
  - No database server to manage locally
  - Free tier (500MB, no credit card)
  - Live dashboard at supabase.com to view/edit your rows like a spreadsheet
  - Simple Python API: supabase.table("customers").insert({...}).execute()

Tables managed:
  - customers               : one row per customer profile
  - credit_behavior_monthly : one row per customer per month
  - retraining_log          : audit trail of every model retraining run
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from supabase import Client, create_client

# ── Load credentials from .env ─────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

# ── Create the single shared client ───────────────────────────────────
# Gracefully handle missing credentials (e.g. in tests or CI)
supabase: Optional[Client] = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("✅ Supabase client initialized")
    except Exception as e:
        logger.warning(f"⚠️ Supabase client creation failed: {e}")
else:
    logger.warning(
        "⚠️ SUPABASE_URL / SUPABASE_KEY not set — DB features disabled.\n"
        "   Copy .env.example → .env and add your Supabase credentials."
    )

# SUPABASE SCHEMA
# tables:
#   customers               — static profile per customer
#   credit_behavior_monthly — monthly behavioral record
#   retraining_log          — audit trail of model retraining runs

def ping() -> bool:
    """Return True if Supabase is reachable."""
    try:
        supabase.table("customers").select("customer_id").limit(1).execute()
        return True
    except Exception as e:
        logger.error(f"❌ Supabase unreachable: {e}")
        return False

# SEEDING — one-time import from existing CSVs
def seed_from_csv(customers_path: str,behavior_path: str,batch_size: int = 500) -> dict:
    """
    Upload existing CSV data to Supabase.
    """
    customers_upserted = 0
    behavior_upserted  = 0

    # ── Customers 
    if os.path.exists(customers_path):
        cdf = pd.read_csv(customers_path)
        records = cdf.to_dict(orient="records")

        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            supabase.table("customers").upsert(batch, on_conflict="customer_id").execute()
            customers_upserted += len(batch)

        logger.info(f"  ✅ Customers upserted: {customers_upserted:,}")
    else:
        logger.warning(f"  customers CSV not found: {customers_path}")

    # ── Behavior 
    if os.path.exists(behavior_path):
        bdf = pd.read_csv(behavior_path)
        # Add a year column for the unique constraint (synthetic data → 2025)
        if "year" not in bdf.columns:
            bdf["year"] = 2025
        records = bdf.to_dict(orient="records")

        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            supabase.table("credit_behavior_monthly").upsert(
                batch, on_conflict="customer_id,month,year"
            ).execute()
            behavior_upserted += len(batch)

        logger.info(f"  ✅ Behavior rows upserted: {behavior_upserted:,}")
    else:
        logger.warning(f"  behavior CSV not found: {behavior_path}")

    return {"customers_upserted": customers_upserted, "behavior_upserted": behavior_upserted}

# CRUD — Customers

def add_customer(data: dict) -> dict:
    """
    Insert a new customer profile.
    Auto-stamps registered_at = now() if not provided.
    If customer_id is None / missing, the DB auto-generates it (IDENTITY column).
    Raises ValueError if customer_id already exists.
    """
    # If a customer_id was explicitly provided, check for duplicates
    if data.get("customer_id") is not None:
        existing = (
            supabase.table("customers")
            .select("customer_id")
            .eq("customer_id", data["customer_id"])
            .execute()
        )
        if existing.data:
            raise ValueError(f"Customer {data['customer_id']} already exists.")
    else:
        # Remove the key entirely so the DB IDENTITY column auto-generates it
        data.pop("customer_id", None)

    # Auto-stamp registration timestamp if not provided by caller
    if not data.get("registered_at"):
        data["registered_at"] = datetime.now(timezone.utc).isoformat()

    result = supabase.table("customers").insert(data).execute()
    new_record = result.data[0] if result.data else {}
    logger.info(f"Added customer {new_record.get('customer_id')} (registered_at={data['registered_at']})")
    return new_record


def update_customer(customer_id: int, data: dict) -> dict:
    """Update an existing customer profile. Returns updated record."""
    result = (
        supabase.table("customers")
        .update(data)
        .eq("customer_id", customer_id)
        .execute()
    )
    return result.data[0] if result.data else {}

def _compute_account_age(record: dict) -> int:
    """
    Compute account_age_months dynamically from registered_at.
    Falls back to the stored account_age_months column if registered_at is missing
    (handles legacy customers who were created before this field existed).
    """
    registered_at_str = record.get("registered_at")
    if registered_at_str:
        try:
            from dateutil import parser as dateparser
            registered_dt = dateparser.parse(registered_at_str)
            if registered_dt.tzinfo is None:
                registered_dt = registered_dt.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - registered_dt
            return max(0, delta.days // 30)
        except Exception as e:
            logger.warning(f"Could not parse registered_at '{registered_at_str}': {e}")
    # Legacy fallback — use the stored static value
    return record.get("account_age_months", 0)


def get_customer(customer_id: int) -> Optional[dict]:
    """Return customer record dict with dynamically computed account_age_months."""
    result = (
        supabase.table("customers")
        .select("*")
        .eq("customer_id", customer_id)
        .execute()
    )
    if not result.data:
        return None
    record = result.data[0]
    # Always override with live-computed age — never trust the stale DB integer
    record["account_age_months"] = _compute_account_age(record)
    return record

def get_customer_profile(customer_id: int) -> Optional[dict]:
    """Alias for get_customer, mapping to the new automated flow."""
    return get_customer(customer_id)

# CRUD — Monthly Behavior
def add_behavior_record(data: dict) -> dict:
    """
    Insert a monthly behavior record.
    Raises ValueError if a record for (customer_id, month, year) already exists.
    """
    existing = (
        supabase.table("credit_behavior_monthly")
        .select("id")
        .eq("customer_id", data["customer_id"])
        .eq("month", data["month"])
        .eq("year", data["year"])
        .execute()
    )
    if existing.data:
        raise ValueError(
            f"Behavior record for customer {data['customer_id']} "
            f"month {data['month']}/{data['year']} already exists."
        )

    result = supabase.table("credit_behavior_monthly").insert(data).execute()
    logger.info(f"Added behavior for customer {data['customer_id']} ({data['month']}/{data['year']})")
    return result.data[0] if result.data else {}


def get_customer_history(customer_id: int) -> list:
    """Return full behavioral history for a customer, sorted by year+month."""
    result = (
        supabase.table("credit_behavior_monthly")
        .select("*")
        .eq("customer_id", customer_id)
        .order("year")
        .order("month")
        .execute()
    )
    return result.data or []

def get_raw_transaction_history(customer_id: int, months: int = 6) -> list:
    """Return raw transactions for a customer, sorted by newest first."""
    result = (
        supabase.table("raw_transactions")
        .select("*")
        .eq("customer_id", customer_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


# EXPORT — Supabase → CSV (used by monthly retraining job)
def export_to_csv(customers_path: str, behavior_path: str) -> dict:
    """
    Pull all data from Supabase and write to CSV files.
    The snap pipeline and training scripts consume these CSVs.
    Supabase returns 1000 rows per request by default —
    """
    PAGE = 1000

    # Customers
    all_customers = []
    offset = 0
    while True:
        chunk = (
            supabase.table("customers")
            .select("*")
            .range(offset, offset + PAGE - 1)
            .execute()
        )
        all_customers.extend(chunk.data or [])
        if len(chunk.data or []) < PAGE:
            break
        offset += PAGE

    cdf = pd.DataFrame(all_customers)
    os.makedirs(os.path.dirname(customers_path), exist_ok=True)
    cdf.to_csv(customers_path, index=False)

    # Behavior 
    all_behavior = []
    offset = 0
    while True:
        chunk = (
            supabase.table("credit_behavior_monthly")
            .select("*")
            .order("customer_id")
            .order("year")
            .order("month")
            .range(offset, offset + PAGE - 1)
            .execute()
        )
        all_behavior.extend(chunk.data or [])
        if len(chunk.data or []) < PAGE:
            break
        offset += PAGE

    bdf = pd.DataFrame(all_behavior)
    # Drop DB-only columns the snap pipeline doesn't need
    bdf = bdf.drop(columns=["id", "recorded_at"], errors="ignore")
    # Rename 'year' back if needed — snap pipeline only uses 'month' as 1–12
    os.makedirs(os.path.dirname(behavior_path), exist_ok=True)
    bdf.to_csv(behavior_path, index=False)

    logger.info(f"✅ Exported {len(cdf):,} customers + {len(bdf):,} behavior rows from Supabase to CSV")
    return {"n_customers": len(cdf), "n_behavior_rows": len(bdf)}

# RETRAINING LOG
def log_retraining(trigger: str,success: bool,cold_start_auc: Optional[float] = None,full_model_auc: Optional[float] = None,n_customers: Optional[int] = None,n_behavior_rows: Optional[int] = None,notes: Optional[str] = None) -> dict:
    """Write one row to the retraining_log table. Returns the inserted record."""
    payload = {
        "trigger":         trigger,
        "success":         success,
        "cold_start_auc":  cold_start_auc,
        "full_model_auc":  full_model_auc,
        "n_customers":     n_customers,
        "n_behavior_rows": n_behavior_rows,
        "notes":           notes,
        "run_at":          datetime.now(timezone.utc).isoformat(),
    }
    result = supabase.table("retraining_log").insert(payload).execute()
    return result.data[0] if result.data else {}


def get_retraining_log(limit: int = 20) -> list:
    """Return the most recent retraining log entries."""
    result = (
        supabase.table("retraining_log")
        .select("*")
        .order("run_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []
