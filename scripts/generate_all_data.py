"""
Generate All Data
Convenience script to run the full data generation pipeline:
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.data.generate_customers import generate_customers
from src.data.generate_behavior import generate_monthly_behavior
from src.data.feature_pipeline import run_snap_pipeline


def main():
    customers_path = os.path.join(PROJECT_ROOT, "data", "customers.csv")
    behavior_path  = os.path.join(PROJECT_ROOT, "data", "credit_behavior_monthly.csv")
    snapshots_path = os.path.join(PROJECT_ROOT, "data", "model_snapshots.csv")

    print("=" * 60)
    print("BAAKI — Full Data Generation Pipeline")
    print("=" * 60)

    print("\n Generating customer profiles...")
    generate_customers(output_path=customers_path)

    print("\n Generating monthly behavioral data...")
    generate_monthly_behavior(customers_path=customers_path, output_path=behavior_path)

    print("\n Running feature engineering pipeline...")
    run_snap_pipeline(customers_path, behavior_path, snapshots_path)

    print("\n" + "=" * 60)
    print("✅ All data generated successfully!")
    print(f"   {customers_path}")
    print(f"   {behavior_path}")
    print(f"   {snapshots_path}")
    print("=" * 60)

