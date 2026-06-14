-- 0004_issuance_revocation.sql
-- Revocation marker on the issuance ledger (ADR 0009 §4 "revoke" action, #377).
--
-- ADR 0009 scopes ONLINE revocation / CRL distribution as a FUTURE extension: an
-- offline-signed license.json cannot be remotely killed once it has shipped to an
-- air-gapped deployment. So at this layer "revoke" is a vendor-side LEDGER FLAG that
-- records isA has revoked the entitlement (contract terminated, key compromise, …).
-- A revoked row is retained for audit but drops out of the active fleet roster /
-- showback, exactly like a superseded row. NULL revoked_at == not revoked.
--
-- Forward-only DDL (no migration framework yet — see fleet/README.md). Targets
-- PostgreSQL. Apply with e.g.:
--     psql "$FLEET_DATABASE_URL" -f fleet/migrations/0004_issuance_revocation.sql

ALTER TABLE issuance_ledger
    ADD COLUMN IF NOT EXISTS revoked_at     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS revoked_reason TEXT;

-- The active fleet roster filters out revoked rows alongside superseded ones.
CREATE INDEX IF NOT EXISTS idx_issuance_ledger_revoked_at
    ON issuance_ledger (revoked_at);
