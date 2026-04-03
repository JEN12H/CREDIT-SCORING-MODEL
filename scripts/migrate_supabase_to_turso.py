"""
Supabase → Turso Migration Script
----------------------------------
Uses Turso's native HTTP REST API instead of libsql-client (which has issues).
Reads credentials from .env file.
"""

import os
import json
import requests
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# ─────────────────────────────────────────────────────────────────
# CREDENTIALS (loaded from .env)
# ─────────────────────────────────────────────────────────────────
SUPABASE_URL    = os.environ.get("SUPABASE_URL")
SUPABASE_KEY    = os.environ.get("SUPABASE_KEY")
TURSO_URL       = os.environ.get("TURSO_URL")       # e.g. https://xxx.turso.io
TURSO_AUTH_TOKEN= os.environ.get("TURSO_AUTH_TOKEN")

# Update these with your exact Supabase table names
TABLES_TO_MIGRATE = [
    "raw_transactions",
    "credit_behavior_monthly",
]
BATCH_SIZE = 50  # rows per HTTP request (safe for Turso's payload limits)
# ─────────────────────────────────────────────────────────────────


def turso_execute(statements: list[dict]) -> dict:
    """
    Call Turso's HTTP API with a list of SQL statements.
    Each statement is a dict: {"q": "SQL...", "params": [...]}
    """
    url = f"{TURSO_URL}/v2/pipeline"
    headers = {
        "Authorization": f"Bearer {TURSO_AUTH_TOKEN}",
        "Content-Type": "application/json",
    }
    # Build the pipeline payload
    requests_payload = [
        {"type": "execute", "stmt": stmt} for stmt in statements
    ]
    requests_payload.append({"type": "close"})

    payload = {"requests": requests_payload}
    response = requests.post(url, headers=headers, json=payload, timeout=30)

    if response.status_code != 200:
        raise Exception(
            f"Turso HTTP {response.status_code}: {response.text[:500]}"
        )
    return response.json()


def detect_sql_type(val) -> str:
    """Map a Python value to its SQLite type."""
    if val is None:
        return "TEXT"
    if isinstance(val, bool):
        return "INTEGER"
    if isinstance(val, int):
        return "INTEGER"
    if isinstance(val, float):
        return "REAL"
    return "TEXT"


def to_sql_value(val):
    """
    Convert a Python value to Turso's HTTP API arg format.
    Turso's /v2/pipeline endpoint ONLY accepts {"type":"text","value":"..."}.
    SQLite handles casting to the column's declared type (INTEGER, REAL, etc.).
    """
    if val is None:
        return {"type": "null"}
    if isinstance(val, (dict, list)):
        return {"type": "text", "value": json.dumps(val)}
    return {"type": "text", "value": str(val)}


def create_table_sql(table_name: str, sample_row: dict) -> str:
    """Generate a CREATE TABLE IF NOT EXISTS statement from a sample row."""
    col_defs = []
    for col, val in sample_row.items():
        sql_type = detect_sql_type(val)
        col_defs.append(f'"{col}" {sql_type}')
    return f'CREATE TABLE IF NOT EXISTS "{table_name}" ({", ".join(col_defs)});'


def migrate_table(supabase: Client, table_name: str):
    print(f"\n[STARTING] Migrating table: {table_name}")
    start = 0
    total_migrated = 0

    while True:
        # 1. Fetch a batch from Supabase
        response = supabase.table(table_name).select("*").range(start, start + BATCH_SIZE - 1).execute()
        data = response.data

        if not data:
            print(f"[DONE] {table_name}: {total_migrated} rows migrated.")
            break

        columns = list(data[0].keys())

        # 2. Drop + recreate table to fix any schema mismatch from earlier failed runs
        if start == 0:
            drop_stmt = {"sql": f'DROP TABLE IF EXISTS "{table_name}"', "args": []}
            turso_execute([drop_stmt])
            create_stmt = {
                "sql": create_table_sql(table_name, data[0]),
                "args": []
            }
            turso_execute([create_stmt])
            print(f"  -> Table '{table_name}' dropped and recreated in Turso.")

        # 3. Build INSERT statements for this batch
        placeholders = ", ".join(["?" for _ in columns])
        safe_cols    = ", ".join([f'"{c}"' for c in columns])
        insert_sql   = f'INSERT OR IGNORE INTO "{table_name}" ({safe_cols}) VALUES ({placeholders})'

        statements = []
        for row in data:
            args = [to_sql_value(row[col]) for col in columns]
            statements.append({"sql": insert_sql, "args": args})

        # 4. Send the batch to Turso
        turso_execute(statements)
        total_migrated += len(data)
        print(f"  -> Pushed {total_migrated} rows...")

        start += BATCH_SIZE


def main():
    print("=" * 55)
    print("   BAAKI Credit Scoring - Supabase to Turso Migration")
    print("=" * 55)

    # Validate credentials
    missing = [k for k, v in {
        "SUPABASE_URL": SUPABASE_URL, "SUPABASE_KEY": SUPABASE_KEY,
        "TURSO_URL": TURSO_URL, "TURSO_AUTH_TOKEN": TURSO_AUTH_TOKEN
    }.items() if not v]
    if missing:
        raise ValueError(f"Missing credentials in .env: {missing}")

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print(f"Connected to Supabase: {SUPABASE_URL}")
    print(f"Target Turso DB:       {TURSO_URL}\n")

    for table in TABLES_TO_MIGRATE:
        try:
            migrate_table(supabase, table)
        except Exception as e:
            print(f"[ERROR] Failed migrating '{table}': {e}")

    print("\n[SUCCESS] Migration completed!")


if __name__ == "__main__":
    main()
