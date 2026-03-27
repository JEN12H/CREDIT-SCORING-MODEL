# BNPL Production Automation Plan

This document outlines the exact architectural changes required to transition this project from a "Sandbox" environment (where synthetic features are manually passed) to a **Fully Automated Production Environment** (where the frontend only passes a `customer_id` and the backend dynamically calculates real-time credit features from raw transactions).

---

## 🏗️ 1. Database: Create the Raw Transactions Ledger
Your first step is moving away from fabricated behavioral data. You need a raw ledger to track exactly what users are buying and repaying every day.

**In Supabase SQL Editor, run:**
```sql
CREATE TABLE raw_transactions (
    transaction_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id VARCHAR NOT NULL REFERENCES customers(customer_id),
    transaction_type VARCHAR NOT NULL CHECK (transaction_type IN ('Purchase', 'Repayment', 'Fee', 'Penalty')),
    amount NUMERIC(10, 2) NOT NULL,
    merchant VARCHAR,
    status VARCHAR NOT NULL DEFAULT 'Completed',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```
**Goal:** Your frontend/payment gateway simply `INSERT`s a row here every time a user makes a purchase or pays a BNPL bill.

---

## 🧹 2. API Schema: Decouple the Frontend
Right now, `FullModelInput` forces the frontend to do ML math. We need to replace it with a hyper-simple payload.

**File to modify:** `src/api/schemas.py`

**The Change:** 
Create a new request schema that only asks for an ID.
```python
from pydantic import BaseModel

class PredictionRequest(BaseModel):
    customer_id: str
```
**Goal:** The frontend UI now only has to write `fetch('/api/v1/predict/auto', { body: { customer_id: "CUST_123" } })`.

---

## 🗄️ 3. Database Functions: Fetching Real Data
The backend now needs to fetch the data that the frontend is no longer sending.

**File to modify:** `src/db/supabase.py`

**The Change:** 
Add helper functions to query Supabase directly for a specific customer in real-time.
*   `def get_customer_profile(customer_id: str) -> dict:` (Fetches Age, Income, Education from the `customers` table).
*   `def get_customer_history(customer_id: str, months: int = 6) -> list[dict]:` (Fetches their raw transactional or aggregated history for the window).

---

## ⚙️ 4. Feature Engineering: Real-Time Calculation
Currently, `run_snap_pipeline()` processes entire massive CSV files for model training. You need to extract its core logic so it can run instantly for a *single* user during an API request.

**File to modify:** `src/data/feature_pipeline.py`

**The Change:** 
Create a new function specifically for real-time inference:
```python
def calculate_single_user_features(profile_data: dict, history_data: list) -> dict:
    # 1. Calculate util_avg_3m
    # 2. Calculate payment_ratio_avg_3m
    # 3. Check for consecutive_missed_due
    # ... calculates all 40 ML features from the raw history ...
    return final_40_features_dictionary
```

---

## 🔗 5. Final Wiring: The Scoring Route
Finally, stitch the new workflow together in your main prediction endpoint. 

**File to modify:** `src/api/routes/scoring.py`

**The Change:** 
Update `predict_auto()` to execute the full automated chain.

```python
@router.post("/auto", response_model=ScoringResponse)
def predict_auto(request: PredictionRequest):
    # 1. Fetch data from DB
    profile = get_customer_profile(request.customer_id)
    history = get_customer_history(request.customer_id)
    
    # 2. Calculate ML features dynamically
    features = calculate_single_user_features(profile, history)
    
    # 3. Model Evaluation
    result = _handler.score_customer(features)
    
    # 4. Return Score
    return _build_response(result, model_type="auto_routed")
```

---

## 🎉 The Final State Overview
Once these 5 steps are completed, your system achieves True One-Click Automation:
1. **User Side:** Rahul clicks "Check Credit Limit" on the app.
2. **Frontend Request:** Sends exactly one thing: `{ "customer_id": "Rahul_99" }`.
3. **Backend Logic:** Supabase grabs Rahul's raw transactions ➡️ Python transforms them into the 40 ML features instantly ➡️ The AI model calculates the score.
4. **App Display:** Returns a 750 Credit Score to Rahul's screen in milliseconds.
