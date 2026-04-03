"""
Seed Turso
One-time script to upload existing CSV data to Turso.
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.db.turso import seed_from_csv, ping

def main():
    customers_path = os.path.join(PROJECT_ROOT, "data", "customers.csv")
    behavior_path  = os.path.join(PROJECT_ROOT, "data", "credit_behavior_monthly.csv")

    print("Checking Turso connection...")
    if not ping():
        print("❌ Cannot reach Turso. Check your .env credentials.")
        return

    print("✅ Turso reachable. Starting seed...")
    result = seed_from_csv(customers_path, behavior_path)
    print(f"✅ Seed complete: {result}")

if __name__ == "__main__":
    main()


