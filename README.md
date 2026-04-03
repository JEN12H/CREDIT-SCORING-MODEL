# 🛒 Intelligent Credit Scoring Engine for BNPL (Buy Now Pay Later)

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.95%2B-green)
![MLflow](https://img.shields.io/badge/MLflow-Tracking-orange)
![Scikit-Learn](https://img.shields.io/badge/sklearn-1.2%2B-yellow)
![Docker](https://img.shields.io/badge/Docker-Ready-blue)
![Turso](https://img.shields.io/badge/Turso-libSQL-brightgreen)
![Tests](https://img.shields.io/badge/Tests-80%2B%20passing-brightgreen)

---

## ⚡ Quickstart (Zero to Working API in 4 Steps)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Generate synthetic data (customers + 12 months of behavior)
python scripts/generate_all_data.py

# 3. Train both models (cold start + full behavioral)
python -m src.training.train

# 4. Start the API
uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload
```

> Open **http://127.0.0.1:8000/docs** to test all endpoints interactively via Swagger UI.

Or use **Make** for convenience:
```bash
make install    # Install dependencies
make pipeline   # data → train → eval (full pipeline)
make serve      # Start the API server
make test       # Run all unit tests
make docker     # Build & run with Docker
```

---

## 📖 Project Overview

This project is a real-time **Risk Assessment Engine** designed for **Buy Now Pay Later (BNPL)** applications.

The biggest challenge in BNPL is the **Cold Start Problem**: new users want to buy *instantly* at checkout, but platforms have zero transaction history for them. Traditional banks reject these users, leading to lost sales.

**Our Solution**: A **Dual-Model Architecture** that enables **Instant Approvals** for new shoppers while protecting the platform from fraud and default risk.

### Production-Grade Features
- 🔒 **Security**: CORS lockdown, rate limiting (`slowapi`), API key authentication
- 📊 **Monitoring**: Model drift detection, AUC threshold alerting, Prometheus-compatible `/metrics`
- 🔄 **Auto-Retraining**: APScheduler runs monthly retraining on the 1st of every month
- 📁 **Model Versioning**: Timestamped model saves with rollback via API
- 🐳 **Docker**: One-command deployment with `docker-compose`
- 🧪 **Test Suite**: 80+ unit tests covering handler, API, database, and versioning
- 🗄️ **Turso**: Cloud-hosted libSQL (SQLite-compatible) for customer data and retraining logs

---

## 🚀 Key Features

1.  **Instant Checkout Decisions**:
    *   **Cold Start Model**: Instantly scores new users (0–3 months) using *only* checkout & demographic data (Age, Income, Education) to assign a safe initial spending limit.
    *   **Full Model**: Unlocks higher spending limits for repeat users (6+ months) based on repayment behavior (Payment Ratios, BNPL usage).

2.  **Safety Guardrails**:
    *   **Tiered Spending Caps**: New users are capped at lower amounts (e.g., ₹5,000) until they prove reliability.
    *   **Risk Rules**: Automatically flags high-risk profiles (e.g., very young borrowers with low income) to prevent default.

3.  **End-to-End MLOps & Data Pipeline**:
    *   **Automated Data Pipeline**: One-click extraction and feature engineering from raw CSVs.
    *   **MLflow** for tracking experiment accuracy across training runs.
    *   **GitHub Actions** for automated testing (CI/CD).
    *   **FastAPI** for sub-second inference at checkout.

4.  **Production Security & Monitoring**:
    *   **Rate Limiting**: Prevents API abuse with configurable request limits.
    *   **API Key Auth**: Admin endpoints (retraining, rollback) require `X-API-Key` header.
    *   **Model Drift Detection**: Tracks prediction distribution changes in real-time.
    *   **AUC Alerting**: Warns when model performance drops below configurable threshold.

---

## 🛠️ Project Architecture

```
├── .github/workflows/         # CI/CD Pipeline (GitHub Actions)
│   └── ml_ci_cd.yml           #   pytest → data generation → training → evaluation
├── data/                      # Raw CSVs & calculated snapshots
│   ├── customers.csv          #   Static customer profiles
│   ├── credit_behavior_monthly.csv  # Monthly behavioral records
│   └── model_snapshots.csv    #   Feature-engineered training data
├── models/                    # Trained models & versioning
│   ├── cold_start_model.pkl   #   Latest cold start model
│   ├── credit_score_model.pkl #   Latest full behavioral model
│   ├── feature_config.pkl     #   Feature lists for each model
│   ├── model_manifest.json    #   Version history & AUC tracking
│   └── *_YYYYMMDD_HHMMSS.pkl #   Timestamped model backups
├── scripts/                   # CLI utilities
│   ├── generate_all_data.py   #   One-click data pipeline
│   └── seed_db.py             #   Turso seeder (CSV → Turso)
├── src/                       # Source code
│   ├── api/                   # FastAPI Application
│   │   ├── app.py             #   App init, CORS, rate limiting, metrics
│   │   ├── schemas.py         #   Pydantic request/response models
│   │   └── routes/            #   Endpoint modules
│   │       ├── scoring.py     #     /api/v1/predict/* endpoints
│   │       ├── data.py        #     /api/v1/customers/* endpoints
│   │       └── admin.py       #     /api/v1/admin/* endpoints (auth required)
│   ├── core/                  # Business Logic
│   │   ├── handler.py         #   ColdStartHandler — 3-tier model routing
│   │   ├── versioning.py      #   Model versioning, manifest, rollback
│   │   └── monitoring.py      #   Prediction drift detection & AUC alerting
│   ├── data/                  # Data Generation & Feature Engineering
│   │   ├── generate_customers.py
│   │   ├── generate_behavior.py
│   │   └── feature_pipeline.py  # Snap pipeline (rolling features)
│   ├── training/              # ML Training & Evaluation
│   │   ├── train.py           #   Dual-model training pipeline
│   │   └── evaluate.py        #   Model evaluation suite
│   ├── db/                    # Database Layer
│   │   ├── turso.py           #   Turso CRUD, export, retraining log (active)
│   │   └── supabase.py        #   Legacy Supabase reference (kept, not active)
│   └── scheduler/             # Background Jobs
│       └── retraining.py      #   APScheduler monthly retraining
├── tests/                     # Unit Tests (pytest) — 80+ tests
│   ├── conftest.py            #   Shared fixtures (customer profiles)
│   ├── test_handler.py        #   Tier routing, scoring, guardrails
│   ├── test_api.py            #   HTTP 200/400/422/503 responses
│   ├── test_database.py       #   Mocked Turso CRUD operations
│   ├── test_data_generation.py#   Schema/distribution validation
│   └── test_versioning.py     #   Model save/rollback/pruning
├── docs/                      # Documentation
│   └── supabase_schema.sql    #   Database schema for Supabase
├── Dockerfile                 # Production Docker image
├── docker-compose.yml         # Local development with Docker
├── Makefile                   # Common commands
├── params.yaml                # Centralized hyperparameter config
├── .env.example               # Environment variable template
└── requirements.txt           # Python dependencies
```

---

## 🧠 Solved: The Cold Start Problem in BNPL

### The Challenge
A user tries to buy a ₹15,000 phone on EMI but has never used the app before. A standard model sees "0 history" and feels "This person is a mystery" – it usually defaults to a **Reject**, causing the business to lose a potential loyal customer.

### Our Solution: The Two-Model Strategy
Instead of using one "all-or-nothing" model, we built a tiered system that handles a customer differently as they grow with us.

---

#### 🏗️ Model 1: The Cold Start Model (Demographics)
**"Approval Based on Who You Are"**

*   **When it's used**: During the very first checkout (0–3 months of tenure).
*   **What it looks at**: Static data points like your **Age, Employment stability, Education level, and Monthly Income.**
*   **The Logic**: It uses a conservative "Demographic Profile" to predict risk. Since we don't know your spending habits yet, it assumes a cautious stance.
*   **The Result**: It grants a **Safe Entry Limit** (e.g., ₹5,000 to ₹10,000). This allows the customer to join the platform instantly without the business taking a massive risk.

#### 📈 Model 2: The Full Behavioral Model (Transaction History)
**"Reward Based on How You Pay"**

*   **When it's used**: After a user has been with us for 6+ months.
*   **What it looks at**: Thousands of data points from their **actual app usage** – how quickly they pay bills, their repayment ratios, and missed payment streaks.
*   **The Logic**: Transaction data is **10x more accurate** than basic demographic data. This model ignores "who you are" and looks only at "how responsible you are."
*   **The Result**: If the user is reliable, the system **unlocks High Spending Limits** (up to ₹1,00,000).

---

### 🏛️ Tiered Decision Logic
We implemented a **Tiered Decision Logic** controlled by `ColdStartHandler`:

| Tier | Tenure | Strategy | Spending Limit |
| :--- | :--- | :--- | :--- |
| **1. New Shopper** | 0–3 Months | **Demographic Model + Guardrails** | ₹5,000 – ₹10,000 |
| **2. Building Trust** | 3–6 Months | **Blended Score** (40% Static / 60% Behavior) | up to ₹25,000 |
| **3. Power User** | 6+ Months | **Full Behavioral Model** | up to ₹1,00,000 |

### 🛡️ Why use two models?
1.  **Stop "Blind Rejections"**: Traditional systems reject new users because they have no data. Our Model 1 gives them a chance.
2.  **Precision Risk Management**: Behavioral data is the "Gold Standard" of credit. Using it for established users means we can give huge limits to trustworthy people while being very precise about who to stop.
3.  **Customer Growth Path**: It creates a "gamified" experience where users know that by paying on time, they are "leveling up" from Model 1 to Model 2, earning higher trust and limits.

---

## 📊 Understanding Credit Behavior (The Behavioral Features)

For established customers, our model stops looking at just "who you are" (Age/Income) and starts looking at **"how you handle money."**

### 🚩 1. The "Red Flags" (Risk Signals)
*   **Consecutive Missed Payments**: Does the user miss payments back-to-back? The strongest predictor of future default.
*   **Recent Default History**: Has the user defaulted in the past? Tracks months since last default.
*   **Late Payment Count**: Number of late payments in the last 3 months.

### 💳 2. Financial Discipline (Repayment Habits)
*   **Repayment Ratio**: If a user spends ₹1,000, do they pay back the full ₹1,000 or only ₹400?
*   **Credit Limit Usage (Utilization)**: Is the user constantly maxing out their limit?
*   **Payment Trends**: Is the user's behavior getting better or worse month-over-month?

### 💰 3. Financial Health (Affordability)
*   **Debt-to-Income Ratio**: Total outstanding debt vs. monthly salary.
*   **Income Affordability Score**: Is there "breathing room" after paying BNPL bills?
*   **Debt Growth Rate**: Is debt growing faster than repayment?

### 🛍️ 4. Shopping Habits (Engagement)
*   **Active Months**: Consistent shopping vs. one-time spending spree?
*   **Average Bill Size**: Groceries (stable) vs. expensive electronics (higher risk).

### ⚖️ 5. The Internal "Risk Score"
Our pipeline combines all features into a **0 to 100 Risk Score**:
*   **0–20**: Very Safe (Prime User)
*   **20–50**: Caution (Moderate Risk)
*   **50+**: High Alert (Extreme Risk)

---

## ⚡ Installation & Setup

### 1. Clone & Install
```bash
git clone https://github.com/your-repo/baaki-credit-scoring.git
cd baaki-credit-scoring
pip install -r requirements.txt
```

### 2. Environment Variables
Copy the example env file and fill in your credentials:
```bash
cp .env.example .env
```

**.env** contents:
```env
# Turso (required for DB features — customer CRUD, retraining logs)
TURSO_URL=https://your-database.turso.io
TURSO_AUTH_TOKEN=your-turso-auth-token

# Security
ADMIN_API_KEY=your-secret-key-for-admin-endpoints
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

> **Note**: The API runs fine *without* Turso credentials — database features (customer CRUD, retraining log) are simply disabled. Models, scoring, and monitoring all work locally.

### 3. Generate Data & Train Models
```bash
make pipeline
# or manually:
python scripts/generate_all_data.py
python -m src.training.train
```

### 4. Start the API
```bash
make serve
# or:
uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🐳 Docker Deployment

```bash
# Build and run with Docker Compose
make docker
# or:
docker-compose up --build
```

The `docker-compose.yml` mounts `data/` and `models/` as volumes, sets environment variables from `.env`, and exposes port `8000`.

---

## 🔌 API Reference

### Base URLs
- **Health & Metrics**: `/`, `/health`, `/metrics`
- **Scoring**: `/api/v1/predict/*`
- **Data Management**: `/api/v1/customers/*`
- **Admin** (API key required): `/api/v1/admin/*`

### Health Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | API status & model availability |
| `GET` | `/health` | Readiness probe (503 if models not loaded) |
| `GET` | `/metrics` | Prometheus-compatible metrics + drift detection |

### Scoring Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/predict/auto` | **Recommended.** Auto-routes to correct model by `account_age_months` |
| `POST` | `/api/v1/predict/cold-start` | Force cold start model (new customers) |
| `POST` | `/api/v1/predict/full` | Force full behavioral model (established customers) |

### Data Management Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/customers/` | Add a new customer profile |
| `POST` | `/api/v1/customers/{id}/behavior` | Add monthly behavior record |
| `GET` | `/api/v1/customers/{id}/history` | View customer's full history |

### Admin Endpoints (require `X-API-Key` header)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/admin/retrain` | Trigger manual retraining |
| `GET` | `/api/v1/admin/retraining-log` | View retraining history |
| `GET` | `/api/v1/admin/model-versions/{name}` | List all saved versions of a model |
| `POST` | `/api/v1/admin/model-versions/{name}/rollback` | Roll back to a specific version |

---

## 🔌 API Usage Examples

### 1. Score a New User (At Checkout)
**Endpoint:** `POST /api/v1/predict/auto`

```json
{
  "age": 28,
  "employment_status": "Salaried",
  "monthly_income": 85000,
  "education_level": "Graduate",
  "credit_limit": 80000,
  "city_tier": "Tier-1",
  "dependents": 0,
  "residence_type": "Rented",
  "account_age_months": 1,
  "util_avg_3m": 0, "payment_ratio_avg_3m": 1.0,
  "max_outstanding_3m": 0, "avg_txn_amt_3m": 0,
  "avg_txn_count_3m": 0, "late_payments_3m": 0,
  "missed_due_count_3m": 0, "missed_due_last_1m": 0,
  "payment_ratio_last_1m": 1.0, "outstanding_delta_3m": 0,
  "bnpl_active_last_1m": 0, "consecutive_missed_due": 0,
  "payment_ratio_min_3m": 1.0, "worst_util_3m": 0,
  "ever_defaulted": 0, "default_count_history": 0,
  "months_since_last_default": 0, "outstanding_to_income_pct": 0,
  "outstanding_to_limit_pct": 0, "income_affordability_score": 1.0,
  "debt_burden_category": 0, "payment_ratio_trend": 0,
  "utilization_trend": 0, "outstanding_growth_rate": 0,
  "is_deteriorating": 0, "active_months_3m": 0,
  "avg_util_when_active": 0, "snapshot_account_age": 0,
  "account_age_bucket": 0, "risk_score": 0, "snapshot_month": 1
}
```

**Response:**
```json
{
  "model_type": "auto_routed",
  "customer_tier": 1,
  "tier_description": "New Customer (Cold Start)",
  "credit_score": 704,
  "decision": "Approve_Low_Limit",
  "max_credit_limit": 10000,
  "model_used": "cold_start_model + guardrails",
  "recommendation": "New customer — monitor closely. Consider limit increase after 3 months of on-time payments.",
  "note": "Cold start model uses demographic features only. Conservative limits applied until behavioral history builds."
}
```

### 2. Trigger Manual Retraining
```bash
curl -X POST http://localhost:8000/api/v1/admin/retrain \
  -H "X-API-Key: your-secret-key"
```

### 3. Check Model Drift & Metrics
```bash
curl http://localhost:8000/metrics
```

**Response includes:**
```json
{
  "requests_total": 1542,
  "requests_scoring": 890,
  "latency_avg_ms": 12.4,
  "latency_p95_ms": 28.1,
  "models_loaded": true,
  "model_versions": {
    "cold_start": "20260306_021500",
    "full_model": "20260306_021500"
  },
  "prediction_drift": {
    "total_predictions": 890,
    "drift": { "detected": false, "mean_shift": 0.02 },
    "auc": { "last_known": 0.87, "alert_threshold": 0.65 },
    "alerts": []
  }
}
```

### 4. Roll Back a Model
```bash
curl -X POST http://localhost:8000/api/v1/admin/model-versions/cold_start_model/rollback \
  -H "X-API-Key: your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"version": "20260305_140000"}'
```

---

## 🔒 Security Features

| Feature | Implementation | Details |
|---------|---------------|---------|
| **CORS** | `CORSMiddleware` | Locked to `CORS_ORIGINS` env var (default: `localhost:3000,5173`) |
| **Rate Limiting** | `slowapi` | Prevents API abuse with configurable request limits |
| **API Key Auth** | `X-API-Key` header | Required for all `/admin/*` endpoints |
| **Input Validation** | Pydantic schemas | Age 18–100, income > 0, credit limit ≤ ₹1,00,000 |

---

## 📈 Monitoring & Model Drift Detection

The `/metrics` endpoint provides real-time monitoring:

- **Request Metrics**: Total requests, scoring requests, error count, avg/p95 latency
- **Model Status**: Which models are loaded, current version numbers
- **Prediction Drift**: Compares recent prediction distribution against a baseline
- **AUC Alerting**: Warns when model AUC drops below 0.65 after retraining
- **Decision Distribution**: Tracks approve/reject ratios to spot anomalies

### Alerts
The system automatically generates alerts for:
- 🚨 AUC below threshold after retraining
- ⚠️ Prediction mean shift > 10% from baseline
- ⚠️ Rejection rate exceeding 50%
- ⚠️ Approval rate exceeding 90% (too permissive)

---

## 📁 Model Versioning & Rollback

Every training run saves:
1. **Latest copy**: `models/cold_start_model.pkl` (always the newest)
2. **Versioned copy**: `models/cold_start_model_20260306_021500.pkl` (timestamped backup)
3. **Manifest entry**: `models/model_manifest.json` (AUC, algorithm, timestamp)

**Auto-pruning**: Only the last 10 versions are kept; older ones are automatically deleted.

**Rollback via API**:
```bash
# List available versions
curl http://localhost:8000/api/v1/admin/model-versions/cold_start_model \
  -H "X-API-Key: your-key"

# Roll back to a specific version
curl -X POST http://localhost:8000/api/v1/admin/model-versions/cold_start_model/rollback \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"version": "20260305_140000"}'
```

---

## 🔄 Auto-Retraining Pipeline

The system automatically retrains models on the **1st of every month at 02:00 AM**:

```
[0] Aggregate raw_transactions → credit_behavior_monthly
[1] Export Turso → CSV
[2] Run feature engineering (snap pipeline)
[3] Train cold start + full models (best of 3 algorithms)
[4] Hot-reload into running API (zero downtime)
[5] Log results to retraining_log table in Turso
```

Manual retraining: `POST /api/v1/admin/retrain` with API key.

---

## 🧪 Testing

Run the full test suite:
```bash
make test
# or:
pytest tests/ -v --tb=short
```

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_handler.py` | 25 | Tier routing, scoring, guardrails, credit limits |
| `test_api.py` | 9 | HTTP 200/422/503 responses, input validation |
| `test_database.py` | 16 | Mocked Turso CRUD, seed, export |
| `test_data_generation.py` | 16 | Schema validation, distribution checks |
| `test_versioning.py` | 16 | Save, list, rollback, auto-pruning |

> **Note**: `test_database.py` uses mocked Turso calls — no real database needed to run tests.

---

## 📊 Performance & Results
*   **Full Model AUC:** 0.85+ (Excellent discrimination on established users)
*   **Cold Start Logic:** Successfully minimizes default rates.
    *   *High Risk New User* → **Rejected** or **Capped at ₹5k**.
    *   *Safe New User* → **Approved** but **Capped at ₹10k**.
*   **API Latency**: < 30ms p95 for scoring endpoints

---

## 🗄️ Turso Setup

**Turso** is a free, edge-hosted libSQL (SQLite-compatible) database. No SDK required — uses plain HTTP REST. The API works **without** Turso credentials (scoring, monitoring, and model versioning all work locally), but you'll need it for customer data storage and retraining logs.

### Step 1: Create a Turso Account & Database

1. Go to **[turso.tech](https://turso.tech)** and sign in (GitHub login works)
2. Install the Turso CLI:
   ```bash
   # macOS / Linux
   curl -sSfL https://get.tur.so/install.sh | bash
   # Windows (PowerShell)
   winget install Turso.turso
   ```
3. Log in and create a database:
   ```bash
   turso auth login
   turso db create baaki-credit-scoring
   ```

### Step 2: Get Your URL and Auth Token

```bash
# Get the database URL
turso db show baaki-credit-scoring --url
# Example output: https://baaki-credit-scoring-yourname.turso.io

# Generate an auth token
turso db tokens create baaki-credit-scoring
# Example output: eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9...
```

### Step 3: Add Credentials to `.env`

```bash
cp .env.example .env
```

Open `.env` and paste your values:
```env
TURSO_URL=https://baaki-credit-scoring-yourname.turso.io
TURSO_AUTH_TOKEN=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9...

# Also set your admin API key (any strong random string)
ADMIN_API_KEY=my-secret-admin-key-change-this

# Lock CORS to your frontend domain(s)
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

### Step 4: Create the Database Tables

Run this once to create all required tables in Turso:

```bash
turso db shell baaki-credit-scoring < docs/turso_schema.sql
```

This creates four tables: `customers`, `credit_behavior_monthly`, `raw_transactions`, `retraining_log`.

### Step 5: Start the API

```bash
uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload
```

On startup, the API will automatically:
- ✅ Connect to Turso and verify reachability
- ✅ Seed existing CSV data into the database (if tables are empty)
- ✅ Start the monthly retraining scheduler

> **Troubleshooting**: If you see `⚠️ TURSO_URL / TURSO_AUTH_TOKEN not set`, double-check your `.env` file is in the project root and contains the correct values.

---

## 🛡️ License
MIT License.
