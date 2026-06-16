## Inspiration

Healthcare access data is often messiest in the places where planning decisions matter most. A facility list can say a hospital exists, but a planner still needs to know whether the claims are source-backed, whether the district-level gap is real, and whether the next step is deployment, referral, or verification.

We built **Databricks Copilot: Medical Desert Map** for that workflow: a confidence-aware planning assistant for non-technical healthcare planners, NGO coordinators, and analysts working across India.

## What it does

The app helps users answer three operational questions:

- **Where should we act first?** The Map and Top Care Gaps views rank districts by health need, provider scarcity, and uncertainty.
- **Can we trust the supply evidence?** Provider cards show source-backed claims, automated check status, and trust tiers instead of treating every facility row as ground truth.
- **What should happen next?** The product suggests actions such as deploy/build, call or verify, fix records, route referrals, or monitor.

Key workflows include:

- a district-level medical desert map,
- a Top Care Gaps shortlist for doctor deployment planning,
- provider-claim cards with source links and service chips,
- filters for districts with provider claims versus no mapped claims,
- compact uncertainty explanations for health need, gap confidence, and provider trust,
- saved plan actions and notes, and
- Copilot-style explanations for methodology, caveats, and next steps.

## How we built it

We built the project as a **Databricks App** with a Streamlit front end and a Databricks-style lakehouse data flow.

The data pipeline organizes the messy facility records into:

- **Bronze:** raw facility and geography inputs.
- **Silver:** normalized provider, address, PIN code, district, and service-claim features.
- **Feature tables:** facility evidence features, geo-quality indicators, supply estimates, and district health-need inputs.
- **Gold:** app-facing outputs such as care-gap rankings, provider trust, intervention recommendations, conformal sets, and review queues.

The decision layer combines several statistical and ML components:

- **CatBoost supply imputers:** Capacity and doctor-count gaps are imputed with CatBoost regressors trained on observed rows. The models use native categorical handling, log1p target transforms, 5-fold out-of-fold validation, cohort-median baselines, clipped predictions, and MLflow logging. Capacity imputation improved MAE by about 13.6% versus the cohort-median baseline; doctor-count imputation was more conservative, improving MAE by about 1.5%.
- **Bayesian-style provider validity posterior:** Facility evidence is scored from source URLs, geography consistency, service-claim evidence, missingness, contradiction flags, contact evidence, recency, and semantic quality.
- **Calibrated provider trust:** District cards now show a simple High/Medium/Low trust tier. The score blends row-level Bayesian validity posterior with an empirical-Bayes-smoothed hard-check pass rate, so a thin sample such as 0/1 checks does not collapse into a misleading visible 0%.
- **Wilson confidence intervals:** District and facility rates use Wilson 95% intervals for finite-row uncertainty, including check-pass rates, review-needed rates, critical supply-gap rates, and planning category volumes. These intervals are more stable than naive normal intervals for small or extreme proportions.
- **Split-conformal coverage:** Facility trust sets are wrapped with split-conformal prediction sets over the validity posterior. The current artifact targets alpha = 0.10, uses a nonconformity score `s = 1 - validity_posterior`, and reaches about 91.8% empirical coverage on the automated proxy-valid class. Because the calibration target is `trustworthy_supply_signal`, the app labels this as provisional proxy coverage, not human-verified accuracy.
- **Active review queues:** The system ranks facilities and districts where one more source check, geocode check, or claim review is most likely to change the decision.

Operationally, we used:

- **Unity Catalog / Databricks SQL** for governed tables and queryable outputs,
- **MLflow** for model and scoring-policy tracking,
- **Databricks Apps** for the live application,
- **Streamlit** for the planner workflow, and
- **Cloud Run** as an additional public demo deployment path.

## Challenges we ran into

The main challenge was not rendering a map; it was avoiding false certainty.

Specific issues included:

- facility claims were noisy, duplicated, incomplete, or contradicted by geography,
- many rows lacked capacity or doctor counts,
- no large human-verified gold label set existed for facility truth,
- Indian address and PIN-code joins needed careful normalization,
- geocoding had to be treated as source agreement rather than ground truth, and
- the UI had to stay understandable for a planner rather than exposing every intermediate data artifact.

That pushed us toward a product posture where the app says what it knows, what it does not know, and what a planner should verify before staffing.

## Accomplishments that we're proud of

- We turned messy facility records into a live, multi-view planning app rather than a static dashboard.
- We separated **health need**, **gap confidence**, and **provider trust** so users can distinguish real care gaps from weak local evidence.
- We added provider-claim evidence cards with service chips, source links, and check status.
- We implemented CatBoost supply imputers, Wilson confidence intervals, Bayesian-style trust scoring, and split-conformal uncertainty sets.
- We kept the product honest: proxy trust is never presented as measured medical truth.
- We deployed the app publicly while preserving secret hygiene and keeping API keys out of the repo.

## What we learned

The hardest part of healthcare-access planning is not producing a score. It is making the score usable: explaining why it exists, how uncertain it is, and what action should follow.

We learned that:

- uncertainty should be visible in the product, not hidden in notebooks,
- a planner needs a small number of clear decisions, not every raw metric,
- confidence intervals and conformal sets are useful only if the UI explains their limits,
- geocoding and external sources are best treated as agreement signals, and
- Databricks Apps can support a strong end-to-end workflow when paired with governed tables, MLflow, and careful fallback data paths.

## What's next

The next step is to move from proxy decision support toward stronger validation:

- build a larger gold/silver verified label set for provider truth,
- recalibrate conformal coverage against human-reviewed labels,
- add stronger facility-photo/place enrichment with safe attribution,
- deepen the human review loop so corrections improve future scoring,
- track real intervention outcomes where available, and
- continue simplifying the UI for fast three-minute demo comprehension.

The long-term goal is a trustworthy planning assistant that helps public-health teams decide **where to intervene first, what action is most plausible, and where the data still needs human judgment**.
