-- Create the n8n database for local-dev docker-compose.
-- Mirrors the in-cluster `n8n` database used by the n8n workflow-automation
-- service (see deployments/kubernetes/local/values/n8n.yaml). Postgres only
-- auto-creates POSTGRES_DB on first init, so n8n needs its own DB here.
SELECT 'CREATE DATABASE n8n'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'n8n') \gexec
