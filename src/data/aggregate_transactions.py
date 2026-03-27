"""
Aggregator script to compile raw_transactions into the standard monthly behavior format.
"""
import os
import pandas as pd
from datetime import datetime

from src.db.supabase import supabase

def aggregate_raw_to_monthly(output_path="data/credit_behavior_monthly.csv"):
    print("Fetching raw_transactions from Supabase...")
    
    # Supabase REST limits to 1000 rows. Let's do pagination.
    PAGE = 1000
    all_txns = []
    offset = 0
    while True:
        chunk = supabase.table("raw_transactions").select("*").range(offset, offset + PAGE - 1).execute()
        data = chunk.data or []
        all_txns.extend(data)
        if len(data) < PAGE:
            break
        offset += PAGE
        print(f"  Fetched {offset} rows so far...")
        
    if not all_txns:
        print("No raw transactions found.")
        return
        
    print(f"Total raw transactions retrieved: {len(all_txns)}")
    
    # Fetch customers limits for accurate utilization math
    print("Fetching customer profiles for accurate limit generation...")
    all_custs = supabase.table("customers").select("customer_id, credit_limit").execute().data or []
    limits = {c["customer_id"]: (c["credit_limit"] or 100000) for c in all_custs}

    print("Aggregating into monthly trends...")
    # Load into dataframe
    df = pd.DataFrame(all_txns)
    df["created_at"] = pd.to_datetime(df["created_at"])
    df["month"] = df["created_at"].dt.month
    df["year"] = df["created_at"].dt.year
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    
    # Process group by customer, year, month
    grouped = df.groupby(["customer_id", "year", "month"])
    
    monthly_records = []
    
    for (cid, year, month), group in grouped:
        purchases = group[group["transaction_type"] == "Purchase"]["amount"]
        repayments = group[group["transaction_type"] == "Repayment"]["amount"]
        penalties = group[group["transaction_type"] == "Penalty"]["amount"]
        
        purchases_sum = purchases.sum()
        repayments_sum = repayments.sum()
        penalties_sum = penalties.sum()
        num_txn = len(purchases)
        avg_txn = purchases.mean() if num_txn > 0 else 0
        
        late_payment = 1 if penalties_sum > 0 else 0
        missed_due = 1 if (len(repayments) == 0 and purchases_sum > 0) else 0
        default_event = 1 if missed_due and late_payment else 0
        
        payment_ratio = 1.0
        if purchases_sum > 0:
            payment_ratio = min(repayments_sum / purchases_sum, 1.0)
            
        # Simplified outstanding balance logic. 
        outstanding_balance = max(purchases_sum + penalties_sum - repayments_sum, 0)
        
        # Credit utilization
        limit = float(limits.get(cid, 100000.0))
        credit_utilization = min(outstanding_balance / limit, 1.0)
        
        monthly_records.append({
            "customer_id": cid,
            "month": int(month),
            "year": int(year),
            "credit_utilization": float(round(credit_utilization, 4)),
            "late_payment": int(late_payment),
            "payment_ratio": float(round(payment_ratio, 4)),
            "outstanding_balance": float(round(outstanding_balance, 2)),
            "default_event": int(default_event),
            "num_transactions": int(num_txn),
            "avg_transaction_amount": float(round(avg_txn, 2)),
            "missed_due_flag": int(missed_due)
        })
        
    out_df = pd.DataFrame(monthly_records)
    
    # Save CSV for training pipeline
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    out_df.to_csv(output_path, index=False)
    print(f"✅ Generated {len(out_df)} monthly behavior records and saved to {output_path}")

    # Step: Upsert back to credit_behavior_monthly table so the API can use it
    print("Upserting aggregated behaviors back into Supabase for real-time inference routing...")
    upsert_records = out_df.to_dict(orient="records")
    batch_size = 500
    for i in range(0, len(upsert_records), batch_size):
        batch = upsert_records[i:i+batch_size]
        try:
            supabase.table("credit_behavior_monthly").upsert(batch, on_conflict="customer_id,month,year").execute()
            print(f"  ➜ Upserted {i+len(batch)}/{len(upsert_records)} records...")
        except Exception as e:
            print(f"Upsert warning: {e}")

    print("✅ Complete!")
    
if __name__ == "__main__":
    aggregate_raw_to_monthly()
