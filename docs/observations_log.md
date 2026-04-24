# Observations log — for the content / calibration assistant

Things Claude Code has noticed during implementation that the conversational
assistant (working on rubric, prompts, and demo narrative) should weigh in on.
Grouped by category, newest at the top within each section. The companion
write-up for the SAM.gov API specifically lives in [sam_gov_issues.md](sam_gov_issues.md).

---

## Calibration datapoints (feed into rubric discussion)

### 2026-04-23 — DOC Cloud Services Provider Vehicle Strategy (email)

Sent as an email with `SAM.govDOCRFP.pdf` attached. Ingested via the email
adapter; PDF extracted to 4,348 chars of full_text.

**Screening output:**
- `fit_score = 12`, `recommendation = skip`, `confidence = high`, `effort_estimate = None`
- Triggered disqualifier: **hd_out_of_domain** — "procurement is for native hyperscale cloud infrastructure services from OEM providers (AWS, Azure, GCP); Meridian is a systems integrator, not a hyperscale CSP"
- Three high-severity deal breakers:
  1. "Meridian is not an Original Equipment Manufacturer Cloud Service Provider"
  2. "This is a Special Notice announcing procurement strategy, not a solicitation requesting proposals"
  3. "Contract scale ($4.1B over 10 years) is 160x our absolute maximum capacity"
- Zero open questions
- Three similar past proposals surfaced, all tagged **weak** relevance (Maryland DHS, CMS, DOC Trade Data Phase II)

**Why this matters for calibration:**
This was pre-classified as an *adjacent / ambiguous-pursue* candidate based on
title alone (Commerce + cloud + strategy). The rubric correctly identified it
as **skip** for substantive reasons — not just keyword mismatch. Worth showing
as a "the rubric does something smarter than title-matching" demo moment.

**Questions for the assistant:**
1. Is `hd_out_of_domain` the right disqualifier bucket for "RFP is for a *different kind of vendor* (hyperscaler vs. integrator)"? Or does that deserve its own disqualifier?
2. The "Special Notice vs. real solicitation" distinction came through as a deal breaker, not a disqualifier. Should it be a hard disqualifier? (Arguably no — sometimes Special Notices are actionable market research opportunities.)
3. Contract-scale (160x) triggered a deal breaker but not the `hd_contract_value_floor` check. The floor is about minimum; we don't have a ceiling disqualifier. Is "too big" a hard disqualifier or just a deal breaker? Current rubric only has a floor.

---

### 2026-04-24 — Phase 4 retrospective (themes for content/demo)

**Calibration decisions applied empirically, not theoretically (all ✅ landed in code):**
- Slack notification threshold **75 → 50**. Maybe-band screenings (50-74)
  are where the agent's emergent reasoning is most striking; gating Slack
  at 75 hid them.
- `auto_draft_threshold` **90 → 80**. At 90 full_auto silently no-op'd on
  every realistic pursue. 80 matches the plan's "obvious pursue" band.
- `mode` default = `manual`. Honest deployment story; hot-reload makes
  the live mode-flip a low-cost demo moment.

**Live-only failure modes that wouldn't have shown on synthetic data — all ✅ resolved:**
- Anthropic SDK refuses non-streaming requests when `max_tokens` could
  push the call past 10 min. → `LLMClient._call_with_retries` now
  always uses `messages.stream()`. Same final text + usage shape
  downstream; no surprises on small calls; unblocks the long ones.
- Drafting at `max_tokens=16000` truncates mid-section on substantive
  RFPs. → bumped to 32000. Sonnet 4.5 ceiling is 64000, so still
  conservative.
- Three n8n data-shape bugs in one workflow (sliding since-marker
  race, splitOut on a non-existent `.data` field, draft_id source
  confusion in the format node). → fixed-window + per-job dedupe in
  staticData; splitOut removed (httpRequest already auto-splits
  arrays); draft_id pulled via `$('Filter unsent').item.json`. All
  only visible from actual `runData` on a real execution. **Lesson
  worth keeping for future n8n work:** never trust assumed shape;
  inspect a real execution before wiring downstream nodes.

**Demo-side observations worth keeping (mix of ✅ and open):**
- ✅ The drafting agent reads the screening verdict and produces a
  no-bid response when screening is skip, a real proposal when it's
  pursue. Emergent from the prompt design, not coded — strong
  narrative beat for the demo.
- ✅ The 📥 ingest card matters more than expected. Without it
  manual mode reads as a dead pipeline; with it, even a `skip` RFP
  produces a visible "something landed" signal.
- ⏳ **Open:** failed draft jobs are silent — no Slack card on
  `status='failed'`. Watcher only handles `completed`. Worth a
  follow-up "draft failed" notification before the demo so an
  invisible failure on stage is impossible.
- ✅ Full pipeline timing for a clear-pursue full_auto run, observed
  end-to-end: ingest card ~1-2 min, screening card ~3-4 min,
  draft-ready card ~8-10 min. Cron interval (2 min) + screening
  (~80s) + drafting (~5 min) + watcher tick (30s) account for
  almost all of it.

### 2026-04-24 — Drafting max_tokens bumped 16000 → 32000  ✅ FIXED

Live full_auto run on a real Treasury / Fiscal Service "Cloud Data
Warehouse Modernization" RFP failed the drafting step. Both the first
Claude call and the auto-retry returned valid JSON that was truncated
mid-string in the very first section (Cover Letter), tripping
``LLMClient._parse_json``'s "non-JSON twice" terminal failure. Job
ended at ``status='failed'`` with the response excerpt preserved in
``error_message`` for postmortem.

Root cause: ``max_tokens=16000`` wasn't enough headroom for an
8-section first-draft proposal on a substantive RFP. Empirical draft
sizes:
- Lightweight RFPs (DHHS Benefits Warehouse synthetic):     ~7-8k tokens
- DOC Cloud Services no-bid response:                       ~2k tokens
- Cloud Data Warehouse / Fiscal Service (truncated):        > 16k tokens

**Resolution:** Bumped ``_DRAFT_MAX_TOKENS`` to 32000 — comfortable 2-3×
headroom on realistic pursue-band drafts. Sonnet 4.5's ceiling is 64000.
Bumping uncovered a follow-on issue (SDK refuses non-streaming requests
above the implicit 10-min budget) which forced switching the LLMClient
to streaming — that's now the default for every call. Re-fired the
same Cloud DW draft and it completed cleanly in ~4m25s, 8 sections,
50KB markdown export.

**Demo-side implication (⏳ still open):** When drafting fails, the user
has no Slack signal — the draft_completion_watcher only fires "draft
ready" cards on ``status='completed'``. Failed jobs sit silently in
``draft_jobs`` with ``error_message`` populated. Worth surfacing as a
"draft failed" Slack card from the watcher so a real failure during
the demo doesn't stay invisible.

### 2026-04-24 — Slack notification threshold lowered from 75 → 50  ✅ APPLIED

Maybe-scored RFPs (fit 50–74) tend to surface the strongest *emergent*
reasoning from the screening agent — temporal-incoherence catches (e.g.
"RFP appears to be from 2021 with response deadline of June 28, 2021, but
current date is April 24, 2026"), document-type inference (Special Notice
vs. solicitation), and nuanced deal-breaker identification. At threshold
75 those signals were hidden in the dashboard; at 50 they land in Slack.

**Resolution:** dropped `slack.notification_threshold` to 50 in
`config/config.yaml` and the `SLACK_NOTIFICATION_THRESHOLD` default in
`docker-compose.yml`. Threshold is a config value, not hardcoded — teams
with higher volume can raise it to 60–75 once they trust the agent's
calibration, no code change required.

### 2026-04-24 — Manual-mode ingestion visibility  ✅ FIXED

Under `mode: manual` RFPs ingest silently: DB entry, one `discovery_ingest`
audit row, no Slack signal until a human triggers screening. During
demonstration or for teams just rolling this out, that looks like a dead
pipeline even when it's working correctly.

**Resolution:** added a "📥 New RFP ingested" Slack card that fires
regardless of mode, implemented as a shared webhook-triggered sub-workflow
(`services/n8n/workflows/slack_ingest_notification.json`) that
`discovery_email.json` and `discovery_sam_gov.json` both call in parallel
with the screening path. In chain/full_auto mode you'll see two cards per
RFP — the first says "something landed," the second says "here's what we
think about it." That's intentional: ingest visibility is separate from
screening visibility.

### 2026-04-24 — Config hot-reload on mtime  ✅ APPLIED

**Resolution:** `services/api/config/loader.py` now stats the config file on
every `get_config()` call and reloads when mtime changes. Effect:
`config.mode` edits (and everything else in `config.yaml`) take effect on
the next API call without a uvicorn restart — so the demo-time mode flip
between `manual` / `chain` / `full_auto` is a visible operational-
maturity moment rather than a "give me 30 seconds while I restart the
backend." Thread-safe via the existing RLock.

### 2026-04-24 — Postgres volume survived a Docker Desktop restart, but tables came up empty  ⏳ PARTIALLY ADDRESSED

Mid-Phase-3B build, Docker Desktop's `com.docker.service` (the Windows
service backing the daemon) stopped — every `docker` command hung. User
restarted Docker Desktop. Afterward, the named volumes `kaizen_postgres_data`
and `kaizen_n8n_data` still existed (`docker volume ls`), but `SELECT COUNT(*)`
on every user-facing table returned 0. The Phase 1/2/3 smoke-test data
(12 RFPs + 2 drafts + screenings) was wiped. Past-proposal data had to
be re-indexed via `python -m services.api.rag.indexer`.

**Hypothesis:** when containers are recreated against a "present but
unreadable" volume, Postgres's entrypoint reruns `initdb` on the empty
mount. Docker's volume pointer survived but its contents didn't. Possibly
triggered by running `docker compose down` while the daemon was in a
half-dead state.

**Status:**
- ✅ **Pre-flight verified at start of Phase 4:** a clean `docker compose
  down` + `up -d` cycle preserves the volume identically (12 RFPs, 4
  past proposals, 2 drafts all round-tripped). The data-loss path is
  specifically the *Docker Desktop service crash* path, not normal
  compose lifecycle.
- ✅ **PowerShell scripts hardened.** `scripts/demo_start.ps1` and
  `demo_stop.ps1` were halting mid-script because `docker compose`'s
  progress lines go to stderr and `$ErrorActionPreference = 'Stop'`
  was treating them as terminating errors. Fixed by scoping
  `$ErrorActionPreference = 'Continue'` around the docker calls.
- ✅ **`scripts/demo_reset.{sh,ps1}`** added in Phase 4 — TRUNCATE +
  re-index past proposals + restart in 37 s. The "oh no" button.
- ⏳ **Still open as a demo-day risk:** if Docker Desktop crashes
  during the demo, the volume could come back empty per the original
  hypothesis. Mitigation = pre-seed fresh just before going on stage
  (Phase 7 supplemental's plan) + the recorded backup video.

### 2026-04-23 — Drafting agent smoke runs (Phase 3 Checkpoint 3)

Ran the drafting agent end-to-end on two RFPs already in the DB.

**DOC Cloud Services — screening said skip, drafting produced a no-bid response:**
All 8 sections flagged for review with notes like "This is a no-bid letter
rather than a proposal. The RFP is a Special Notice..." The agent correctly
read the screening's skip verdict and pivoted to a no-bid response rather
than producing a proposal Meridian wouldn't want to submit. Good
behavioral alignment between screening and drafting — worth calling out in
the demo as "the drafting agent respects the screening agent's verdict".

**DHHS Benefits Warehouse (synthetic) — screening pursue, drafting produced a full proposal draft:**
- 7432 words across 8 sections; 2 past proposals retrieved and cited as
  `provenance.source_ids`
- Per-section provenance correctly matched the template's
  static/semi_static/dynamic classification
- **Anti-hallucination behavior was excellent**:
  - Pricing Narrative: confidence=0.30, "CRITICAL: framework only, pricing
    team must populate specific rates"
  - Staffing Plan: confidence=0.60, "CRITICAL: Must insert specific named
    personnel with detailed resumes"
  - Cover Letter: review-flagged for missing date + solicitation number
- 6 of 8 sections flagged `human_review_required: true` with specific,
  actionable notes. Overall confidence_summary: medium.

**Demo implications:**
- The dual run (no-bid vs. full draft) is a good story: the drafting agent
  isn't just a template filler; it reads context from screening.
- Per-section confidence grading is useful — reviewers can sort by
  confidence ascending to know what to scrutinize.
- Review notes are specific enough to turn into a checklist for the
  proposal lead.

**Open question for the demo narrative:** do we lead with the pursue case
(showing rich draft quality) or the skip case (showing smart behavior)?
The no-bid path is less expected and arguably more memorable, but the
pursue path shows the craft.

### 2026-04-23 — Drafting call latency  ✅ FIXED via Phase 3B async drafting

Drafting takes **5-6 minutes per call** on a realistic RFP (DHHS Benefits
Warehouse → 7432 words, ~5m 40s end-to-end). At the time this was a
problem because:

- `httpx` default 300s timeout was hit in smoke test — caller timed out
  while the server finished in the background (persisted correctly).
- For n8n workflows and the Streamlit UI, we'd want either (a) bumped
  client timeouts to 600s, or (b) drafting as a background job with
  polling, or (c) a "this will take a few minutes" UX state.

**Resolution:** Phase 3B implemented option (b). `POST /rfp/{id}/draft`
gained `?mode=async|sync` (default async) — async returns a `job_id`
immediately and runs drafting via FastAPI `BackgroundTasks`; sync
preserves the original blocking behavior as a deterministic demo
fallback. New `draft_jobs` table tracks status (queued | running |
completed | failed). New `GET /draft/job/{id}` and `GET /draft_jobs`
endpoints power the n8n `draft_completion_watcher` workflow that fires
the "draft ready" Slack card on completion. Both async and sync paths
verified end-to-end. ``max_tokens=16000`` was later bumped to 32000 +
streaming switched on (see entry above) once we hit a real RFP that
exceeded that budget.

### 2026-04-22/23 — Synthetic DHHS Benefits Warehouse (manual ingest)

Pre-screening test RFP I constructed to validate the pipeline end-to-end.

**Screening output (first run, max_tokens=4096):** ✅ **FIXED** — truncated
JSON — the agent errored with "Claude returned non-JSON response twice."
Resolved by bumping `llm.max_tokens` from 4096 → 8192 (Screening JSON is
rich enough to overflow 4096 on real RFPs). Worth flagging to the
assistant: the prompt's JSON schema may be denser than the 4096 default
implicitly assumed. Drafting later hit the same class of issue and got
its own bump to 32000 + streaming (separate entry above).

**Screening output (8192-token run):** `fit_score=82, pursue, medium
effort, confidence=high`. Dimensions weighted reasonably. Rubric version
`1.0`. Good sanity baseline.

---

## Limitations in extraction / parsing (deferred; flag if unacceptable)

### NAICS regex false positives on email ingestion ~~(unfixed)~~ **fixed 2026-04-23**

Original behavior: the email normalizer used `\b(\d{6})\b` and extracted
`['202612', '518210']` from the DOC Cloud RFP — only `518210` is real NAICS.

**Fix (commit on 2026-04-23):** two-pass extractor in
`services/api/agents/discovery/normalizer.py::_extract_naics`.
- Pass 1: proximity match — codes within ~20 chars after the word "NAICS"
  (case-insensitive). Highest confidence.
- Pass 2: sector-prefix-validated fallback — a 6-digit token is accepted only
  if its first two digits are a valid NAICS sector (11, 21, 22, 23, 31-33,
  42, 44-45, 48-49, 51-56, 61-62, 71-72, 81, 92). Sectors 20, 99, etc. are
  silently rejected.

Re-ran extraction on the stored DOC Cloud `full_text` — now returns
`['518210']` cleanly. 7 synthetic unit cases all pass.

LLM-based extraction is still reserved behind
`sources.email.use_llm_extraction` (default off). The regex approach is
sufficient for the current demo corpus.

### Email subject → RFP title verbatim

The normalizer sets `rfp.title = email.subject` as-is. When you sent the DOC
RFP with subject just `"rfp"`, the title in the DB is `"rfp"` (useless for the
Dashboard list view). No cleanup / enrichment happens.

**Options:**
- Leave as-is and tell users to write descriptive subjects (cheapest)
- Look for a `### ` header or `Subject:` pattern in the *body* and prefer that
- LLM extraction (same flag as above) — low-confidence field, good fit
- Prepend/append sender info for disambiguation (`"[k.rfp.cs.26] rfp"`)

### Email-body-only messages (no attachment)

Current adapter handles text body + PDF attachments. Word docs, RTFs, ZIPs of
RFP packages are not touched. If the team forwards procurement-portal
notifications where the RFP is attached as `.docx`, we'll lose it.

**Options:** add `.docx` extraction via `python-docx` (small addition). Not
urgent unless the demo corpus includes them.

---

## Content-format quirks we've already fixed (FYI, for future bundles)

### proposal_template.yaml — unquoted `|` in provenance_tagging

The `provenance_tagging` block used lines like
`- "generated" | "retrieved_from_past_proposal" | ...`
which broke `yaml.safe_load` because `|` is YAML's block-scalar indicator.
Wrapped each line in single quotes so it parses as a literal string. Content
is preserved; no meaning changes.

**FYI for the assistant:** if future YAML blocks document allowed enum values
with `|` separators, wrap them in quotes or use a comment instead.

### PastProposal.sections — fixed-field model was too strict

The Phase 1 pydantic `ProposalSections` had fixed fields
(`exec_summary`, `qualifications`, `technical`, `pricing`, `attachments`)
that didn't match the real section names in the delivered past proposals
(`Executive Summary`, `Company Qualifications`, `Past Performance`,
`Technical Approach`, `Staffing Plan and Key Personnel`, `Pricing Narrative`,
`Supporting Attachments`, and the `LESSONS LEARNED` bonus on PP-2024-019).
Changed to `sections: Dict[str, str]` so the content team isn't constrained
to a fixed shape.

**Implication:** the drafting template (`config/proposal_template.yaml`)
defines the canonical section set going forward. Section names there should
match what past proposals actually use, so RAG retrieval "reusable_sections"
lines up.

---

## Open questions for the content / demo side

### Is email-primary OK for the demo narrative?

SAM.gov was the original primary. The supplemental plan downgraded it to
secondary because of documented API issues (see [sam_gov_issues.md](sam_gov_issues.md)).
Email is now `primary: true` in `config/config.yaml`. The demo story should
center on email with SAM.gov as "we designed for multi-source; here's the
secondary adapter working too."

**Question:** does the demo narrative / deck still treat SAM.gov as the
headline source? If so, it probably should be rewritten to lead with email.

### LLM extraction default — off vs. on for the demo?

Config flag `sources.email.use_llm_extraction` is reserved (currently
unimplemented but wired into the loader). Turning it on would improve the
NAICS / title / due-date extraction significantly, at the cost of one extra
small Claude call per email.

**Question:** for the demo, do we want the "look, Claude extracted the NAICS
from the RFP text" moment, or is the regex-level extraction enough?

### Should we handle "not an RFP" emails explicitly?

Gmail system messages (security alerts, setup prompts) that land in the inbox
get ingested as `source_type=email` RFPs with nonsense titles. Screening
correctly returns `fit_score=0 / skip` on them, which is graceful. But they
clutter the RFP list.

**Options:**
- Filter in the IMAP adapter by sender allowlist / subject regex (boring but
  works)
- Let screening mark them as `status='dismissed'` automatically when
  `fit_score < 5` (auto-triage policy question)
- Leave as-is and let users dismiss manually (consistent with real-world
  inbox noise)

### Contract-size ceiling as a hard disqualifier?

Current rubric has `hd_contract_value_floor` (too small) but no ceiling. The
DOC Cloud RFP ($4.1B) surfaced this as a deal breaker rather than a
disqualifier. Do we want a `hd_contract_value_ceiling` at some multiple of
Meridian's target range? That'd be consistent with the "we can't bid if..."
framing.

---

## Things appended after this was written

_(reserve space for Chris to log new things as they come up during
calibration and Phase 3+ work)_
