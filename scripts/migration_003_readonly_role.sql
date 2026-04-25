-- Migration 003: Read-only Postgres role for the SQL admin endpoint
-- (Phase 7).
--
-- Idempotent. Apply once against the already-populated Postgres:
--   psql -h 127.0.0.1 -U kaizen -d kaizen_rfp -f scripts/migration_003_readonly_role.sql
--
-- Or via:
--   ./.venv/Scripts/python.exe services/api/db/migrate.py
-- (services/api/db/schema.sql is idempotent and now includes this block, so
-- a fresh DB picks it up automatically.)

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rfp_readonly') THEN
        EXECUTE 'CREATE ROLE rfp_readonly LOGIN PASSWORD ''kaizen_readonly_pw''';
    END IF;
END $$;

GRANT CONNECT ON DATABASE kaizen_rfp TO rfp_readonly;
GRANT USAGE ON SCHEMA public TO rfp_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO rfp_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO rfp_readonly;

COMMIT;
