# Dataset & Connection Reference — DAIS 2026 Virtue Foundation Hackathon

_Last updated: 2026-06-15_

## Databricks connection

- **CLI:** v1.3.0
- **Profile:** `7474647301321645` (only valid profile)
- **Host:** https://dbc-54942fa9-145a.cloud.databricks.com
- **Default SQL warehouse:** `1b331b704066b677`
- **Catalog:** `databricks_virtue_foundation_dataset_dais_2026` (DELTASHARING_CATALOG)
- **Schema:** `virtue_foundation_dataset`

Query pattern (AI tools; names are literal — no special chars here so no backticks needed):
```bash
databricks experimental aitools tools discover-schema <catalog.schema.table> --profile 7474647301321645
databricks experimental aitools tools query "SELECT ..." --profile 7474647301321645
```

## The three source tables

| Table | Rows | Role |
|---|---|---|
| `facilities` | 10,088 (51 cols) | Web-extracted facility **claims** + provenance/trust signals. NOT ground truth. |
| `india_post_pincode_directory` | 165,627 | Geocoded postal directory (district/state/lat-long). Authoritative. |
| `nfhs_5_district_health_indicators` | ~700 districts | District health need/outcomes. Authoritative (survey). |

### `facilities` key columns
- Provenance: `source_types` (overture/dynamic/constant/kie), `source_ids`, `source_urls`, `source_content_id`, `cluster_id` (entity-resolution / merge cluster)
- Claims (noisy JSON-in-strings): `specialties`, `procedure`, `equipment`, `capability`, `capacity`, `numberDoctors`
- Legitimacy: `officialWebsite`, `officialPhone`, `email`, `distinct_social_media_presence_count`, `affiliated_staff_presence`, `custom_logo_presence`, `recency_of_page_update`, engagement metrics
- Geo: `latitude`/`longitude` — **partly broken** (e.g. "Sanjivani Multi Speciality Hospital", addressed in Kerala, coords in the North Atlantic). Validate against `address_stateOrRegion`/pincode.

## Documentation links

- **Table 1 (`facilities`)** — Virtue Foundation FDR pipeline output (no standalone data dictionary):
  - https://www.databricks.com/blog/databricks-good-and-virtue-foundation-partnering-connect-medical-volunteers-critical-health
  - https://virtuefoundation.org/research-analytics/
  - Underlying open source (the `overture` provenance): https://overturemaps.org/
- **Table 2 (`india_post_pincode_directory`)** — Dept. of Posts, Govt. of India:
  - https://www.data.gov.in/catalog/all-india-pincode-directory
  - https://www.data.gov.in/resource/all-india-pincode-directory-till-last-month (lat/long version)
  - https://www.indiapost.gov.in/pin/
- **Table 3 (`nfhs_5_district_health_indicators`)** — NFHS-5 (IIPS):
  - https://www.nfhsiips.in/nfhsuser/nfhs5.php

Citation rule for the app: Table 1 is *claimed/derived* (cite per-record `source_urls`); Tables 2 & 3 are *authoritative* (present as ground truth).

## Pre-cleaned assets (already built) — under `output/data/`

| File | Notes |
|---|---|
| `district_health_facility_cleaned.csv` (1.3M) | **494 districts.** The app's backbone. See dictionary below. |
| `district_health_facility_cleaned_data_dictionary.csv` | Column docs for the above. |
| `facility_health_cleaned.csv` (49M) | Facility-grain join with `join_strategy`/`join_confidence`/`data_readiness_score`/`needs_human_review`/`plausible_geo` — labels for the predictive engine. |
| `facility_health_cleaned_data_dictionary.csv` | Column docs. |
| `pincode_bridge.csv` (1.6M) | facility PIN → normalized state/district crosswalk. |
| `actual_insights_summary.json` | Pre-computed rankings (top care gaps, desert candidates). |
| `analysis_summary.json`, `cleaned_dataset_audit.json` | Audits. |
| `raw_*.csv` | Raw extracts of the 3 source tables. |
| `output/plots/...` | Pre-rendered insight plots (top_care_gaps, need_vs_trustworthy_supply, etc.). |
| `output/jupyter-notebook/*.ipynb` | Cleaning + insights + NFHS summary notebooks. |

### `district_health_facility_cleaned.csv` — key columns (494 districts)
- **Keys:** `state_ut`, `district_name`
- **Supply (observed, not census):** `observed_facility_rows`, `unique_facility_ids`, `trustworthy_supply_rows`/`_rate` (+CI), `contradicted_or_geo_invalid_rate`, parsed capacity/doctor stats
- **Service signals:** `maternity_signal_rate`, `emergency_signal_rate`, `diagnostic_signal_rate`, `ncd_signal_rate`
- **Need:** `health_need_score` + NFHS condition columns (institutional births, anaemia, BP, blood sugar, cervical/breast/oral screening, etc.)
- **Gaps:** `care_gap_score`, `trust_gap_score`, `district_medical_desert_priority_score`, `best_care_signal_score`
- **Recommendation:** `planning_category` (real_desert_candidate / phantom_desert_or_verification_gap / supply_record_quality_problem / referral_or_capacity_candidate / mixed_or_monitor)
- **Uncertainty:** `district_data_quality_score`, `district_uncertainty_level`, `avg_join_confidence`, `needs_human_review_rate` (+CI), `plausible_geo_rate`, `exact_join_rate`, `source_url_rate`
- **Evidence:** `sample_facility_names`, `sample_claim_evidence`, `sample_source_urls`

### `planning_category` distribution
real_desert_candidate: 8 · phantom_desert_or_verification_gap: 15 · supply_record_quality_problem: 93 · referral_or_capacity_candidate: 99 · mixed_or_monitor: 279

## Known data-quality / join traps
- State alias: NFHS `Maharastra` vs pincode `MAHARASHTRA` (handled via crosswalk; Maharashtra gap now 0).
- District renames need crosswalk: Gurgaon/Gurugram, Bangalore/Bengaluru Urban, Darjiling/Darjeeling, Haora/Howrah, etc.
- NFHS table has trailing spaces in district names; numeric columns include some strings ("NA") that need casting.
- Pincode lat/long are strings with literal "NA" for missing.
- NFHS is district-grain context, never a facility-level fact.

## Standout NFHS condition stats (demo hooks)
- Cervical screening 1.6% mean / breast 0.7% / oral cancer 0.7% — vs men's tobacco 40.6%.
- Women 15–49 anaemia 55.9% mean (up to 70%+).
- Child stunting 33.5% mean (up to 60.6%).
- Institutional births down to 21.4% (Mon, Nagaland).
