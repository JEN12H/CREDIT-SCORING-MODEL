-- ============================================================
-- BAAKI Credit Scoring — Supabase Schema
-- ============================================================
-- Run this SQL ONCE in your Supabase project:
--   supabase.com → Your Project → SQL Editor → Paste & Run
-- ============================================================


-- 1. CUSTOMERS
--    One row per customer. customer_id is auto-generated.
--    The DB assigns 1, 2, 3… automatically on INSERT.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
    customer_id        BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    age                INTEGER     NOT NULL,
    employment_status  TEXT        NOT NULL,
    education_level    TEXT        NOT NULL,
    monthly_income     INTEGER     NOT NULL,
    credit_limit       INTEGER     NOT NULL,
    city_tier          TEXT        NOT NULL,
    dependents         INTEGER     NOT NULL DEFAULT 0,
    residence_type     TEXT        NOT NULL,
    account_age_months INTEGER     NOT NULL DEFAULT 0,  -- legacy fallback; prefer registered_at
    registered_at      TIMESTAMPTZ NOT NULL DEFAULT now(), -- used to compute age dynamically
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ⚠️ If the table already exists with BIGINT, run this to convert:
-- ALTER TABLE customers ALTER COLUMN customer_id ADD GENERATED ALWAYS AS IDENTITY;

-- If the table already exists, add the column with:
-- ALTER TABLE customers ADD COLUMN IF NOT EXISTS registered_at TIMESTAMPTZ NOT NULL DEFAULT now();



-- 2. CREDIT BEHAVIOR MONTHLY
--    One row per customer per calendar month.
--    Unique constraint prevents duplicate entries.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS credit_behavior_monthly (
    id                     BIGSERIAL   PRIMARY KEY,
    customer_id            BIGINT      NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    month                  INTEGER     NOT NULL CHECK (month BETWEEN 1 AND 12),
    year                   INTEGER     NOT NULL,
    credit_utilization     FLOAT       NOT NULL DEFAULT 0,
    late_payment           INTEGER     NOT NULL DEFAULT 0,
    payment_ratio          FLOAT       NOT NULL DEFAULT 1.0,
    outstanding_balance    FLOAT       NOT NULL DEFAULT 0,
    default_event          INTEGER     NOT NULL DEFAULT 0,
    num_transactions       INTEGER     NOT NULL DEFAULT 0,
    avg_transaction_amount FLOAT       NOT NULL DEFAULT 0,
    missed_due_flag        INTEGER     NOT NULL DEFAULT 0,
    recorded_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (customer_id, month, year)
);

-- Index to speed up customer history lookups
CREATE INDEX IF NOT EXISTS idx_behavior_customer ON credit_behavior_monthly(customer_id);


-- 3. RETRAINING LOG
--    Audit trail — every model retraining run is recorded here.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS retraining_log (
    id               BIGSERIAL   PRIMARY KEY,
    run_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    trigger          TEXT        NOT NULL,   -- 'scheduled' or 'manual'
    cold_start_auc   FLOAT,
    full_model_auc   FLOAT,
    n_customers      INTEGER,
    n_behavior_rows  INTEGER,
    success          BOOLEAN     NOT NULL DEFAULT FALSE,
    notes            TEXT
);
