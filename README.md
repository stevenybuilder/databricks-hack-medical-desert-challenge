# Databricks Copilot: Medical Desert Map

Confidence-aware medical-desert planning for India. The app uses Bayesian-style provider trust scoring, uncertainty-aware geospatial analysis, CatBoost supply imputation, Wilson confidence intervals, and split-conformal proxy coverage to help planners decide where to deploy doctors, where to call or verify providers, and where the evidence is still too weak to trust.

Built for the [Databricks Apps & Agents for Good Hackathon 2026](https://dais-for-good-2026.devpost.com/). Project page: [Databricks Copilot: Medical Desert Map](https://devpost.com/software/databricks-copilot-medical-desert-map).

## Live Demo

- Public Cloud Run app: https://caregap-app-31043195041.us-central1.run.app/
- Databricks App: https://caregap-app-7474647301321645.aws.databricksapps.com
- Devpost submission: https://devpost.com/software/databricks-copilot-medical-desert-map

The Databricks App may require workspace authentication. The Cloud Run app is the public demo path.

## What It Does

CareGap helps a healthcare planner answer three questions:

- **Where should we act first?** The Map and Top Care Gaps views rank districts by health need, provider scarcity, and uncertainty.
- **Can we trust the provider evidence?** Facility cards show source-backed claims, service chips, check status, and trust tiers instead of treating every row as ground truth.
- **What should happen next?** The app recommends deploy/build, call or verify, fix records, referral routing, or monitoring.

Core workflows:

- Medical desert map with district-level care-gap scoring.
- Top Care Gaps shortlist for doctor deployment planning.
- Provider-claim cards with source links, service chips, and automated check status.
- Filters for districts with provider claims versus no mapped claims.
- Hover explanations for health need, gap confidence, and provider trust.
- Planner notes and saved actions for demo handoff.
- Copilot explanations for methodology, caveats, and next steps.

## Technical Approach

The app is a Streamlit front end over a Databricks-style lakehouse flow:

- **Bronze:** raw facility, geography, and claim inputs.
- **Silver:** normalized provider, address, PIN code, district, and service-claim features.
- **Feature tables:** provider evidence features, geo-quality indicators, supply estimates, and district health-need inputs.
- **Gold:** care-gap rankings, provider trust, conformal sets, intervention outputs, and review queues.

Decision and uncertainty layers:

- **CatBoost supply imputers:** capacity and doctor-count gaps are imputed with CatBoost regressors trained on observed rows. The scripts use native categorical handling, log1p target transforms, 5-fold out-of-fold validation, cohort-median baselines, clipped predictions, and MLflow logging.
- **Provider validity posterior:** facility evidence is scored from source URLs, geography consistency, service claims, missingness, contradiction flags, contact evidence, recency, and semantic quality.
- **Calibrated provider trust:** district cards show High/Medium/Low trust. The score blends row-level Bayesian validity posterior with an empirical-Bayes-smoothed hard-check pass rate so thin samples do not collapse into misleading visible zeroes.
- **Wilson confidence intervals:** bounded district/facility rates use Wilson 95% intervals for finite-row uncertainty, including check-pass, review-needed, and critical supply-gap rates.
- **Split-conformal proxy coverage:** facility trust sets wrap the validity posterior with split-conformal prediction sets. Current calibration targets alpha = 0.10 and reports about 91.8% empirical coverage on the automated proxy-valid class, not human-verified medical truth.
- **Active review queues:** rows are prioritized when another source check, geocode check, or claim review is likely to change the decision.

## Built With

- Databricks Apps
- Databricks SQL Warehouse
- Delta Lake / Unity Catalog
- MLflow
- Python
- Streamlit
- Pandas / NumPy / scikit-learn
- CatBoost
- PyDeck / H3-style district mapping
- Google Maps geocoding and place metadata workflows
- Google Cloud Run

## Repository Layout

```text
app/
  app.py                  # Streamlit entrypoint
  app.yaml                # Databricks Apps configuration
  lib/                    # UI, data access, trust, map/gaps/copilot modules
scripts/
  catboost/               # Capacity and doctor-count imputation training
  build_conformal_calibration.py
  build_statistical_decision_report.py
docs/
  devpost/                # Devpost copy and media notes
output/data/              # Public cleaned aggregate artifacts used by CSV mode
Dockerfile                # Cloud Run public demo image
```

Sensitive geocoding outputs, API keys, local caches, SQLite state, and raw/debug artifacts are excluded by `.gitignore`, `.dockerignore`, and `.gcloudignore`.

## Run Locally

From the repository root:

```bash
.venv/bin/streamlit run app/app.py
```

Then open:

```text
http://127.0.0.1:8501
```

The app defaults to `DATA_BACKEND=csv` and reads the cleaned public artifacts under `output/data/`.

## Cloud Run Deploy

The public demo is deployed with:

```bash
gcloud run deploy caregap-app \
  --source . \
  --region us-central1 \
  --project project-flash-490419 \
  --allow-unauthenticated \
  --update-env-vars DATA_BACKEND=csv \
  --quiet
```

The Docker image copies `app/`, `.streamlit/`, and the allowed public `output/data/` artifacts only.

## Caveats

This is proxy decision support, not verified medical truth. Provider trust reflects evidence quality and automated checks. The current conformal calibration uses a proxy pseudo-label until a larger human-verified gold/silver label set exists.

## Team

Built by Steven Yang, Ji Chen, Ayush Mishra, and Changbin Gong.
