# SAM.gov integration: observed issues vs. implementation intent

_Written for the conversational assistant working the Checkpoint 1–2 content bundle. Date: 2026-04-23._

## What the Discovery agent was built to do

The Discovery agent (`services/api/agents/discovery.py`) is designed to:

1. Poll SAM.gov's public v2/search API on a schedule (n8n cron, 4 hr default) with a configured NAICS filter.
2. Dedupe incoming records by `sha256(solicitation_number + title)`.
3. Populate each record's `full_text` by following the `description` field (a URL) to SAM.gov's noticedesc endpoint.
4. Hand off to the Screening agent, which requires `full_text` — it's a required template variable in `screening_user.txt` (`{{rfp_full_text}}`) that Claude uses to ground every claim in the rubric.

Every other piece of the POC works fine: manual ingest (`POST /rfp/ingest`), PDF upload (`POST /rfp/upload`), RAG over past proposals, the Screening agent end-to-end (validated on a synthetic DHHS RFP → fit_score 82 / pursue), and all downstream persistence.

The automated ingest path is where reality and design diverge.

## Four concrete problems, observed 2026-04-23

### 1. Rate limits make iterative development painful

- Personal / test API keys are capped at **10 requests/day**.
- Our primary key has a higher ceiling (~1000/day) but was exhausted by exploratory keyword tuning.
- A single "prepare the demo corpus" pass costs at minimum `1 search + N description fetches` (one fetch per RFP). For the 5–8 RFPs the guidance doc targets, that's 6–9 requests minimum, leaving almost no room for iteration on a test key.

Implication: no way to use a test key for realistic work; easy to burn the primary key by mistake.

### 2. The `q=` keyword parameter doesn't filter the way the docs suggest

Behaviors observed:

- **Single-word keywords** (`q=data`, `q=modernization`, `q=analytics`) return *the same 20 records* as a no-keyword search of the same NAICS, in the same date-descending order. Suggests either silent no-op or such a loose match that every opportunity in NAICS 541511 contains the word somewhere.
- **Multi-word OR expressions with parentheses** (`q=(data platform) OR (analytics platform) OR (data warehouse)`) return **0 results** across the same NAICS codes and lookback window.
- Docs claim a Dismax query parser. Empirical behavior contradicts that.

Implication: we can't narrow the API-level search to "data-platform-flavored" RFPs. We have to pull broad NAICS batches and filter client-side — which is fine at moderate scale but multiplies the request count and amplifies problem 1.

### 3. The `description` endpoint is returning HTTP 500 for every record we tried

This is the biggest one.

- Search records expose a `description` field that is a URL, of the form
  `https://api.sam.gov/prod/opportunities/v1/noticedesc?noticeid=<GUID>`.
- Hitting that URL with `api_key=...` returns **500** with body:
  `{"errorCode":"INTERNAL SERVER ERROR","errorMessage":"Application has encountered some issues. Please retry again in some..."}`
- Tested on 4 different notice IDs — all 500.
- Tried alternate URL forms (`v1/noticedesc` without `/prod/`, `v2/noticedesc`) — both return **404**.
- This is a SAM.gov-side issue, not ours (the error message is their generic app-tier error, and the notices exist — the UI at `sam.gov/workspace/contract/opp/<GUID>/view` renders the full description without issue).

Implication: **we cannot programmatically populate `full_text`**. Without `full_text`, Screening cannot run — its prompt literally has no content to reason over. Step 3 of the pipeline is down, which blocks step 4.

### 4. NAICS 541511 is dominated by hardware/software sustainment, not data-platform work

NAICS 541511 (Custom Computer Programming Services) is the canonical code for custom software development and is what Meridian's `config/fit_rubric.yaml` treats as primary. But in the last 90 days on SAM.gov, the top records under 541511 are:

- Navy: Venom Software and GARMIN System Sustainment for F-5 aircraft
- Air Force: BOSS HW/SW MX Renewal
- VA: JERON Nurse Call Support
- DoD: LABVIEW Software Brand Name Development
- Air Force: Airfield Automated System Technical Support

That is — hardware vendors and legacy-system support, not data-platform modernization. 541512 and 518210 skew similarly. 541690 (scientific/technical consulting) is more promising but largely non-data (sanitary surveys, pharma studies, peanut standards verification).

Implication: even if we fix the API issues, the "obvious pursue" bucket that the rubric was calibrated against — $1.5M–$12M federal-civilian data-platform modernization — may be genuinely scarce in SAM.gov's public pipeline during this window. Procurement cycles vary; right now is apparently thin.

## What this means for the demo and Checkpoint 2

Current DB state:

- 6 real SAM.gov RFPs persisted. All have titles, agencies, due dates, `source_url` pointing to the sam.gov UI. **None have `full_text`** (because of problem 3).
- 2 synthetic RFPs already screened successfully (fit_score 82 pursue, validates the rubric works).

Checkpoint 2 asks the user to "test screening on real RFPs, iterate rubric." That hinges on having real RFPs with usable content. We currently can't get content programmatically.

## Options we're weighing

### A. Lean into the issue, adjust the demo narrative

Effort: minimal. Present Discovery as "designed, tested against real SAM.gov, with caveats we documented." Demo uses manually-uploaded RFPs for the actual screening flow. This is defensible — real proposal teams dealing with SAM.gov hit exactly these issues and build around them.

### B. Manual PDF / text ingestion for the demo corpus

Effort: 15–30 min of clicking. Open each `source_url` on sam.gov, download the PDF or copy the description text, feed through `POST /rfp/upload` or `POST /rfp/ingest`. Gets us real content in the DB. Doesn't scale but we only need 5–8 for calibration + demo.

### C. Scrape the sam.gov UI pages directly

Effort: a few hours, medium fragility. Each `source_url` we already store (e.g. `https://sam.gov/workspace/contract/opp/<GUID>/view`) renders the full description server-side. A BeautifulSoup pass would work today. But: sam.gov TOS likely prohibits scraping, and the HTML layout drifts. I'd want legal sign-off before making this the default path in a real product.

### D. GSA bulk-data dumps

Effort: medium. GSA publishes bulk opportunity data downloads periodically (different service, different auth). Fine for demo; not real-time. Worth investigating for a v2 of the POC.

### E. Switch source entirely

Effort: high. FPDS (Federal Procurement Data System) only covers awarded contracts, not open RFPs. Commercial alternatives (Bloomberg Gov, FedConnect) exist but require paid licenses. Overkill for a POC.

## What I'd recommend we talk through

1. **For Chris's demo Monday** — is A+B acceptable? The automated path is genuinely working modulo SAM.gov's own endpoint being broken; B gets us real content for the screening demo without pretending the API works better than it does.
2. **Should the rubric be retuned** — if the pursue-bucket RFPs really aren't in SAM.gov's current pipeline, the rubric's implicit assumption that "NAICS 541511 + certain keywords = pursue" may need softening, or the rubric needs examples beyond 541511.
3. **For ambiguous-bucket coverage** — we have 1–2 decent candidates in the DB already (DOC Cloud Services Strategy, FEC AWS RFI). Is that enough for calibration if we can't add the HHS Population Health one?
4. **Long-term reliability story** — if the project goes forward, what's the right source-of-truth? Option D (bulk downloads) is probably the answer, but that's a larger discussion.
