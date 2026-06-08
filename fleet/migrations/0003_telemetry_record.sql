-- 0002_telemetry_record.sql
-- Telemetry intake store (ADR 0009 §3, issue #375) — the best-effort counterpart
-- of the issuance ledger. One row per reported telemetry snapshot.
--
-- Data boundary (ADR 0009 §5): metadata ONLY — no customer business data, no PII.
-- All three reachability tiers (realtime / periodic / offline-upload) land here;
-- the `source` column records how a record arrived.
--
-- Plain forward-only DDL (no migration framework yet — see fleet/README.md).
-- Targets PostgreSQL. Apply with e.g.:
--     psql "$FLEET_DATABASE_URL" -f fleet/migrations/0002_telemetry_record.sql

CREATE TABLE IF NOT EXISTS telemetry_record (
    id                    BIGSERIAL   PRIMARY KEY,
    -- Ties the snapshot to its ledger row (ADR 0009 §3).
    license_id            TEXT        NOT NULL REFERENCES issuance_ledger (license_id),
    -- The credential that authenticated this record (#374's per-deployment HMAC id).
    deployment_secret_id  TEXT,
    -- When the deployment says it was last active (its clock). Drives honest-silence.
    last_seen             TIMESTAMPTZ NOT NULL,
    -- When the console persisted this record (server clock).
    received_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- How this record reached us: 'realtime' | 'periodic' | 'offline-upload'.
    source                TEXT        NOT NULL DEFAULT 'realtime',
    -- Edition actually active (vs. entitled).
    active_edition        TEXT,
    -- Module keys reported as actively used.
    active_modules        JSONB       NOT NULL DEFAULT '[]'::jsonb,
    -- Per-module usage counters, e.g. {"erp": 1200}.
    module_usage          JSONB       NOT NULL DEFAULT '{}'::jsonb,
    -- Showback rollup totals (ADR 0008 §3), e.g. {"requests": 50000}.
    showback_totals       JSONB       NOT NULL DEFAULT '{}'::jsonb,
    -- ADR 0008 §3 over-license flag.
    over_license          BOOLEAN     NOT NULL DEFAULT FALSE
);

-- Per-license history + "latest snapshot" / honest-silence lookups (ADR 0009 §4).
CREATE INDEX IF NOT EXISTS idx_telemetry_record_license_last_seen
    ON telemetry_record (license_id, last_seen DESC);

-- Audit / silence-per-deployment by credential.
CREATE INDEX IF NOT EXISTS idx_telemetry_record_secret_id
    ON telemetry_record (deployment_secret_id);
