# Past Proposal PP-2023-008
# Meridian Data Solutions - Proposal for Maryland Department of Human Services
# Benefits Analytics Platform

metadata:
  proposal_id: "PP-2023-008"
  title: "Benefits Analytics Platform"
  client: "Maryland Department of Human Services"
  solicitation_number: "CATS+-TORFP-F50B3400029"
  submitted_date: "2023-02-14"
  award_date: "2023-04-28"
  contract_value: 4_200_000
  period_of_performance: "24 months with one 12-month option"
  outcome: "won"
  role: "prime"
  naics: "541512"
  contract_vehicle: "Maryland CATS+"
  key_themes:
    - "state"
    - "social services"
    - "benefits administration"
    - "analytics platform"
    - "data governance"
    - "Snowflake"
    - "Tableau"

---

## Executive Summary

Meridian Data Solutions is pleased to submit this proposal to the Maryland Department of Human Services (DHS) in response to solicitation CATS+-TORFP-F50B3400029 for the Benefits Analytics Platform. As a Maryland-headquartered firm with deep experience in both Maryland state government and federal benefits administration (including our ongoing HHS CMS work on healthcare data modernization), Meridian brings a combination of local presence, domain expertise, and proven delivery capability that is uniquely aligned to DHS's needs.

The Benefits Analytics Platform will unify data from Maryland's SNAP, TCA, and Medicaid program systems into a single analytical foundation, enabling DHS leadership to answer cross-program questions about caseload trends, benefits utilization, and program outcomes. Our proposed solution establishes a Snowflake-based data platform with a dbt transformation layer, Tableau for executive reporting, and an integrated data governance framework - all grounded in Maryland's existing cloud posture and CATS+ technical standards.

Our three differentiators for this engagement are: (1) Maryland-local presence, with all key personnel within one hour of Baltimore; (2) direct federal benefits administration experience through our CMS work, applicable to the federal reporting requirements embedded in SNAP and Medicaid programs; and (3) demonstrated data governance capability through our 9-person dedicated governance practice.

Meridian is committed to delivering the Benefits Analytics Platform as a production-grade asset that DHS will operate long past the contract period. Our approach prioritizes knowledge transfer and DHS staff enablement from day one.

## Company Qualifications

Founded in 2015 and headquartered in Silver Spring, Maryland, Meridian Data Solutions employs 118 data engineers, architects, and analysts focused exclusively on government data modernization. Our firm holds an active Secret facility clearance, ISO 9001:2015 and ISO 27001:2022 certifications, and delivers against a CMMI Level 3-appraised process framework.

Meridian holds an active position on the Maryland CATS+ master contract and has delivered five prior engagements under CATS+ across the Maryland Department of Transportation, the Maryland Department of Budget and Management, and the Maryland Judiciary. Our Maryland-based staff totals 54 personnel, all within the DMV metropolitan area, with 12 staff specifically experienced in Maryland state government technology environments.

Our firm maintains current data processing authorizations with the Maryland Department of Information Technology (DoIT) and has completed the Maryland Data Security Awareness program for all staff. Our engagement approach for state agencies is rooted in CATS+ best practices: tight integration with agency technical staff, minimal reliance on proprietary tooling, and explicit knowledge transfer planning from contract initiation.

Every Meridian engagement follows our Mission Delivery Framework, which combines Agile delivery practices with our CMMI Level 3 process controls. For state engagements we specifically emphasize operational handoff - ensuring that agency staff are positioned to independently operate and extend the solutions we deliver.

## Past Performance

Meridian's past performance directly aligned with this Benefits Analytics Platform engagement includes three programs spanning state benefits administration, federal healthcare data, and Maryland state data platforms.

### CMS Healthcare Data Pipeline Modernization, HHS Centers for Medicare & Medicaid Services (2021-2023)

**Contract Value:** $6,100,000
**Role:** Subcontractor to Booz Allen Hamilton
**Period:** 24 months (delivered; extended twice)
**Scope:** Modernized 22 healthcare data pipelines from Informatica to Airflow and dbt on AWS. Established CMS's first production dbt environment and data quality monitoring framework. Directly relevant experience with federal benefits data, Medicaid reporting, and the data structures that underpin Maryland's Medicaid program.

**Relevance:** Demonstrates Meridian's fluency with federal benefits data structures and the reporting obligations Maryland DHS must satisfy for its Medicaid program.

### Maryland Department of Transportation Traffic Data Warehouse (2022-2023)

**Contract Value:** $2,900,000
**Role:** Prime
**Period:** 14 months
**Scope:** Built Maryland DOT's first cloud data warehouse on Snowflake. Migrated five legacy reporting systems. Delivered 11 executive and operational dashboards in Tableau.

**Relevance:** Demonstrates Meridian's ability to deliver Snowflake-based state agency analytics platforms within the Maryland CATS+ framework, with direct applicability to the technical architecture proposed for DHS.

### Virginia DOT Transportation Analytics (2021)

**Contract Value:** $1,400,000
**Role:** Prime
**Period:** 12 months
**Scope:** Built Virginia DOT's traffic incident analytics platform on Snowflake. Integrated six state data sources. Delivered real-time operational dashboards.

**Relevance:** Demonstrates Meridian's state-agency data platform delivery capability in the DMV region.

## Technical Approach

Our technical approach for the Benefits Analytics Platform establishes a modern cloud data platform on Snowflake, with transformation managed by dbt, analytics surfaced through Tableau, and governance anchored by a phased Collibra deployment.

### Our Understanding of the Technical Challenge

DHS manages three major benefits programs (SNAP, TCA, Medicaid) that currently operate on separate data systems with inconsistent reporting cadences and no unified analytical view. DHS leadership has identified cross-program analytics as a critical unmet need. The technical challenge is twofold: first, to consolidate the three program data sources into a unified, reliable analytical platform; second, to do so while preserving the integrity of each program's federal reporting obligations.

### Proposed Solution Architecture

The Benefits Analytics Platform comprises four layers:

1. **Ingestion layer** - Fivetran-based CDC from the three program source systems into Snowflake staging tables.

2. **Transformation layer** - dbt models organized in a medallion pattern (bronze/silver/gold), with explicit data quality tests at each layer.

3. **Governance layer** - Collibra catalog integrated with dbt metadata, providing lineage tracking and data classification.

4. **Analytics layer** - Tableau server with row-level security aligned to DHS's role hierarchy, configured for both executive and operational reporting.

### Technical Methodology

We propose a three-phase approach:

**Phase 1 (Months 1-8): Foundation and First Program.** Provision Snowflake environment. Integrate SNAP program data. Deliver initial executive dashboards. Establish governance framework.

**Phase 2 (Months 9-16): Expansion.** Integrate TCA and Medicaid program data. Deliver cross-program analytics. Expand dashboard coverage to operational users.

**Phase 3 (Months 17-24): Operational Handoff.** Complete knowledge transfer to DHS staff. Transition ownership of platform operations to DHS. Provide extended support through option year.

### Risk Identification and Mitigation

The three highest-probability risks we have identified are:

1. **Federal reporting continuity** - DHS's federal reporting obligations to CMS and USDA cannot be disrupted. Mitigation: parallel-run approach for each program's federal reporting pipelines during migration, with automated reconciliation.

2. **Program-specific business logic translation** - Each benefits program has unique eligibility rules and reporting structures. Mitigation: dedicated program SMEs for each program, with explicit business logic documentation as a deliverable.

3. **Data classification and privacy** - SNAP and Medicaid data have strict privacy requirements. Mitigation: our 9-person governance practice will lead classification and access control design from Phase 1.

## Staffing Plan and Key Personnel

Meridian proposes a core team of 9 full-time engineers plus 2 part-time SME consultants. All 11 team members are based in Maryland or Northern Virginia. Program Manager is Jennifer Ramirez, PMP, who has led Meridian's prior Maryland state engagements.

Detailed resumes for all key personnel are attached in Attachment C.

## Pricing Narrative

Meridian's pricing for the Benefits Analytics Platform is structured under Maryland CATS+ labor categories with transparent pricing and no hidden fees. Our pricing philosophy is to align cost to value - our proposed price reflects the scope of work required to deliver a production-grade platform, without loading fees for capabilities DHS does not need. Detailed pricing is provided in Attachment D.

## Supporting Attachments

Attachment A: Past Performance Questionnaires (3 references)
Attachment B: Maryland CATS+ Master Contract
Attachment C: Key Personnel Resumes
Attachment D: Pricing Workbook
Attachment E: SAM.gov Registration
Attachment F: Data Security and Privacy Plan
