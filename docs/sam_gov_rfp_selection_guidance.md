# SAM.gov RFP Selection Guidance for Testing

## Purpose

You need 5-8 real SAM.gov RFPs as your test corpus. The screening agent needs to run on real data so you can calibrate the rubric and demonstrate realistic outputs in the demo. This guide tells you exactly how to find the right RFPs and which ones to use.

## Registration

Register for a free SAM.gov API key at https://open.gsa.gov/api/get-opportunities-public-api/. Takes about 10 minutes. Add to your `.env` as `SAM_GOV_API_KEY`.

## Search strategy: three buckets of RFPs

You want a spread of RFPs that will produce meaningfully different screening outputs. The rubric is only as credible as the variation it shows, so you want RFPs that clearly pursue, clearly skip, and genuinely sit in the middle.

### Bucket 1: Obvious "pursue" candidates (2-3 RFPs)

These should score 80+ and cleanly map to Meridian's sweet spot. Criteria:
- NAICS code: **541511** (Custom Computer Programming), **541512** (Computer Systems Design), or **518210** (Computing Infrastructure)
- Value range: **$1.5M - $12M** (Meridian's sweet spot)
- Scope keywords: "data warehouse," "data platform," "ETL," "data modernization," "analytics," "Snowflake," "dbt," "data pipeline"
- Set-aside: **Small business** or **Total small business** (Meridian qualifies)
- Agency: federal civilian preferred (Commerce, HHS, DHS, Treasury, Education)
- Due date: at least 30 days out

**How to find them on SAM.gov:**
```
Keywords: "data modernization" OR "data platform" OR "analytics platform"
NAICS: 541511, 541512
Set-aside: Small Business Set-Aside (FAR 19.5)
Posted Date: Last 30 days
Response Deadline: More than 30 days from today
```

### Bucket 2: Obvious "skip" candidates (2-3 RFPs)

These should score below 50 and/or trigger hard disqualifiers. Criteria (pick 2-3 that hit different failure modes):

- **Too big:** Value over $25M - triggers our value ceiling
- **Wrong NAICS:** 561210 (Facilities Support), 236220 (Commercial Construction), or 492110 (Couriers) - outside our capability set
- **Clearance mismatch:** Requires TS/SCI facility clearance - triggers hard disqualifier
- **Wrong set-aside:** 8(a) set-aside - triggers hard disqualifier
- **Too small / too short:** Sub-$250K or less than 7 days to respond

**How to find them on SAM.gov:**
Look for RFPs that would obviously not fit. One good target: any DoD intelligence community RFP with TS/SCI requirements. Another: any facilities management or construction RFP. Another: any 8(a) set-aside data engineering RFP (we don't qualify).

### Bucket 3: Ambiguous middle (1-2 RFPs)

These should score 55-75 and generate genuine open questions and deal-breakers. Criteria:
- Adjacent NAICS (e.g., 541690 Scientific/Technical Consulting)
- At the edges of our value range ($250K-$500K or $15M-$25M)
- Mixed scope (data components plus out-of-scope components)
- Federal defense agencies (less common for us than civilian)
- Stretch past-performance match

**These are the most valuable RFPs for the demo.** They show the rubric producing nuanced output with clear reasoning and flagged uncertainty. A score of 68 with three open questions is a better demo moment than a score of 92 with no questions.

## Specific recommendations

I can't hand you exact solicitation numbers because SAM.gov opportunities expire and rotate constantly. But here's what to do Saturday morning:

1. **Go to https://sam.gov/search/?index=opp** (the opportunity search).

2. **Filter by NAICS 541511 in the advanced filters.** Set status to "Active" and response due date to "Next 60 days."

3. **Scan the first page for good matches.** You're looking for titles that include words like "data platform," "modernization," "analytics," "warehouse," "cloud migration," or "pipeline."

4. **For each candidate, check:**
   - Does it clearly fit Meridian's capabilities?
   - Is it in our value range?
   - Is the response due far enough out that we'd have time?
   - Are there set-aside restrictions we fail?

5. **Save the full opportunity as a PDF** (SAM.gov has a download button) for each one you pick. Also note the solicitation number, agency, and response due date for the ingestion schema.

6. **Repeat for the "skip" bucket** with different filters - facilities management, construction, or RFPs with TS/SCI requirements.

## A concrete suggestion for where to look for the ambiguous middle

Look at recent **Sources Sought** or **RFI** notices on SAM.gov. These are pre-solicitation notices where agencies are gauging market interest before formally releasing an RFP. They tend to have messier scope descriptions and are genuinely harder to score cleanly. This is exactly the flavor you want for the ambiguous middle bucket.

## Backup plan if SAM.gov is frustrating

If you can't find enough good RFPs on SAM.gov in 30 minutes of browsing, here are two backup paths:

**Path 1: Use archived/expired RFPs.** SAM.gov shows historical opportunities too. An RFP from 2024 that's since been awarded is fine for demo purposes - we're not actually bidding, we're demonstrating the screening. The ingestion code should be date-agnostic.

**Path 2: Fabricate one plausible RFP and be transparent about it.** If you really need one more and can't find it, compose a realistic RFP text by combining elements from real ones. Note in the demo that one of your test RFPs is synthesized. This is defensible given the time constraint and focuses attention on the screening logic rather than the ingestion.

## Once you have your RFPs

Save them as individual files in `sample_data/rfps/` with this naming convention:
- `rfp_pursue_01_<short_title>.pdf`
- `rfp_pursue_02_<short_title>.pdf`
- `rfp_skip_01_<short_title>.pdf`
- `rfp_middle_01_<short_title>.pdf`

The naming makes your demo flow easy to orchestrate - you can immediately grab a "pursue" example when you want to show a strong screen.

## Expected screening outputs to calibrate against

Before you start screening, here's roughly what the rubric should produce for each bucket. If actual outputs diverge wildly from these expectations, the rubric needs calibration.

| Bucket | Expected fit_score | Expected recommendation | Expected confidence |
|---|---|---|---|
| Obvious pursue | 78-92 | pursue | medium-high |
| Obvious skip (value too big) | 30-55 | skip | high |
| Obvious skip (wrong NAICS) | 15-40 | skip | high |
| Obvious skip (TS/SCI) | any | skip (hard disqualifier) | high |
| Ambiguous middle | 55-74 | maybe | low-medium |

If a clear pursue is scoring below 75, the rubric is too strict. If an obvious skip is scoring above 60, the rubric is too loose or the hard disqualifiers aren't triggering.

## When you're ready to calibrate

Once you've run screening on your 5-8 RFPs, come back to the conversational assistant with the outputs. Specifically share:

- The RFP title and brief description for each
- The fit_score and recommendation the agent produced
- Any outputs that surprised you (too high, too low, weird reasoning)

The assistant will help you adjust the rubric weights, sharpen the scoring guidance, or revise the prompts to produce more consistent, calibrated output. This is Checkpoint 2.
