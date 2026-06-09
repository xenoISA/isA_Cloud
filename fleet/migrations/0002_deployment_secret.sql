-- 0002_deployment_secret.sql
-- Per-deployment telemetry HMAC secret (ADR 0009 §3, issue #374).
--
-- SENSITIVE TABLE. This is the *verification keyset* for telemetry intake (#375).
-- HMAC is symmetric, so the secret value itself must be retained vendor-side (a
-- one-way hash cannot recompute an HMAC). It is deliberately kept in a SEPARATE
-- table from issuance_ledger so that:
--   * the broad, frequently-read fleet roster query never loads secret bytes, and
--   * this table can be granted/encrypted/audited independently of the metadata
--     ledger. Apply DB-level at-rest protection (column encryption / restricted
--     GRANTs) the same way other vendor secrets are protected.
--
-- Blast radius: a leaked deployment secret only forges THAT customer's telemetry
-- (metadata-only, ADR 0009 §5), never a license — licenses are signed with the
-- offline ed25519 private key, which never enters this system.
--
-- Forward-only DDL (no migration framework yet — see fleet/README.md). Apply with:
--     psql "$FLEET_DATABASE_URL" -f fleet/migrations/0002_deployment_secret.sql

CREATE TABLE IF NOT EXISTS deployment_secret (
    -- Stable, NON-secret pointer; matches issuance_ledger.deployment_secret_id.
    deployment_secret_id  TEXT  PRIMARY KEY,
    -- The HMAC-SHA256 key (secrets.token_urlsafe(32)). SENSITIVE.
    secret                TEXT  NOT NULL,
    -- Which customer this secret authenticates (revocation / audit).
    customer_id           TEXT  NOT NULL,
    -- Informational link to the ledger lineage row. Intentionally NOT a FK so a
    -- renewed/rotated license_id cannot orphan a still-valid secret mid-rotation.
    license_id            TEXT
);

-- Revoke-by-customer / audit lookups.
CREATE INDEX IF NOT EXISTS idx_deployment_secret_customer_id
    ON deployment_secret (customer_id);
