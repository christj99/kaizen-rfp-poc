-- Migration 002: draft_jobs table for Phase 3B async drafting.
--
-- Idempotent. Apply once against the already-populated Postgres:
--   psql -h 127.0.0.1 -U kaizen -d kaizen_rfp -f scripts/migration_002_draft_jobs.sql

BEGIN;

CREATE TABLE IF NOT EXISTS draft_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rfp_id UUID REFERENCES rfps(id) ON DELETE CASCADE,
    status TEXT NOT NULL,                       -- 'queued' | 'running' | 'completed' | 'failed'
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    draft_id UUID REFERENCES drafts(id) ON DELETE SET NULL,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_draft_jobs_rfp_id
    ON draft_jobs (rfp_id);

CREATE INDEX IF NOT EXISTS idx_draft_jobs_status_created
    ON draft_jobs (status, created_at DESC);

COMMIT;
