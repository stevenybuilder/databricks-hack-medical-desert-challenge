# Golden Facility Prediction Phase

_Last updated: 2026-06-15_

## Decision

Add a supervised-learning phase only after building a cleaned golden facility
dataset. The model should predict facility attributes for newly selected map
locations, but every prediction must carry evidence, confidence, and an abstain
path. The goal is proactive recommendations grounded in corroborated facility
records, not a model that launders messy FDR claims into truth.

## Product purpose

When a user clicks or selects a new location on the map, the engine should answer:

- What facility or facilities are likely nearby?
- What type of facility is this likely to be?
- Which service signals are likely present: maternity, emergency, diagnostics,
  chronic/NCD, oncology/screening, pharmacy, lab?
- What are plausible capacity and doctor-count bands?
- Does the location look like a trustworthy supply signal, a weak claim, or a
  contradiction needing review?
- How should the app act: recommend, verify first, enrich sources, or abstain?

## Source tiers

Use source tiers so model labels remain auditable.

| Tier | Sources | Role |
|---|---|---|
| A | ABDM Health Facility Registry (HFR), authoritative government/state registries when accessible | Identity, facility type, location, ownership, official registry evidence. |
| B | Overture Maps Places, OpenStreetMap/Healthsites.io, data.gov.in Hospital Directory, PM-JAY or other public program lists | Open corroboration and extra attributes. |
| C | Facility official website, source URLs from FDR, social/contact evidence | Claim support and recency/provenance. |
| D | Google Places/Geocoding, Mappls/MapmyIndia | Runtime validation and uncertainty reduction only, unless license review explicitly allows durable training use. |

HFR is the strongest ground-truth candidate for facility identity, but HFR still
does not prove clinical quality or service availability. Overture/OSM/Healthsites
are good open corroboration sources. Google/Mappls are useful validators for
ambiguous records, but do not use them as durable training labels without a terms
review.

Useful source links:

- HFR/ABDM: https://abdm.gov.in/health-facilities
- Overture Places: https://docs.overturemaps.org/guides/places/
- Healthsites.io: https://develop.healthsites.io/
- OpenStreetMap healthcare tags: https://wiki.openstreetmap.org/wiki/Key:healthcare
- data.gov.in Hospital Directory: https://www.data.gov.in/catalog/hospital-directory-national-health-portal

## Golden dataset construction

Create `golden_facility_training_set` from the current cleaned facility table plus
external source agreement.

Required grain:

```text
one row per canonical facility-location candidate
```

Minimum columns:

- canonical IDs: `golden_facility_id`, `unique_id`, optional HFR ID, Overture ID,
  OSM ID, Healthsites ID, source-specific IDs.
- location: normalized address, PIN, district/state, lat/lon, geohash/H3,
  admin-match fields, geocoder quality metadata.
- labels: facility type, ownership, system of medicine, service-signal labels,
  trustworthy/existence posture, contradiction flags, capacity band, doctor-count band.
- evidence: source tier, matched source count, exact/fuzzy match type, URLs,
  evidence snippets, match score, source timestamps.
- uncertainty: label confidence, abstain reason, conflict reason, reviewer status.

Label policy:

| Label class | Definition | Model use |
|---|---|---|
| `gold` | Tier A match plus consistent admin geography, or multiple independent Tier B/C sources agreeing. | Train and evaluate. |
| `silver` | Strong open-source agreement, but no authoritative registry match. | Train with lower sample weight or validate separately. |
| `bronze` | FDR-only or weak/fuzzy corroboration. | Do not train final supervised model; use for active learning. |
| `conflict` | Sources disagree on identity, district, PIN, facility type, or location. | Exclude from training; send to review queue. |

## Model tasks

Train separate, interpretable tasks instead of one opaque score. The first model
family is calibrated logistic regression because it is a defensible baseline for
small source-corroborated tabular labels and produces probabilities for
abstention. Compare against LightGBM/CatBoost only after enough gold/silver labels
exist per task.

| Task | Output | Suggested model |
|---|---|---|
| Facility existence/trust posture | passed checks / needs review / contradicted | Calibrated logistic classifier with abstention. |
| Facility type | hospital, clinic, lab, pharmacy, dental, blood bank, etc. | Multiclass calibrated logistic classifier. |
| Service signals | maternity, emergency, diagnostic, NCD, oncology/screening | One binary calibrated logistic classifier per service. |
| Capacity band | none/unknown, small, medium, large, very large | Multiclass calibrated logistic baseline; later compare ordinal/quantile methods. |
| Doctor-count band | none/unknown, solo/small team, medium, large | Multiclass calibrated logistic baseline; later compare ordinal/quantile methods. |
| Location/admin confidence | high, medium, low, conflict | Rule-assisted classifier using geospatial features. |

Available-at-selection features:

- selected lat/lon, H3 cell, district/state/PIN from India Post bridge;
- nearby known facility density and nearest-neighbor distances;
- Overture/OSM/Healthsites nearby categories and confidence where available;
- district health-need features from NFHS as context, not labels;
- facility-name/address text features when user provides a name;
- current cleaned facility evidence fields if the selected location matches an
  existing FDR row.

## Evaluation

Report only metrics that are backed by golden labels:

- holdout accuracy/F1 for type and service signals;
- precision/recall for `contradicted` and `needs_review`;
- calibration curves or Brier score for tasks with enough labels;
- coverage at confidence thresholds, for example "model answers 62% of locations
  at >=0.8 confidence and abstains on the rest";
- error slices by state, facility type, rural/urban, source tier, and sparse
  districts.

Do not report supervised accuracy on weak/programmatic labels. Keep the existing
active uncertainty queue for regions where the model abstains or sources conflict.

## Databricks implementation

Recommended tables in `workspace.default`:

| Table | Purpose |
|---|---|
| `golden_facility_source_matches` | Raw source-to-source matches with match scores and conflict reasons. |
| `golden_facility_training_set` | One row per canonical facility-location with labels and evidence tier. |
| `facility_prediction_features` | Feature table for training and map-click inference. |
| `facility_prediction_outputs` | Predictions for selected/new map locations with confidence and abstain reason. |
| `trust_uncertainty_model_versions` | Model report cards, feature lists, metrics, thresholds, and known blind spots. |

Model serving path:

```text
map click -> feature lookup/enrichment -> model endpoint -> prediction +
confidence + evidence tier + abstain/review action -> UI card and persisted row
```

## Current seed builder

The initial dev scaffold is:

```bash
python3 scripts/build_golden_facility_seed.py
```

It writes local seed artifacts under `output/data/`:

- `golden_facility_source_matches_seed.csv`
- `golden_facility_training_set_seed.csv`
- `facility_prediction_features_seed.csv`
- `facility_prediction_outputs_seed.csv`
- `golden_facility_seed_report.json`

These are deliberately **not** trainable supervised labels. The current seed rows
are bronze/conflict only and exist to define schema, evidence tiers, abstention,
and report-card behavior before registry/open-data corroboration promotes rows to
gold or silver.

The training/report scaffold is:

```bash
python3 scripts/train_facility_prediction_models.py
```

With the current seed artifacts it writes `output/data/facility_prediction_model_report.json`
showing `0` trained tasks. That is correct until rows are promoted to gold/silver.

## Guardrails

- Never use NFHS district indicators as facility-level labels.
- Never collapse `unknown` into `false`.
- Do not use Google/Mappls data as durable training data unless license review
  explicitly permits it.
- Preserve source IDs and evidence URLs with every label and prediction.
- Prefer abstention over confident guesses in sparse or conflicting regions.
- Keep active uncertainty queues as the feedback loop for new labels.

## Phase acceptance criteria

- Golden dataset exists with source tiers, evidence fields, and conflict labels.
- At least one supervised task is trained and evaluated on Tier A/B holdout labels.
- Model outputs include confidence, abstain reason, evidence tier, and source links.
- New map-selected locations can be scored and persisted to Delta.
- The app shows a report card explaining label coverage, metrics, slices, and
  limits before any prediction is treated as actionable.
