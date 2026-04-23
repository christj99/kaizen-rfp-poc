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
- _Optional:_ SAM.gov API key (free; register at https://sam.gov/content/api-keys)
- _Optional:_ Slack Incoming Webhook URL for discovery notifications
- _Optional:_ OpenAI API key for embeddings (used by the RAG indexer)

## Configuration

Behavior is driven by `config/config.yaml`. See that file for the full reference. Highlights:

- `mode` — `manual` | `chain` | `full_auto`
- `screening.threshold_pursue` / `threshold_maybe`
- `drafting.auto_draft_threshold`
- `sources.sam_gov.naics_filter`

## The four modes

_Section coming at Phase 4._

## Demo flow walkthrough

_Section coming at Checkpoint 4._

## Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## Architecture deep-dive

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Credits

Built as a take-home case study. Scaffolding and infrastructure implemented with Claude Code; domain content (rubrics, prompts, sample proposals) authored separately.
