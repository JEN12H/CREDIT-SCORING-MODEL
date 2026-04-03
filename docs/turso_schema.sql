-- ============================================================
-- BAAKI Credit Scoring — Turso (SQLite) Schema
-- ============================================================
-- Run this SQL in your Turso project using the CLI:
--   turso db shell baaki-credit-scoring < docs/turso_schema.sql
-- ============================================================

-- 1. CUSTOMERS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
    customer_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    age                INTEGER     NOT NULL,
    employment_status  TEXT        NOT NULL,
    education_level    TEXT        NOT NULL,
    monthly_income     INTEGER     NOT NULL,
    credit_limit       INTEGER     NOT NULL,
    city_tier          TEXT        NOT NULL,
    dependents         INTEGER     NOT NULL DEFAULT 0,
    residence_type     TEXT        NOT NULL,
    account_age_months INTEGER     NOT NULL DEFAULT 0,
    registered_at      TEXT        NOT NULL, -- ISO-8601 string
    created_at         TEXT        NOT NULL DEFAULT current_timestamp
);

-- 2. CREDIT BEHAVIOR MONTHLY
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS credit_behavior_monthly (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id            INTEGER     NOT NULL,
    month                  INTEGER     NOT NULL CHECK (month BETWEEN 1 AND 12),
    year                   INTEGER     NOT NULL,
    credit_utilization     REAL        NOT NULL DEFAULT 0,
    late_payment           INTEGER     NOT NULL DEFAULT 0,
    payment_ratio          REAL        NOT NULL DEFAULT 1.0,
    outstanding_balance    REAL        NOT NULL DEFAULT 0,
    default_event          INTEGER     NOT NULL DEFAULT 0,
    num_transactions       INTEGER     NOT NULL DEFAULT 0,
    avg_transaction_amount REAL        NOT NULL DEFAULT 0,
    missed_due_flag        INTEGER     NOT NULL DEFAULT 0,
    recorded_at            TEXT        NOT NULL DEFAULT current_timestamp,
    UNIQUE (customer_id, month, year),
    FOREIGN KEY(customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_behavior_customer ON credit_behavior_monthly(customer_id);

-- 3. RAW TRANSACTIONS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw_transactions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id      INTEGER NOT NULL,
    amount           REAL    NOT NULL,
    transaction_type TEXT    NOT NULL,  -- Purchase, Repayment, Penalty
    created_at       TEXT    NOT NULL DEFAULT current_timestamp,
    FOREIGN KEY(customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_transactions_customer ON raw_transactions(customer_id DESC, created_at DESC);

-- 4. RETRAINING LOG
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS retraining_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at           TEXT        NOT NULL DEFAULT current_timestamp,
    trigger          TEXT        NOT NULL,   -- 'scheduled' or 'manual'
    cold_start_auc   REAL,
    full_model_auc   REAL,
    n_customers      INTEGER,
    n_behavior_rows  INTEGER,
    success          INTEGER     NOT NULL DEFAULT 0,  -- 0 = false, 1 = true
    notes            TEXT
);
