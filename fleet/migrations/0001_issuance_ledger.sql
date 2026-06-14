-- 0001_issuance_ledger.sql
-- License-issuance ledger (ADR 0009 §1) — the vendor-side source of truth.
-- One row per issued license / renewal. Metadata ONLY (ADR 0009 §5): no customer
-- business data, no PII.
--
-- There is no migration framework in this repo yet (no alembic). This is a plain
-- forward-only DDL file; a migration runner is a follow-up (see fleet/README.md).
-- Targets PostgreSQL. Apply with e.g.:
--     psql "$FLEET_DATABASE_URL" -f fleet/migrations/0001_issuance_ledger.sql

CREATE TABLE IF NOT EXISTS issuance_ledger (
    license_id            TEXT        PRIMARY KEY,
    customer_id           TEXT        NOT NULL,
    edition               TEXT        NOT NULL,
    -- Licensed module keys (e.g. ["erp","mes","commercial_tower"]).
    entitled_modules      JSONB       NOT NULL DEFAULT '[]'::jsonb,
    quota_tier            TEXT,
    issued_at             TIMESTAMPTZ NOT NULL,
    not_before            TIMESTAMPTZ NOT NULL,
    -- NULL expires_at = no expiry (perpetual).
    expires_at            TIMESTAMPTZ,
    -- Self-reference: set on the PRIOR row when a renewal supersedes it.
    -- A row with superseded_by IS NULL is the current/active issuance.
    superseded_by         TEXT        REFERENCES issuance_ledger (license_id),
    -- How the signed bundle was shipped (ADR 0007), e.g. 'offline-bundle'.
    delivery              TEXT,
    -- Populated by #374 (per-deployment telemetry credential). NULL at issuance.
    deployment_secret_id  TEXT
);

-- Roster / by-customer lookups filter on these.
CREATE INDEX IF NOT EXISTS idx_issuance_ledger_customer_id
    ON issuance_ledger (customer_id);

-- Expiry calendar / renewal alerts (ADR 0009 §4) scan current rows by expiry.
CREATE INDEX IF NOT EXISTS idx_issuance_ledger_expires_at
    ON issuance_ledger (expires_at);

-- "Current roster" = WHERE superseded_by IS NULL; index the active set.
CREATE INDEX IF NOT EXISTS idx_issuance_ledger_active
    ON issuance_ledger (superseded_by);
