# Past Proposal PP-2024-014
# Meridian Data Solutions - Proposal for Department of Commerce
# International Trade Administration - Trade Data Modernization Phase II

metadata:
  proposal_id: "PP-2024-014"
  title: "Trade Data Modernization Phase II"
  client: "U.S. Department of Commerce, International Trade Administration"
  solicitation_number: "1331L524Q00056"
  submitted_date: "2024-03-18"
  award_date: "2024-05-22"
  contract_value: 8_400_000
  period_of_performance: "24 months with two 12-month options"
  outcome: "won"
  role: "prime"
  naics: "541511"
  contract_vehicle: "GSA MAS SIN 54151S"
  key_themes:
    - "federal civilian"
    - "data platform modernization"
    - "cloud migration"
    - "analytics enablement"
    - "Snowflake"
    - "dbt"

---

## Executive Summary

Meridian Data Solutions is pleased to submit this proposal to the International Trade Administration (ITA) in response to solicitation 1331L524Q00056 for the Trade Data Modernization Phase II program. Over the past four years, Meridian has delivered three federal civilian data modernization programs of comparable scope, including our 2022-2024 work on ITA's Trade Data Phase I platform, which established the foundational data warehouse this Phase II work will extend. We bring deep continuity with ITA's technical architecture, a demonstrated track record delivering against CMMI Level 3-appraised processes, and a team of 14 engineers with active experience in Snowflake, dbt, and federal cloud compliance.

Phase II extends the Phase I foundation by operationalizing trade analytics for 12 additional ITA business units, migrating three remaining legacy data sources from on-premise SQL Server to Snowflake, and establishing the first production FedRAMP-aligned dbt transformation layer for ITA. Our proposed solution builds directly on the architectural patterns established in Phase I, reduces delivery risk through team continuity, and completes ITA's transition to a unified cloud data platform within the 24-month base period.

Our three differentiators for this engagement are: (1) direct continuity with the Phase I team, eliminating onboarding risk and preserving institutional knowledge; (2) demonstrated depth in the exact technical stack ITA has selected (Snowflake, dbt, Airflow on AWS GovCloud); and (3) a governance-first delivery approach, grounded in our ISO 27001-certified security management system and our dedicated 9-person data governance practice.

Meridian is committed to delivering Phase II within budget, on schedule, and with the transparency ITA has come to expect from our Phase I engagement.

## Company Qualifications

Founded in 2015 and headquartered in Silver Spring, Maryland, Meridian Data Solutions employs 118 data engineers, architects, and analysts focused exclusively on government data modernization. Our firm holds an active Secret facility clearance, ISO 9001:2015 and ISO 27001:2022 certifications, and delivers against a CMMI Level 3-appraised process framework.

Meridian holds active positions on the GSA Multiple Award Schedule (SINs 54151S and 518210C), NASA SEWP VI, and Maryland CATS+. Our firm is registered in SAM.gov (CAGE 8MDS2, UEI MRDN8402KLMQ) and maintains clean past performance across 42 completed federal and state engagements totaling $94M in contract value over the past five years.

Our dedicated federal civilian practice is led by Dr. Rachel Okonkwo, Chief Growth Officer, who joined Meridian from the U.S. Census Bureau where she led the 2020 Decennial Data Processing team. Our technical leadership is led by Marcus Halloran, CTO, who brings 18 years of data engineering experience including eight years at Booz Allen Hamilton on DoD and HHS programs.

Every Meridian engagement follows our Mission Delivery Framework, which combines Agile delivery practices with our CMMI Level 3 process controls. Weekly status reviews, monthly technical reviews, and quarterly executive briefings ensure full transparency with our government partners throughout the engagement lifecycle.

## Past Performance

Meridian's past performance directly aligned with Phase II's requirements includes three programs of comparable scope, domain, and technical approach.

### Trade Data Modernization Phase I, U.S. Department of Commerce ITA (2022-2024)

**Contract Value:** $6,100,000
**Role:** Prime
**Period:** 24 months (completed on schedule, 4% under budget)
**Scope:** Established ITA's cloud data platform on AWS GovCloud, migrating 14 legacy data sources to Snowflake and building the foundational dbt transformation layer. Delivered 6 executive dashboards in Tableau. Established data governance framework with Collibra.

**Relevance to Phase II:** This program is Phase II's direct predecessor. The architecture, governance framework, and delivery team proposed for Phase II are extensions of this completed work. No other bidder can claim equivalent continuity.

### CMS Healthcare Data Pipeline Modernization, HHS Centers for Medicare & Medicaid Services (2021-2023)

**Contract Value:** $6,100,000
**Role:** Subcontractor to Booz Allen Hamilton
**Period:** 24 months (delivered; extended twice)
**Scope:** Modernized 22 healthcare data pipelines from Informatica to Airflow and dbt on AWS. Established CMS's first production dbt environment and data quality monitoring framework.

**Relevance to Phase II:** Demonstrates Meridian's ability to migrate legacy ETL to dbt at federal scale, with direct applicability to the three remaining SSIS pipelines identified in Phase II's scope.

### Maryland Benefits Analytics Platform, Maryland Department of Human Services (2023-2025)

**Contract Value:** $4,200,000
**Role:** Prime
**Period:** 24 months (ongoing; Phase 1 delivered 2024)
**Scope:** Built Maryland DHS's first cloud analytics platform on Snowflake with dbt transformation layer and Tableau reporting. Established data governance practice and quality monitoring.

**Relevance to Phase II:** Demonstrates Meridian's ability to operationalize analytics for downstream business units, directly relevant to Phase II's requirement to extend trade analytics to 12 additional ITA business units.

## Technical Approach

Our Phase II technical approach builds on three foundations established in Phase I: the Snowflake data warehouse on AWS GovCloud, the dbt-based transformation layer, and the Collibra-anchored governance framework. Phase II extends these foundations in three dimensions: (1) migration of the three remaining legacy data sources, (2) operationalization of analytics for 12 additional business units, and (3) establishment of production-grade FedRAMP-aligned controls on the dbt layer.

### Our Understanding of the Technical Challenge

ITA's Phase I established the platform; Phase II must operationalize it. The three remaining legacy sources (Export Control System, Commercial Service Report System, and the International Trade Statistics Warehouse) represent the highest-complexity migration targets because of their age, bespoke business logic, and critical role in ITA's operational cadence. Analytics operationalization for 12 business units requires not only technical delivery but also change management and training, which we have planned for accordingly.

### Proposed Solution Architecture

Phase II's architecture extends Phase I without structural change. Three new components are introduced:

1. A dbt Cloud production deployment configured for FedRAMP Moderate authorization, with fine-grained role-based access control aligned to ITA's existing Active Directory integration.

2. A Fivetran-based CDC ingestion pipeline for the three remaining legacy sources, operating in parallel with the existing Python-based pipelines during migration.

3. An expanded Tableau server footprint to accommodate the 12 new business units, configured with Tableau-native row-level security aligned to ITA's business unit hierarchy.

### Technical Methodology

We propose a four-phase approach across the 24-month base period:

**Phase 2A (Months 1-6): Foundation Extension.** Provision dbt Cloud production environment. Complete FedRAMP documentation package. Onboard three business units as pilot users.

**Phase 2B (Months 7-12): Legacy Migration Wave 1.** Migrate Export Control System and Commercial Service Report System. Complete data quality validation. Cut over production workloads.

**Phase 2C (Months 13-18): Legacy Migration Wave 2 and Expansion.** Migrate International Trade Statistics Warehouse. Onboard six additional business units.

**Phase 2D (Months 19-24): Completion and Transition.** Onboard remaining three business units. Complete FedRAMP Moderate authorization. Execute knowledge transfer to ITA internal team.

### Risk Identification and Mitigation

The three highest-probability risks we have identified, drawn from Phase I lessons-learned, are:

1. **Legacy business logic translation fidelity** - Mitigation: two-week parallel-run period for each migrated source with automated reconciliation.

2. **FedRAMP authorization schedule** - Mitigation: early engagement with ITA's FISMA team and parallel documentation preparation during Phase 2A.

3. **Business unit change management** - Mitigation: dedicated 0.5 FTE change management lead throughout, with structured training curriculum.

## Staffing Plan and Key Personnel

Meridian proposes a core team of 14 full-time engineers supplemented by 3 part-time specialists. The team structure retains the Phase I Program Manager (Sarah Chen, 4,200 hours on Phase I) and Technical Lead (James Wu, 4,100 hours on Phase I), providing full continuity on ITA's environment. Seven of the 14 FTEs are Phase I alumni; the remaining seven are new to ITA but bring specialized expertise in the specific technical areas Phase II requires.

Detailed resumes for all key personnel are attached in Volume III.

## Pricing Narrative

Meridian's pricing for Phase II reflects the program's risk profile, team continuity benefits, and the economies of scale achievable through Phase I's established architecture. We have structured our pricing around GSA MAS SIN 54151S with labor categories mapped to ITA's standard labor category framework.

Our pricing philosophy for Phase II reflects our commitment to delivering predictable outcomes within predictable budgets. We have structured pricing to minimize variable costs and to provide ITA with budget predictability throughout the engagement. Detailed pricing is provided in Volume IV.

## Supporting Attachments

Volume II: Past Performance Questionnaires (3 references)
Volume III: Key Personnel Resumes
Volume IV: Pricing Workbook
Volume V: SAM.gov Registration
Volume VI: Representations and Certifications
Volume VII: Small Business Subcontracting Plan
