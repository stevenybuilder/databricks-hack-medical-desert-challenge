# External Evidence and Uncertainty Strategy

_Last updated: 2026-06-15_

## Why this layer exists

The FDR facility table is a structured extraction from open web text, not a
facility registry. The workflow is:

```text
web crawl -> GenAI extraction -> entity resolution -> facility record
```

That makes the records useful, but operationally fragile:

- facilities can map to the wrong district or impossible coordinates;
- multiple real facilities can merge under one ambiguous name;
- contact fields can exist without proving reachability;
- capacity and doctor-count fields are sparse, heavy-tailed, and sometimes
  implausible;
- source pages can be stale or describe a different facility.

Because this hackathon flow cannot rely on manual/human verification labels, the
strategy is to quantify uncertainty, cite the evidence, and rank what would benefit
most from source enrichment or stress testing.

## Evidence tiers

| Tier | Source | Use |
|---|---|---|
| A | ABDM Health Facility Registry | Authoritative existence, identity, type, location when available. |
| A | PM-JAY empanelled hospitals | Active hospital-network existence and specialty/service hints. |
| A | India Post PIN directory via data.gov.in | PIN-to-district/state bridge, ambiguity counts, centroid checks. |
| B | Overture Maps Places | Independent POI name/category/coordinate/contact confidence. |
| B | OpenStreetMap / Overpass / Healthsites | Community-mapped facility coordinate/name corroboration. |
| B | National Health Portal / data.gov.in health datasets | Legacy hospital metadata, contact, and specialization corroboration. |
| B | Google Maps / Mappls geocoding | Location existence, coordinate, place ID, and precision metadata; not sufficient alone for verified facility truth. |
| C | geoBoundaries / district boundary files | Spatial containment and boundary-crossing checks. |
| C | HMIS / NHSRC district indicators | District/block service context and plausibility checks. |
| C | NFHS-5 district fact sheets | Need-side health indicators only, not facility ground truth. |
| C | Facility website and provided source URLs | Citation and claim context; not sufficient alone for high-risk service claims. |

Tier C evidence is necessary for transparency but should not be treated as verified
truth.

## Missing and incomplete data handling

Missing fields are informative signals, not blanks to hide. The pipeline handles
them by field type:

| Gap | Handling |
|---|---|
| Missing/suspicious coordinates | LLM parses Indian address text; Google/Mappls validates location; H3 smooths noisy but plausible points. |
| Missing facility identity | Match against HFR, PM-JAY, National Health Portal/data.gov, Overture, OSM/Healthsites. Unmatched means unknown, not fake. |
| Weak district/PIN join | Normalize state/district aliases, same-state fuzzy matching, PIN ambiguity flags, join confidence. |
| Missing capacity/doctor counts | Estimate from facility-type/operator/state peer groups, expose p10-p90 intervals, confidence, and `*_is_estimated`. |
| Missing services/equipment/procedures | Treat as absent evidence, not absence of service; enrich from registries/source pages or queue high-impact rows. |
| Missing contacts/reachability | Enrich phone/email/site from registries and POI sources; actual reachability still needs call/email outcome. |
| Stale or missing source URL | Downweight readiness, keep row in uncertainty queue, require stronger external corroboration before use. |

## Active uncertainty outputs

The pipeline now writes two queues:

- `output/data/active_learning_facility_queue.csv`
- `output/data/active_learning_district_queue.csv`
- `output/data/geo_validation_candidates.csv`
- `output/data/geocoder_uncertainty_priors.csv`

These are active-learning inspired but no-oracle. They answer:

```text
Which rows would most reduce decision uncertainty if we enriched, corroborated,
or stress-tested them next?
```

## Queue actions

| Action | Meaning |
|---|---|
| `contradiction_audit` | Geography, impossible values, or internal contradictions make the row risky. |
| `semantic_missingness_enrichment` | Critical operational fields are missing or estimated. |
| `join_bridge_enrichment` | Pincode/district/state mapping uncertainty drives the risk. |
| `high_impact_uncertainty_reduction` | High district health need plus fragile facility evidence. |
| `sparse_segment_coverage` | The row is from a thin facility/operator/state segment. |
| `stress_test_desert_call` | District recommendation may be high-impact but rests on thin evidence. |
| `rate_ci_reduction` | District-level rate intervals are wide because of small observed samples. |

## App implementation

The Streamlit app should expose an **Uncertainty** tab:

- data-quality reality table explaining why the raw data is messy;
- external evidence source tiers;
- missing/incomplete data volume plus handling plan;
- top facility uncertainty queue with reasons and interval fields;
- top district uncertainty queue with Wilson confidence intervals;
- estimated capacity/doctors with empirical p10-p90 intervals;
- external geocoding uncertainty: provider status, location type, partial-match
  flag, admin-geography agreement, and source-agreement reason codes;
- recommendation fragility warnings where CIs or proxy bands are wide.

The UI must avoid the word `verified` unless a future authoritative source match
supports it. Current labels should be:

- `passed_checks`;
- `needs_review`;
- `contradicted_or_geo_invalid`;
- `estimated`;
- `unknown`.

For the CLI batch geo workflow, see `GEO_VALIDATION_CLI.md`.
