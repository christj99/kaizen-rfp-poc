# Troubleshooting

Issues encountered during development with their diagnoses and fixes. Each entry follows: _what you see → why → what to do_.

---

## Stack startup

### `docker compose up` fails with "port is already allocated"

Another process is using 5432 (Postgres) or 5678 (n8n). Stop the conflicting process or change the port in `.env` (`POSTGRES_PORT`, `N8N_PORT`) and re-run `./scripts/demo_start.sh`.

### `pg_isready` never succeeds

Docker Desktop may not be running. Start it and retry. On Windows, confirm WSL 2 integration is enabled.

### `migrate.py` errors with "could not connect to server" / `psycopg2.OperationalError: ... server closed the connection unexpectedly`

The IPv6 trap. On Windows machines with WSL enabled, `wslrelay.exe` binds `[::1]:5432` and intercepts connections that resolve `localhost` to `::1` first. Fix: in `.env`, set `POSTGRES_HOST=127.0.0.1` (IPv4-explicit) instead of `localhost`. The default in `.env.example` is already `127.0.0.1` for this reason.

### FastAPI log says `ModuleNotFoundError: services`

You're running uvicorn from the wrong directory. `demo_start.sh` runs it from the repo root, which is required — `services` is a package rooted there.

### `./scripts/demo_start.ps1` halts mid-script with "NativeCommandError" referencing docker compose

PowerShell 5.1's `$ErrorActionPreference='Stop'` treats stderr lines from native commands as errors. `docker compose`'s progress output goes to stderr even on success. Already-fixed in `scripts/demo_start.ps1`, `demo_stop.ps1`, and `demo_reset.ps1` — they scope `$ErrorActionPreference='Continue'` around the docker calls. If you see this error again, the symptom is one of those scripts was edited and lost the scoping. The fix is in commit history.

### "ANTHROPIC_API_KEY not set" but the key IS in `.env`

`load_dotenv()` defaults to `override=False`. If your shell already exports the variable as an empty string, `.env` gets ignored. `services/api/_env.py` works around this by clearing empty-string env vars before `load_dotenv()` — but if you set the variable as truly empty in your shell after that import, it'll re-stick. Diagnose: `python -c "import os; print(repr(os.environ.get('ANTHROPIC_API_KEY')))"`. If it's empty, unset the shell variable explicitly.

---

## Postgres / data

### Tables come up empty after a Docker Desktop restart

Known incident pattern: when Docker Desktop's `com.docker.service` (the Windows service backing the daemon) crashes mid-run and the user restarts Docker, named volumes can survive but Postgres re-runs `initdb` on what it sees as an empty data directory. A clean `docker compose down` + `up -d` cycle (no service crash in between) preserves data correctly — verified before Phase 4 work.

**Mitigations:**
- Don't use `docker compose down -v` — that explicitly removes volumes.
- Keep the demo seed (`scripts/seed_data.sh`) ready to repopulate quickly.
- For demo day, pre-seed fresh just before going on stage.

### `pgvector` extension missing

The Phase 0 migration creates it (`CREATE EXTENSION IF NOT EXISTS "vector";`). If you're on a fresh container that hasn't run the migration: `python services/api/db/migrate.py`. The Postgres image is `pgvector/pgvector:pg16` which has the binary; the `CREATE EXTENSION` just registers it.

### `ivfflat` index complaints on small corpus

Removed in Phase 2 — sequential scan with `vector_cosine_ops` is exact and fast at POC scale. If you re-add the index for a larger corpus, set `lists` close to `sqrt(rows)` and bump `ivfflat.probes` per session before queries.

---

## SAM.gov

See [docs/sam_gov_issues.md](sam_gov_issues.md) for the full write-up. Quick reference:

- **`description` endpoint returns 500.** SAM.gov-side issue, not ours. Adapter falls back: status flagged as `needs_manual_review`, error preserved in `source_metadata.description_fetch_status`. Surface in the Dashboard's Needs Attention queue.
- **Daily quota exhausted.** Personal API keys cap at ~10 requests/day; production keys ~1000. Sleep until midnight UTC or use a different key.
- **`q=` keyword filter unreliable.** Single-word queries match everything; multi-word OR expressions match nothing. Don't depend on it; filter client-side after a NAICS-bounded pull.

---

## Email / IMAP

### `IMAP credentials missing` when no creds problem is obvious

Two checks: (1) `.env` has `DEMO_EMAIL_USERNAME` and `DEMO_EMAIL_PASSWORD` populated; (2) the password has no spaces. Gmail displays app passwords as four space-separated quartets ("buqu fysh gpxp nsux") for readability — strip the spaces before pasting into `.env`. The IMAP adapter strips internally too, but easier to keep `.env` clean.

### IMAP login succeeds in test but the `discovery_email` workflow finds nothing

`mark_as_read=true` in `config.yaml`'s `sources.email.adapters[0]` is the default. After the first successful pickup, messages are marked SEEN on the server and won't show up in the next `AND(seen=False)` fetch. To re-trigger: in Gmail, mark the message Unread, or send a fresh email.

### Streamlit shows email RFPs with `title='rfp'`

The normalizer uses the email's Subject line verbatim. If the sender wrote "rfp" as the subject, that's what the title becomes. Workaround: descriptive subject lines. Future: enable `sources.email.use_llm_extraction` for LLM-driven title cleanup (config flag exists; not implemented).

---

## n8n workflows

### Workflows fail to import via the API with "unknown field" errors

n8n 1.x rejects fields it doesn't expect on `POST /workflows` (e.g. `active`, `pinData`, `tags`). The importer (`scripts/import_n8n_workflows.py`) strips to the four canonical fields: `name`, `nodes`, `connections`, `settings`. If you imported manually and got rejections, use the importer.

### `import_n8n_workflows.py` halts with `UnicodeEncodeError` on Windows

cp1252 console can't encode em-dashes / arrows in workflow names. The importer reconfigures `sys.stdout` / `sys.stderr` to UTF-8 at startup; if you see this error, you may have an older copy of the script. Pull latest.

### Webhook-triggered workflow returns 404

The webhook URL only resolves when the workflow is **active**. Check the toggle in the top-right of the workflow editor. The importer's `--activate` flag turns on the three scheduled/sub-workflows by default (`Discovery — Email`, `Draft completion watcher`, `Slack ingest notification`). Webhook test workflows (`chain_mode`, `full_auto_mode`, `slack_notification`) stay inactive by design — activate manually if you want them.

### Watcher fires duplicate Slack cards

Shouldn't happen with the per-job-id dedupe (workflow staticData). If it does: open the watcher in n8n → top-right kebab → **Reset workflow's persisted data**. That clears `notifiedJobIds`. Next run will treat all completed/failed jobs in the 15-min window as new and re-fire — accept those duplicates and the dedupe will catch up from there.

### Watcher's "draft ready" Slack card has no Download .md button

The button uses a hard-wired `http://localhost:8000` URL because `KAIZEN_API_URL` is `http://host.docker.internal:8000` (resolvable inside the n8n container, not from the user's browser). If your demo runs on a non-default API port, edit the `Format draft-ready Slack` Code node in `draft_completion_watcher.json` and re-import.

---

## Streamlit

### Sidebar shows extra entries (app, chat, dashboard, ...) that look like file-based pages

Streamlit auto-discovers a sibling `pages/` directory next to the entry script and turns each `.py` file into a sidebar item, *bypassing* `st.navigation`. We renamed the directory to `screens/` to prevent this. If you renamed it back to `pages/`, undo that.

### `StreamlitAPIException: Multiple Pages specified with URL pathname render`

`st.Page(callable, title=..., ...)` infers the URL pathname from the callable's name. If every page module exports a function called `render`, all six pages collapse to the same URL. Pass an explicit `url_path=` to each `st.Page`. Already done in `services/ui/app.py`; if you see this, you removed the `url_path` args.

### `ImportError: attempted relative import with no known parent package` on every page

Streamlit runs `app.py` as a script, not as a Python package, so `from .. import api_client` raises. Fix: bare imports, with `services/ui/` on `sys.path`. The first lines of `app.py` insert it. Pages do `import api_client` and `from components import ...` — bare names. Don't switch back to relative imports.

### Material icons render as literal text

Streamlit's `:material/icon_name:` syntax only works in widget labels, `st.tabs` labels, and `st.markdown` *without* `unsafe_allow_html`. Inside raw HTML strings (e.g. `st.markdown("<div>:material/inbox:</div>", unsafe_allow_html=True)`) the syntax is not parsed and renders as text.

For HTML contexts: use plain Unicode emoji (📥, ✅, ⚠, ⏳). The `empty_state()` component does this. The Markdown-export anchor in RFP Detail does too.

---

## Drafting

### Draft job stuck in `running` for >7 minutes

The draft is probably still drafting. Sonnet 4.5 with `max_tokens=32000` on a substantive RFP can take 4-6 minutes per call; if the LLMClient retries on a non-JSON response, that's another 4-6 minutes. Wait it out — the watcher will fire when it terminates.

If a job's been `running` for >12 minutes with no progress, uvicorn likely lost the BackgroundTasks worker (e.g. process killed). Mitigation:

```sql
UPDATE draft_jobs SET status='failed',
  error_message='worker disappeared (likely uvicorn restart)',
  completed_at=NOW()
WHERE id='<job_id>';
```

Then re-trigger via the UI's Generate-draft button.

### "Streaming is required for operations that may take longer than 10 minutes"

Anthropic SDK refuses non-streaming requests when `max_tokens` could exceed a 10-minute budget at the model's expected token rate. The LLMClient now uses streaming for every call (`messages.stream` → `get_final_message()`); no plumbing change downstream. If you see this, you reverted that change.

### Failed draft has no Slack signal

The watcher in `draft_completion_watcher.json` queries terminal-status jobs (completed OR failed) and branches on `job.status` to format different cards. If you only see `:memo: Draft ready` cards and never `:warning: Draft failed`, the workflow may not be the latest version. Re-run `python scripts/import_n8n_workflows.py --activate`.

---

## Quick "is everything alive?" check

```bash
# Containers
docker ps --format "{{.Names}}: {{.Status}}"

# API
curl -sf http://localhost:8000/health

# Streamlit
curl -sf http://localhost:8501/healthz

# n8n (only if you imported workflows)
curl -sf -u admin:change-me http://localhost:5678/healthz
```

If any return non-zero, that's the layer to chase first. The full e2e test (`./scripts/test_end_to_end.sh`) does this plus exercises every ingestion path + screening + drafting; ~7 minutes if everything's working.
