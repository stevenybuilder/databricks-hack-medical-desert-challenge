# CareGap Agent — Teammate Brief

_A high-level overview of what we built for the Databricks "Apps & Agents for Good" hackathon._

## 1. The one-liner

> **CareGap Agent** turns messy, web-derived Indian healthcare-facility data into **confidence-aware medical-desert intervention recommendations** — it shows *where* care gaps are, *why*, *what to do about it*, and *how much to trust the data*, with every claim cited and every uncertainty surfaced.

Built on Databricks (Lakehouse + Unity Catalog + MLflow + Databricks Apps). The whole posture is **honest about messy data**: high field coverage ≠ high trust, so we treat extracted fields as *claims to verify*, not facts.

## 2. Live app

- **URL:** https://caregap-app-7474647301321645.aws.databricksapps.com
- **Access:** it's a Databricks App behind workspace login (no anonymous public access is possible). Teammates need a login in **this** workspace (`dbc-54942fa9-145a`); the app is already shared with the workspace `users` group. See §7 for the access reality on Free Edition.
- **Run locally** (fastest for dev, no cloud needed): `.venv/bin/streamlit run app/app.py` — defaults to reading the local cleaned CSVs.

## 3. What the app does (7 views)

| View | What it answers |
|---|---|
| **Map** | Where are the medical deserts? Trust-weighted H3 risk map of India, click a facility for cited source evidence. |
| **Top care gaps** | Which districts to act on first? Ranked leaderboard with a Deploy / Verify / Fix / Refer / Monitor action per district. |
| **Interventions** | What should we deploy? "Next Best Health Access Intervention" (mobile clinic, CHW outreach, pharmacy screening, insurance enrollment, etc.) ranked by an **expected-value** score with confidence + cited triggers. |
| **Scenario lab** | What if? Best / most-likely / worst-case supply bands + what-if levers (add clinics, +capacity, telehealth adoption). |
| **Uncertainty console** | How messy is the data? Semantic missingness, Wilson/Bayesian confidence intervals, geo-validation, active-learning triage queues. |
| **Trust & conformal** | Can we trust this record? Per-facility `P(valid \| evidence)` Bayesian posterior + conformal prediction sets + a transparent additive trust-score breakdown. |
| **Decisions & feedback** | Human-in-the-loop: notes/overrides/shortlists, source-conflict resolution, and a governed "propose policy update → human approves" loop. |

**Honesty rule we enforced everywhere:** the dataset has **no broadband / elderly-share / travel-time** columns, so we never fabricate them — we substitute the nearest real NFHS proxy and label it, and telehealth is always pinned to low confidence ("broadband not in dataset").

## 4. The data & stats engine

### 4.1 How we cleaned the data

Three raw inputs were fused into two clean tables:

| Raw input | Rows × cols | Source | Role |
|---|---|---|---|
| FDR facilities | 10,088 × 48 | Databricks Foundational Data Refresh (`virtue_foundation_dataset.facilities`) | The facilities themselves |
| India Post PIN directory | 165,627 × 11 | data.gov.in | Map PIN → district/state |
| NFHS-5 district indicators | 706 × 109 | DHS Program | Real health-need signal per district |

The cleaning pipeline (in `scripts/`) does, in order:

1. **Dedup** facilities on `unique_id` (10,088 → **10,077**; 11 dupes tracked, not silently dropped).
2. **PIN extraction** from messy address text via regex `(?<!\d)([1-9]\d{5})(?!\d)` (9,032 matched, 150 `no_valid_pincode`).
3. **PIN→district bridge** by aggregating India Post to **19,586** unique PINs with modal district/state + ambiguity flags.
4. **Name normalization** — state/district alias maps (e.g. `Maharastra→maharashtra`, `Gurugram→gurgaon`, `Prayagraj→allahabad`), lowercasing, trimming the trailing-whitespace trap in 704/706 NFHS names.
5. **Geo-validation** — India bbox check (6–38°N, 68–98°E), haversine distance to PIN centroid, `geo_quality` classes; **6 facilities** flagged with coordinates literally outside India.
6. **Numeric parsing + outlier capture** — `capacity_num` (≤100k cap; 200k-bed claims flagged), `number_doctors_num` (≤50k), `year_established_num` (1800–2026), recency dates. Each field gets an explicit **semantic-missing** label so `"null"` strings / `[]` / "No details provided" are *not* counted as data.
7. **Hierarchical imputation** for missing capacity/doctors using facility-type × operator-type × state cohorts (with fallbacks), emitting **p10–p90 intervals** + a confidence label — never a bare point estimate.
8. **Tiered join** facility→PIN→district→NFHS, each row tagged with a `join_confidence` (0.95 exact → 0.55 city-fallback → 0.0 unjoined) and a written `join_uncertainty_reason`.
9. **District aggregation** → **494** districts with care-gap / desert-priority / trust-gap scores, planning category, and Wilson CIs on every rate.

**Outputs (`output/data/`):** `facility_health_cleaned.csv` (10,077 × 102) and `district_health_facility_cleaned.csv` (494 × 98), plus the PIN bridge, data dictionaries, a `cleaned_dataset_audit.json`, and active-learning review queues. Audit result: `upload_ready = true` (0 errors, 1 dedup warning).

### 4.2 The statistics & "ML" — what's real

This is **decision-support statistics, not a trained classifier** — and we're explicit about that because **there are zero verified (gold) labels**.

- **Bayesian record-validity posterior** `P(valid | evidence)` (`app/lib/trust.py`): a transparent log-odds update — `logit(post) = logit(prior) + Σ wₖ·indicatorₖ` — over a documented evidence model (e.g. `geo_plausible +0.85`, `has_source_urls +0.55`, `contradicted_or_geo_invalid −1.40`). Thresholds drive auto-accept (≥0.85) / review / quarantine actions.
- **Wilson + Jeffreys-Beta(0.5,0.5) confidence intervals** on all district/facility rates (so every percentage shows its uncertainty band, e.g. `46.6% [42.2–51.0%]`).
- **Split-conformal prediction sets** wrapping the posterior — calibrated on the *proxy* `trustworthy_supply_signal` label (explicitly "provisional"): `α=0.1`, `q̂=0.0802`, **empirical coverage 0.9183** on 2,008 calibration / 1,996 eval rows.
- **Hierarchical p10–p90 shrinkage** for supply estimates (see cleaning step 7).
- **Expected-value intervention ranking** (not a model — a transparent EV score with cited triggers).

### 4.3 CatBoost supply imputers (trained supervised models)

We **do** train real CatBoost models — but only where genuine observed targets exist: **imputing missing capacity and doctor counts**. ~75% of capacity and ~64% of doctor values are missing; the remaining observed values (2,498 / 3,614 real, non-outlier rows) are the training labels. This is non-circular (real measured targets, not rule-derived), unlike the validity task where no gold labels exist.

- **Model:** `CatBoostRegressor` on `log1p(target)`, native categorical handling, early stopping. Code: `scripts/catboost/{features.py, train_capacity.py, train_doctors.py}`.
- **Honest evaluation:** 5-fold out-of-fold cross-validation on observed rows, benchmarked head-to-head against the previous **cohort-median** imputation on the *same* folds (no leakage).

| Imputer | CatBoost MAE | Cohort-median MAE | MAE improvement | R² |
|---|---|---|---|---|
| **Capacity (beds)** | **125.4** | 145.1 | **−13.6%** | **0.22** (vs 0.04) |
| Doctor count | 23.9 | 24.3 | −1.5% | ≈0.00 |

- **Read it straight:** CatBoost is a **clear win for capacity** (lower MAE/RMSE, 5× better R², top drivers `capability_len`, `operatorTypeId`, `procedure_len`, `year_established`). For **doctor count** the gain is **marginal** — the target is brutally skewed (median = 2 doctors) so there's little learnable signal; we report it as-is rather than dress it up.
- **Tracked in MLflow** (`caregap_scoring_policies`, runs `catboost_capacity_imputer_v1` / `catboost_doctors_imputer_v1`) with full metrics + feature importances; models saved to `output/catboost/*.cbm` and imputations to `output/catboost/*_imputations.csv`.
- **Where it runs:** trained **locally** (data is tiny — seconds, no cluster needed); a bundle notebook (`databricks/notebooks/07_train_catboost_imputers.py`) registers them to **Unity Catalog** (`workspace.caregap_models.caregap_capacity_imputer`, `caregap_doctor_imputer`) for governance + serving.

### 4.4 Honest scope — what we still don't do

- **No supervised *trust/validity* classifier.** That task has **0 gold labels** — only the rule-derived `trustworthy_supply_signal` — so modeling it would just re-learn the rules. We deliberately keep trust as the transparent Bayesian scorer (§4.2) instead of an opaque model trained on its own outputs.
- Everything user-facing is framed as **proxy decision-support, not gold-label accuracy.**

Detailed writeups: `cleaned_dataset_actions.md`, `tricky_fields.md`, `stats_iteration_1.md`, `Bayesian_stats_product_strategy.md`, `docs/STATISTICAL_DECISION_FRAMEWORK.md`.

## 5. Databricks architecture (the platform story)

```
FDR raw (virtue_foundation_dataset)  ─┐
prior cleaned tables + UC volume      ─┤→ bronze → silver → features → MLflow → gold → views → App
```

- **Unity Catalog medallion** in catalog `workspace`: `caregap_bronze` (8) → `caregap_silver` (4) → `caregap_features` (3 Feature-Engineering tables) → `caregap_gold` (5 tables + 5 views) → `caregap_models`.
- **Gold decision tables:** `medical_desert_scores` (494), `intervention_recommendations` (3,458), `provider_confidence` (10,077), `scenario_simulations`, `review_queue` (9,807).
- **MLflow:** experiment `caregap_scoring_policies` — **6 runs that track *scoring policies*, not trained models** (notebook `04_track_scoring_policies.py`). Runs + headline metrics:
  - `provider_confidence_policy` → human_review_rate **0.6824**, low_confidence_rate **0.7753**, passed_proxy_rate **0.1984**.
  - `medical_desert_risk_policy` → composite rule-based index over 6 features.
  - `intervention_recommender_policy` → 491 districts scored, telehealth_not_recommended_rate **0.8381**, EV median **0.0439** (range −0.53…+1.05).
  - `conformal_uncertainty_wrapper` → coverage **0.9183** (α=0.1, q̂=0.0802).
  - **`v1.2_baseline` → `v1.3_telehealth_penalty`** *governed hillclimb*: rule-agreement **75.7% → 98.8%** (+23.1pp), telehealth-ranked-#1 districts **120 → 6**. Tagged `deployment_status = proposal_pending_human_approval` (never auto-deployed).
  - **Registered model** `workspace.caregap_models.caregap_scoring_policy` is a `mlflow.pyfunc` wrapper over the transparent rule-based scorer (13 input features) — **not a fitted classifier**; output is annotated `validation_posture = proxy_decision_support_not_gold_validated`.
- **Governed feedback** tables for the "self-improving but human-approved" loop.
- **Everything is Infrastructure-as-Code** via a Databricks Asset Bundle (`databricks.yml`): one command rebuilds it all.

## 6. How to rebuild / operate

```bash
export DATABRICKS_CONFIG_PROFILE=7474647301321645   # the authed CLI profile
databricks bundle deploy                 # push notebooks, job, app, experiment
databricks bundle run caregap_medallion  # rebuild bronze→…→gold + MLflow (serverless)
databricks bundle run caregap_app        # (re)deploy + start the app
databricks apps logs caregap-app         # debug the running app
```

Free Edition = **serverless only**, single catalog `workspace`. The medallion job's weekly schedule ships **paused** (trigger manually).

## 7. Sharing reality (important)

- Databricks Apps **cannot be made anonymously public** — they always require a Databricks login.
- The app is granted to the workspace **`users`** group, so anyone who is a member of *this* workspace can open the URL.
- **Free Edition usually does not let you add other users to your workspace.** So practical options for teammates:
  1. **Demo via screen-share** from this account, or
  2. **Run locally** — clone the repo and `streamlit run app/app.py` (uses the bundled cleaned CSVs, no cloud needed), or
  3. If we move to a paid/Team workspace, invite teammates by email — they'll get access automatically via the `users`-group grant already set.

## 8. Repo map

- `app/` — Streamlit app (`app.py` + `lib/{data,ui,interventions,simulator,trust,decisions}.py`)
- `databricks/notebooks/01..06` — medallion + MLflow notebooks · `databricks.yml` + `resources/` — the bundle
- `scripts/` — local data-prep + stats builders · `output/data/` — cleaned CSVs + artifacts
- Briefs: `stats_iteration_1.md`, `visual_enhancements_1.md`, `databricks_tool_integration_1.md`, `teammate_brief.md` (this file)
- `docs/` — deeper specs (data dictionary, statistical framework, UC governance, app wiring, UX audit/QA)
