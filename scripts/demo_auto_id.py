"""
Demo: Complete Customer Flow (Auto-ID + Cold-Start Scoring)
============================================================
1. Frontend signs up a customer (NO customer_id sent)
2. Backend auto-generates an ID and returns it
3. Frontend uses that ID to request a credit score
4. Backend uses cold-start model for new customers automatically
"""
import requests
import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = "http://127.0.0.1:8000/api/v1"

print("=" * 60)
print("  FULL DEMO: Signup -> Auto ID -> Credit Score")
print("=" * 60)

# Step 1: Create a new customer (NO customer_id!)
print("\n--- STEP 1: Frontend signs up a new customer ---")
print("   Sending: age, income, employment... (NO customer_id)")
r1 = requests.post(f"{BASE}/customers/", json={
    "age": 26,
    "employment_status": "Salaried",
    "education_level": "Graduate",
    "monthly_income": 55000,
    "city_tier": "Tier-1",
    "dependents": 0,
    "residence_type": "Rented",
})
data1 = r1.json()
print(f"   Response Status: {r1.status_code}")
print(f"   Auto-Generated Customer ID: {data1.get('customer_id')}")
print(f"   Credit Limit Assigned: Rs.{data1.get('credit_limit_assigned', 'N/A')}")

cust_id = data1.get("customer_id")

# Step 2: Frontend saves the ID and requests credit score
if cust_id:
    print(f"\n--- STEP 2: Frontend requests credit score for customer {cust_id} ---")
    print(f"   Sending: {{ customer_id: {cust_id} }}")
    r2 = requests.post(f"{BASE}/predict/auto", json={"customer_id": cust_id})
    score_data = r2.json()
    print(f"   Response Status: {r2.status_code}")
    
    if r2.status_code == 200:
        print(f"\n   --- CREDIT SCORE RESULT ---")
        print(f"   Credit Score:      {score_data.get('credit_score')}")
        print(f"   Decision:          {score_data.get('decision')}")
        print(f"   Max Credit Limit:  Rs.{score_data.get('max_credit_limit', 0)}")
        print(f"   Model Used:        {score_data.get('model_used')}")
        print(f"   Risk Warnings:     {score_data.get('risk_warnings', [])}")
        print(f"   Recommendation:    {score_data.get('recommendation', 'N/A')}")
        print(f"   Note:              {score_data.get('note', 'N/A')}")
    else:
        print(f"   Error: {score_data.get('detail', score_data)}")

print("\n" + "=" * 60)
print("  DEMO COMPLETE")
print("=" * 60)
print("\n  Summary:")
print(f"  1. Customer signed up WITHOUT providing an ID")
print(f"  2. Backend auto-generated ID: {cust_id}")
print(f"  3. Credit score calculated using cold-start model")
print(f"     (because new customer has 0 months of transaction history)")
