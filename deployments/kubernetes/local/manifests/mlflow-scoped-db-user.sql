-- Scoped MLflow Postgres user (issue #785).
-- Run once after `mlflow` DB exists, then rotate the K8s secret
-- `mlflow-db-credentials` to use this user instead of the shared `postgres`
-- superuser.
--
-- Usage:
--   kubectl exec -n isa-cloud-local postgresql-0 -c postgresql -- bash -c '
--     PGPASSWORD="$(cat $POSTGRES_PASSWORD_FILE)" psql -U postgres \
--       -v pwd="$(openssl rand -hex 24)" -f /tmp/scoped.sql
--   '
-- (then capture the password and patch the secret out-of-band — never inline).

-- Idempotent role creation
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mlflow') THEN
    CREATE ROLE mlflow WITH LOGIN PASSWORD :'pwd';
  END IF;
END $$;

-- Lock the database down to the scoped role + reset previous public grants
REVOKE ALL ON DATABASE mlflow FROM PUBLIC;
GRANT CONNECT ON DATABASE mlflow TO mlflow;
GRANT CREATE, USAGE ON SCHEMA public TO mlflow;
ALTER SCHEMA public OWNER TO mlflow;

-- Reparent existing tables + sequences to the new owner.  Generated DDL is
-- printed via gset/\gexec so the script runs idempotently as the schema grows.
SELECT 'ALTER TABLE ' || quote_ident(schemaname) || '.' || quote_ident(tablename) || ' OWNER TO mlflow;'
FROM pg_tables WHERE schemaname = 'public' \gexec

SELECT 'ALTER SEQUENCE ' || quote_ident(sequence_schema) || '.' || quote_ident(sequence_name) || ' OWNER TO mlflow;'
FROM information_schema.sequences WHERE sequence_schema = 'public' \gexec

-- Future objects created by `mlflow` user will have correct ownership; we still
-- need a default privilege so other roles (e.g. backup) can read.
ALTER DEFAULT PRIVILEGES FOR ROLE mlflow IN SCHEMA public GRANT SELECT ON TABLES TO mlflow;
