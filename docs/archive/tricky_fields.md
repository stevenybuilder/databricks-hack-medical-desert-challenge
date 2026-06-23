# Tricky Fields in the Hackathon Dataset

## Executive Summary

This hackathon dataset is best understood as a **noisy, web-derived healthcare-facility claims dataset for India**, not a clean registry.

You have **10,000 healthcare-facility records across India**, with **51 columns**. The records combine structured fields with uneven free text about claimed capabilities, equipment, procedures, services, facility type, location, staffing, and capacity.

The most important framing from Michael Burk's hackathon notes is:

> **Treat noisy fields as claims to verify, not ground truth.**

The dataset looks more complete than it really is. Many fields are technically populated, but contain semantic missingness such as `"null"` strings, empty arrays like `[]`, `unknown` markers, inconsistent extracted values, or values that are obviously implausible. This makes the core challenge less about building a chatbot and more about building a planner-facing app that can **extract structure, cite evidence, communicate uncertainty, and persist human decisions**.

---

## Where the Dataset Comes From

According to the hackathon notes, the data is the output of the **Foundational Data Refresh, or FDR**, a pipeline that turns open-web content into structured healthcare infrastructure data:

```text
Web sources → GenAI extraction → Entity resolution → FDR dataset
```

The pipeline uses web sources, GenAI extraction, and entity resolution to produce structured records. That means most important fields should be treated as **claims extracted from web text**, not verified operational facts.

The dataset is especially tricky because India is extremely dense and healthcare access varies sharply across regions. Michael's slides note India has roughly **1.4B people**, around **484 people per km²**, and far more facilities in FDR than any other country. That makes the dataset high-impact, but also risky: a false claim about capability, staffing, equipment, or capacity could lead to bad planning or referrals.

---

## Goal of the Hackathon

The Databricks Apps & Agents for Good Hackathon 2026 challenges teams to build **agentic data apps for social impact** using Databricks tools such as **Lakebase, Agent Bricks, and Databricks Apps**.

Michael Burk's notes make the goal more concrete: build a **Databricks App** that helps a **non-technical healthcare planner** do useful work with messy facility data.

The app should help users:

1. Extract structure from messy records.
2. Show the underlying evidence.
3. Communicate uncertainty honestly.
4. Persist decisions such as notes, overrides, shortlists, scenarios, and reviews.

A strong app should not simply answer, “Which hospital has ICU care?” It should answer something closer to:

> “This facility appears to claim ICU care. The supporting text is shown below. Confidence is medium because the claim appears in the description, but capacity is missing and no equipment evidence was found. Suggested action: add to verification queue before using for planning.”

---

## Suggested Tracks

Teams should pick one track:

| Track | Core question |
|---|---|
| **Facility Trust Desk** | Can a facility actually do what it claims? |
| **Medical Desert Planner** | Where are the real, highest-risk gaps in care? |
| **Referral Copilot** | Where should a patient or coordinator go? |
| **Data Readiness Desk** | What must be fixed before planning can trust it? |

All four tracks are really about the same underlying challenge: **turn messy claims into cautious, evidence-backed decisions for non-technical users.**

---

## Core Requirements

The project must:

- Run as a **Databricks App on Free Edition**.
- Use the provided facility dataset.
- Support a clear non-technical user workflow.
- Cite the underlying facility text for any important claim, recommendation, score, or ranking.
- Communicate uncertainty instead of presenting weak evidence as fact.
- Persist user actions such as notes, overrides, shortlists, scenarios, or review decisions.

---

## Judging Criteria

The judging criteria from the notes and official site emphasize:

1. **Product judgment**
2. **Evidence and uncertainty**
3. **Technical execution**
4. **Ambition**

The two most important themes for this dataset are **evidence** and **uncertainty**. Judges are likely to reward apps that show their work, expose contradictions, and help users make safe planning decisions despite messy data.

---

## The Core Dataset Problem: Hidden Uncertainty

The dataset has a deceptive quality problem: many fields appear to have high coverage, but the values themselves are often weak, missing in disguise, contradictory, or extracted incorrectly.

Common patterns include:

- `"null"` strings instead of actual null values.
- Empty arrays such as `[]` or `[""]` masquerading as populated fields.
- `unknown` values inside otherwise populated text fields.
- GenAI extraction artifacts, such as years parsed as `7` or operator types parsed as URLs.
- Implausible statistical outliers, such as facilities claiming hundreds of thousands of beds.
- Cross-field contradictions, such as bed capacity without doctors or enormous bed-to-doctor ratios.
- Ambiguous fields where the unit is unclear, such as whether capacity means beds, ICU beds, daily patients, staff, or something else.

This is the key opportunity: **do not hide uncertainty behind confident answers. Make uncertainty useful.**

---

## Tricky Fields and How to Handle Them

| Field / area | Why it is tricky | What the app should do |
|---|---|---|
| **description** | Has 100% coverage in the notes, but it is free-text web-derived evidence, not verified truth. | Use it as the primary citation source. Highlight exact snippets that support any important answer. |
| **source_urls / source_content_id** | These fields track provenance. They are essential for evidence, but source quality may vary by website and freshness. | Show citations for every important claim. Display source domain, extraction date if available, and confidence. |
| **specialties** | Databricks Genie analysis reported that around **73%** contain `unknown` markers despite appearing populated. | Normalize specialties, separate known from unknown, and avoid treating “present but unknown” as usable data. |
| **capability** | Slide coverage is around **99.7%**, but Genie analysis reported around **80% unknowns**. Capability may mean service line, specialty, department, marketing claim, or inferred service. | Treat as a claim. Show evidence text and confidence. Cluster related capabilities into planner-friendly categories. |
| **procedure** | Slide coverage is around **92.5%**, but Genie analysis reported around **62% unknowns**. Procedure names may be inconsistent, overly broad, duplicated, or inferred. | Map variants to standard procedure groups and flag weak or unsupported extractions. |
| **equipment** | Slide coverage is around **77%**. Genie analysis reported roughly **22% to 28.5% incomplete**, depending on definition, including empty arrays `[]` and `[""]`. Missing equipment does **not** mean the facility lacks it. | Distinguish “claimed present,” “not mentioned,” and “conflicting or unclear.” Use equipment claims carefully for referrals. |
| **capacity** | One of the most problematic fields. Genie analysis reported around **75% missing or incomplete**, with many records containing `"null"` strings instead of real numbers. Capacity may also mean beds, ICU beds, patients per day, staff capacity, or something else. | Parse numeric value and unit separately. Validate ranges. Never compare capacity unless units match. Show “unknown” rather than pretending null is data. |
| **numberDoctors** | Genie analysis reported around **64% missing**, including many `"null"` strings. Doctor counts are essential for staffing and bed-to-doctor checks. | Treat as a high-priority verification field. Use cross-field checks against capacity and facility type. |
| **yearEstablished** | Genie analysis reported around **52.4% missing**. Some values are invalid or ambiguous, such as `7`, `1`, future dates, or dates that may refer to a website, department, trust, or article rather than facility founding. | Validate year range. Treat implausible values as extraction errors. Cite source text before using as a trust signal. |
| **recency_of_page_update** | Genie analysis reported around **64.8% missing**. Data freshness is a trust signal, but often unavailable. | Show freshness when available. Penalize missing or stale recency in trust scoring, but do not over-penalize if other evidence is strong. |
| **operatorTypeId** | Missingness may be relatively low, but the field can contain malformed values such as URLs instead of categories. Public/private status is also critical for planning. | Normalize to planner-friendly categories such as public, private, nonprofit, trust, unknown. Flag malformed values. |
| **affiliationTypeIds** | Genie analysis reported very high missingness, around **87.7%**. | Treat organizational relationships as mostly unavailable unless explicitly supported. |
| **area** | Genie analysis reported extremely high missingness, around **98.7%**. | Do not rely on this for service coverage. Use geospatial methods and user assumptions instead. |
| **location / coordinates** | Coordinates may be incorrect. Genie analysis found facilities with coordinates outside India. A facility's address also may not imply realistic service area. | Validate coordinates against India boundaries and expected state/city. Flag out-of-country or state-mismatched points. |
| **entity identity / duplicates** | The FDR pipeline includes entity resolution, but duplicate or near-duplicate facilities can still exist under spelling, address, phone, or website variants. | Surface possible duplicates. Let users merge, split, or flag records. Persist those decisions. |
| **digital trust signals** | Fields such as social media presence, followers, and logo can be useful but are not proof of medical capability. | Use only as weak supporting signals. Do not equate marketing presence with actual clinical capability. |

The biggest gotcha: **high coverage does not mean high trust**. `capability`, `description`, and similar fields may be present, but they remain extracted claims. `capacity`, `numberDoctors`, `yearEstablished`, and `equipment` often need cleaning, validation, and human review before planning can rely on them.

---

## Highest-Priority Missing or Incomplete Fields

Based on the Databricks Genie exploration pasted into this note, these are the fields most worth cleaning first if the goal is to get “true” insights.

### Critical Priority: More Than 60% Missing or Incomplete

| Field | Reported issue | Why it matters |
|---|---:|---|
| **capacity** | Around **75.0% missing or incomplete**; Genie reported **7,568 records** affected, including many `"null"` strings. | Core to facility planning, medical desert analysis, referral load, and capacity scenarios. |
| **numberDoctors** | Around **64.0% missing**; Genie reported **6,455 records** affected, including many `"null"` strings. | Needed for staffing checks and bed-per-doctor ratios. |
| **recency_of_page_update** | Around **64.8% missing**; Genie reported **6,542 records** affected. | Important trust signal for whether a source is current. |
| **procedure** | Genie reported around **62% unknowns**. | Critical for procedure-based referral and facility capability claims. |
| **capability** | Genie reported around **80% unknowns** despite field presence. | Central to the app, but risky if treated as authoritative. |
| **specialties** | Genie reported around **73% unknown markers**. | Important for referrals and planning, but heavily uncertain. |

### High Priority: 30% to 60% Missing or Incomplete

| Field | Reported issue | Why it matters |
|---|---:|---|
| **yearEstablished** | Around **52.4% missing**, with only around **4,775 valid years** reported. | Useful trust and maturity signal, but only after validation. |
| **equipment** | Around **22% to 28.5% incomplete**, depending on whether empty arrays and unknowns are counted. | Critical for referral routing, especially imaging, dialysis, surgery, emergency care, and ICU planning. |

### Other Sparse or Problematic Fields

| Field | Reported issue | Why it matters |
|---|---:|---|
| **affiliationTypeIds** | Around **87.7% missing**. | Weak support for network or ownership analysis. |
| **area** | Around **98.7% missing**. | Not reliable for service-area planning. |
| **operatorTypeId** | Around **7.5% missing**, but malformed values such as URLs may appear. | Public/private/nonprofit status is important for planning and equity analysis. |

---

## Statistical Outliers and Data Quality Red Flags

The Genie analysis identified several examples of values that should be flagged before being used in insights:

- Facilities claiming **200,000 bed capacity**, which is almost certainly a data extraction error.
- A facility claiming **15,000 doctors**.
- A hospital with **1,391 beds but only 1 doctor** on record.
- `yearEstablished = 7`, suggesting data type or GenAI extraction confusion.
- **6 facilities with coordinates outside India**, including an example of a Nagpur facility placed at approximately **2.95°N, 41.39°E**.
- **6 facilities with capacity greater than zero but 0 doctors**.
- **25 facilities with suspicious bed-to-doctor ratios**, such as greater than 500:1 or less than 0.1:1.
- `operatorTypeId` values containing URLs instead of operator categories.

These red flags are not just data-cleaning bugs. They are product opportunities: the app can help a planner understand which facilities, regions, and fields need verification before decisions are made.

---

## Interesting Trends to Exploit

These trends from the Genie analysis could support strong product narratives and demo scenarios.

### Geographic Patterns

- **Maharashtra** has the most records, with roughly **1,575 facilities**.
- **Gujarat** follows with roughly **981 facilities**.
- **Uttar Pradesh** follows with roughly **919 facilities**.
- These differences create opportunities to identify medical deserts using both facility density and uncertainty scores.

### Facility Distribution

- Roughly **56% hospitals**.
- Roughly **37% clinics**.
- Roughly **5% dentists**.
- Roughly **87.6% private operators**.
- Public facilities appear heavily underrepresented, around **4.6%**, or roughly **469 public facilities** in the dataset.

This is important because a naive planner might mistake dataset representation for real-world supply. A good app should say when public-sector coverage is likely incomplete or underrepresented.

### Digital Trust Signals

- Genie analysis reported that around **94.5%** of facilities have some social media signal.
- Only around **20%** have more than **1,000 followers**.
- The combination of high follower count and actual specialty data was reported for about **3,689 facilities**.
- Custom logo presence was reported around **86%**.

These may be useful as weak trust signals, but they should not be treated as proof that a facility can perform a clinical service.

### Temporal Patterns

- Establishment years reportedly peak around **2010–2014**, suggesting a recent explosion of facilities or recent web visibility.
- Only around **4,775 facilities** have valid establishment years, leaving roughly **52%** missing temporal context.

---

## The Uncertainty Opportunity

The challenge explicitly says to **communicate uncertainty instead of presenting weak evidence as fact**. That is the biggest differentiator.

A basic chatbot would likely:

- Hide uncertainty behind confident-sounding answers.
- Silently drop facilities with missing data.
- Present impossible values such as “1,391 beds” or “200,000 beds” as fact.
- Fail to cite source text.
- Fail to preserve planner decisions.

A stronger hackathon project should:

- Quantify uncertainty with transparent, reproducible metrics.
- Cite source text for every important claim, score, ranking, or recommendation.
- Expose contradictions rather than papering over them.
- Show best-case, worst-case, and most-likely scenarios where data is uncertain.
- Persist user decisions such as notes, overrides, shortlists, verification status, and review outcomes.
- Help planners decide **what to verify next**, not just answer one-off questions.

---

## Ambitious Product Ideas

### 1. Evidence-Backed Trust Scoring

Build a multi-dimensional uncertainty or trust score for each facility. The score should not be a mysterious AI number; it should show its components.

Possible scoring dimensions:

| Dimension | Example checks |
|---|---|
| **Data completeness** | Are capacity, doctors, equipment, specialties, and procedures present and usable? |
| **Evidence support** | Does the underlying description or source text explicitly support the claim? |
| **Cross-field consistency** | Do capacity, doctors, facility type, and capabilities make sense together? |
| **Geographic validity** | Are coordinates inside India and consistent with city/state? |
| **Temporal validity** | Is `yearEstablished` plausible? Is the source recently updated? |
| **Source/provenance quality** | Is there a usable source URL or source content ID? Are multiple sources consistent? |
| **Digital trust signals** | Does the facility have a website, social presence, custom logo, or follower count? Use only as weak evidence. |
| **Human review status** | Has a planner verified, overridden, or flagged this record? |

Example user-facing output:

> **Uncertainty: 65 / 100**
> Main contributors: missing capacity data (+20), no recent source update (+15), contradictory doctor count (+30).
> Recommendation: verify capacity and staffing before using this facility in a referral or planning scenario.

### 2. Provenance Visualization

Use `source_urls` and `source_content_id` to create a citation system.

Example:

> **Capacity claim:** 100 beds
> **Source:** justdial.com
> **Extracted:** 2024-10-21
> **Confidence:** Low
> **Reason:** capacity appears in web text, but no unit-specific supporting context was found.

Use color coding or badges such as:

- **Strong evidence:** source text directly supports the claim.
- **Weak evidence:** claim is inferred or ambiguous.
- **Conflicting evidence:** sources disagree.
- **Missing evidence:** field is absent, null-like, or unknown.

### 3. Conflict Resolution Interface

When multiple sources disagree, do not silently choose one value.

Example:

> Capacity ranges from **50 to 150 beds** across 3 sources. The most recent source claims **100 beds**. Confidence is medium. Please choose a planning assumption or mark for verification.

Let planners:

- Choose the source they trust.
- Override a field value.
- Mark a field as verified, rejected, or needs follow-up.
- Add notes explaining the decision.
- Persist the decision for future sessions.

### 4. Scenario Planning for the Medical Desert Planner Track

Instead of showing only a single number such as “this district has 5 hospitals,” show uncertainty bands.

Example:

| Scenario | Facilities | Estimated capacity | Notes |
|---|---:|---:|---|
| **Best case** | 5 facilities | 500 beds | Includes all claimed facilities and capacity values. |
| **Most likely** | 3–4 facilities | 250–350 beds | Excludes weak claims and implausible capacity outliers. |
| **Worst case** | 2 verified facilities | 150 beds | Uses only high-confidence facilities. |

This approach is much more honest for planning than pretending the dataset is fully verified.

### 5. Missing Data Impact Analysis

Show how unknown data affects decisions.

Example:

> We do not know specialist availability for **47%** of facilities in this region. This reduces referral confidence and makes the district a high-priority verification target.

This is especially useful for the **Data Readiness Desk** track.

---

## Recommended Track: Data Readiness Desk

The strongest track for this dataset may be:

> **Data Readiness Desk:** What must be fixed before planning can trust it?

This directly addresses the messy-data challenge and aligns with the judging criteria around evidence, uncertainty, product judgment, and ambition.

A strong Data Readiness Desk could:

1. Score each facility's trustworthiness.
2. Identify systematic data issues by region, facility type, operator type, or source.
3. Highlight fields that block reliable planning, such as capacity, doctors, procedures, equipment, and specialties.
4. Suggest targeted verification campaigns.
5. Track improvement over time as users validate records.
6. Persist user actions such as notes, overrides, and verification decisions.

Example product claim:

> “Verify these 50 high-impact facilities first. Doing so could improve regional planning confidence by 40% because they sit in high-need areas and have unresolved capacity/equipment claims.”

---

## Example Data Quality Workflow

A planner-friendly workflow could look like this:

1. **Select a geography or planning question**
   Example: “Where are emergency-care gaps in Maharashtra?”

2. **View facility supply with uncertainty bands**
   Show verified, likely, and weakly supported facilities separately.

3. **Open a facility trust card**
   Display claimed services, evidence snippets, source URLs, field completeness, contradictions, and trust score.

4. **Resolve or flag issues**
   Let users mark fields as verified, override values, add notes, or request follow-up.

5. **Persist decisions**
   Store notes, overrides, shortlists, scenario assumptions, and review decisions.

6. **Recompute planning outputs**
   Update maps, rankings, referral recommendations, or readiness scores based on verified data and user decisions.

---

## Practical Interpretation

A weak answer would say:

> Facility X has ICU, CT, and surgery.

A stronger hackathon-style answer would say:

> Facility X appears to claim emergency care and imaging. Evidence: quoted source text. Confidence is medium because equipment is mentioned but capacity is missing and the source text is ambiguous. Suggested action: mark for verification or shortlist with caution.

That is the spirit of the hackathon: **build a useful planner-facing tool that is honest about messy healthcare infrastructure data rather than pretending the extracted fields are clean facts.**

---

## Notes on the Genie Analysis

The field percentages and anomaly counts in this file come from the pasted Databricks Genie exploration. They should be treated as **working findings to validate in SQL or a notebook** before final judging.

The most important Genie-derived findings to re-check are:

- `capacity` missing or incomplete rate.
- `numberDoctors` missing rate.
- `recency_of_page_update` missing rate.
- Unknown-marker rates in `specialties`, `capability`, and `procedure`.
- Empty-array and `[""]` rates in `equipment`.
- Out-of-country coordinate count.
- Implausible capacity, doctor count, and bed-to-doctor outliers.
- Public/private/operator-type distribution.

The unrelated Databricks profile-ID exchange from the pasted Genie text was not included because it is not part of the dataset or hackathon analysis.

---

## Sources

- Databricks Apps & Agents for Good Hackathon 2026: https://developers.databricks.com/hackathon/apps-agents-for-good-2026
- Databricks hackathon quick-start checklist: https://developers.databricks.com/hackathon/quick-start-checklist
- Databricks hackathon synced dataset template: https://developers.databricks.com/templates/hackathon-app-with-synced-dataset
- Databricks blog on Foundational Data Refresh: https://www.databricks.com/blog/databricks-good-and-virtue-foundation-partnering-connect-medical-volunteers-critical-health
- Michael Burk hackathon notes/slides from the provided screenshots.
- Databricks Genie dataset exploration pasted into this conversation.
