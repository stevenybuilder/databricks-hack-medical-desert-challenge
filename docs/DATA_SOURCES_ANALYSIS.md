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

### Table 1 — `facilities` (10,088 raw rows × 48 cols → 10,077 cleaned × 102)

- **11 duplicate `unique_id` rows** in raw; cleaned keeps one row + source occurrence count.
- **Field coverage** (the "treat noisy fields as claims" reality):

  | Field | Coverage | | Field | Coverage |
  |---|---|---|---|---|
  | name | 99.4% | | description | 99.2% |
  | address_zipOrPostcode | 99.3% | | capability | 98.8% |
  | latitude / longitude | 98.8% | | procedure | 98.6% |
  | source_urls | 98.8% | | equipment | 97.8% |
  | numberDoctors | **36.0%** | | yearEstablished | **47.6%** |
  | capacity | **25.0%** | | | |

  → Text/claim fields are nearly complete; **structured operational fields
  (capacity, doctors, year) are sparse** and cannot anchor rankings alone.

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

- **Needs human review: 3,029 rows = 30.1%** (95% CI [29.2%, 31.0%]). ~1 in 3 facility
  records is not safe to use as-is — this is the problem the app exists to surface.
- **Trustworthy supply: 7,046 rows (69.9%)** — what survives the trust filter.
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

- **District uncertainty:** lower 209 · medium 105 · higher 180. ~36% of districts carry
  *higher* uncertainty — the app must show this, not hide it.

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

---

## 9. Implications for the build (honor these in the app)

| Finding | What the app must do |
|---|---|
| 30% of facilities need human review | Surface a "to verify" state prominently; never present claims as fact. |
| `numberDoctors`/`capacity` have impossible maxima (15k, 4k) | Cap/winsorize before aggregating; show median + range, not mean; flag outliers. |
| Heavy-tailed operational fields | Log-scale visuals; robust percentile stats. |
| 6 outside-India + 928 far-from-centroid geos | Geo-quality badge per facility; the ocean hospital is the opening demo. |
| Confidence intervals exist for every rate | Show CIs / uncertainty bands in the UI (it's a scored criterion). |
| `planning_category` already computed | Drive build/verify/refer recommendation chips directly from it. |
| capacity/doctors/year are sparse (25–48%) | Don't rank on them alone; lean on need + trustworthy supply + service signals. |
| NFHS is district-grain, older, sample | Label it "district context"; keep `district_uncertainty_level` visible. |
| No population/travel denominator | Call gap scores "proxies" honestly; (stretch) add WorldPop + distance approx. |
| Claims must be cited | Wire `sample_source_urls` / `sample_claim_evidence` into every claim shown. |
| Derived scores are well-behaved | Safe to color the map and rank the leaderboard on `care_gap_score`. |
