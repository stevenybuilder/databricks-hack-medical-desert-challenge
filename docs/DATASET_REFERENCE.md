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

## Canonical cleaned tables in Unity Catalog (`workspace.default`)

These are the **single source of truth** for the deployed app (created by the
cleaning pipeline). The app reads them when `DATA_BACKEND=warehouse`; local dev
defaults to the CSVs below.

| UC table | Rows |
|---|---|
| `workspace.default.hackathon_facility_health_cleaned` | 10,077 |
| `workspace.default.hackathon_district_health_facility_cleaned` | 494 |
| `workspace.default.hackathon_pincode_bridge` | — |
| `workspace.default.hackathon_district_unmatched_pincode_facility_counts` | — |
| `workspace.default.active_learning_facility_queue` | planned |
| `workspace.default.active_learning_district_queue` | planned |
| `workspace.default.trust_uncertainty_model_versions` | planned |
| `workspace.default.golden_facility_source_matches` | planned |
| `workspace.default.golden_facility_training_set` | planned |
| `workspace.default.facility_prediction_features` | planned |
| `workspace.default.facility_prediction_outputs` | planned |
| Volume `workspace.default.hackathon_cleaned` | source CSV uploads |

> Cleanup note: an earlier duplicate schema `workspace.vf_hackathon` was removed —
> use `workspace.default.hackathon_*` only.

### The full data picture (to avoid confusion)
- **Raw source (read-only Delta share):** `databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.*`
- **Cleaned (canonical):** `workspace.default.hackathon_*` (above)
- **Local dev copies:** `output/data/*.csv`

## Pre-cleaned assets (already built) — under `output/data/`

| File | Notes |
|---|---|
| `district_health_facility_cleaned.csv` (1.3M) | **494 districts.** The app's backbone. See dictionary below. |
| `district_health_facility_cleaned_data_dictionary.csv` | Column docs for the above. |
| `facility_health_cleaned.csv` (49M) | Facility-grain join with `join_strategy`/`join_confidence`/`data_readiness_score`/`needs_human_review`/`plausible_geo` — proxy features for the trust/uncertainty engine. |
| `facility_health_cleaned_data_dictionary.csv` | Column docs. |
| `pincode_bridge.csv` (1.6M) | facility PIN → normalized state/district crosswalk. |
| `semantic_missingness_summary.csv` | Semantic validity and missing/invalid rates for capacity, doctors, year established, recency, and equipment. |
| `active_learning_facility_queue.csv` | Top 500 active-uncertainty facility rows for source enrichment, stress testing, and cautious UI surfacing. |
| `active_learning_district_queue.csv` | Top 250 active-uncertainty district rows with rate CIs and decision-fragility signals. |
| `geo_validation_candidates.csv` | Top geo-invalid/suspicious facility rows for Google/Mappls/API source enrichment, with action, uncertainty bands, and reason codes. |
| `geocoder_uncertainty_priors.csv` | Transparent priors for how geocoder statuses/location types affect proxy confidence bands. |
| `golden_facility_source_matches_seed.csv` | Seed source/context rows for the golden facility phase; not training truth. |
| `golden_facility_training_set_seed.csv` | Bronze/conflict seed labels and evidence tiers; all rows abstain from supervised training until promoted. |
| `facility_prediction_features_seed.csv` | Initial feature table contract for map-click prediction. |
| `facility_prediction_outputs_seed.csv` | Rule-baseline prediction outputs with confidence, evidence tier, and abstain reason. |
| `golden_facility_seed_report.json` | Report-card counts and guardrails for the seed artifacts. |
| `facility_prediction_model_report.json` | Supervised trainer report: model choice, trained/skipped tasks, metrics, and abstention policy. |
| `decision_category_volume_summary.csv` | Category volumes, percentages, Wilson intervals, and Bayesian Jeffreys intervals by grain. |
| `statistical_decision_policy_report.json` | Decision rules and statistical-method policy for confidence thresholds, expected value, Bayesian updates, and causal boundaries. |
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
Current `district_health_facility_cleaned.csv` distribution:
real_desert_candidate: 31 · phantom_desert_or_verification_gap: 54 ·
supply_record_quality_problem: 89 · referral_or_capacity_candidate: 90 ·
mixed_or_monitor: 230

## Known data-quality / join traps
- State alias: NFHS `Maharastra` vs pincode `MAHARASHTRA` (handled via crosswalk; Maharashtra gap now 0).
- District renames need crosswalk: Gurgaon/Gurugram, Bangalore/Bengaluru Urban, Darjiling/Darjeeling, Haora/Howrah, etc.
- NFHS table has trailing spaces in district names; numeric columns include some strings ("NA") that need casting.
- Pincode lat/long are strings with literal "NA" for missing.
- NFHS is district-grain context, never a facility-level fact.
- Facility operational fields contain semantic missingness: string `"null"`, empty
  arrays, blank extracted lists, no-evidence text, invalid dates, and unparseable
  numbers. Use status/confidence/display fields instead of raw values.
- The cleaned data currently has no human-verified facility label set. Use proxy
  trust scores, confidence intervals, and active uncertainty ranking rather than
  claiming measured model accuracy.

## Active uncertainty and proxy trust data

The app should expose active uncertainty queues instead of relying on unavailable
human labels. These tables are planned in `workspace.default`; local CSVs already
exist in `output/data/`:

| Table | Purpose |
|---|---|
| `active_learning_facility_queue` | Ranked facility rows with active uncertainty score, action, reasons, proxy trust band, capacity/doctor prediction intervals, and source fields. |
| `active_learning_district_queue` | Ranked district rows with active uncertainty score, action, reasons, Wilson intervals, care/trust gap scores, and sample evidence. |
| `trust_uncertainty_model_versions` | Optional report card for proxy-score versions: features, score weights, interval policy, sensitivity checks, and limitations. |

These tables turn weak proxy labels into a no-human-label uncertainty loop:

```text
semantic/proxy trust score -> active uncertainty queue -> source enrichment or
sensitivity analysis -> updated confidence bands -> safer recommendations
```

Initial statistical posture:

- Programmatic labels are weak labels, not gold labels.
- Wilson intervals are appropriate for district rates.
- Empirical p10-p90 intervals are appropriate for estimated capacity/doctors.
- Proxy trust bands are triage uncertainty bands, not measured accuracy intervals.
- Google/Mappls geocoding, HFR/ABDM, PM-JAY, OSM/Overture, and source URLs are
  source-agreement signals. They reduce uncertainty only when provider metadata,
  admin geography, pincode, and facility-name checks agree.

## Planned golden facility prediction data

Phase 5 adds supervised learning only after source-corroborated labels exist. The
target dataset is `workspace.default.golden_facility_training_set`, built by
conflating cleaned FDR rows with HFR/ABDM, Overture, OSM/Healthsites, India Post,
government directories, and cited facility sources.

Planned source-tier policy:

| Tier | Meaning |
|---|---|
| `gold` | Authoritative registry match or strong independent source agreement. |
| `silver` | Open-data corroboration but no authoritative registry match. |
| `bronze` | Weak/FDR-only evidence; keep for active learning, not final training. |
| `conflict` | Sources disagree; exclude from training and route to review. |

Predictions for new map-selected locations should be written to
`workspace.default.facility_prediction_outputs` with model version, confidence,
evidence tier, abstain/review reason, and source links.

## External geocoding explainability data

`geo_validation_candidates.csv` is the bridge between the cleaning work and the
parallel Google Maps geocoding/API work. It includes:

- `external_validation_action` for the next enrichment step;
- `external_validation_priority_score` for active API-call triage;
- `pre_geocode_uncertainty_band_low_km` and `_high_km`;
- `external_evidence_sources_to_check`;
- `external_uncertainty_reason_codes`;
- `geocoder_acceptance_rule`;
- `google_response_fields_to_store`.

Use it to explain why a coordinate is fragile and what external data would reduce
uncertainty. Do not convert a geocoder hit into `verified`; convert it into a
smaller or larger proxy band depending on source agreement.

## Standout NFHS condition stats (demo hooks)
- Cervical screening 1.6% mean / breast 0.7% / oral cancer 0.7% — vs men's tobacco 40.6%.
- Women 15–49 anaemia 55.9% mean (up to 70%+).
- Child stunting 33.5% mean (up to 60.6%).
- Institutional births down to 21.4% (Mon, Nagaland).
