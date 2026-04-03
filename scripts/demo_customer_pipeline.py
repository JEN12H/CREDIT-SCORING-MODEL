import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient
from src.api.app import app
from src.db.turso import add_raw_transaction, _single_execute
from src.data.aggregate_transactions import aggregate_raw_to_monthly

def run_demo():
    print("🚀 Starting End-to-End Customer Pipeline Demo\n")
    
    with TestClient(app) as client:
        customer_id = 99999
        
        # 0. Clean up any previous test runs for this ID
        print(f"🧹 Cleaning up any old data for Customer ID: {customer_id}...")
        _single_execute("DELETE FROM raw_transactions WHERE customer_id = ?", [customer_id])
        _single_execute("DELETE FROM credit_behavior_monthly WHERE customer_id = ?", [customer_id])
        _single_execute("DELETE FROM customers WHERE customer_id = ?", [customer_id])
        
        # 1. Create Customer via API
        print(f"\n👤 PHASE 1: Frontend User Onboarding")
        customer_payload = {
            "customer_id": customer_id,
            "age": 28,
            "employment_status": "Salaried",
            "education_level": "Bachelors",
            "monthly_income": 85000,
            "city_tier": "Tier 1",
            "residence_type": "Rented",
            "dependents": 0
        }
        
        response = client.post("/api/v1/customers/", json=customer_payload)
        if response.status_code != 201:
            print(f"❌ Failed to create customer: {response.text}")
            return
            
        print(f"✅ Customer Profile Created in Turso")
        print(f"✅ Auto-Assigned Credit Limit: ₹{response.json().get('credit_limit_assigned')}\n")
        
        # 2. Add Raw Transactions — multiple small transactions per month (real-world scenario!)
        print("💳 PHASE 2: Customer Makes Individual Daily Transactions")
        print("   (Just like a real customer buying groceries, paying bills, etc.)\n")
        txns = [
            # --- JANUARY: 4 small purchases, then a repayment ---
            {"customer_id": customer_id, "amount": 150.0,  "transaction_type": "Purchase",  "created_at": "2026-01-03T10:00:00Z"},  # groceries
            {"customer_id": customer_id, "amount": 500.0,  "transaction_type": "Purchase",  "created_at": "2026-01-10T14:00:00Z"},  # electricity bill
            {"customer_id": customer_id, "amount": 200.0,  "transaction_type": "Purchase",  "created_at": "2026-01-18T11:00:00Z"},  # fuel
            {"customer_id": customer_id, "amount": 350.0,  "transaction_type": "Purchase",  "created_at": "2026-01-25T09:00:00Z"},  # shopping
            {"customer_id": customer_id, "amount": 1200.0, "transaction_type": "Repayment", "created_at": "2026-01-28T17:00:00Z"},  # paid back in full!
            
            # --- FEBRUARY: 3 purchases, partial repayment ---
            {"customer_id": customer_id, "amount": 800.0,  "transaction_type": "Purchase",  "created_at": "2026-02-05T10:00:00Z"},  # rent top-up
            {"customer_id": customer_id, "amount": 250.0,  "transaction_type": "Purchase",  "created_at": "2026-02-14T19:00:00Z"},  # dining
            {"customer_id": customer_id, "amount": 100.0,  "transaction_type": "Purchase",  "created_at": "2026-02-20T12:00:00Z"},  # coffee & snacks
            {"customer_id": customer_id, "amount": 900.0,  "transaction_type": "Repayment", "created_at": "2026-02-27T10:00:00Z"},  # partial repayment
            
            # --- MARCH: 2 purchases, full repayment (best behavior!) ---
            {"customer_id": customer_id, "amount": 300.0,  "transaction_type": "Purchase",  "created_at": "2026-03-08T10:00:00Z"},  # groceries
            {"customer_id": customer_id, "amount": 450.0,  "transaction_type": "Purchase",  "created_at": "2026-03-15T15:00:00Z"},  # clothes
            {"customer_id": customer_id, "amount": 750.0,  "transaction_type": "Repayment", "created_at": "2026-03-29T10:00:00Z"},  # full repayment
            
            # --- APRIL: 3 purchases, 1 repayment ---
            {"customer_id": customer_id, "amount": 600.0,  "transaction_type": "Purchase",  "created_at": "2026-04-02T10:00:00Z"},  # electronics
            {"customer_id": customer_id, "amount": 120.0,  "transaction_type": "Purchase",  "created_at": "2026-04-10T11:00:00Z"},  # snacks
            {"customer_id": customer_id, "amount": 80.0,   "transaction_type": "Purchase",  "created_at": "2026-04-18T13:00:00Z"},  # coffee
            {"customer_id": customer_id, "amount": 800.0,  "transaction_type": "Repayment", "created_at": "2026-04-25T10:00:00Z"},  # repayment
        ]
        
        for txn in txns:
            add_raw_transaction(txn)
        print(f"   ✅ {len(txns)} individual raw transactions logged across 4 months!")
        print("   📅 Jan: 4 purchases + 1 repayment")
        print("   📅 Feb: 3 purchases + 1 partial repayment")
        print("   📅 Mar: 2 purchases + 1 full repayment")
        print("   📅 Apr: 3 purchases + 1 repayment\n")
        
        # 3. Run Aggregator
        print("⚙️  PHASE 3: Aggregator Script Converts Raw Transactions → Monthly Data Points")
        aggregate_raw_to_monthly()
        
        # Fetch and show what the aggregated data looks like for this customer
        agg = _single_execute(
            "SELECT month, year, num_transactions, avg_transaction_amount, outstanding_balance, "
            "credit_utilization, payment_ratio, missed_due_flag "
            "FROM credit_behavior_monthly WHERE customer_id = ? ORDER BY year, month",
            [customer_id]
        )

        print("\n   📊 Aggregated Monthly Data (what the ML model actually sees):")
        print(f"   {'Month':<10} {'# Txns':<10} {'Avg Amt':>10} {'Outstanding':>14} {'Utilization':>14} {'Pay Ratio':>11} {'Missed Due':>12}")
        print("   " + "-"*76)
        for row in agg:
            month_name = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][row['month']]
            print(f"   {month_name+' '+str(row['year']):<10} {row['num_transactions']:<10} {row['avg_transaction_amount']:>10.2f} {row['outstanding_balance']:>14.2f} {row['credit_utilization']:>14.4f} {row['payment_ratio']:>11.4f} {row['missed_due_flag']:>12}")
        print(f"\n   ✅ {len(txns)} raw transactions → {len(agg)} aggregated monthly rows!\n")
        
        # 4. Get Score
        print("🎯 PHASE 4: Frontend Requests Real-Time Credit Score")
        score_payload = {"customer_id": customer_id}
        score_response = client.post("/api/v1/predict/auto", json=score_payload)
        
        if score_response.status_code != 200:
            print(f"❌ Failed to get score: {score_response.text}")
            return
            
        res = score_response.json()
        print("\n==================================================")
        print("🏆 FINAL CREDIT SCORE RESULT")
        print("==================================================")
        print(f"Customer Tier:     Tier {res.get('customer_tier')} ({res.get('tier_description')})")
        print(f"Credit Score:      {res.get('credit_score')}")
        print(f"Default Prob:      {res.get('default_probability')}")
        print(f"Decision:          {res.get('decision')}")
        print(f"Recommended Limit: ₹{res.get('max_credit_limit')}")
        print(f"Active Model:      {res.get('model_used')}")
        print("==================================================\n")
        print("🎉 Demo completed successfully!")

if __name__ == "__main__":
    run_demo()
