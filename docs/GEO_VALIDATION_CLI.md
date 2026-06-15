# Geo Validation CLI Workflow

_Last updated: 2026-06-15_

## Decision

Use Databricks AI tools for the LLM "janitor" step and use a map/geocoder provider for
physical validation.

- LLM role: parse messy Indian facility address text into structured JSON.
- Google Maps / Mappls role: validate that the cleaned address exists and return coordinates
  plus quality metadata.
- No-human-label role: convert ambiguous geocoder outcomes, provider conflicts, and
  high-impact clinical records into active uncertainty queue entries.

This avoids training a model or hand-labeling every facility. The work becomes
source-agreement scoring and uncertainty triage, not a labeling marathon.

## Confirmed workspace tooling

Profile:

```bash
PROFILE=7474647301321645
WAREHOUSE=1b331b704066b677
```

Ready model endpoints observed from CLI:

- `databricks-gemini-3-5-flash`
- `databricks-meta-llama-3-3-70b-instruct`
- `databricks-gpt-oss-20b`
- `databricks-gpt-oss-120b`

CLI groups used:

```bash
databricks experimental aitools tools query
databricks experimental aitools tools discover-schema
databricks serving-endpoints list
databricks serving-endpoints query
```

## Current geo problem from warehouse

Read-only command:

```bash
databricks experimental aitools tools query \
  --profile "$PROFILE" \
  --warehouse "$WAREHOUSE" \
  --file output/sql/geo_validation_summary.sql \
  -o json
```

Observed current counts:

| Geo quality | Rows | Meaning |
|---|---:|---|
| `plausible` | 7,859 plus 2 contradicted | Usually usable |
| `moderate_distance_from_pincode_centroid` | 1,164 | Needs validation if operationally important |
| `far_from_pincode_centroid` | 928 | High-priority correction queue |
| `missing_coordinates` | 118 | Need geocode or external registry |
| `outside_india_bbox` | 6 | Demo-grade failure; fix/flag immediately |

## Generate local batch artifacts

```bash
.venv/bin/python scripts/prepare_geo_validation_batch.py \
  --limit 250 \
  --endpoint databricks-gemini-3-5-flash
```

Outputs:

- `output/data/geo_validation_candidates.csv`
- `output/data/geocoder_uncertainty_priors.csv`
- `output/data/geo_validation_ai_prompts.jsonl`
- `output/sql/geo_validation_summary.sql`
- `output/sql/geo_validation_candidates_create.sql`
- `output/sql/geo_address_janitor_ai_query.sql`
- `output/sql/geo_fuzzy_reconciliation.sql`
- `output/sql/lakeflow_geo_validation_pipeline.sql`

The candidate CSV includes explainability fields for the notebook/app:

| Field | Meaning |
|---|---|
| `external_validation_action` | What the pipeline should do next: replace coordinate, geocode missing coordinate, compare PIN/district, or monitor. |
| `external_validation_priority_score` | Value-of-information score combining geo failure severity, medical-desert impact, health need, and data readiness. |
| `pre_geocode_uncertainty_band_low_km` / `_high_km` | Heuristic planning band around current coordinate disagreement before external evidence is applied. |
| `external_evidence_sources_to_check` | Google, India Post, Mappls, HFR/ABDM, PM-JAY, OSM/Overture, or source URL checks to use. |
| `external_uncertainty_reason_codes` | JSON reason codes explaining why the row is in the queue. |
| `geocoder_acceptance_rule` | Human-readable rule for when a geocoder result can reduce uncertainty. |
| `google_response_fields_to_store` | API metadata that must be persisted for explainability. |
| `fuzzy_precheck_status` / `fuzzy_precheck_reasons` | PIN/state/district sanity checks reused from the cleaning script before geocoder spend. |
| `city_pincode_district_similarity` | Normalized city-vs-PIN-district fuzzy score for conflict triage. |

## Run Databricks LLM janitor in parallel

The generated SQL creates two Delta tables:

- `workspace.default.hackathon_geo_validation_candidates`
- `workspace.default.hackathon_geo_address_janitor`

Run them sequentially because the janitor table depends on the candidates table:

```bash
databricks experimental aitools tools query \
  --profile "$PROFILE" \
  --warehouse "$WAREHOUSE" \
  --file output/sql/geo_validation_candidates_create.sql

databricks experimental aitools tools query \
  --profile "$PROFILE" \
  --warehouse "$WAREHOUSE" \
  --file output/sql/geo_address_janitor_ai_query.sql
```

Then run the fuzzy reconciliation stage:

```bash
databricks experimental aitools tools query \
  --profile "$PROFILE" \
  --warehouse "$WAREHOUSE" \
  --file output/sql/geo_fuzzy_reconciliation.sql
```

That creates `workspace.default.hackathon_geo_fuzzy_reconciliation`, which checks
the LLM-parsed city/state/PIN against the existing PIN bridge and join confidence.

Observed 2026-06-15 run:

| Table | Rows |
|---|---:|
| `workspace.default.hackathon_geo_validation_candidates` | 250 |
| `workspace.default.hackathon_geo_address_janitor` | 250 |
| `workspace.default.hackathon_geo_fuzzy_reconciliation` | 250 |

Fuzzy precheck status in candidates:

| Status | Rows |
|---|---:|
| `fuzzy_ok` | 139 |
| `city_pin_district_conflict` | 84 |
| `state_pin_conflict` | 12 |
| `ambiguous_pin_bridge` | 12 |
| `weak_health_join` | 3 |

Reconciliation status after LLM parsing:

| Status | Rows |
|---|---:|
| `ready_for_geocoder` | 138 |
| `parsed_city_district_conflict` | 83 |
| `pre_geocoder_review` | 24 |
| `parsed_state_conflict` | 5 |

Read-only summaries and independent checks can use `--concurrency`, but dependent
table-creation steps should stay sequential.

## DLT / Lakeflow answer

The fuzzy-match techniques are worth using now. Standing up a full Lakeflow
pipeline is not worth the hackathon overhead unless this becomes a scheduled job.
The generated `output/sql/lakeflow_geo_validation_pipeline.sql` is a production
template with materialized views over the candidate, LLM janitor, and reconciliation
tables. Use it later when the workflow needs incremental refresh, expectations,
or scheduled runs.

## Non-geocoder sources for cleanup

Geocoding fixes location, but it does not prove facility truth. Use these other
open datasets and methods in parallel:

| Source/method | What it cleans or verifies |
|---|---|
| ABDM Health Facility Registry | Existence, official facility identity, facility type, location where available. |
| PM-JAY empanelled hospitals | Active hospital-network existence and broad service/specialty hints. |
| India Post PIN directory via data.gov.in | PIN/state/district bridge, ambiguity flags, centroid sanity checks. |
| National Health Portal / data.gov.in health datasets | Legacy names, contacts, public/private status, specialty corroboration. |
| Overture Maps Places | Independent POI name/category/coordinate/contact confidence. |
| OpenStreetMap / Overpass / Healthsites | Community-mapped facility names and coordinates. |
| geoBoundaries | District/state containment checks for coordinates and joins. |
| HMIS / NHSRC and NFHS-5 | District context and need-side plausibility, not individual facility truth. |
| Fuzzy/entity matching | Normalize names, states, districts, PINs; deduplicate and detect city/PIN/state conflicts. |

## Missing and incomplete data

Current policy:

- Missing coordinates: run LLM address parsing, geocoder validation, then keep
  approximate/conflicting outcomes in the uncertainty queue.
- Missing capacity/doctors: use the existing peer-group estimate columns with
  p10-p90 intervals and confidence labels; never present estimates as observed.
- Missing services/equipment/procedures: treat as missing evidence, not evidence
  of absence; enrich from registries/source pages or review high-impact rows.
- Missing contacts: enrich from registry/POI/source data, but reachability only
  improves after a call/email outcome.
- Missing source URL or stale recency: downweight `data_readiness_score` and keep
  stronger corroboration requirements before reducing uncertainty.

## Google / Mappls validation step

For each `parsed_address.geocoder_query`, call a geocoder with India restriction:

```text
https://maps.googleapis.com/maps/api/geocode/json
  ?address=<URL_ENCODED_QUERY>
  &components=country:IN
  &key=$GOOGLE_MAPS_API_KEY
```

Store the response metadata:

- `status`
- `formatted_address`
- `place_id`
- `geometry.location.lat`
- `geometry.location.lng`
- `geometry.location_type`
- `partial_match`
- `plus_code`
- provider name and timestamp

For India, retry with `landmark + locality + city + state + PIN` when the first pass is
`APPROXIMATE` or `ZERO_RESULTS`. Use Mappls/MapmyIndia as a provider fallback for rural,
landmark-heavy, or narrow-lane addresses.

Google's current docs distinguish result precision with `location_type` values
such as `ROOFTOP`, `RANGE_INTERPOLATED`, `GEOMETRIC_CENTER`, and `APPROXIMATE`,
and expose `ZERO_RESULTS` plus `partial_match`. Google also cautions that a precise
geocoder location does not by itself prove the address exists. Therefore the app
must show provider metadata and admin-geography agreement rather than just a green
"verified" badge.

## Quality rules

| Geocoder result | Action |
|---|---|
| `ROOFTOP` | Accept as high-quality correction |
| `RANGE_INTERPOLATED` | Accept unless it crosses district/PIN boundary |
| `GEOMETRIC_CENTER` with `premise` / `sublocality` / strong locality match | Accept for H3/neighborhood analysis, flag if facility-level precision matters |
| `APPROXIMATE` | Retry with landmark/locality query; otherwise route to uncertainty queue |
| `ZERO_RESULTS` | Search HFR/PM-JAY/Mappls; otherwise route to uncertainty queue |
| `partial_match=true` | Medium quality; route high-impact rows to uncertainty queue |

## Statistical confidence update

Use a Bayesian-style source-agreement update, but label it as a proxy:

```text
internal evidence prior
+ geocoder precision signal
+ admin geography agreement
+ registry/source corroboration
- contradiction or partial-match penalty
= updated proxy trust band
```

Implementation policy:

- Narrow the geo band only when provider coordinates, formatted address, state,
  district/PIN, and name tokens agree.
- Keep the band wide when Google and Mappls disagree, when a result is approximate,
  or when the geocoder only returns a region center.
- Do not compute Brier score, ECE, or measured accuracy without ground-truth labels.
- Feed unresolved or high-impact cases into `active_learning_facility_queue.csv`
  using `external_validation_action` and reason codes.

## No-human-label answer

No model-training label set is required for geocoding, and the hackathon flow does
not depend on manual verification. Ambiguous geocoder outcomes should be converted
into uncertainty signals:

- `geo_quality`;
- `geo_distance_km_to_pincode_centroid`;
- `join_confidence`;
- `join_uncertainty_reason`;
- active uncertainty queue priority.

If a future workflow adds authoritative source matches, those outcomes can improve
the proxy score. They are not required before running the LLM parser + geocoder
pipeline.

## Sources

- Google Geocoding API request/response docs: https://developers.google.com/maps/documentation/geocoding/guides-v3/requests-geocoding
- Google Maps Geocoding location types: https://developers.google.com/maps/documentation/javascript/geocoding
- Google location validation architecture note: https://developers.google.com/maps/architecture/geocoding-address-validation
- Databricks `ai_query`: https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_query
- Databricks AI Functions overview: https://docs.databricks.com/aws/en/large-language-models/ai-functions
- ABDM Health Facility Registry: https://facility.abdm.gov.in/
- PM-JAY empanelled hospital search: https://hospitals.pmjay.gov.in/Search/
- Open Government Data India APIs: https://www.data.gov.in/apis
- India Post PIN directory: https://www.data.gov.in/resource/all-india-pincode-directory-till-last-month
- Overture Maps Places guide: https://docs.overturemaps.org/guides/places/
- OpenStreetMap healthcare tags: https://wiki.openstreetmap.org/wiki/Key:healthcare
- Healthsites.io: https://www.healthsites.io/
- geoBoundaries: https://www.geoboundaries.org/
- NFHS-5 district fact sheets: https://dhsprogram.com/publications/publication-OF43-Other-Fact-Sheets.cfm
- NHSRC HMIS analysis: https://nhsrcindia.org/hmis-data-analysis
