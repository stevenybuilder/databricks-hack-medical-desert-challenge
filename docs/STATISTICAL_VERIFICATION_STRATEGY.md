# Statistical Uncertainty Strategy

_Last updated: 2026-06-15_

This spec adapts the useful statistical and ML ideas from
`/Users/stevenyang/Documents/intuit-hackathon` to the Virtue Foundation facility
trust problem **without assuming human verification labels are available**.

The constraint changes the modeling posture:

- We can quantify uncertainty.
- We can rank records for source enrichment and stress testing.
- We can build weak/proxy trust scores.
- We cannot claim measured model accuracy against real facility truth.

So the product should not promise "self-improving from doctor labels" for the
hackathon demo. It should instead show a defensible **active uncertainty queue**:
the rows and districts where additional evidence, source corroboration, or cautious
decision handling would reduce uncertainty the most.

## Intuit concepts to reuse

| Intuit concept | Facility-trust translation without human labels | Concrete implementation |
|---|---|---|
| Informative missingness | Missing `capacity`, `numberDoctors`, equipment, or recency is itself a source-quality signal. | Preserve missingness/status fields as model inputs and UI evidence. Never hide missingness behind a single imputed value. |
| Confidence-band mindset | We cannot calibrate against truth, but we can show how much evidence uncertainty surrounds proxy scores. | Label scores as proxy scores; show intervals and abstain/route-to-review when uncertainty is high. |
| Confidence intervals | District rates are based on finite observed facility rows. | Use Wilson intervals for rates such as review need, trustworthy supply, capacity-observed, doctor-observed, equipment, and recency. |
| Empirical prediction intervals | Missing numeric fields need ranges, not point estimates. | Use cohort medians plus empirical p10-p90 prediction intervals for capacity and doctor counts. |
| Active learning / value of information | No oracle is available, so active learning becomes active data-quality triage. | Rank facility/district rows by uncertainty, clinical impact, contradiction risk, decision leverage, and sparse-segment coverage. |
| External source agreement | Google/Mappls/registry matches can reduce uncertainty without becoming gold labels. | Store provider metadata, compare admin geography and names, then widen/narrow proxy bands with reason codes. |
| Hierarchical shrinkage | Many segments are small. | Prefer state/type/operator cohort estimates, then broader cohorts, then global fallbacks; never trust tiny raw cell means. |
| Robust validation | Random pretty metrics are not useful without ground truth. | Validate internally with invariants: interval ordering, score bounds, monotone risk flags, no Gaussian assumptions for heavy-tailed fields. |
| Risk-adjusted decisions | A high-need district with uncertain supply should not be treated the same as a confirmed desert. | Use build/verify/refer/monitor categories and show uncertainty bands before operational decisions. |
| Model-risk reporting | Judges should see what the model cannot know. | Include "proxy, not verified truth" language, missingness summaries, active queue output, and confidence intervals. |

## Statistical missing-data approach

1. **Classify missingness**
   - MCAR is unlikely.
   - MAR is plausible when missingness depends on facility type, operator type, state,
     source type, or recency.
   - MNAR / informative missingness is likely for capacity, doctors, and equipment
     because stronger or more digitally mature facilities may publish more details.

2. **Preserve missingness as signal**
   - Use `capacity_status`, `doctor_count_status`, `year_established_status`,
     `recency_status`, `equipment_status`, and `semantic_missing_critical_count`.
   - Include missingness in trust/readiness scores.

3. **Estimate, but do not launder estimates into facts**
   - Current numeric treatment uses cohort medians with empirical intervals.
   - Show `capacity_display_value` / `doctor_count_display_value` with
     `*_estimate_interval_low` and `*_estimate_interval_high`.
   - UI copy must say "estimated" when `*_is_estimated = true`.

4. **Avoid Gaussian assumptions**
   - Operational fields are heavy-tailed and bounded fields are often floor/ceiling
     heavy.
   - Use medians, quantiles, ranks, robust caps, log-scale views, Wilson intervals,
     and sensitivity bands.

5. **Run sensitivity analysis**
   - Recompute district recommendations under pessimistic and optimistic supply
     assumptions.
   - Districts that remain high priority under both are more robust.

## Active uncertainty queue

The generated queue is active-learning inspired, but it does not assume a human
oracle. It answers:

```text
Where would one more piece of evidence most reduce decision uncertainty?
```

The pipeline now writes:

- `output/data/active_learning_facility_queue.csv`
- `output/data/active_learning_district_queue.csv`

### Facility queue score

The facility queue combines:

```text
clinical impact
+ semantic/data uncertainty
+ contradiction risk
+ decision leverage
+ sparse-segment coverage
```

Signals include high district health need, estimated/missing capacity and doctors,
wide capacity/doctor prediction intervals, critical supply gaps, low join
confidence, non-plausible geography, ambiguous pincode mapping, missing source URLs,
missing contact evidence, and rare facility/operator/state segments.

The top actions are:

| Action | Meaning |
|---|---|
| `contradiction_audit` | Geography, impossible values, or other contradictions make the row risky. |
| `semantic_missingness_enrichment` | Critical operational fields are missing or estimated. |
| `join_bridge_enrichment` | Pincode/district/state mapping uncertainty drives the risk. |
| `high_impact_uncertainty_reduction` | High health need plus high uncertainty. |
| `sparse_segment_coverage` | The row represents a thin segment where assumptions are weak. |
| `uncertainty_monitor` | Keep visible, but lower immediate triage priority. |

### District queue score

The district queue combines:

```text
care gap score
+ trust gap score
+ health need score
+ confidence-interval width
+ district uncertainty level
+ small sample uncertainty
```

It is designed to find districts where the recommendation is likely sensitive to
uncertain facility evidence.

## Confidence interval policy

Use different intervals for different evidence types:

| Evidence type | Interval method | Interpretation |
|---|---|---|
| District rates | Wilson 95% confidence interval | Finite-sample uncertainty over observed facility rows. |
| Missing numeric facility values | Empirical p10-p90 prediction interval | Plausible planning range from similar observed facilities. |
| Proxy trust score | Heuristic uncertainty band | Not statistically calibrated; used for triage only. |
| Geocoding/provider result | Heuristic source-agreement band | Uses provider metadata plus India Post/admin agreement; not a verified facility label. |
| Health indicators | Use NFHS values as district context | Do not turn district survey estimates into facility-level facts. |

Important: without ground-truth labels, proxy trust intervals are **not** accuracy
intervals. They are uncertainty bands over evidence quality.

## External geocoding and source-agreement layer

The parallel geocoding workflow should be treated as an uncertainty reducer, not a
truth oracle:

```text
raw facility address -> Databricks AI address janitor -> Google/Mappls geocoder
-> India Post/NFHS admin cross-check -> proxy confidence update
```

The generated geo batch now writes:

- `output/data/geo_validation_candidates.csv`
- `output/data/geocoder_uncertainty_priors.csv`

For each candidate, keep these explainability fields visible:

- `external_validation_action`;
- `external_validation_priority_score`;
- `pre_geocode_uncertainty_band_low_km`;
- `pre_geocode_uncertainty_band_high_km`;
- `external_evidence_sources_to_check`;
- `external_uncertainty_reason_codes`;
- `geocoder_acceptance_rule`.

The uncertainty logic is:

- `ROOFTOP` or `RANGE_INTERPOLATED` plus matching country/state/PIN/district can
  narrow the geo band.
- `GEOMETRIC_CENTER` can support district or H3-level analysis but should usually
  keep facility-routing uncertainty visible.
- `APPROXIMATE`, `ZERO_RESULTS`, `partial_match=true`, or provider/admin conflicts
  keep the row in the active uncertainty queue.
- ABDM/HFR, PM-JAY, OSM/Overture, and facility websites are source-agreement
  evidence. They do not become gold labels unless the source is authoritative for
  the exact claim being made.

This gives the judges a statistics answer to garbage-in/garbage-out: uncertainty
shrinks only when independent evidence agrees, and it widens when sources conflict.

## Weak supervision posture

Programmatic labels can be useful as weak signals:

- `trustworthy_supply_signal`
- `needs_human_review`
- `critical_supply_gap_flag`
- `contradicted_or_geo_invalid_signal`
- `join_confidence`
- `semantic_data_quality_score`
- `supply_data_confidence_score`

But they are not ground truth. A model trained only on these labels learns the
current rules. For the hackathon, use them for ranking, explanation, and
consistency checks rather than claiming supervised accuracy.

## Supervised learning after golden labels

The next build phase can use supervised learning if the project first creates a
source-corroborated `golden_facility_training_set`.

Label tiers:

| Tier | Use |
|---|---|
| `gold` | Train and evaluate supervised models. |
| `silver` | Train with lower sample weight or use as secondary validation. |
| `bronze` | Active learning only; do not use for final accuracy claims. |
| `conflict` | Exclude from training; route to review. |

Recommended supervised tasks:

- facility type classification;
- service-signal multi-label prediction;
- existence/trust posture with abstention;
- capacity and doctor-count band prediction;
- location/admin confidence classification.

Metrics are valid only on held-out Tier A/B labels. Report coverage at confidence
thresholds and abstention rate alongside accuracy/F1/calibration. For map-selected
new locations, the prediction contract is:

```text
prediction + confidence + evidence tier + source links + abstain/review reason
```

Commercial geocoders can reduce runtime uncertainty, but they should not become
durable supervised labels without explicit license review.

## What to show in the app

- Active uncertainty queue tab: top districts/facilities to enrich or stress-test.
- Wilson interval bands on district rates.
- Estimated capacity/doctors with interval low/high.
- "Proxy, not verified truth" labels on trust scores.
- Sensitivity badge: robust / fragile recommendation.
- Data quality reasons: missingness, wide interval, bad geo, low join confidence,
  ambiguous pincode, sparse segment.

## Answer to the Slack question

For "Do you have even a handful of manually verified facilities?":

- No, and we are not relying on that for the hackathon.
- The statistical response is to avoid pretending proxy labels are truth.
- We use confidence intervals, prediction intervals, informative missingness,
  weak supervision, and active uncertainty ranking to decide where the evidence is
  strong enough and where the recommendation is fragile.

That is the defensible no-human-label loop:

```text
semantic/proxy trust score -> active uncertainty queue -> source enrichment or
sensitivity analysis -> updated confidence bands -> safer recommendations
```
