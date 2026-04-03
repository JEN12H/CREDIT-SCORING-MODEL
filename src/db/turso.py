"""
Database Layer — Turso (libSQL / SQLite)
=========================================

Replaces src/db/supabase.py. All operations use Turso's HTTP REST API
via the requests library. No external SDK required.

Credentials are loaded from .env:
  TURSO_URL        — e.g. https://baakioperations-ansh-chamriya.turso.io
  TURSO_AUTH_TOKEN — JWT auth token from Turso dashboard

Tables managed:
  - customers               : one row per customer profile
  - credit_behavior_monthly : one row per customer per month
  - raw_transactions        : individual transaction events
  - retraining_log          : audit trail of every model retraining run
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import requests
from dotenv import load_dotenv

# ── Load credentials from .env ─────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TURSO_URL: str        = os.getenv("TURSO_URL", "")
TURSO_AUTH_TOKEN: str = os.getenv("TURSO_AUTH_TOKEN", "")

if not TURSO_URL or not TURSO_AUTH_TOKEN:
    logger.warning(
        "TURSO_URL / TURSO_AUTH_TOKEN not set — DB features disabled.\n"
        "Add them to your .env file."
    )
else:
    logger.info("Turso client configured: %s", TURSO_URL)


# ── Core HTTP helper ───────────────────────────────────────────────────

def _execute(statements: list[dict]) -> list[dict]:
    """
    Send a list of SQL statements to Turso's /v2/pipeline endpoint.
    Each statement: {"sql": "...", "args": [...]}
    Returns list of result sets, one per statement.

    Raises RuntimeError on HTTP error or Turso-level error.
    """
    url = f"{TURSO_URL}/v2/pipeline"
    headers = {
        "Authorization": f"Bearer {TURSO_AUTH_TOKEN}",
        "Content-Type": "application/json",
    }
    requests_payload = [
        {"type": "execute", "stmt": stmt} for stmt in statements
    ]
    requests_payload.append({"type": "close"})

    resp = requests.post(url, headers=headers, json={"requests": requests_payload}, timeout=30)

    if resp.status_code != 200:
        raise RuntimeError(f"Turso HTTP {resp.status_code}: {resp.text[:500]}")

    results = resp.json().get("results", [])

    # Check each result for errors returned by Turso
    rows_list = []
    for i, result in enumerate(results):
        if result.get("type") == "error":
            raise RuntimeError(f"Turso SQL error on statement {i}: {result.get('error')}")
        if result.get("type") == "ok":
            rows_list.append(result.get("response", {}).get("result", {}))

    return rows_list


def _rows_to_dicts(result: dict) -> list[dict]:
    """
    Convert Turso's column/row format into a list of plain dicts.
    result = {"cols": [{"name": "col1"}, ...], "rows": [[{"type":"...", "value":"..."}], ...]}
    """
    cols = [c["name"] for c in result.get("cols", [])]
    rows = result.get("rows", [])
    records = []
    for row in rows:
        record = {}
        for col, cell in zip(cols, row):
            val = cell.get("value")
            # Turso returns everything as strings — cast integers and floats back
            cell_type = cell.get("type")
            if cell_type == "integer" and val is not None:
                val = int(val)
            elif cell_type == "float" and val is not None:
                val = float(val)
            elif cell_type == "null":
                val = None
            record[col] = val
        records.append(record)
    return records


def _single_execute(sql: str, args: list = None) -> list[dict]:
    """Convenience wrapper for executing a single SQL statement."""
    stmt = {"sql": sql, "args": [_to_turso_arg(a) for a in (args or [])]}
    results = _execute([stmt])
    return _rows_to_dicts(results[0]) if results else []


def _to_turso_arg(val) -> dict:
    """Convert a Python value to Turso's typed argument format."""
    if val is None:
        return {"type": "null"}
    if isinstance(val, bool):
        return {"type": "integer", "value": str(1 if val else 0)}
    if isinstance(val, int):
        return {"type": "integer", "value": str(val)}
    if isinstance(val, float):
        return {"type": "float", "value": str(val)}
    if isinstance(val, (dict, list)):
        return {"type": "text", "value": json.dumps(val)}
    return {"type": "text", "value": str(val)}


# ── Ping ───────────────────────────────────────────────────────────────

def ping() -> bool:
    """Return True if Turso is reachable."""
    try:
        _single_execute("SELECT customer_id FROM customers LIMIT 1")
        return True
    except Exception as e:
        logger.error("Turso unreachable: %s", e)
        return False


# ── Seeding — one-time import from existing CSVs ──────────────────────

def seed_from_csv(customers_path: str, behavior_path: str, batch_size: int = 100) -> dict:
    """
    Upload existing CSV data to Turso.
    Uses INSERT OR REPLACE to handle duplicates gracefully.
    """
    customers_upserted = 0
    behavior_upserted = 0

    # ── Customers
    if os.path.exists(customers_path):
        cdf = pd.read_csv(customers_path)
        records = cdf.to_dict(orient="records")
        cols = list(records[0].keys()) if records else []
        placeholders = ", ".join(["?" for _ in cols])
        safe_cols = ", ".join([f'"{c}"' for c in cols])
        sql = f'INSERT OR REPLACE INTO customers ({safe_cols}) VALUES ({placeholders})'

        for i in range(0, len(records), batch_size):
            batch = records[i: i + batch_size]
            statements = [
                {"sql": sql, "args": [_to_turso_arg(r[c]) for c in cols]}
                for r in batch
            ]
            _execute(statements)
            customers_upserted += len(batch)

        logger.info("Customers upserted: %s", customers_upserted)
    else:
        logger.warning("customers CSV not found: %s", customers_path)

    # ── Behavior
    if os.path.exists(behavior_path):
        bdf = pd.read_csv(behavior_path)
        if "year" not in bdf.columns:
            bdf["year"] = 2025
        records = bdf.to_dict(orient="records")
        cols = list(records[0].keys()) if records else []
        placeholders = ", ".join(["?" for _ in cols])
        safe_cols = ", ".join([f'"{c}"' for c in cols])
        sql = f'INSERT OR REPLACE INTO credit_behavior_monthly ({safe_cols}) VALUES ({placeholders})'

        for i in range(0, len(records), batch_size):
            batch = records[i: i + batch_size]
            statements = [
                {"sql": sql, "args": [_to_turso_arg(r[c]) for c in cols]}
                for r in batch
            ]
            _execute(statements)
            behavior_upserted += len(batch)

        logger.info("Behavior rows upserted: %s", behavior_upserted)
    else:
        logger.warning("behavior CSV not found: %s", behavior_path)

    return {"customers_upserted": customers_upserted, "behavior_upserted": behavior_upserted}


# ── CRUD — Customers ───────────────────────────────────────────────────

def add_customer(data: dict) -> dict:
    """
    Insert a new customer profile.
    Auto-stamps registered_at = now() if not provided.
    If customer_id is None / missing, Turso auto-generates it (AUTOINCREMENT).
    Returns the new record including the auto-generated customer_id.
    Raises ValueError if customer_id already exists.
    """
    # Duplicate check if customer_id explicitly provided
    if data.get("customer_id") is not None:
        existing = _single_execute(
            "SELECT customer_id FROM customers WHERE customer_id = ?",
            [data["customer_id"]]
        )
        if existing:
            raise ValueError(f"Customer {data['customer_id']} already exists.")
    else:
        data.pop("customer_id", None)

    if not data.get("registered_at"):
        data["registered_at"] = datetime.now(timezone.utc).isoformat()

    cols = list(data.keys())
    placeholders = ", ".join(["?" for _ in cols])
    safe_cols = ", ".join([f'"{c}"' for c in cols])
    insert_sql = f'INSERT INTO customers ({safe_cols}) VALUES ({placeholders})'
    args = [data[c] for c in cols]

    # Execute insert + get last inserted ID in one pipeline
    results = _execute([
        {"sql": insert_sql, "args": [_to_turso_arg(a) for a in args]},
        {"sql": "SELECT last_insert_rowid() AS customer_id", "args": []},
    ])

    new_id_rows = _rows_to_dicts(results[1]) if len(results) > 1 else []
    new_id = new_id_rows[0]["customer_id"] if new_id_rows else None
    data["customer_id"] = new_id

    logger.info("Added customer %s (registered_at=%s)", new_id, data["registered_at"])
    return data


def update_customer(customer_id: int, data: dict) -> dict:
    """Update an existing customer profile. Returns updated record."""
    if not data:
        return get_customer(customer_id) or {}

    set_clause = ", ".join([f'"{k}" = ?' for k in data.keys()])
    args = list(data.values()) + [customer_id]
    _single_execute(
        f'UPDATE customers SET {set_clause} WHERE customer_id = ?',
        args
    )
    return get_customer(customer_id) or {}


def _compute_account_age(record: dict) -> int:
    """
    Compute account_age_months dynamically from registered_at.
    Falls back to the stored account_age_months column if registered_at is missing.
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
            logger.warning("Could not parse registered_at '%s': %s", registered_at_str, e)
    return record.get("account_age_months", 0)


def get_customer(customer_id: int) -> Optional[dict]:
    """Return customer record dict with dynamically computed account_age_months."""
    rows = _single_execute(
        "SELECT * FROM customers WHERE customer_id = ?",
        [customer_id]
    )
    if not rows:
        return None
    record = rows[0]
    record["account_age_months"] = _compute_account_age(record)
    return record


def get_customer_profile(customer_id: int) -> Optional[dict]:
    """Alias for get_customer, mapping to the automated flow."""
    return get_customer(customer_id)


# ── CRUD — Monthly Behavior ────────────────────────────────────────────

def add_behavior_record(data: dict) -> dict:
    """
    Insert a monthly behavior record.
    Raises ValueError if a record for (customer_id, month, year) already exists.
    """
    existing = _single_execute(
        "SELECT id FROM credit_behavior_monthly WHERE customer_id=? AND month=? AND year=?",
        [data["customer_id"], data["month"], data["year"]]
    )
    if existing:
        raise ValueError(
            f"Behavior record for customer {data['customer_id']} "
            f"month {data['month']}/{data['year']} already exists."
        )

    cols = list(data.keys())
    placeholders = ", ".join(["?" for _ in cols])
    safe_cols = ", ".join([f'"{c}"' for c in cols])
    _single_execute(
        f'INSERT INTO credit_behavior_monthly ({safe_cols}) VALUES ({placeholders})',
        [data[c] for c in cols]
    )
    logger.info("Added behavior for customer %s (%s/%s)", data["customer_id"], data["month"], data["year"])
    return data


def get_customer_history(customer_id: int) -> list:
    """Return full behavioral history for a customer, sorted by year + month."""
    return _single_execute(
        "SELECT * FROM credit_behavior_monthly WHERE customer_id=? ORDER BY year ASC, month ASC",
        [customer_id]
    )


def get_raw_transaction_history(customer_id: int, months: int = 6) -> list:
    """Return raw transactions for a customer, sorted newest first."""
    return _single_execute(
        "SELECT * FROM raw_transactions WHERE customer_id=? ORDER BY created_at DESC",
        [customer_id]
    )


def add_raw_transaction(data: dict) -> dict:
    """
    Insert a single raw transaction record.
    Auto-stamps created_at = now() if not provided.
    Returns the inserted data dict.
    """
    if not data.get("created_at"):
        data["created_at"] = datetime.now(timezone.utc).isoformat()

    cols = list(data.keys())
    placeholders = ", ".join(["?" for _ in cols])
    safe_cols = ", ".join([f'"{c}"' for c in cols])
    _single_execute(
        f'INSERT INTO raw_transactions ({safe_cols}) VALUES ({placeholders})',
        [data[c] for c in cols]
    )
    logger.info(
        "Added raw transaction: customer=%s type=%s amount=%s",
        data.get("customer_id"), data.get("transaction_type"), data.get("amount")
    )
    return data


# ── Export — Turso → CSV (used by monthly retraining job) ─────────────

def export_to_csv(customers_path: str, behavior_path: str) -> dict:
    """
    Pull all data from Turso and write to CSV files.
    The snap pipeline and training scripts consume these CSVs.
    Uses LIMIT/OFFSET pagination matching Supabase's 1000-row page size.
    """
    PAGE = 1000

    # Customers
    all_customers = []
    offset = 0
    while True:
        chunk = _single_execute(
            "SELECT * FROM customers LIMIT ? OFFSET ?",
            [PAGE, offset]
        )
        all_customers.extend(chunk)
        if len(chunk) < PAGE:
            break
        offset += PAGE

    cdf = pd.DataFrame(all_customers)
    os.makedirs(os.path.dirname(customers_path), exist_ok=True)
    cdf.to_csv(customers_path, index=False)

    # Behavior
    all_behavior = []
    offset = 0
    while True:
        chunk = _single_execute(
            "SELECT * FROM credit_behavior_monthly ORDER BY customer_id, year, month LIMIT ? OFFSET ?",
            [PAGE, offset]
        )
        all_behavior.extend(chunk)
        if len(chunk) < PAGE:
            break
        offset += PAGE

    bdf = pd.DataFrame(all_behavior)
    bdf = bdf.drop(columns=["id", "recorded_at"], errors="ignore")
    os.makedirs(os.path.dirname(behavior_path), exist_ok=True)
    bdf.to_csv(behavior_path, index=False)

    logger.info(
        "Exported %s customers + %s behavior rows from Turso to CSV",
        len(cdf), len(bdf)
    )
    return {"n_customers": len(cdf), "n_behavior_rows": len(bdf)}


# ── Retraining Log ─────────────────────────────────────────────────────

def log_retraining(
    trigger: str,
    success: bool,
    cold_start_auc: Optional[float] = None,
    full_model_auc: Optional[float] = None,
    n_customers: Optional[int] = None,
    n_behavior_rows: Optional[int] = None,
    notes: Optional[str] = None,
) -> dict:
    """Write one row to the retraining_log table. Returns the inserted payload."""
    payload = {
        "trigger":         trigger,
        "success":         1 if success else 0,   # SQLite booleans are integers
        "cold_start_auc":  cold_start_auc,
        "full_model_auc":  full_model_auc,
        "n_customers":     n_customers,
        "n_behavior_rows": n_behavior_rows,
        "notes":           notes,
        "run_at":          datetime.now(timezone.utc).isoformat(),
    }
    cols = list(payload.keys())
    placeholders = ", ".join(["?" for _ in cols])
    safe_cols = ", ".join([f'"{c}"' for c in cols])
    _single_execute(
        f'INSERT INTO retraining_log ({safe_cols}) VALUES ({placeholders})',
        [payload[c] for c in cols]
    )
    return payload


def get_retraining_log(limit: int = 20) -> list:
    """Return the most recent retraining log entries."""
    return _single_execute(
        "SELECT * FROM retraining_log ORDER BY run_at DESC LIMIT ?",
        [limit]
    )
