# Medical Desert Navigator — App

VF-Match-style Databricks App for visiting/volunteer clinicians: find where your
specialty is needed most across India, and which facilities can be trusted.

See `../docs/PRODUCT_SPEC.md`, `../docs/BUILD_PLAN.md`, `../docs/DATA_SOURCES_ANALYSIS.md`.

## Run locally

```bash
# from the project root (databricks_hackathon/)
.venv/bin/streamlit run app/app.py
# then open http://localhost:8501
```

The app reads the pre-cleaned tables from `../output/data/` by default.
Override the location with `DATA_DIR=/path/to/data`.

## Structure

```
app/
  app.py              # Streamlit entrypoint — tabs: Map / Top care gaps / Uncertainty
  app.yaml            # Databricks Apps run config
  requirements.txt
  lib/
    config.py         # paths, specialty maps, metrics, basemaps, colors
    data.py           # load + hexbin + facility points + districts + leaderboard
    ui.py             # CSS, header, facility card, region detail, legend
../.streamlit/config.toml   # dark Google Earth-style command theme
```

## Phases

1. ✅ Skeleton map — H3 hexbin map, specialty filter, metric layers.
2. ✅ Map facilities (click-to-fly + cited detail) + Top Care Gaps leaderboard + region detail.
3. ✅ Uncertainty workflow — external source tiers, data-quality failure modes,
   active district/facility explainability queues, geo source-agreement candidates,
   geocoder priors, and golden-label seed reports.
4. ⬜ Persist user actions (shortlist/notes/review outcomes) to Delta.
5. ⬜ Golden facility prediction engine — supervised models trained only on a
   corroborated golden dataset; predicts facility attributes for new map-selected
   locations with confidence, evidence tier, and abstention.
6. ⬜ Polish + deploy + 3-min demo.

## Golden prediction seed artifacts

Build the Phase 5 seed tables locally:

```bash
python3 scripts/build_golden_facility_seed.py
```

The script writes bronze/conflict-only seed artifacts under `output/data/` and the
Uncertainty tab displays `golden_facility_seed_report.json`. These rows define the
schema and abstention behavior; they are not supervised training labels until Tier
A/B source corroboration promotes them.

The tab also reads these explainability artifacts when present:

- `active_learning_district_queue.csv`
- `active_learning_facility_queue.csv`
- `geo_validation_candidates.csv`
- `geocoder_uncertainty_priors.csv`

Those surfaces show reason codes, confidence intervals, proxy trust bands,
pre-geocode uncertainty bands, and the external source checks needed to reduce
uncertainty.

Run the trainer/report scaffold:

```bash
python3 scripts/train_facility_prediction_models.py
```

Current expected result is `0` trained tasks because the seed rows are not gold or
silver labels. Once labels are promoted, the same script trains calibrated
logistic-regression task models and writes `facility_prediction_model_report.json`.

Build the decision-statistics report card:

```bash
python3 scripts/build_statistical_decision_report.py
```

This writes `decision_category_volume_summary.csv`,
`statistical_decision_policy_report.json`, and
`docs/STATISTICAL_DECISION_FRAMEWORK.md`. The Uncertainty tab uses these artifacts
to show category volumes, percentages, Wilson intervals, Bayesian Jeffreys
intervals, and which statistical methods are valid now versus later.

## Deploy to Databricks Apps (later)

`data.py` currently reads local CSVs. For deployment, swap
`load_facilities()` to query the Unity Catalog Delta tables via the SQL
warehouse, then `databricks bundle deploy` / `databricks apps deploy`.
