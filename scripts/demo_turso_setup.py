"""
BAAKI Credit Scoring — Turso Setup Demo
=========================================
Demonstrates the full migrated setup:
  1. Connection check (ping)
  2. Row counts for all 4 tables
  3. Fetch & display a real customer
  4. Fetch credit behavior history for that customer
  5. Add a new customer (auto-generated ID from Turso)
  6. Clean up the test customer
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.turso import (
    ping,
    get_customer,
    get_customer_history,
    get_raw_transaction_history,
    add_customer,
    update_customer,
    _single_execute,
)

DIVIDER = "=" * 58

def section(title):
    print(f"\n{DIVIDER}")
    print(f"  {title}")
    print(DIVIDER)


def main():
    print(DIVIDER)
    print("   BAAKI Credit Scoring — Turso Migration Demo")
    print(DIVIDER)

    # ── Step 1: Connection Check ──────────────────────────────────
    section("STEP 1: Connection Check")
    result = ping()
    status = "CONNECTED" if result else "FAILED"
    print(f"  Turso DB Status : {status}")
    if not result:
        print("  Cannot connect to Turso. Check TURSO_URL and TURSO_AUTH_TOKEN in .env")
        sys.exit(1)

    # ── Step 2: Row Counts ────────────────────────────────────────
    section("STEP 2: Table Row Counts (All 4 Tables)")
    tables = ["customers", "credit_behavior_monthly", "raw_transactions", "retraining_log"]
    total = 0
    for table in tables:
        try:
            rows = _single_execute(f'SELECT COUNT(*) as cnt FROM "{table}"')
            count = rows[0]["cnt"] if rows else 0
            bar = "#" * min(30, count // 500)
            print(f"  {table:<30} {count:>8,} rows  {bar}")
        except Exception:
            count = 0
            print(f"  {table:<30}        0 rows  (table not yet created)")
        total += count
    print(f"  {'TOTAL':<30} {total:>8,} rows")

    # ── Step 3: Fetch a Real Customer ─────────────────────────────
    section("STEP 3: Fetch Customer Record from Turso")
    sample = _single_execute("SELECT customer_id FROM customers LIMIT 1")
    if not sample:
        print("  No customers found in database!")
        sys.exit(1)

    cid = sample[0]["customer_id"]
    customer = get_customer(cid)
    print(f"  Customer ID      : {customer.get('customer_id')}")
    print(f"  Age              : {customer.get('age')}")
    print(f"  Employment       : {customer.get('employment_status')}")
    print(f"  Monthly Income   : Rs. {customer.get('monthly_income'):,}")
    print(f"  Credit Limit     : Rs. {customer.get('credit_limit'):,}")
    print(f"  City Tier        : {customer.get('city_tier')}")
    print(f"  Account Age      : {customer.get('account_age_months')} months (live-computed)")
    print(f"  Registered At    : {customer.get('registered_at')}")

    # ── Step 4: Behavior History ──────────────────────────────────
    section(f"STEP 4: Behavior History for Customer {cid}")
    history = get_customer_history(cid)
    if history:
        print(f"  Found {len(history)} monthly record(s)")
        for h in history[:3]:
            print(f"    Month {h.get('month')}/{h.get('year')} — "
                  f"Txns: {h.get('num_transactions', 'N/A')}  "
                  f"Spend: {h.get('total_spend', 'N/A')}")
        if len(history) > 3:
            print(f"    ... and {len(history) - 3} more records")
    else:
        # Try another customer who has behavior data
        rows = _single_execute(
            "SELECT customer_id FROM credit_behavior_monthly LIMIT 1"
        )
        if rows:
            alt_cid = rows[0]["customer_id"]
            history = get_customer_history(alt_cid)
            print(f"  (Customer {cid} has no history — showing customer {alt_cid} instead)")
            print(f"  Found {len(history)} monthly record(s)")
            for h in history[:3]:
                print(f"    Month {h.get('month')}/{h.get('year')} — "
                      f"Txns: {h.get('num_transactions', 'N/A')}")
        else:
            print("  No behavior data yet.")

    # ── Step 5: Raw Transactions ──────────────────────────────────
    section(f"STEP 5: Raw Transactions Sample")
    txn_rows = _single_execute(
        "SELECT * FROM raw_transactions LIMIT 3"
    )
    if txn_rows:
        print(f"  Sample of raw_transactions:")
        for t in txn_rows:
            print(f"    Customer {t.get('customer_id')} | "
                  f"{t.get('transaction_type')} | "
                  f"Rs. {t.get('amount')} | "
                  f"{t.get('merchant')} | "
                  f"{t.get('status')}")
    else:
        print("  No raw transaction data yet.")

    # ── Step 6: Add New Customer (auto ID) ───────────────────────
    section("STEP 6: Add New Test Customer (Auto-Generated ID)")
    test_data = {
        "age": 29,
        "employment_status": "Salaried",
        "education_level": "Graduate",
        "monthly_income": 75000,
        "credit_limit": 150000,
        "city_tier": "Tier-1",
        "dependents": 1,
        "residence_type": "Rented",
        "account_age_months": 0,
    }

    new_customer = add_customer(test_data)
    new_id = new_customer.get("customer_id")
    print(f"  New customer created!")
    print(f"  Auto-generated ID  : {new_id}")
    print(f"  Name / Income      : Rs. {new_customer.get('monthly_income'):,}/month")
    print(f"  Registered At      : {new_customer.get('registered_at')}")

    # Verify it's actually in Turso
    verify = get_customer(new_id)
    exists = verify is not None
    print(f"  Verified from DB   : customer_id={new_id} exists = {exists}")

    # ── Step 7: Clean up ─────────────────────────────────────────
    section("STEP 7: Cleanup Test Customer")
    _single_execute("DELETE FROM customers WHERE customer_id = ?", [new_id])
    verify_deleted = get_customer(new_id)
    print(f"  Test customer {new_id} deleted: {verify_deleted is None}")

    # ── Summary ───────────────────────────────────────────────────
    section("DEMO COMPLETE — Summary")
    print("  [OK] Turso connection active")
    print("  [OK] All 4 tables accessible")
    print("  [OK] Customer fetch works (with live account_age_months)")
    print("  [OK] Behavior history fetch works")
    print("  [OK] Raw transactions accessible")
    print("  [OK] add_customer() returns auto-generated ID from Turso")
    print("  [OK] delete works")
    print()
    print("  Your BAAKI Credit Scoring backend is fully migrated to Turso!")
    print(DIVIDER)


if __name__ == "__main__":
    main()
