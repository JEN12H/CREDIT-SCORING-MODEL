"""
Seed Supabase
One-time script to upload existing CSV data to Supabase.
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.db.supabase import seed_from_csv, ping

def main():
    customers_path = os.path.join(PROJECT_ROOT, "data", "customers.csv")
    behavior_path  = os.path.join(PROJECT_ROOT, "data", "credit_behavior_monthly.csv")

    print("Checking Supabase connection...")
    if not ping():
        print("❌ Cannot reach Supabase. Check your .env credentials.")
        return

    print(" Supabase reachable. Starting seed...")
    result = seed_from_csv(customers_path, behavior_path)
    print(f" Seed complete: {result}")

if __name__ == "__main__":
    main()


