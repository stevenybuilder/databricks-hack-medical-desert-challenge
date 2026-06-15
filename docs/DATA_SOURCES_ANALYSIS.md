# Data Sources & Analysis — DAIS 2026 Virtue Foundation Hackathon

_Last updated: 2026-06-15_

This is the analytical companion to `DATASET_REFERENCE.md` (connection + columns).
All numbers below are from the computed artifacts in `output/data/`
(`analysis_summary.json`, `cleaned_dataset_audit.json`) and the live schema discovery.

---

## 1. Provenance chain (how the data was made)

```
Web sources (Bright Data crawl)  →  GenAI extraction (GPT)  →  Entity resolution (dedupe & match)  →  FDR dataset
```

Implication: **Table 1 is claimed/derived data, not ground truth.** Every uncertainty
in crawl coverage, LLM extraction, and the merge step propagates into the facility
records. Tables 2 (India Post) and 3 (NFHS-5) are authoritative and can be treated as
ground truth for geography and need respectively.

---

## 2. Source-by-source analysis

### Table 1 — `facilities` (10,088 raw rows × 48 cols → 10,077 cleaned × 144)

- **11 duplicate `unique_id` rows** in raw; cleaned keeps one row + source occurrence count.
- **Semantic field coverage** (the "treat noisy fields as claims" reality):

  | Field | Semantically valid | Missing / invalid |
  |---|---:|---:|
  | `capacity` | **24.9%** | 75.1% |
  | `numberDoctors` | **36.0%** | 64.0% |
  | `yearEstablished` | **47.3%** | 52.7% |
  | `recency_of_page_update` | **35.0%** | 65.0% |
  | `equipment` | 70.5% | 29.5% |

  → Raw fields often looked complete because `"null"`, empty arrays, and no-evidence
  strings were present. After semantic cleaning, **structured operational fields
  (capacity, doctors, year, recency) are sparse** and cannot anchor rankings alone.

- **Provenance/trust signals present:** `source_types` (overture/dynamic/constant/kie),
  `source_ids`, `source_urls`, `cluster_id` (merge cluster), plus legitimacy signals
  (official website/phone, social presence, logo, affiliated staff, recency, engagement).

### Table 2 — `india_post_pincode_directory` (165,627 × 11)

- Role: **geocoding + administrative bridge** (PIN → district/state, with lat/long).
- `pincode_bridge.csv` distilled this to **19,586** PIN→district mapping rows used by the join.
- Lat/long are strings with literal `"NA"`; cast/filter before use.

### Table 3 — `nfhs_5_district_health_indicators` (706 × 109)

- **District-grain need/outcome data** — the strongest available ground truth for *need*.
- 109 columns spanning household conditions, insurance, education, fertility/family
  planning, maternal & delivery care, immunization, child illness/nutrition, anaemia,
  NCD markers (BP, blood sugar), cancer screening, tobacco, alcohol.
- Caveat: **older than the facility data**, and a survey sample — use as context, never
  as a facility-level fact.

---

## 3. Cross-source join analysis (10,077 facilities)

| Join strategy | Rows | Share |
|---|---|---|
| `pincode_district_state_exact` | 9,032 | 89.6% |
| `pincode_only_no_health_match` | 397 | 3.9% |
| `facility_city_state_fallback` | 301 | 3.0% |
| `no_valid_pincode` | 150 | 1.5% |
| `pincode_district_state_fuzzy` | 131 | 1.3% |
| `unjoined` | 66 | 0.7% |

- **Health-join rate 95% CI: [93.4%, 94.4%]** — strong coverage.
- **Valid PIN rate 95% CI: [96.5%, 97.1%]**.
- 60 unmatched pincode-district groups retained for audit (district rename / split traps).

---

## 4. Trust & data-readiness analysis

- **Needs uncertainty review: 7,812 rows = 77.5%** (95% CI [76.7%, 78.3%]). After
  semantic missingness handling, most records are not safe to use as-is. This is
  the problem the app exists to surface and improve.
- **Trustworthy supply: 4,004 rows (39.7%)** — what survives the stricter trust filter.
- **Geo quality:**

  | Geo class | Rows | Share |
  |---|---|---|
  | plausible | 7,861 | 78.0% |
  | moderate distance from PIN centroid | 1,164 | 11.6% |
  | far from PIN centroid | 928 | 9.2% |
  | missing coordinates | 118 | 1.2% |
  | **outside India bbox** | **6** | 0.06% |

  → The 6 "outside India bbox" rows are the **ocean-hospital class** (the Sanjivani
  example in the North Atlantic). Small in count, huge as a demo proof of why
  verification matters. The 928 "far from centroid" rows are the larger silent risk.

- **District uncertainty:** lower 4 · medium 275 · higher 215. ~44% of joined districts
  carry *higher* uncertainty — the app must show this, not hide it.

---

## 5. Distribution analysis (Michael Burk's explicit ask)

Normality tests reject Gaussian for all operational fields; they are heavy-tailed with
implausible maxima — i.e. **claims contain data errors that distribution analysis flags.**

| Field | n | median | mean | p95 | max | skew | Gaussian? |
|---|---|---|---|---|---|---|---|
| `capacity` (beds) | 2,511 | 100 | 191 | 798 | 4,000 | 4.1 | no (closer to log-normal) |
| `numberDoctors` | 3,629 | 2 | 31.7 | 94 | **15,000** | 36 | no — extreme outliers |
| `followers` | 8,873 | 245 | 8,066 | 5,390 | **15,000,000** | 54 | no |
| `post_count` | 3,774 | 0 | 44 | 6 | 59,000 | 42 | no |
| `health_need_score` | 9,464 | 0.49 | 0.48 | 0.62 | 0.77 | -0.21 | ~symmetric |
| `medical_desert_priority_score` | 9,464 | 0.36 | 0.36 | 0.53 | 0.78 | 0.71 | mild right skew |

Takeaways:
- **`numberDoctors` max = 15,000 and `capacity` max = 4,000** are almost certainly
  extraction errors → outlier capping / winsorization required before any aggregation.
- Operational fields need **log-scale** handling and robust (median/percentile) stats,
  not means.
- The derived **need/desert scores are well-behaved** (bounded, near-symmetric) → safe to
  rank and color a map on.

---

## 6. Derived scores & recommendation taxonomy (already computed)

- `health_need_score` — percentile composite over adverse NFHS indicators.
- `care_gap_score`, `district_medical_desert_priority_score`, `trust_gap_score`,
  `best_care_signal_score` — proxy gap measures (high need + low *trustworthy* supply).
- `planning_category` (the build-vs-verify recommendation), distribution over 494 districts:

  | Category | # | Action |
  |---|---|---|
  | `real_desert_candidate` | 8 | genuine unmet need → deploy/help |
  | `phantom_desert_or_verification_gap` | 15 | unverified → verify first |
  | `supply_record_quality_problem` | 93 | records broken → fix |
  | `referral_or_capacity_candidate` | 99 | capacity exists → refer |
  | `mixed_or_monitor` | 279 | monitor |

- **Top care-gap districts** (all `real_desert_candidate`, mostly 1 observed facility,
  0 trustworthy): Kendujhar (Odisha), Siwan (Bihar), Dumka & Simdega (Jharkhand),
  Mandla (MP), Koraput & Nabarangapur (Odisha), Mahesana (Gujarat).

---

## 7. Standout condition stats (patient-condition focus / demo hooks)

- Preventive cancer screening near-zero everywhere: cervical 1.6% mean, breast 0.7%,
  oral 0.7% — vs **men's tobacco use 40.6%**.
- Women 15–49 anaemia 55.9% mean (up to 70%+).
- Child stunting 33.5% mean (up to 60.6%).
- Institutional births down to 21.4% (Mon, Nagaland).

---

## 8. Known limitations (from `cleaned_dataset_audit.json`)

1. NFHS indicators are district-level and **older** than the web-extracted facility data.
2. Observed FDR facility counts are **not a verified supply census**.
3. District matching depends on PIN + name harmonization; unmatched groups retained.
4. Claimed services are detected from extracted text and **must be cited/verified**.
5. **No travel-time or population denominator** → care gaps are proxy scores, not
   definitive access measures.

6. **No human-verified facility label set yet** → current trust scores are
   evidence/proxy confidence, not measured accuracy. For the hackathon, use
   confidence intervals, prediction intervals, active uncertainty ranking, and
   sensitivity analysis rather than claiming calibrated accuracy. The next build
   phase should create a source-corroborated golden facility dataset before any
   supervised accuracy claims.

7. **External datasets reduce uncertainty only through agreement** → Google/Mappls
   geocoder metadata, India Post admin geography, HFR/ABDM, PM-JAY, OSM/Overture,
   and source URLs should be compared as independent evidence. A single API hit is
   not a gold label.

---

## 9. Statistical and ML strategy from the Intuit playbook

The relevant ideas from `/Users/stevenyang/Documents/intuit-hackathon` are directly
applicable here:

| Intuit concept | Why it matters here without human labels | Implementation |
|---|---|---|
| Informative missingness | Missing facility capacity/doctors/equipment is not random and may reflect source quality or facility maturity. | Preserve semantic missingness flags as model features. Do not impute without flags. |
| Selection bias | Weak labels are produced by our own rules, so treating them as truth creates circularity. | Use weak labels only for triage/explanation. Do not report supervised accuracy metrics without ground truth. |
| Confidence intervals | District rates come from finite observed facility rows. | Show Wilson intervals for review need, trustworthy supply, capacity-observed, doctor-observed, equipment, and recency. |
| Empirical prediction intervals | Missing numeric fields need ranges, especially with sparse cohorts. | Show p10-p90 cohort intervals for estimated capacity and doctor counts. |
| Hierarchical shrinkage | Many districts and facility/operator segments are small. | Estimate from narrow cohorts when supported, then broader cohorts, then global fallback. |
| Active learning | With no oracle, active learning becomes active uncertainty triage. | Queue score = clinical impact + uncertainty + contradiction risk + decision leverage + sparse-segment learning value. |
| Source-agreement scoring | External sources can narrow bands when they agree and widen bands when they conflict. | Geo candidates carry external validation actions, geocoder priors, reason codes, and pre-geocode uncertainty bands. |
| Model-risk report card | Judges and users need to see assumptions, not just outputs. | Show proxy-label coverage, missingness, interval widths, active queue yield, and known blind spots. |

Practical interpretation for missing data:

- Use robust cohort imputation for planning values, not truth claims.
- Keep intervals and confidence fields visible.
- Run sensitivity analysis: do district recommendations survive pessimistic vs
  optimistic assumptions about missing supply?
- Treat unverified as unknown, not false.
- Do not call proxy trust scores calibrated accuracy without human or authoritative labels.

---

## 10. Implications for the build (honor these in the app)

| Finding | What the app must do |
|---|---|
| 77.5% of facilities need review | Make the Uncertainty Queue a core workflow; never present claims as fact. |
| `numberDoctors`/`capacity` have impossible maxima (15k, 4k) | Cap/winsorize before aggregating; show median + range, not mean; flag outliers. |
| Heavy-tailed operational fields | Log-scale visuals; robust percentile stats. |
| 6 outside-India + 928 far-from-centroid geos | Geo-quality badge per facility; the ocean hospital is the opening demo. |
| Parallel Google Maps / Mappls geocoding work | Treat provider status, location type, partial-match, place ID, and admin match as explainable uncertainty features. |
| Confidence intervals exist for every rate | Show CIs / uncertainty bands in the UI (it's a scored criterion). |
| `planning_category` already computed | Drive build/verify/refer recommendation chips directly from it. |
| capacity/doctors/year are sparse (25–48%) | Don't rank on them alone; lean on need + trustworthy supply + service signals. |
| NFHS is district-grain, older, sample | Label it "district context"; keep `district_uncertainty_level` visible. |
| No population/travel denominator | Call gap scores "proxies" honestly; (stretch) add WorldPop + distance approx. |
| Claims must be cited | Wire `sample_source_urls` / `sample_claim_evidence` into every claim shown. |
| Derived scores are well-behaved | Safe to color the map and rank the leaderboard on `care_gap_score`. |
| No human-verified labels | Use active uncertainty queues and sensitivity checks; do not claim measured accuracy. |
| Golden supervised phase planned | Build labels from HFR/authoritative registries plus Overture/OSM/Healthsites/government-directory/source agreement; reserve Google/Mappls for runtime validation unless license review approves durable training use. |
