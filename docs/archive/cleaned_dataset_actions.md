# Cleaned Dataset Actions

Generated on June 15, 2026.

## Primary Output

The primary cleaned dataset is district-level:

- `output/data/district_health_facility_cleaned.csv`
- Rows: 494 districts
- Columns: 98
- Grain: one row per joined `state_ut` + `district_name`

Facility-level data is retained as an audit/evidence layer:

- `output/data/facility_health_cleaned.csv`
- Rows: 10,077 deduplicated facility records
- Columns: 102
- Grain: one row per facility `unique_id`

## Why District-Level

District is the defensible analytic grain because the NFHS health indicators are district-level, while facility rows are web-extracted claims from the FDR pipeline. The facility table is useful evidence, but not a verified supply registry.

The district dataset aggregates facility evidence into planning signals:

- observed FDR facility rows
- trustworthy supply rows/rate
- source URL evidence rate
- human-review rate
- geography quality rate
- maternity, emergency, diagnostic, and chronic-care claim signal rates
- NFHS health need score
- care gap, trust gap, best-care signal, and medical desert proxy scores

## Ground Truth Assumptions

- NFHS district health indicators are treated as the strongest available ground-truth signal for district-level health need.
- India Post PIN-to-district mappings are treated as the geographic bridge, with ambiguity retained.
- FDR facility rows are not ground truth. They are observed web-extracted facility claims.
- Facility service/capability claims should be cited and verified before operational use.
- Medical desert labels are triage categories, not final policy truth.

## Cleaning Actions

- Deduplicated raw facility rows by `unique_id`.
- Preserved duplicate-source evidence using `source_unique_id_occurrences` and `source_duplicate_unique_id`.
- Parsed six-digit Indian PIN codes from `address_zipOrPostcode`.
- Joined facilities to India Post by PIN code.
- Collapsed India Post rows to a modal district/state bridge per PIN code.
- Added PIN ambiguity metrics where a PIN maps to multiple districts/states.
- Normalized state and district names, including observed spelling/rename traps such as `Maharastra` to Maharashtra, Gurugram/Gurgaon, Prayagraj/Allahabad, and Bengaluru/Bangalore.
- Joined district/state keys to NFHS district health indicators.
- Added join strategy, match score, confidence, and uncertainty reason fields.
- Flagged geospatial anomalies using India bounding-box checks and distance to pincode centroid.
- Parsed numeric-looking facility fields such as capacity, number of doctors, followers, and post counts.
- Flagged extreme numeric outliers rather than deleting them.
- Added claim-evidence coverage fields for description, specialties, procedure, equipment, and capability.
- Added care-signal text flags for maternity, emergency, diagnostics, and chronic/NCD care.
- Added `trustworthy_supply_signal` for facility rows with strong join, plausible geography, source URLs, sufficient claim fields, and no extreme parsed outliers.
- Added `needs_human_review` for low confidence, weak evidence, suspicious geography, or extreme fields.

## Planning Categories

District rows are categorized as:

- `real_desert_candidate`: high need, low trustworthy observed supply.
- `phantom_desert_or_verification_gap`: facilities exist, but claims/evidence are weak.
- `supply_record_quality_problem`: supply records exist but are contradicted, geo-invalid, or suspicious.
- `referral_or_capacity_candidate`: relatively better trust/supply signal; possible referral or interim routing region.
- `mixed_or_monitor`: does not cleanly fit the above categories.

Final category counts:

- `mixed_or_monitor`: 279
- `referral_or_capacity_candidate`: 99
- `supply_record_quality_problem`: 93
- `phantom_desert_or_verification_gap`: 15
- `real_desert_candidate`: 8

## Validation Result

Audit file:

- `output/data/cleaned_dataset_audit.json`

Upload readiness:

- `upload_ready`: true
- Errors: 0
- Warnings: 1

Remaining warning:

- Raw facilities contained 11 duplicate `unique_id` rows. The cleaned facility table keeps one row per `unique_id` and records source occurrence count.

Validated checks included:

- row counts
- required columns
- unique district keys
- unique cleaned facility IDs
- score bounds in `[0, 1]`
- category validity
- count consistency, such as trustworthy rows not exceeding observed rows
- JSON/notebook validity

## Key Findings

Top care-gap candidates:

- Odisha - Kendujhar
- Bihar - Siwan
- Jharkhand - Dumka
- Jharkhand - Simdega
- Madhya Pradesh - Mandla

Least trustworthy district records:

- Jharkhand - Simdega
- Odisha - Koraput
- Madhya Pradesh - Mandla
- Jammu & Kashmir - Udhampur
- Haryana - Jind

Best care-signal regions:

- Rajasthan - Kota
- Rajasthan - Ajmer
- Tamil Nadu - The Nilgiris
- Rajasthan - Jaipur
- Kerala - Thiruvananthapuram

## Notebooks

Cleaning and join notebook:

- `output/jupyter-notebook/hackathon_dataset_cleaning_analysis.ipynb`

Actual region/facility insights notebook:

- `output/jupyter-notebook/actual_facility_district_insights.ipynb`

## Databricks Upload

Upload completed after the audit passed.

Volume:

- `/Volumes/workspace/default/hackathon_cleaned`

Uploaded files:

- `/Volumes/workspace/default/hackathon_cleaned/district_health_facility_cleaned.csv`
- `/Volumes/workspace/default/hackathon_cleaned/facility_health_cleaned.csv`
- `/Volumes/workspace/default/hackathon_cleaned/district_unmatched_pincode_facility_counts.csv`
- `/Volumes/workspace/default/hackathon_cleaned/pincode_bridge.csv`
- `/Volumes/workspace/default/hackathon_cleaned/cleaned_dataset_audit.json`
- `/Volumes/workspace/default/hackathon_cleaned/actual_insights_summary.json`
- `/Volumes/workspace/default/hackathon_cleaned/cleaned_dataset_actions.md`

Created tables:

- `workspace.default.hackathon_district_health_facility_cleaned` - 494 rows
- `workspace.default.hackathon_facility_health_cleaned` - 10,077 rows
- `workspace.default.hackathon_district_unmatched_pincode_facility_counts` - 60 rows
- `workspace.default.hackathon_pincode_bridge` - 19,586 rows

## Upload Candidates

The validated datasets ready for Databricks upload are:

- `district_health_facility_cleaned.csv`
- `facility_health_cleaned.csv`
- `district_unmatched_pincode_facility_counts.csv`
- `pincode_bridge.csv`
- `cleaned_dataset_audit.json`
- `actual_insights_summary.json`
