"""
src.db — Database Layer (Turso / libSQL)
=========================================
Manages all persistence using Turso (hosted libSQL / SQLite).
Provides connection management, CRUD operations, and data import/export.

Functions:
    ping()                  — Check Turso connectivity
    add_customer()          — Insert a new customer profile
    get_customer()          — Fetch a customer by ID
    update_customer()       — Update customer fields
    add_behavior_record()   — Insert a monthly behavior record
    get_customer_history()  — Retrieve full behavioral history
    seed_from_csv()         — Bulk-import CSVs into Turso (one-time setup)
    export_to_csv()         — Export Turso tables -> local CSVs (for retraining)
    log_retraining()        — Write a retraining audit entry
    get_retraining_log()    — Fetch recent retraining audit entries

Credentials: set TURSO_URL and TURSO_AUTH_TOKEN in .env
"""

from src.db.turso import (
    ping,
    add_customer,
    get_customer,
    update_customer,
    add_behavior_record,
    get_customer_history,
    seed_from_csv,
    export_to_csv,
    log_retraining,
    get_retraining_log,
)

__all__ = [
    "ping",
    "add_customer",
    "get_customer",
    "update_customer",
    "add_behavior_record",
    "get_customer_history",
    "seed_from_csv",
    "export_to_csv",
    "log_retraining",
    "get_retraining_log",
]
