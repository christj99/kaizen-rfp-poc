# Kaizen RFP POC

RFP automation proof-of-concept for a B2B proposal team, built as a single cohesive tool composed of three loosely-coupled agents.

> Status: scaffolding (Phase 0). See the implementation plan for what's still to come.

## Overview

_To be filled in._

## Architecture

_ASCII diagram coming at Phase 6._

The three agents:

1. **Discovery Agent** — ingests RFPs from SAM.gov (and, as a stretch, email), normalizes them, deduplicates, stores them.
2. **Screening Agent** — scores RFPs against a structured fit rubric via Claude, retrieves similar past proposals via RAG, outputs a go/no-go with reasoning.
3. **Drafting Agent** — generates first-draft proposals against a template using retrieval-augmented generation over past proposals.

## Quick start

### Linux / macOS (or Git Bash on Windows)

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate     # use .venv/Scripts/activate under Git Bash on Windows
pip install -r requirements.txt
./scripts/demo_start.sh
```

### Windows PowerShell

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\scripts\demo_start.ps1
```

> Note: if PowerShell blocks local scripts, run once as your user:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
> Avoid invoking the `.sh` scripts through WSL's `bash` — WSL sees its own Linux filesystem, not your Windows venv.

Edit `.env` and set `ANTHROPIC_API_KEY` at minimum before starting.

URLs after startup:

- Streamlit UI:  http://localhost:8501
- FastAPI docs:  http://localhost:8000/docs
- n8n:           http://localhost:5678

To tear down: `./scripts/demo_stop.sh` (or `.\scripts\demo_stop.ps1`).

## Prerequisites

- Docker Desktop (for Postgres + n8n)
- Python 3.11+
- An Anthropic API key
- A throwaway Gmail (or any IMAP) inbox — see "Demo email setup" below
- _Optional:_ SAM.gov API key (free; register at https://sam.gov/content/api-keys)
- _Optional:_ Slack Incoming Webhook URL for discovery notifications
- _Optional:_ OpenAI API key for embeddings (used by the RAG indexer)

## Demo email setup

Email is the primary demo ingestion source (see `docs/sam_gov_issues.md` for
why the SAM.gov-only path was downgraded to secondary). The pipeline connects
to an IMAP inbox, polls for unread messages, and turns each one into an RFP.

1. **Create a throwaway Gmail account** (e.g. `yourname.rfps.demo@gmail.com`).
2. **Enable 2-factor auth** — Gmail requires it before issuing app passwords.
   <https://myaccount.google.com/security>
3. **Generate an app-specific password** at <https://myaccount.google.com/apppasswords>.
   Select "Mail" as the app. Copy the 16-character password — you won't see it again.
4. **IMAP is on by default** for new Gmail accounts. If you reused an older account,
   confirm it at Gmail → Settings → Forwarding and POP/IMAP.
5. **Add credentials to `.env`:**
   ```
   DEMO_EMAIL_USERNAME=yourname.rfps.demo@gmail.com
   DEMO_EMAIL_PASSWORD=<16-char app password, no spaces>
   ```
6. After starting the stack, test the connection via `POST /discovery/run/demo_gmail`
   (or click "Run now" in the UI's Settings → Adapters section once Phase 5 lands).

> Never commit `.env`. Only `.env.example`.

## Configuration

Behavior is driven by `config/config.yaml`. See that file for the full reference. Highlights:

- `mode` — `manual` | `chain` | `full_auto`
- `screening.threshold_pursue` / `threshold_maybe`
- `drafting.auto_draft_threshold`
- `sources.sam_gov.naics_filter`

## The four modes

Behavior is driven by `config.mode` in `config/config.yaml`:

- **`manual`** — Discovery still ingests RFPs. Nothing auto-chains. Humans kick off screening and drafting from the UI or API.
- **`chain`** — Every newly-ingested RFP is automatically screened. Drafting still requires a human trigger.
- **`full_auto`** — Screening is automatic. If `screening.fit_score >= drafting.auto_draft_threshold` (default 90), drafting is *also* queued automatically via `POST /rfp/{id}/draft?mode=async`, and the Slack "draft ready" notification fires when the job completes.

The `POST /orchestrate` endpoint reads `config.mode` on every invocation, so flipping modes is a config edit + API restart (or `reload_config()` call from the Settings page in Phase 5). n8n workflows call `/orchestrate` per new RFP — no n8n changes needed when modes change.

## n8n workflows

Six workflows ship under `services/n8n/workflows/`:

| File | Trigger | Purpose |
|---|---|---|
| `discovery_email.json` | Schedule (2 min) | **Primary.** Polls Gmail, ingests new emails, runs `/orchestrate`, fires Slack if fit ≥ threshold. |
| `discovery_sam_gov.json` | Schedule (4 hr) | Secondary. Same pattern against SAM.gov. Leave inactive in dev (quota). |
| `chain_mode.json` | Webhook `POST /webhook/kaizen/chain-mode {rfp_id}` | Force chain mode for one RFP, regardless of `config.mode`. |
| `full_auto_mode.json` | Webhook `POST /webhook/kaizen/full-auto-mode {rfp_id}` | Force full_auto for one RFP; kicks off async drafting. |
| `draft_completion_watcher.json` | Schedule (30 s) | Polls `/draft_jobs?status=completed` and fires "draft ready" Slack notifications. |
| `slack_notification.json` | Webhook `POST /webhook/kaizen/slack-notify` | Reusable sub-workflow: any tool can POST an RFP id here to trigger a Slack card. |

### Importing the workflows into n8n

1. Open http://localhost:5678, log in with `N8N_BASIC_AUTH_USER` / `N8N_BASIC_AUTH_PASSWORD` from `.env`.
2. Click **Workflows** → **Create workflow** → kebab menu → **Import from file** (or drag the JSON onto the canvas).
3. Repeat for each file under `services/n8n/workflows/`.
4. Each workflow loads with `"active": false`. For the ones you want on cron (`discovery_email.json`, `draft_completion_watcher.json`), toggle the "Active" switch in the top right.
5. The workflows reference the following environment variables (exposed by `docker-compose.yml`):
   - `KAIZEN_API_URL` — set to `http://host.docker.internal:8000` automatically
   - `KAIZEN_UI_URL` — `http://localhost:8501`
   - `SLACK_WEBHOOK_URL` — pulled from your `.env`
   - `SLACK_NOTIFICATION_THRESHOLD` — default `75`
6. No n8n credential objects are required. Every HTTP call either targets a local service or uses the env-provided Slack webhook URL as-is.

### Slack setup

1. Create a Slack app (<https://api.slack.com/apps>) with Incoming Webhooks enabled.
2. Install the app to your workspace and copy the webhook URL.
3. Paste it into `.env` as `SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...`
4. Restart the stack (`./scripts/demo_stop.ps1` then `./scripts/demo_start.ps1`) — n8n reads env at container start.

### Testing a workflow in isolation

In the n8n UI, open any workflow and click **Execute Workflow** (or the "Execute node" button on a specific node). For webhook-triggered ones (`chain_mode`, `full_auto_mode`, `slack_notification`), click **Execute Workflow** once to arm the test URL, then POST to the listed webhook path.

## Demo flow walkthrough

1. `./scripts/demo_start.ps1` (or `.sh`) brings everything up.
2. Send an email with an RFP (PDF attached) to the address in `DEMO_EMAIL_USERNAME`.
3. Within 2 minutes, `discovery_email.json` polls Gmail, ingests the message (PDF text extracted), runs `/orchestrate` (which honors `config.mode`), and posts a Slack card if the fit score clears `SLACK_NOTIFICATION_THRESHOLD`.
4. In `full_auto` mode, high-scoring RFPs also trigger async drafting. `draft_completion_watcher.json` fires a "draft ready" Slack card 5-6 minutes later.
5. Click "Review in dashboard" in Slack to jump into the Streamlit UI (Phase 5 work).
6. Need to reset the demo? `./scripts/demo_reset.ps1` — under 60 seconds, clean slate with past proposals re-indexed.

## Demo flow walkthrough

_Section coming at Checkpoint 4._

## Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## Architecture deep-dive

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Credits

Built as a take-home case study. Scaffolding and infrastructure implemented with Claude Code; domain content (rubrics, prompts, sample proposals) authored separately.
