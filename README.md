# Kaizen RFP POC

A loosely-coupled multi-agent RFP automation system for a B2B proposals team. Built as a take-home case study for a Data Engineer role at Kaizen Labs against a fictional federal/SLED data-modernization firm (Meridian Data Solutions).

The system ingests RFPs from email, SAM.gov, manual upload, or arbitrary URLs; screens each one against a calibrated rubric using Claude with retrieval-augmented context from past proposals; and (for clear pursues) drafts a first-pass proposal with explicit per-section provenance so the proposal lead knows exactly what was generated, what was retrieved, and what still needs human input.

## Architecture

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ Email IMAP  │  │ SAM.gov API │  │ Manual PDF  │  │ URL ingest  │
│  adapter    │  │  adapter    │  │  upload     │  │  adapter    │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       └────────────────┴────────────────┴────────────────┘
                                │
                         ┌──────▼──────┐
                         │ Normalizer  │  RawIngestionRecord -> RFP
                         └──────┬──────┘
                                │
                         ┌──────▼──────┐
                         │  Deduper    │  (sha256(solnum + title))
                         └──────┬──────┘
                                │
       ┌────────────────────────┼────────────────────────┐
       │                        ▼                        │
       │             ┌──────────────────┐                │
       │             │  /orchestrate    │  honors        │
       │             │ (mode-aware)     │  config.mode   │
       │             └────────┬─────────┘                │
       │                      │                          │
       │      ┌───────────────┼───────────────┐          │
       │      ▼               ▼               ▼          │
       │ Screening agent  Drafting agent  Discovery     │
       │  + RAG over      + template-     scheduled     │
       │  past proposals  aware sections  via n8n       │
       │                  + provenance                  │
       │                                                │
       │     ┌─────────────────┴──────────────────┐     │
       │     ▼                                    ▼     │
       │  Postgres + pgvector                  Slack   │
       │  (rfps, screenings,                  (Block  │
       │   drafts, draft_jobs,                Kit via │
       │   past_proposals,                    n8n)    │
       │   audit_log)                                  │
       │                                               │
       └─────────────────────┬─────────────────────────┘
                             ▼
                  Streamlit UI (8501)
```

**Three agents:**
- **Discovery** — pluggable adapter pattern. Pollable adapters (email, SAM.gov) run on n8n schedules; user-triggered adapters (manual upload, URL) hit the same normalizer + deduper pipeline.
- **Screening** — loads `fit_rubric.yaml` + `company_profile.yaml`, retrieves 3 similar past proposals via RAG, asks Claude for a structured assessment with rubric breakdown, deal-breakers, and open questions.
- **Drafting** — loads `proposal_template.yaml`, retrieves similar proposals, asks Claude to produce all sections with explicit provenance (`generated` / `retrieved` / `static`) and per-section confidence + review flags. Async via FastAPI `BackgroundTasks` + a `draft_jobs` table; n8n's draft-completion watcher posts a "draft ready" Slack card on completion.

**Storage:** Postgres 16 with `pgvector` for the RAG index. Tables: `rfps`, `screenings`, `drafts`, `draft_jobs`, `past_proposals`, `proposal_chunks`, `audit_log`.

**LLM:** Claude Sonnet 4.5 via the Anthropic SDK (streaming for every call — long drafts exceed the 10-minute non-streaming cap). Embeddings via OpenAI `text-embedding-3-small` (Anthropic doesn't expose embeddings).

## Quick start

```bash
git clone <repo>
cd kaizen-rfp-poc

# Required: copy and fill in API keys
cp .env.example .env

# Then edit .env to set ANTHROPIC_API_KEY, OPENAI_API_KEY, DEMO_EMAIL_USERNAME,
# DEMO_EMAIL_PASSWORD, SLACK_WEBHOOK_URL, and (optionally) SAM_GOV_API_KEY.

# One-time setup
python -m venv .venv
source .venv/Scripts/activate     # Git Bash / WSL on Windows
# .\.venv\Scripts\Activate.ps1     # native PowerShell
pip install -r requirements.txt

# Bring everything up
./scripts/demo_start.sh            # Linux / macOS / Git Bash
# .\scripts\demo_start.ps1          # native PowerShell

# Import + activate the n8n workflows (see the n8n setup section below
# for the manual-UI alternative).
python scripts/import_n8n_workflows.py --activate

# Seed a populated demo state
./scripts/seed_data.sh
```

URLs once running:

| | URL | Notes |
|---|---|---|
| Streamlit UI | http://localhost:8501 | The demo surface |
| FastAPI docs | http://localhost:8000/docs | Swagger UI for every endpoint |
| n8n | http://localhost:5678 | Scheduled discovery + Slack notifications |

To tear down: `./scripts/demo_stop.sh` (or `demo_stop.ps1`).

## Prerequisites

- **Docker Desktop** running (Postgres + n8n containers)
- **Python 3.11+**
- **Anthropic API key** ([console.anthropic.com](https://console.anthropic.com))
- **OpenAI API key** ([platform.openai.com/api-keys](https://platform.openai.com/api-keys)) — embeddings only
- **Throwaway Gmail account** with an app password ([myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)) — required for the email-ingestion demo path
- **Slack Incoming Webhook URL** ([api.slack.com/apps](https://api.slack.com/apps) → Incoming Webhooks) — required for the Slack notification demo
- _Optional:_ SAM.gov API key ([sam.gov/content/api-keys](https://sam.gov/content/api-keys)) for live federal-RFP polling

## Demo email setup

The IMAP adapter is the primary demo source. Five-minute setup:

1. Create a throwaway Gmail account (e.g. `yourname.rfps.demo@gmail.com`).
2. Enable **2-Step Verification** at [myaccount.google.com/security](https://myaccount.google.com/security) — required before app passwords.
3. Generate an **app-specific password** at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords). Pick "Mail" as the app type. Copy the 16-character password (you won't see it again).
4. New Gmail accounts have IMAP enabled by default. If you reused an older account, confirm at Gmail → Settings → Forwarding and POP/IMAP.
5. Add to `.env`:
   ```
   DEMO_EMAIL_USERNAME=yourname.rfps.demo@gmail.com
   DEMO_EMAIL_PASSWORD=<16-char app password, no spaces>
   ```
6. After `./scripts/demo_start.sh`, test by visiting **Settings → Adapter management** in the UI and clicking **Test connection** on `demo_gmail`.

## Configuration

`config/config.yaml` drives everything. Hot-reloaded on file mtime — edit and save to flip mode without an API restart.

```yaml
mode: manual             # manual | chain | full_auto

screening:
  threshold_pursue: 75   # fit_score >= → recommendation 'pursue'
  threshold_maybe: 50    # 50-74 → 'maybe'

drafting:
  auto_draft_threshold: 80  # full_auto only: queue draft if fit_score >= 80

slack:
  notification_threshold: 50  # screening-card fires if fit_score >= this

llm:
  model: claude-sonnet-4-5
  max_tokens: 8192
  temperature: 0.3
```

Source-specific config (`sources.email.adapters[0].host`, `sources.sam_gov.adapters[0].naics_filter`, etc.) lives under `sources.*` — see the file for the full shape. Multiple adapter instances per source family are supported (run two Gmail mailboxes, two SAM.gov keys, etc.) without code changes.

## The four modes

`config.mode` controls how aggressively the system chains agents. Flip it live to demo behavior changes:

- **`manual`** — Discovery still ingests RFPs. Nothing auto-chains. Humans kick off screening and drafting from the UI or API. Safe production default.
- **`chain`** — Newly-ingested RFPs are automatically screened. Drafting still requires a human trigger.
- **`full_auto`** — Screening is automatic. RFPs whose `fit_score >= drafting.auto_draft_threshold` _and_ recommendation isn't `skip` also get drafted automatically (async). The "draft ready" Slack card fires when the job completes.

`POST /orchestrate` reads `config.mode` on every call. n8n workflows route every newly-ingested RFP through `/orchestrate`, so flipping modes doesn't require touching n8n.

## The three agents

### Discovery (`services/api/agents/discovery/`)

Adapter pattern. Each adapter yields `RawIngestionRecord`; the normalizer turns those into typed `RFP` rows. Pollable adapters live under `services/api/agents/discovery/adapters/` (`email_imap.py`, `sam_gov.py`); user-triggered paths (`manual_upload.py`, `url_ingest.py`) expose helper functions called directly by the FastAPI ingest endpoints. Dedupe is a sha256 of `solicitation_number + title` — same RFP arriving via two adapters lands once.

### Screening (`services/api/agents/screening.py`)

Loads `fit_rubric.yaml` + `company_profile.yaml`, retrieves 3 similar past proposals via the RAG retriever, substitutes 15 markers into `screening_user.txt`, and calls Claude with a JSON-schema-guided prompt. Output is a structured `Screening` with rubric-dimension breakdown, hard-disqualifier results, deal-breakers, open questions, and similar-proposal citations. Persists to `screenings` and transitions `rfp.status` to `screened`.

### Drafting (`services/api/agents/drafting.py`)

Single Claude call (`drafting_system.txt` is the system prompt; the user prompt is assembled here) produces an 8-section first draft with explicit per-section provenance, confidence (0.3/0.6/0.9), `needs_review` flag, and review notes. Anti-hallucination rules in the prompt mean pricing numbers and named personnel always come through as flagged placeholders rather than invented plausible-looking values. Async via FastAPI `BackgroundTasks` + `draft_jobs` table; the watcher fires the Slack card on completion or failure.

### Chat (`services/api/agents/chat.py`)

Tool-calling chat backed by Claude. Five tools (`search_rfps`, `search_past_proposals`, `get_rfp_detail`, `get_past_proposal_detail`, `get_screening_detail`) ground every answer in real data from the system. Loop capped at 6 iterations.

## n8n workflow setup (required)

n8n drives the scheduled side of the pipeline: email-discovery polling (every 2 min), SAM.gov polling (every 4 hr, off by default), and the draft-completion watcher (every 30 s). It's also what fires the Slack notifications. **The demo flow assumes n8n is up with the workflows imported and active** — you can ingest, screen, and draft from the Streamlit UI alone, but the email-arrives → Slack-card path needs n8n.

Docker Compose already runs the n8n container (no separate install). What's left is importing the seven workflow JSONs and activating the three scheduled ones.

### The seven workflows

All under `services/n8n/workflows/`:

| File | Trigger | Purpose |
|---|---|---|
| `discovery_email.json` | schedule (2 min) | Polls Gmail; triggers ingest → orchestrate → Slack card. **Active by default.** |
| `discovery_sam_gov.json` | schedule (4 hr) | Same pattern for SAM.gov. Inactive by default (rate-limited). |
| `chain_mode.json` | webhook | Force-chain a specific RFP regardless of `config.mode`. |
| `full_auto_mode.json` | webhook | Force-full-auto a specific RFP. |
| `draft_completion_watcher.json` | schedule (30 s) | Polls `draft_jobs`; fires "draft ready" or "draft failed" Slack cards. **Active by default.** |
| `slack_notification.json` | webhook | Reusable sub-workflow for ad-hoc Slack cards. |
| `slack_ingest_notification.json` | webhook | Sub-workflow called by both discovery workflows for the `📥 New RFP ingested` card. **Active by default** (its production webhook URL has to be reachable for the discovery workflows to call it). |

### Importing the workflows — pick one path

Both paths produce the same end state. The importer script saves five minutes of clicking; the manual UI path is always available and doesn't require generating an API key.

**Path A — via the importer script (faster, recommended for repeat installs):**

1. Open n8n at http://localhost:5678 (basic-auth from `.env`: `N8N_BASIC_AUTH_USER` / `N8N_BASIC_AUTH_PASSWORD`).
2. Settings → n8n API → **Create an API key**. Paste into `.env` as `N8N_API_KEY=eyJ...`.
3. Run `python scripts/import_n8n_workflows.py --activate`. Idempotent — re-run after editing any workflow JSON to push the changes.

**Path B — manually via the n8n UI (no API key required):**

1. Open n8n at http://localhost:5678.
2. For each `.json` file under `services/n8n/workflows/`: Workflows → **Create workflow** → kebab menu → **Import from file** (or drag the JSON onto the canvas).
3. Toggle "Active" on these three:
   - `Discovery — Email (primary)`
   - `Draft completion watcher`
   - `Slack ingest notification (sub-workflow)`
4. Leave the other four inactive — they're webhook-triggered test harnesses (`chain_mode`, `full_auto_mode`, `slack_notification`) and the secondary SAM.gov poller.

### Slack webhook setup

Create a Slack app at [api.slack.com/apps](https://api.slack.com/apps), enable **Incoming Webhooks**, install to your workspace, copy the webhook URL into `.env` as `SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...`. Restart the stack so n8n picks up the new env: `./scripts/demo_stop.sh && ./scripts/demo_start.sh`.

## Demo flow

After `./scripts/demo_start.sh && ./scripts/seed_data.sh`:

1. **Open the Streamlit UI** at http://localhost:8501. Dashboard shows 10 pre-seeded RFPs across all four source types and four status states. The Needs Attention queue surfaces the SAM.gov record whose description-fetch failed.
2. **Open one of the screened RFPs** (e.g. NIH Clinical Research Data) — the rubric breakdown, deal-breakers, open questions, and similar past proposals all render with stable seed content.
3. **Open one of the in-draft RFPs** (USDA FNS SNAP, VHA Healthcare) — see the per-section provenance (`generated` / `retrieved` / `static`), confidence scores, `Needs review` flags, and **Export Markdown** button.
4. **Send a fresh email** to the demo Gmail with a PDF RFP attached. Within ~2 min the Dashboard shows it; within ~3 min the screening card hits Slack (in `chain` or `full_auto` mode).
5. **Flip `config.mode`** in `config/config.yaml` between `manual`, `chain`, `full_auto`. Save the file. The next email exhibits the new behavior — no API restart needed.
6. **Run an adapter ad-hoc** from Settings → Adapter management → **Run now** on `demo_gmail` or `sam_gov_primary`.
7. **Try the chat widget** — _"show me high-fit RFPs from this week"_, _"how did we do on the Maryland DHS work?"_, _"what was our LOST proposal about?"_.
8. **Reset to clean state** with `./scripts/demo_reset.sh` — under 60 seconds.

## Demo reset and seed

| Script | What it does | Time |
|---|---|---|
| `demo_start.sh` | Containers + uvicorn + Streamlit | ~30 s |
| `demo_stop.sh` | Cleanly stop everything | ~10 s |
| `demo_reset.sh` | Wipe user data + re-index past proposals + restart | ~37 s |
| `seed_data.sh` | Load 10 RFPs / 5 screenings / 2 drafts from committed fixtures | ~1 s |
| `test_end_to_end.sh` | Smoke-test every ingestion path + screening + async drafting | ~7 min |
| `build_seed_fixtures.py` | Rebuild `sample_data/seed/*.json` from current DB state (one-off) | ~1 s |
| `import_n8n_workflows.py` | Import all 7 workflows via n8n API | ~5 s |

## Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for common issues:

- Docker Desktop not running / hung
- IMAP login failures
- SAM.gov 500 errors on description fetch (known external issue — see [docs/sam_gov_issues.md](docs/sam_gov_issues.md))
- Postgres volume persistence
- Material-icon syntax in custom HTML

## Architecture deep-dive

[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) covers the adapter pattern, normalizer, RAG indexing, screening prompt structure, drafting provenance design, async-job pattern, n8n workflow patterns, and audit-log design.

## Observations log

[docs/observations_log.md](docs/observations_log.md) is a running record of decisions, calibration tradeoffs, and bug-class lessons surfaced during build. Reviewers who want to see how the project actually evolved (vs. the post-hoc story) will find this useful.

## Future work

Honest list of what would need to happen to take this to production:

- **Real async job queue** — FastAPI `BackgroundTasks` is a POC choice; production wants Redis + Celery/RQ for retries, persistence across uvicorn restarts, and worker pool management.
- **FedRAMP authorization path** — every actual federal RFP requires it. Architecture is FedRAMP-friendly (containerized, no third-party data hops) but no controls package exists.
- **Multi-tenant data isolation** — current code assumes one organization (Meridian). Production would need per-tenant RFP namespaces, separate RAG indices, and per-tenant rubric versions.
- **More source adapters** — FedConnect, Bloomberg Government, BidPrime, agency-specific portals.
- **Rubric calibration loop** — feed `human_override` records (already captured in `audit_log`) back into rubric refinement automatically.
- **`.docx` / `.rtf` attachment parsing** — current adapter only handles text bodies + PDFs.
- **Streaming chat responses** — chat backend already uses streaming under the hood; the Streamlit page renders after completion. SSE would feel snappier.
- **Production observability** — structured logging, Prometheus metrics, distributed tracing across the n8n + FastAPI hop.

## Credits

Built as a Data Engineer take-home for Kaizen Labs. Implementation by Chris Johnson with an LLM coding partner; domain content (rubric, prompts, sample past proposals, demo narrative) authored separately via a conversational Claude collaboration documented in the observations log.
