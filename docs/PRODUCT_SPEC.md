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

A **VF-Match-style, map-heavy app** spined on a **"Top Care Gaps for your specialty"** leaderboard, powered by a facility **trust engine** and a **predictive model** that auto-scores newly-crawled facilities, surfacing **patient-condition burden** and **what to verify** per region.

One-liner for judges: _"VF Match shows you the deserts. We tell you which are real, how sure we are, what conditions you'll face there, and what to do about each — and we keep it true as new facilities come in."_

## The clean non-technical workflow (5 steps)

```
1. Pick your specialty            → one dropdown (e.g. "General Surgery"), VF-Match style
2. See where you're needed most   → map + "Top Care Gaps for <specialty>" leaderboard
3. Click a gap region             → map flies in, shows the evidence
4. Understand the region:
     - Patient conditions most prevalent here  (NFHS district indicators)
     - Facilities that exist + trust score      (the engine)
     - What to verify before relying on them    (unverified/contradicted claims, cited)
     - How sure we are                          (district uncertainty level)
5. Save it                        → shortlist regions/facilities, notes (persistence)
```

## Patient-condition focus (the doctor value)

Per region, the doctor gets a 4-part answer, all from existing cleaned columns:
1. **Where am I needed?** → specialty-matched `care_gap_score` (leaderboard)
2. **What will I treat?** → patient-condition profile from NFHS-5 (e.g. "21% institutional births, 70% women anaemic, ~0% cervical screening")
3. **What's actually there?** → trustworthy facilities + what to verify (cited `sample_claim_evidence` / `sample_source_urls`)
4. **How sure are we?** → `district_uncertainty_level`

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

## Screens

1. **Map + leaderboard** — H3 hexbin choropleth (red=poor → green=good coverage) + "Top Care Gaps for <specialty>" ranked list. The 8 `real_desert_candidate` districts headline.
2. **Region detail** — patient-condition profile (NFHS) + facilities with trust scores + cited evidence + `planning_category` recommendation chip + uncertainty band.
3. **Shortlist / notes** — persisted user actions (Delta table).
4. **(Stretch) Ask AI** — Foundation Model API for NL Q&A / surfacing recommendations.

## Demo arc (science-fair walk-up)

1. Open on the leaderboard: "These are the worst care gaps for an OB/GYN in India." (instant impact)
2. Click #1 (a `real_desert_candidate`): map flies in → condition profile + "0 trustworthy maternity facilities here."
3. Click a `phantom_desert_or_verification_gap` (e.g. the ocean hospital): "Looks covered, but this 'hospital' is geolocated in the Atlantic and its ICU claim is uncorroborated — so we say *verify*, not *build*."
4. "And when a new facility is crawled, the predictive engine scores it automatically — here's the calibration proving it's trustworthy."

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
| Static dataset | **Predictive engine** scores newly-crawled facilities |
| Desert exploration | **Patient-condition profile** per region + **build/verify/refer** recommendation |
