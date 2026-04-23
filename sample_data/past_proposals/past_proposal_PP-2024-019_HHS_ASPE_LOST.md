# Past Proposal PP-2024-019
# Meridian Data Solutions - Proposal for HHS Office of the Assistant Secretary
# for Planning and Evaluation (ASPE) - Predictive Analytics Pilot
# OUTCOME: LOST (important for rubric calibration)

metadata:
  proposal_id: "PP-2024-019"
  title: "Predictive Analytics Pilot for Policy Research"
  client: "HHS Office of the Assistant Secretary for Planning and Evaluation (ASPE)"
  solicitation_number: "75P00124Q00088"
  submitted_date: "2024-06-21"
  award_date: "2024-08-14"
  contract_value_bid: 2_800_000
  period_of_performance: "18 months with one 12-month option"
  outcome: "lost"
  loss_reason: "Past performance relevance - incumbent (Mathematica Policy Research) had 12 years of direct HHS ASPE research work; our healthcare data engineering experience did not translate to policy research evaluation"
  role_bid: "prime"
  naics: "541690"
  contract_vehicle: "open competition"
  key_themes:
    - "federal civilian"
    - "machine learning"
    - "predictive analytics"
    - "policy research"
    - "healthcare"
    - "LOST - past performance mismatch"
    - "stretch bid"

lessons_learned:
  - "NAICS 541690 (scientific/technical consulting) is policy-research-flavored, not data-engineering-flavored. Our past performance in 541511/541512 does not translate as cleanly as we assumed."
  - "Incumbent advantage on research-evaluation work is very strong. Bidding against a 12-year incumbent without a differentiated technical approach is low-probability."
  - "Our ML/predictive analytics capabilities are real but less deep than our data engineering capabilities. We bid as if they were equivalent. They are not."
  - "For future bids in this space, we should either partner with an established research firm (as subcontractor) or pass."

---

## Executive Summary

Meridian Data Solutions is pleased to submit this proposal to the HHS Office of the Assistant Secretary for Planning and Evaluation (ASPE) in response to solicitation 75P00124Q00088 for the Predictive Analytics Pilot for Policy Research. This engagement will develop predictive models to support ASPE's policy evaluation research, with an initial focus on Medicare readmission patterns.

Meridian brings a proven data engineering foundation and an emerging machine learning and predictive analytics practice. Our team has delivered four prior ML-focused engagements across federal civilian agencies, and our ongoing CMS healthcare data pipeline modernization work positions us with deep understanding of the healthcare data landscape that underpins ASPE's research.

Our technical approach emphasizes rigor, reproducibility, and explainability. All models will be developed with full documentation of training data, feature engineering decisions, and validation approaches, enabling ASPE researchers to reproduce, extend, and defend the analytical conclusions derived from our work.

## Company Qualifications

Founded in 2015 and headquartered in Silver Spring, Maryland, Meridian Data Solutions employs 118 data engineers, architects, and analysts focused exclusively on government data modernization. Our firm holds an active Secret facility clearance, ISO 9001:2015 and ISO 27001:2022 certifications, and delivers against a CMMI Level 3-appraised process framework.

Meridian's growing applied machine learning practice is led by Dr. Aisha Nakamura, Principal Data Scientist, who joined Meridian in 2023 from the U.S. Census Bureau's statistical modeling team. Our ML team includes 7 data scientists and ML engineers, with experience spanning classical statistical modeling, gradient-boosted models, and modern LLM applications.

Our healthcare data expertise is grounded in our ongoing subcontract work for HHS CMS on Medicare and Medicaid data pipeline modernization (begun 2021, currently in its second extension period). Through that engagement, our team has developed deep familiarity with CMS claims data structures, Medicare beneficiary data, and the federal reporting obligations that constrain healthcare data analysis.

## Past Performance

Meridian's past performance relevant to this predictive analytics engagement includes:

### HHS CMS Healthcare Data Pipeline Modernization (2021-Present)

**Contract Value:** $6,100,000 (Meridian's portion)
**Role:** Subcontractor to Booz Allen Hamilton
**Relevance:** Direct familiarity with CMS claims data, beneficiary data, and federal healthcare data infrastructure. Meridian has built the pipelines that serve the data ASPE's research programs rely on.

### U.S. Department of Agriculture Food Safety Predictive Analytics (2022)

**Contract Value:** $1,100,000
**Role:** Prime
**Period:** 10 months
**Relevance:** Delivered predictive models for food safety inspection prioritization. Demonstrates Meridian's ability to deliver end-to-end predictive analytics engagements for federal civilian agencies.

### Maryland Department of Health Opioid Response Analytics (2021)

**Contract Value:** $800,000
**Role:** Prime
**Period:** 9 months
**Relevance:** Developed predictive models for opioid overdose hot spot identification. Demonstrates applied ML capability in a healthcare domain.

## Technical Approach

Our approach to the Predictive Analytics Pilot establishes a rigorous methodological foundation and delivers three predictive models across the 18-month base period. We propose a phased approach with built-in methodology validation, iterative model development, and explicit researcher engagement throughout.

### Our Understanding of the Technical Challenge

ASPE's research mission requires predictive analytics that are not merely accurate but defensible, reproducible, and explainable. Unlike operational predictive analytics (where accuracy is the primary metric), policy research analytics must support causal claims, account for confounding, and hold up under scrutiny from both technical reviewers and policy stakeholders.

### Proposed Solution Architecture

We propose a three-pillar technical approach:

1. **Data foundation** - Build a secure research data environment in AWS GovCloud with curated CMS claims data and linked demographic data. Leverage our existing CMS data pipeline infrastructure.

2. **Modeling framework** - Develop predictive models using gradient-boosted decision trees as the primary modeling family, with explicit explainability through SHAP analysis and calibrated confidence intervals.

3. **Research enablement** - Deliver models as reproducible artifacts (Jupyter notebooks, documented training pipelines, reusable feature libraries) that ASPE researchers can extend and adapt.

### Technical Methodology

Six-month cycles with three delivered models across the base period:

**Cycle 1 (Months 1-6): Medicare Readmission Model.** Initial model focused on 30-day readmission prediction. Establishes the methodological foundation for subsequent cycles.

**Cycle 2 (Months 7-12): Medicaid Enrollment Trajectory Model.** Predictive model for Medicaid enrollment duration patterns.

**Cycle 3 (Months 13-18): ASPE-directed Third Model.** Model topic selected in collaboration with ASPE based on lessons from Cycles 1 and 2.

### Risk Identification and Mitigation

1. **Model interpretability for policy use** - Mitigation: SHAP-based feature attribution for every model; quarterly researcher engagement sessions.

2. **Data access and authorization timelines** - Mitigation: early engagement with CMS data governance; leverage existing authorizations from Meridian's CMS pipeline work.

3. **Methodological alignment with ASPE's research standards** - Mitigation: methodology review with ASPE researchers during Cycle 1 before proceeding.

## Staffing Plan and Key Personnel

Meridian proposes a team of 6 full-time personnel, led by Dr. Aisha Nakamura (Principal Data Scientist) as Engagement Lead. The team includes 3 data scientists, 2 data engineers, and 1 part-time methodologist.

## Pricing Narrative

Meridian's pricing reflects our labor-intensive methodology and the researcher-collaboration expectations built into our approach. Detailed pricing under our GSA MAS SIN 54151S labor categories is provided in Volume IV.

## Supporting Attachments

Standard attachments provided.

---

## LESSONS LEARNED - POST-LOSS ANALYSIS

**What we got wrong:**

1. **We over-weighted our healthcare data pipeline experience.** The ASPE engagement is fundamentally a policy research engagement, not a data engineering engagement. Our CMS work made us familiar with the data, but familiarity with data is not the same as experience doing policy research with that data.

2. **We underweighted incumbent advantage.** Mathematica Policy Research has 12 years of direct HHS ASPE work. In research-evaluation contracting, institutional continuity matters enormously, and we had no meaningful counter-narrative.

3. **We represented our ML depth more confidently than is warranted.** Our ML practice is real (7 staff, 4 delivered engagements) but none of those engagements were for a federal research organization. The USDA and Maryland DOH engagements were operational ML, not research ML. The distinction matters.

**Implications for the fit rubric:**

- Past performance relevance should be scored on domain-specific applicability, not just "we've worked in healthcare"
- NAICS 541690 (research/consulting) should be scored lower for Meridian than NAICS 541511/541512 (data engineering)
- Incumbent presence on research-evaluation work should be flagged as a significant concern
- Our ML capabilities should be scored as "emerging" not "core" until we have deeper past performance
