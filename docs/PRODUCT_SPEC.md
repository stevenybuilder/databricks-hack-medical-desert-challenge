# Product Spec — DAIS 2026 Virtue Foundation Hackathon

_Last updated: 2026-06-15_

## Event & contract

- **Event:** DAIS 2026 / Virtue Foundation hackathon (June 15–16, 2026).
- **Deliverable:** a **Databricks App on Free Edition**.
- **Track (pick one):** **Track 2 — Medical Desert Planner** — _"Where are the real, highest-risk gaps in care?"_
  - We answer Track 2's *question* but serve it to a **doctor**, not a government planner (see persona rationale).
- **Core requirements (non-negotiable):**
  1. Runs as a Databricks App on Free Edition
  2. Uses the provided facility dataset
  3. Clear **non-technical user workflow**
  4. **Cite the underlying facility text** for any important claim/score/ranking
  5. **Communicate uncertainty** instead of presenting weak evidence as fact
  6. **Persist user actions** (notes, overrides, shortlists, scenarios, review decisions)
- **Judging criteria:** Product judgment · Evidence & uncertainty · Technical execution · Ambition.
- **Format:** science-fair, judges walk up; demo jumps straight in and explains *why this track*.

## Target audience decision

Named audience (host notes — Michael Burk): (1) **Doctors and medical staff**, (2) Government researchers/planners.

**We build for doctors — specifically the visiting/volunteer clinician.** Rationale:
- VF Match (the Virtue Foundation's *own* product, built by the judges) already serves the government-planner / desert-explorer well. Rebuilding that competes with the incumbent on its turf.
- Doctors are the higher-impact, under-served persona, and they're on VF's actual mission (VF Match's CTA is "Apply to Volunteer").
- The novelty does **not** come from the persona — it comes from the **trust / verification / prediction** layer VF Match lacks. Keep that central; do not drift into a referral chatbot (the host's "proven", low-novelty area).

## Persona

**"Dr. Amara," a visiting/volunteer clinician** (e.g. OB/GYN, general surgeon, oncologist). Non-technical. One job: _decide where her skills do the most good, and know what she's walking into._

## Core product

A **VF-Match-style, map-heavy app** spined on a **"Top Care Gaps for your specialty"** leaderboard, powered by a facility **trust/uncertainty engine** that scores evidence quality for newly-crawled facilities, surfacing **patient-condition burden** and **which evidence is fragile** per region.

One-liner for judges: _"VF Match shows you the deserts. We tell you which are real, how sure we are, what conditions you'll face there, and what to do about each — and we keep it true as new facilities come in."_

The trust layer is explicitly uncertainty-aware. Because the hackathon cannot rely
on human verification labels, it uses confidence intervals, empirical prediction
intervals, weak/proxy labels, and active uncertainty ranking instead of claiming
measured facility-truth accuracy. External datasets and geocoding APIs are used as
source-agreement signals: they can narrow uncertainty bands when Google/Mappls,
India Post, HFR/ABDM, PM-JAY, OSM/Overture, and source URLs agree, but they do
not become gold labels by themselves.

## The clean non-technical workflow (5 steps)

```
1. Pick your specialty            → one dropdown (e.g. "General Surgery"), VF-Match style
2. See where you're needed most   → map + "Top Care Gaps for <specialty>" leaderboard
3. Click a gap region             → map flies in, shows the evidence
4. Understand the region:
     - Patient conditions most prevalent here  (NFHS district indicators)
     - Facilities that exist + trust score      (the engine)
     - Which evidence is fragile                (unverified/contradicted/estimated claims, cited)
     - How sure we are                          (district uncertainty level)
5. Save or stress-test it         → shortlist regions/facilities, notes, and inspect
                                     the active uncertainty queue
```

## Patient-condition focus (the doctor value)

Per region, the doctor gets a 4-part answer, all from existing cleaned columns:
1. **Where am I needed?** → specialty-matched `care_gap_score` (leaderboard)
2. **What will I treat?** → patient-condition profile from NFHS-5 (e.g. "21% institutional births, 70% women anaemic, ~0% cervical screening")
3. **What's actually there?** → trustworthy/proxy facilities + fragile evidence (cited `sample_claim_evidence` / `sample_source_urls`)
4. **How sure are we?** → `district_uncertainty_level`
5. **What should I distrust or enrich?** → active uncertainty queue over facilities
   and districts.

### Specialty ↔ condition ↔ supply mapping

| Specialty | Patient-condition burden (NFHS need) | Supply signal (existing column) |
|---|---|---|
| OB/GYN | low institutional births, high women's anaemia, C-section access | `maternity_signal_rate` |
| Pediatrics | child stunting/wasting/underweight, immunization | `maternity`/`diagnostic` signals |
| Oncology / Gyn-onc | ~0% cervical/breast/oral screening + high tobacco | `diagnostic_signal_rate` |
| Cardiology / Endocrine / Internal Med | high BP, high blood sugar | `ncd_signal_rate` |
| Emergency / General Surgery | general acute access | `emergency_signal_rate` |

### Standout condition stories (demo hooks)
- **Preventive cancer screening is near-zero everywhere:** cervical 1.6% mean, breast 0.7%, oral 0.7% — yet **men's tobacco use is 40.6%**. ("40% use tobacco, <1% ever screened for oral cancer.")
- **Women 15–49 anaemia: 55.9% mean** (up to 70%+).
- **Child stunting: 33.5% mean** (up to 60.6%).
- **Institutional births down to 21.4%** (Mon, Nagaland).

## Build-vs-verify recommendation (already computed: `planning_category`)

| Category | # districts | Doctor-facing meaning |
|---|---|---|
| `real_desert_candidate` | 8 | Genuine unmet need → go help / deploy |
| `phantom_desert_or_verification_gap` | 15 | Looks empty but unverified → verify first |
| `supply_record_quality_problem` | 93 | Facilities exist, records broken → fix |
| `referral_or_capacity_candidate` | 99 | Capacity exists → refer here |
| `mixed_or_monitor` | 279 | Monitor |

## Screens (implemented as three tabs sharing the specialty filter)

1. **🗺️ Map** — H3 hexbin layer (green→amber→red) + clickable facility points colored by
   trust status (passed / needs-review / contradicted). Hover tooltip; **click a dot →
   map flies in + facility detail card** with status badge, location, claimed text, and a
   **cited source link**. Controls: map-layer, basemap (Voyager/Positron/Dark), hex-size,
   geo-flagged toggle, show-facilities. Right panel: coverage KPIs + distribution.
2. **📊 Top care gaps** — specialty-aware leaderboard (need × low trustworthy supply) with
   `planning_category` recommendation chips (deploy / verify / fix / refer / monitor).
   Row-click → **region detail**: recommendation, patient-condition profile (NFHS bars),
   need/trust/uncertainty metrics, and cited sample evidence.
3. **Uncertainty Queue** — active-learning-inspired ranked facility and district
   rows. Each row shows the uncertainty score, action, reasons, confidence intervals,
   estimated capacity/doctors, source/contact fields, and why the row affects the
   recommendation. Includes a geo fix pipeline where Databricks `ai_query` parses
   messy Indian addresses and Google Maps/Mappls validates only the physical location.
   The queue stores provider status, location type, partial-match flag, place ID,
   admin-geography agreement, and pre/post geocode uncertainty bands.
   It also shows missing/incomplete data volume and the treatment plan: registry/POI
   enrichment where possible, estimates with intervals for sparse numeric fields,
   and explicit unknown/review states when evidence is absent.
4. **Shortlist / notes** — persisted user actions (Delta table). _(Phase 3)_
5. **Golden Prediction Report Card** — golden-label coverage, source tiers,
   supervised metrics on held-out corroborated labels, proxy-label limits,
   confidence intervals, interval widths, sensitivity checks, and known blind spots.
   _(Phase 5)_
6. **(Stretch) Ask AI** — Foundation Model API for NL Q&A / surfacing recommendations.

## Demo arc (science-fair walk-up)

1. Open on the leaderboard: "These are the worst care gaps for an OB/GYN in India." (instant impact)
2. Click #1 (a `real_desert_candidate`): map flies in → condition profile + "0 trustworthy maternity facilities here."
3. Click a `phantom_desert_or_verification_gap` (e.g. the ocean hospital): "Looks covered, but this 'hospital' is geolocated in the Atlantic and its ICU claim is uncorroborated — so we say *verify*, not *build*."
4. Open the Uncertainty Queue: "We are not pretending we have human labels. This
   ranks the records and districts where the evidence most threatens the decision."
5. Show the geo fix pipeline: "The LLM cleans Indian address text; the geocoder
   validates reality. We only review approximate or conflicting outcomes."

## How this wins the criteria

- **Product / clean workflow:** specialty-in → where-to-go-out, five steps.
- **Evidence & uncertainty:** "things to verify" + trust scores + cited source text + CIs *are* the product.
- **Technical execution:** runs as a Databricks App on Free Edition over a cleaned Delta layer + Foundation Model API.
- **Ambition:** doctor-facing, condition-aware, predictive trust engine VF Match doesn't offer.

## Differentiation from VF Match (the incumbent)

| VF Match has (replicate the look) | We add (the wedge) |
|---|---|
| H3 hexbin heatmap, insight layers, specialty selector | **Trust-weighted** coverage (phantom facilities don't fill a hex) |
| Facility detail popups | Per-claim **verified / unverified / contradicted** + **cited source text** |
| Static dataset | **Golden facility prediction engine** scores newly selected map locations, predicts likely facility attributes, and abstains when evidence is weak |
| Desert exploration | **Patient-condition profile** per region + **build/verify/refer** recommendation |

## Statistical product guardrails

These guardrails come from the Intuit-style model-risk playbook documented in
`STATISTICAL_VERIFICATION_STRATEGY.md`:

- Do not call a record `verified`; use `passed checks`, `needs review`, or
  `contradicted/geography invalid`.
- Treat missing operational fields as informative missingness, not harmless blanks.
- Preserve estimated values, intervals, and confidence labels in the UI.
- Use HFR, PM-JAY, India Post/data.gov, Overture, OSM/Healthsites, geoBoundaries,
  HMIS/NHSRC, and NFHS as source-agreement or context features according to what
  each source can actually prove.
- Use active-learning-style ranking for uncertainty triage, not supervised accuracy.
- Show Wilson intervals for district rates and empirical intervals for estimated
  capacity/doctors.
- Use external evidence as source-agreement features with reason codes, not as
  automatic truth.
- Show proxy-score and coverage metrics as part of the product, not just the model.
- Train supervised models only on a source-corroborated golden dataset. Weak labels
  can guide review queues, but they cannot support accuracy claims.
- For map-selected new locations, show confidence, evidence tier, source links, and
  abstain/review action with every prediction.
