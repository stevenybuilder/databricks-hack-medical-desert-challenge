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
../.streamlit/config.toml   # light VF-Match theme
```

## Phases

1. ✅ Skeleton map — H3 hexbin map, specialty filter, metric layers.
2. ✅ Map facilities (click-to-fly + cited detail) + Top Care Gaps leaderboard + region detail.
3. ✅ Uncertainty workflow — external source tiers, data-quality failure modes,
   review protocol, geo-validation candidates, and golden-label seed queue.
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

Run the trainer/report scaffold:

```bash
python3 scripts/train_facility_prediction_models.py
```

Current expected result is `0` trained tasks because the seed rows are not gold or
silver labels. Once labels are promoted, the same script trains calibrated
logistic-regression task models and writes `facility_prediction_model_report.json`.

## Deploy to Databricks Apps (later)

`data.py` currently reads local CSVs. For deployment, swap
`load_facilities()` to query the Unity Catalog Delta tables via the SQL
warehouse, then `databricks bundle deploy` / `databricks apps deploy`.
