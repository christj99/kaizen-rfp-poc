# Past Proposal PP-2021-011
# Meridian Data Solutions - Proposal for HHS Centers for Medicare & Medicaid Services
# Healthcare Data Pipeline Modernization (as subcontractor to Booz Allen Hamilton)

metadata:
  proposal_id: "PP-2021-011"
  title: "Healthcare Data Pipeline Modernization"
  client: "HHS Centers for Medicare & Medicaid Services"
  prime: "Booz Allen Hamilton"
  solicitation_number: "HHSM-500-2020-RFP-0184"
  submitted_date: "2021-04-09"
  award_date: "2021-06-12"
  contract_value: 6_100_000  # Meridian's subcontractor portion
  total_contract_value: 18_400_000  # Full prime contract value
  period_of_performance: "24 months with two 12-month options"
  outcome: "won"
  role: "subcontractor"
  naics: "541511"
  contract_vehicle: "HHS SPARC IDIQ"
  key_themes:
    - "federal healthcare"
    - "data pipeline modernization"
    - "Informatica migration"
    - "Airflow"
    - "dbt"
    - "subcontractor role"

---

## Executive Summary

Meridian Data Solutions is pleased to join Booz Allen Hamilton's proposal team for the CMS Healthcare Data Pipeline Modernization program. As Booz Allen's data engineering subcontractor, Meridian will lead the modernization of 22 legacy Informatica pipelines to a modern orchestration platform based on Apache Airflow and dbt, running on AWS GovCloud. This proposal describes Meridian's specific role within the overall program.

Meridian's contribution to this team is deep technical expertise in legacy ETL modernization. Our 6-year track record includes 14 completed Informatica-to-modern-orchestration migrations across federal and state agencies, and our engineering team has established a reusable migration pattern that systematically reduces business logic translation risk. This pattern has been applied successfully at the U.S. Census Bureau, the Maryland Department of Transportation, and two commercial healthcare organizations.

Our role in this engagement is complementary to Booz Allen's overall program management, enterprise architecture, and change management capabilities. We focus exclusively on the data engineering workstream, where our specialized depth produces better outcomes than a generalist integrator could achieve.

## Company Qualifications

Founded in 2015 and headquartered in Silver Spring, Maryland, Meridian Data Solutions employs 118 data engineers, architects, and analysts focused exclusively on government data modernization. Our firm holds an active Secret facility clearance, ISO 9001:2015 and ISO 27001:2022 certifications, and delivers against a CMMI Level 3-appraised process framework.

Meridian brings specialized expertise in data pipeline modernization, with 14 completed migrations from Informatica, SSIS, and similar legacy tools to modern orchestration platforms. Our firm maintains deep partnerships with Booz Allen Hamilton, Deloitte, and General Dynamics IT on federal programs where specialized data engineering depth complements broader systems integration capabilities.

Our subcontractor engagement model is structured for efficiency: a dedicated Meridian program lead integrates directly with the prime's program management, our work is scoped to discrete data engineering deliverables, and we operate under the prime's governance and reporting structure with no duplication of overhead.

Every Meridian engagement follows our Mission Delivery Framework, which combines Agile delivery practices with our CMMI Level 3 process controls. For subcontractor engagements we specifically emphasize clean handoff artifacts - every deliverable includes sufficient documentation for the prime and the client to operate independently post-engagement.

## Past Performance

Meridian's past performance directly relevant to this engagement spans federal, state, and commercial data pipeline modernization programs.

### Federal Communications Commission Data Pipeline Modernization (2019-2021)

**Contract Value:** $3,800,000
**Role:** Prime
**Period:** 20 months
**Scope:** Migrated 17 legacy Informatica pipelines to Apache Airflow on AWS. Delivered reusable migration pattern subsequently deployed at three additional agencies. Completed within budget and delivered three months ahead of schedule.

**Relevance:** The migration pattern established in this FCC engagement is the same pattern we propose to apply to the CMS program, with refinements based on 4 years of subsequent use across other migrations.

### Census Bureau Decennial Data Processing Pipeline (2020)

**Contract Value:** $2,100,000
**Role:** Subcontractor to Accenture Federal
**Period:** 8 months (delivered on schedule)
**Scope:** Contributed data pipeline engineering to the 2020 Decennial data processing infrastructure. Built and operated Airflow-based orchestration for post-enumeration data quality workflows.

**Relevance:** Demonstrates Meridian's ability to operate effectively as a subcontractor within a complex federal program with high-stakes delivery requirements.

### Maryland Department of Transportation Traffic Data Warehouse (2022-2023)

**Contract Value:** $2,900,000
**Role:** Prime
**Period:** 14 months
**Scope:** Built Maryland DOT's first cloud data warehouse on Snowflake. Migrated five legacy reporting systems including SSIS-based pipelines.

**Relevance:** Demonstrates Meridian's continued practice of SSIS-to-modern-orchestration migrations at state agency scale.

## Technical Approach

Our technical approach focuses on the 22-pipeline migration scope within the overall program. We operate under the enterprise architecture Booz Allen establishes and contribute specialized data engineering execution.

### Our Understanding of the Technical Challenge

CMS's 22 legacy Informatica pipelines represent decades of accumulated business logic processing Medicare and Medicaid data. The modernization must preserve every element of that business logic while replacing the underlying execution infrastructure. The challenge is not primarily technical - it is translational. Every pipeline must be reimplemented with bit-identical output relative to its Informatica predecessor, under conditions where the original business logic is often inadequately documented.

### Proposed Solution Architecture

Our scope within the program is:

1. Pipeline-by-pipeline migration using Meridian's established migration pattern, which includes: business logic extraction and documentation, dbt-based transformation implementation, Airflow-based orchestration, automated reconciliation testing.

2. Data quality framework implementation using dbt's native testing capabilities extended with custom assertions for CMS-specific business rules.

3. Runbook and operational documentation for each migrated pipeline, ensuring CMS operations staff can independently manage the modernized pipelines post-engagement.

### Technical Methodology

We propose a wave-based migration approach across the 24-month base period:

**Wave 1 (Months 1-6): Foundation and Simple Pipelines.** Establish shared dbt and Airflow infrastructure. Migrate 6 simpler pipelines to validate the approach.

**Wave 2 (Months 7-14): Complex Pipelines.** Migrate the 11 more complex pipelines with deeper business logic translation work.

**Wave 3 (Months 15-22): Critical Pipelines.** Migrate the 5 most critical pipelines (those with direct federal reporting dependencies). Extended parallel-run period.

**Wave 4 (Months 23-24): Completion and Handoff.** Final documentation, operational handoff, and knowledge transfer.

### Risk Identification and Mitigation

Three primary risks within our scope:

1. **Business logic documentation gaps** - Mitigation: mandatory SME interviews per pipeline during Wave 1; escalation path to Booz Allen and CMS for ambiguous cases.

2. **Parallel-run reconciliation** - Mitigation: automated reconciliation framework delivered in Wave 1 foundation work; 4-week minimum parallel-run per pipeline.

3. **Operational handoff continuity** - Mitigation: CMS operations staff embedded in Wave 3 and Wave 4 per pipeline; runbook-driven handoff protocol.

## Staffing Plan and Key Personnel

Meridian proposes a team of 8 full-time engineers within this engagement, operating under the program governance Booz Allen establishes. Meridian's Engagement Lead is James Wu, Principal Data Engineer, who brings 15 years of federal data engineering experience including 6 years on CMS programs at prior firms.

## Pricing Narrative

Meridian's pricing within this subcontractor engagement follows Booz Allen's overall pricing framework. Our labor rates are structured under GSA MAS SIN 54151S and negotiated with Booz Allen for this specific program. Pricing detail is provided in Booz Allen's consolidated pricing volume.

## Supporting Attachments

All attachments are provided by Booz Allen Hamilton as the prime. Meridian provides supporting documentation including past performance references, key personnel resumes, and SAM.gov registration upon request.
