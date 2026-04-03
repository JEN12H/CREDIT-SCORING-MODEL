"""
Generate dummy raw transactions for all customers in the Turso database
and upload them directly into the raw_transactions table.
"""
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta

import pandas as pd
from src.db.turso import _single_execute, _to_turso_arg, _execute

def generate_transactions(num_months=12):
    # 1. Fetch all customers from the database
    print("Fetching customers from Turso...")
    customers = _single_execute(
        "SELECT customer_id, monthly_income, credit_limit FROM customers"
    )
    
    if not customers:
        print("No customers found in database. Exiting.")
        return

    today = datetime.now(timezone.utc)
    all_transactions = []
    
    print(f"Generating {num_months} months of transactions for {len(customers)} customers...")
    for cust in customers:
        cid = cust["customer_id"]
        income = cust["monthly_income"] or 50000
        
        # Start date: `num_months` ago
        start_date = today - relativedelta(months=num_months)
        
        outstanding = 0.0 # Running balance
        
        # We will loop month by month
        for i in range(num_months):
            current_month = start_date + relativedelta(months=i)
            
            # 90% chance of being active this month
            is_active = random.random() > 0.1 
            
            purchases_total = 0.0
            
            if is_active:
                n_purchases = random.randint(1, 10)
                for _ in range(n_purchases):
                    day_offset = random.randint(1, 28)
                    txn_date = current_month.replace(day=day_offset)
                    # Amount is relative to their income
                    amount = round(random.uniform(100, income * 0.3 / n_purchases), 2)
                    purchases_total += amount
                    
                    all_transactions.append({
                        "customer_id": cid,
                        "transaction_type": "Purchase",
                        "amount": float(amount),
                        "merchant": random.choice(["Amazon", "Flipkart", "Zomato", "Swiggy", "Uber", "Local Store"]),
                        "status": "Completed",
                        "created_at": txn_date.isoformat()
                    })
            
            outstanding += purchases_total
            
            # Repayment behavior (End of the month)
            if outstanding > 0:
                repay_date = current_month.replace(day=28) + timedelta(days=random.randint(0,10))
                
                pay_behavior = random.random()
                if pay_behavior > 0.4:
                    repay_amt = outstanding # Full payment
                elif pay_behavior > 0.1:
                    repay_amt = round(outstanding * random.uniform(0.3, 0.9), 2) # Partial
                else:
                    repay_amt = 0.0 # No payment / Missed Due Date
                    
                if repay_amt > 0:
                    all_transactions.append({
                        "customer_id": cid,
                        "transaction_type": "Repayment",
                        "amount": float(repay_amt),
                        "merchant": "User Bank",
                        "status": "Completed",
                        "created_at": repay_date.isoformat()
                    })
                    outstanding -= repay_amt
                    
                # If they paid very little or missed it entirely
                if repay_amt < outstanding * 0.1:
                    fee_date = repay_date + timedelta(days=5)
                    penalty = round(min(500.0, outstanding * 0.05), 2)
                    all_transactions.append({
                        "customer_id": cid,
                        "transaction_type": "Penalty",
                        "amount": float(penalty),
                        "merchant": "Late Fee",
                        "status": "Completed",
                        "created_at": fee_date.isoformat()
                    })
                    outstanding += penalty

    # 3. Batch insert into Turso
    batch_size = 50
    inserted = 0
    print(f"Total transactions to insert: {len(all_transactions)}")
    for i in range(0, len(all_transactions), batch_size):
        batch = all_transactions[i:i+batch_size]
        cols = list(batch[0].keys())
        placeholders = ", ".join(["?" for _ in cols])
        safe_cols = ", ".join([f'"{c}"' for c in cols])
        sql = f'INSERT INTO raw_transactions ({safe_cols}) VALUES ({placeholders})'
        statements = [
            {"sql": sql, "args": [_to_turso_arg(r[c]) for c in cols]}
            for r in batch
        ]
        _execute(statements)
        inserted += len(batch)
        print(f"  -> Inserted {inserted}/{len(all_transactions)} transactions...")

    print("Dummy transaction generation complete!")

if __name__ == "__main__":
    # Ensure dateutil is installed if ran standalone
    try:
        import dateutil
    except ImportError:
        print("Please install python-dateutil: pip install python-dateutil")
        exit(1)
    generate_transactions(6) # Generate 6 months of data
