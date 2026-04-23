-- Kaizen RFP POC — database schema
-- Applied by scripts/reset_db.sh or services/api/db/migrate.py on a fresh Postgres.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

CREATE TABLE IF NOT EXISTS rfps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,                       -- 'sam_gov' | 'email' | 'manual'
    external_id TEXT,                           -- e.g., SAM.gov solicitation number
    title TEXT NOT NULL,
    agency TEXT,
    naics_codes TEXT[],
    due_date TIMESTAMP,
    value_estimate_low BIGINT,
    value_estimate_high BIGINT,
    full_text TEXT,
    source_url TEXT,
    received_at TIMESTAMP DEFAULT NOW(),
    status TEXT DEFAULT 'new',                  -- 'new'|'screened'|'in_draft'|'submitted'|'won'|'lost'|'dismissed'
    dedupe_hash TEXT UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_rfps_status ON rfps (status);
CREATE INDEX IF NOT EXISTS idx_rfps_received_at ON rfps (received_at DESC);

CREATE TABLE IF NOT EXISTS screenings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rfp_id UUID REFERENCES rfps(id) ON DELETE CASCADE,
    fit_score INT,
    recommendation TEXT,                        -- 'pursue'|'maybe'|'skip'
    rationale JSONB,                            -- structured rubric breakdown
    effort_estimate TEXT,                       -- 'low'|'medium'|'high'
    deal_breakers JSONB,
    open_questions JSONB,
    similar_proposal_ids UUID[],
    model_version TEXT,
    rubric_version TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    human_override TEXT,
    human_override_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_screenings_rfp_id ON screenings (rfp_id);
CREATE INDEX IF NOT EXISTS idx_screenings_created_at ON screenings (created_at DESC);

CREATE TABLE IF NOT EXISTS past_proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT,
    agency TEXT,
    submitted_date DATE,
    outcome TEXT,                               -- 'won'|'lost'|'withdrawn'
    contract_value BIGINT,
    full_text TEXT,
    sections JSONB,                             -- {exec_summary, qualifications, technical, pricing, attachments}
    metadata JSONB
);

CREATE TABLE IF NOT EXISTS proposal_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    past_proposal_id UUID REFERENCES past_proposals(id) ON DELETE CASCADE,
    chunk_text TEXT,
    chunk_section TEXT,
    embedding VECTOR(1536)
);

-- Cosine-distance ivfflat index. Requires ANALYZE after bulk load for best performance.
CREATE INDEX IF NOT EXISTS idx_proposal_chunks_embedding
    ON proposal_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE TABLE IF NOT EXISTS drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rfp_id UUID REFERENCES rfps(id) ON DELETE CASCADE,
    screening_id UUID REFERENCES screenings(id) ON DELETE SET NULL,
    content JSONB,                              -- generated sections
    retrieved_proposal_ids UUID[],
    status TEXT DEFAULT 'generated',            -- 'generated'|'reviewed'|'approved'
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_drafts_rfp_id ON drafts (rfp_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT,
    entity_id UUID,
    action TEXT,
    actor TEXT,                                 -- 'system'|'user'|'claude'
    details JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log (created_at DESC);
