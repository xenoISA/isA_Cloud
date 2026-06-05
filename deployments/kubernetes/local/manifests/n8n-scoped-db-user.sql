-- Scoped n8n Postgres user.
-- Run once after the `n8n` DB exists, then rotate the K8s secret
-- `n8n-db-credentials` to use this user instead of the shared `postgres`
-- superuser.
--
-- Usage:
--   kubectl exec -n isa-cloud-local postgresql-0 -c postgresql -- bash -c '
--     PGPASSWORD="$(cat $POSTGRES_PASSWORD_FILE)" psql -U postgres \
--       -v pwd="$(openssl rand -hex 24)" -f /tmp/scoped.sql
--   '
-- (then capture the password and patch the secret out-of-band — never inline).

-- Idempotent role creation. The password is set by the top-level ALTER ROLE
-- below — psql ':var' interpolation is NOT performed inside a DO $$ $$ block,
-- so the password cannot be passed in here.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'n8n') THEN
    CREATE ROLE n8n WITH LOGIN;
  END IF;
END $$;

-- Set/refresh the role password. Top-level statement, so :'pwd' interpolates.
-- Idempotent — every run re-syncs the role password to the value passed via
-- `psql -v pwd=...`, keeping it in step with the n8n-db-credentials secret.
ALTER ROLE n8n WITH LOGIN PASSWORD :'pwd';

-- Lock the database down to the scoped role + reset previous public grants
REVOKE ALL ON DATABASE n8n FROM PUBLIC;
GRANT CONNECT ON DATABASE n8n TO n8n;
GRANT CREATE, USAGE ON SCHEMA public TO n8n;
ALTER SCHEMA public OWNER TO n8n;

-- Reparent existing tables + sequences to the new owner.  Generated DDL is
-- printed via gset/\gexec so the script runs idempotently as the schema grows.
SELECT 'ALTER TABLE ' || quote_ident(schemaname) || '.' || quote_ident(tablename) || ' OWNER TO n8n;'
FROM pg_tables WHERE schemaname = 'public' \gexec

SELECT 'ALTER SEQUENCE ' || quote_ident(sequence_schema) || '.' || quote_ident(sequence_name) || ' OWNER TO n8n;'
FROM information_schema.sequences WHERE sequence_schema = 'public' \gexec

-- Future objects created by `n8n` user will have correct ownership; we still
-- need a default privilege so other roles (e.g. backup) can read.
ALTER DEFAULT PRIVILEGES FOR ROLE n8n IN SCHEMA public GRANT SELECT ON TABLES TO n8n;
