-- Migration 001: multi-source ingestion schema (supplemental Phase 1 amendment 1.A)
--
-- Renames `rfps.source` -> `source_type`, adds `source_adapter_version`
-- and `source_metadata`, and normalizes legacy values.
--
-- Run once against the already-populated Postgres. Idempotent: safe to run
-- twice. Apply via `scripts/migrate.ps1` / `scripts/migrate.sh` or directly:
--   psql -h 127.0.0.1 -U kaizen -d kaizen_rfp -f scripts/migration_001_multi_source.sql

BEGIN;

-- Rename the column only if it still exists under the old name.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = 'rfps'
           AND column_name = 'source'
    )
    AND NOT EXISTS (
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = 'rfps'
           AND column_name = 'source_type'
    )
    THEN
        EXECUTE 'ALTER TABLE rfps RENAME COLUMN source TO source_type';
    END IF;
END $$;

-- Add the new adapter-metadata columns (guarded to stay idempotent).
ALTER TABLE rfps
    ADD COLUMN IF NOT EXISTS source_adapter_version TEXT,
    ADD COLUMN IF NOT EXISTS source_metadata JSONB;

-- Normalize legacy 'manual' source_type to 'manual_upload' (supplemental
-- plan's new canonical value set).
UPDATE rfps
   SET source_type = 'manual_upload'
 WHERE source_type = 'manual';

-- Backfill source_adapter_version for pre-amendment rows.
UPDATE rfps
   SET source_adapter_version = source_type || '_v1'
 WHERE source_adapter_version IS NULL;

COMMIT;
