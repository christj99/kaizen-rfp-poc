# Architecture deep-dive

For reviewers who want to know how each part actually works. Skip to the section you care about; each is self-contained.

---

## 1. Adapter pattern (Discovery)

Every ingestion path produces the same shape: a `RawIngestionRecord` (defined in `services/api/models/rfp.py`). Downstream — normalizer, deduper, screening, drafting, UI — never sees adapter-specific structure.

```
┌─ adapters/email_imap.py     pollable, IMAP-IDLE-style poll          ┐
├─ adapters/sam_gov.py        pollable, REST search + description URL │  yield RawIngestionRecord
├─ adapters/manual_upload.py  user-triggered, helper functions        │
└─ adapters/url_ingest.py     user-triggered, helper functions        ┘
                                       │
                                       ▼
                       services/api/agents/discovery/normalizer.py
                       (dispatches on adapter_type)
                                       │
                                       ▼
                       services/api/agents/discovery/deduper.py
                       (sha256(solnum + title) → upsert)
                                       │
                                       ▼
                                  rfps table
```

### Adding a new adapter

1. Subclass `AdapterBase` (in `services/api/agents/discovery/base.py`). Implement `health_check()` (always required) and `fetch()` (only for pollable adapters).
2. Yield `RawIngestionRecord` instances from `fetch()`. Set `adapter_type` to the new family name.
3. Add an `_normalize_<adapter_type>()` branch in `services/api/agents/discovery/normalizer.py`. The normalizer is the single place that knows the adapter-specific source-metadata shape.
4. Wire the adapter into the orchestrator's `build_all_adapters()` factory in `services/api/agents/discovery/orchestrator.py`.
5. Optionally: add a Pydantic config model in `services/api/config/loader.py` so the new adapter is configurable from `config.yaml`.

The shared tail (`ingest_raw_record` in orchestrator.py: normalize → dedupe → upsert → audit) means new adapters get all of: dedup, the 📥 Slack ingest card, the dashboard's source filter, and audit-log entries for free.

---

## 2. Normalizer

`services/api/agents/discovery/normalizer.py`. Dispatches on `record.adapter_type`. Each branch:

- Sets `source_type`, `source_adapter_version`, and `source_metadata` (which is JSONB; structure is adapter-specific and surfaced in the UI's RFP-detail "Source metadata" expander).
- Extracts structured fields from raw content via regex / heuristics. NAICS extraction uses a two-pass extractor (proximity match on the word "NAICS", then sector-prefix-validated 6-digit fallback) to reject false positives like 6-digit dates or amounts.
- Computes `dedupe_hash` deterministically.
- Sets `status='needs_manual_review'` when an adapter signals partial failure (e.g. SAM.gov `description_fetch_status='http_500'`).

LLM-based extraction is reserved behind `sources.email.use_llm_extraction` (default off). Worth turning on if regex fields are too noisy for the demo, but the current corpus doesn't need it.

---

## 3. RAG indexing

`services/api/rag/`. Past proposals live as Markdown files under `sample_data/past_proposals/` with a YAML metadata block at the top.

**Indexer (`indexer.py`):**
1. Parse each `*.md` — split on the first `\n---\n` to get metadata + body.
2. Split body into sections by `## ` headers; each section becomes a chunk group.
3. Greedily pack paragraphs into ~350-word chunks (≈ 500 tokens). Section boundaries are preserved in the chunk's `chunk_section` column.
4. Embed each chunk via OpenAI `text-embedding-3-small` (1536 dims, matching `proposal_chunks.embedding VECTOR(1536)`).
5. Insert the proposal row + N chunks in one transaction.

**No `ivfflat` index.** At POC corpus size (tens of chunks) it silently drops matches when cluster count exceeds row count. Sequential scan with `vector_cosine_ops` is exact and fast at this scale. Re-introduce HNSW once the corpus grows past ~1000 chunks.

**Retriever (`retriever.py`):**
1. Embed the query.
2. Fetch top-N (default 20) chunks by cosine distance.
3. Roll up to proposal level — keep each proposal's best (smallest-distance) chunk as the explainability excerpt.
4. Return the top-k proposals with similarity (1 − cosine distance), best section name, and excerpt.

Used by both the screening agent (3 similar past proposals as in-prompt context) and the chat agent's `search_past_proposals` tool.

---

## 4. Screening prompt structure

`services/api/agents/screening.py` + `services/api/llm/prompts/screening_system.txt` + `screening_user.txt`.

**System prompt** declares the agent's role, behavioral standards (ground every claim in evidence; resist score inflation; flag uncertainty as open_questions, not best-guesses), the 8-step process, and the exact JSON output schema (rubric breakdown with hard-disqualifier results, weighted dimensions, deal-breakers, open questions, similar-proposal analysis, calibration notes).

**User prompt** is `screening_user.txt` with 15 marker substitutions:
- `{{rfp_title}}`, `{{rfp_agency}}`, `{{rfp_solicitation_number}}`, `{{rfp_naics}}`, `{{rfp_set_aside}}`, `{{rfp_value_estimate}}`, `{{rfp_due_date}}`, `{{rfp_place_of_performance}}`, `{{rfp_full_text}}`
- `{{company_profile_yaml}}`, `{{fit_rubric_yaml}}` — full YAML inlined
- `{{similar_past_proposals_block}}` — RAG retrieval results, formatted with `proposal_id` so Claude can cite by id in `similar_past_proposals_analysis[].proposal_id`
- `{{current_pursuit_load}}`, `{{days_to_deadline}}`, `{{current_date}}`

**Translation back to the model.** `_translate_response()` in `screening.py` parses Claude's JSON into the typed `Screening` pydantic. Unknown literal values (e.g. `effort_estimate='n/a'`) are coerced to `None` via `_coerce_enum` rather than raising — Claude occasionally returns these on low-information RFPs and we want a successful screening with "not assessed" rather than a 500.

---

## 5. Drafting + provenance

`services/api/agents/drafting.py` + `services/api/llm/prompts/drafting_system.txt`.

**Single Claude call** generates the full 8-section draft. The system prompt enforces three non-negotiable rules:

1. Never invent facts. Every claim about Meridian's past performance, certs, staff, or vehicles must come from the company profile or a retrieved past proposal.
2. Never invent numbers. Pricing, labor rates, durations either come from the source material or are explicit placeholders.
3. Per-section provenance is required: `generated` / `retrieved_from_past_proposal` / `retrieved_from_profile` / `static_boilerplate`, plus `confidence` (low/medium/high) and `human_review_required` (bool) with notes.

Output JSON includes section content, word count, and provenance metadata. `_translate_response()` maps to typed `Draft` + `DraftSection`s. Confidence strings → 0.3/0.6/0.9; `source_ids` validated against the actually-retrieved set so the model can't fabricate plausible UUIDs.

`max_tokens=32000` (Sonnet 4.5 supports up to 64k). 16000 truncated mid-section on substantive RFPs in early testing. The LLMClient always uses streaming (`messages.stream`) — the non-streaming endpoint refuses requests whose `max_tokens × rate` could push past 10 minutes.

The drafting prompt also reads the screening verdict — when screening returns `skip`, drafting produces a structured no-bid response rather than a proposal. This is emergent from the prompt, not coded.

---

## 6. Async job pattern (Phase 3B)

`services/api/main.py`'s `POST /rfp/{id}/draft?mode=async|sync`:

- **`async` (default):** persist a `draft_jobs` row with `status='queued'` + return immediately with the job id. FastAPI `BackgroundTasks` runs `_run_draft_job` after the response is sent. The worker:
  1. Updates job to `status='running'`, sets `started_at`.
  2. Calls `draft_proposal()` — the same function the sync path uses, untouched.
  3. On success: updates to `status='completed'`, sets `draft_id`, audit-logs the duration.
  4. On exception: catches everything, updates to `status='failed'`, persists `error_message[:2000]`, audit-logs `error_class`.
- **`sync`:** preserves Phase 3 behavior — the request blocks for the full Claude call (~5 min). Demo safety net.

`GET /draft/job/{id}` returns the job state. When `status='completed'` it inlines the full draft so pollers don't need a second call.

`GET /draft_jobs?status=...&since=...` is what the n8n watcher polls.

The pattern works for one POC user. Production would replace `BackgroundTasks` with Celery/RQ for retries + worker-pool management + persistence across uvicorn restarts.

---

## 7. n8n workflow patterns

Six workflows under `services/n8n/workflows/`. Two patterns:

**Pollable adapters as discovery workflows** (`discovery_email.json`, `discovery_sam_gov.json`):

```
schedule trigger
  → POST /discovery/run/<adapter_name>
  → expand new_rfp_ids
  → fan-out:
      ├─ POST /webhook/kaizen/ingest-notify  (📥 ingest card, every mode)
      └─ POST /orchestrate                   (mode-aware)
            └─ if fit_score >= threshold:
                  GET /rfp/{id} → format Block Kit → POST Slack
```

The fan-out from `expand new_rfp_ids` to both the ingest sub-workflow and `/orchestrate` is intentional — manual mode still gets a 📥 ingest card even though screening doesn't run.

**Watcher with per-job dedupe** (`draft_completion_watcher.json`):

```
schedule trigger (30 s)
  → compute since-marker (rolling 15-min lookback)
  → GET /draft_jobs?since=...
  → filter: status IN (completed, failed) AND not in notifiedJobIds
       (notifiedJobIds is workflow staticData with TTL pruning)
  → GET /rfp/{id} for context
  → IF status == 'completed':
        format draft-ready Slack → POST
     ELSE:
        format draft-failed Slack → POST
```

The dedupe map is keyed by `job_id` and pruned at 6 hours. Earlier versions used a sliding `since` marker that updated each tick — but if a job's `completed_at` landed between two watcher ticks, the marker advanced past it forever (race condition). The fixed-window + per-job dedupe approach is idempotent: the watcher would have to be down for >15 minutes to miss a job.

**Workflow JSON quirks worth knowing:**
- httpRequest auto-splits array responses into one item per element. Don't add a separate `splitOut` node.
- `$('NodeName').item.json` walks back through n8n's `pairedItem` chain to access an upstream node's output.
- Material icons (`:material/...`) work in Slack `mrkdwn` but not as Slack header text — use Unicode emoji there.
- `$getWorkflowStaticData('global')` is the only persistent state available between runs of an active scheduled workflow.

---

## 8. Config-driven mode switching

`services/api/config/loader.py`:

- `AppConfig` is a pydantic model parsed from `config/config.yaml`. Supports nested sources (multiple adapters per family), threshold sliders, mode, LLM settings.
- `load_config()` stats the config file on every call. When `mtime` changes, re-parses. Effect: `config.mode` edits take effect on the next `/orchestrate` call without an API restart.
- Thread-safe via an `RLock` around the cache update.

Settings page (`services/ui/screens/settings.py`) writes via `PUT /config`, which:
1. Merges the partial update into the existing YAML.
2. Writes back via `yaml.safe_dump`.
3. Triggers `reload_config()` to refresh the in-process cache.
4. Audit-logs the change.

---

## 9. Audit log

`audit_log` table is the system's source of truth for "what happened, when, by whom." Every meaningful state transition writes an entry:

| `action` | `actor` | typical `details` |
|---|---|---|
| `discovery_ingest` | system | adapter_name, source_identifier, was_new, status |
| `discovery_duplicate` | system | adapter_name, dedupe_hash |
| `screen_rfp` | claude | model, input_tokens, output_tokens, schema_enforced |
| `draft_proposal` | claude | model, input_tokens, output_tokens |
| `human_override` | user | recommendation, reason |
| `config_updated` | user | (the partial-update body) |
| `rubric_updated` | user | version, last_updated |
| `chat_response` | claude | input_turns, tools_used, model |
| `queued`/`running`/`completed`/`failed` | system | (entity_type='draft_job') mode, duration_seconds, draft_id, error_class |

The Dashboard's recent-activity feed is just `GET /audit_log?limit=15` rendered with humanized timestamps. The Rubric Editor's version history is the same query filtered to `action='rubric_updated'`.

The plan-level value of this design: "how would you debug a production issue?" has a concrete answer — start by querying audit_log for the entity in question, walk forward through transitions.

---

## 10. Where each layer lives

```
services/api/
├── _env.py                  load .env, treating empty-string vars as unset
├── main.py                  FastAPI surface (every endpoint)
├── config/loader.py         AppConfig pydantic + hot-reload-on-mtime
├── llm/client.py            single LLMClient — streaming, retry, audit
├── llm/prompts/             4 prompt files (screening sys+user, drafting sys, chat sys)
├── models/                  pydantic types: RFP, Screening, Draft, AuditEntry, ...
├── db/
│   ├── schema.sql           ddl
│   ├── client.py            psycopg2 helpers (no orm)
│   └── ...                  scripts/migration_*.sql for existing DBs
├── rag/
│   ├── embeddings.py        OpenAI wrapper
│   ├── indexer.py           parse → chunk → embed → store
│   └── retriever.py         query → top-k proposals
└── agents/
    ├── discovery/           adapter pattern + normalizer + deduper + orchestrator
    ├── screening.py         single-call Claude assessment
    ├── drafting.py          single-call full-draft with provenance
    └── chat.py              tool-calling chat loop

services/ui/                 streamlit
├── app.py                   st.navigation entry
├── api_client.py            cached HTTP client to FastAPI
├── components/              shared badges + layout helpers
└── screens/                 6 pages (dashboard, rfp_detail, ...)

services/n8n/workflows/      7 .json — see README's n8n section
```
