# Entity Resolution Candidate Workflow

This lane produces deterministic facility duplicate/canonical candidates for
human review. It does not merge records, alter `facility_health_cleaned.csv`, or
write to the app.

## Command

```bash
python3 scripts/build_entity_resolution_candidates.py
```

Default inputs and outputs:

| Path | Purpose |
|---|---|
| `output/data/facility_health_cleaned.csv` | Source facility table. |
| `output/data/entity_resolution_candidate_pairs.csv` | Pair-level review queue with similarities, match flags, tiers, and reasons. |
| `output/data/entity_resolution_clusters.csv` | High-confidence connected components with deterministic `er_cluster_id` values and a suggested canonical candidate. |
| `output/data/entity_resolution_summary.json` | Row counts, tier counts, blocking stats, and output paths. |

## Deterministic Inputs

The script uses only local data and Python standard library modules. There are no
web calls, API calls, LLM calls, or new package dependencies.

Signals used from `facility_health_cleaned.csv`:

- `facility_name`
- `address_line1`, `address_line2`, `address_line3`, `address_city`,
  `address_stateOrRegion`, `address_zipOrPostcode`
- `pincode_extracted`
- `officialPhone`, `phone_numbers`
- `email`
- `facility_latitude`, `facility_longitude`, `geo_in_india_bbox`
- `data_readiness_score`
- existing review context such as `source_duplicate_unique_id` and `cluster_id`

## Blocking

Blocking is conservative so pair scoring stays local and bounded:

| Block | Rule |
|---|---|
| PIN | Exact six-digit PIN. |
| City/state/name | Normalized city and state plus significant facility-name token. |
| Phone | Exact normalized phone, excluding values that appear on more than 20 rows. |
| Email | Exact normalized email, excluding values that appear on more than 20 rows. |
| Coordinates | 0.01 degree coordinate bucket. |
| Coordinates plus name | 0.02 degree coordinate bucket plus significant facility-name token. |

Any generated block above `--max-block-size` is skipped. The default cap is 250
rows per block.

## Scoring Features

For each blocked pair, the script emits:

- normalized facility names and `name_similarity`
- normalized address strings and `address_similarity`
- `phone_match`, `email_match`, and shared normalized values
- `pincode_match`
- `city_state_match`
- haversine `geo_distance_km` when plausible coordinates are present
- `match_score`, `match_tier`, `blocking_methods`, and `review_reasons`

Name and address similarities combine standard-library sequence similarity with
token-overlap similarity. Coordinates are used only when they are inside the India
bounding box or otherwise fall in a plausible India latitude/longitude range.

## Match Tiers

| Tier | Meaning |
|---|---|
| `tier_1_high_confidence` | Strong duplicate candidate. Requires local agreement plus shared contact evidence, or very strong name/address/local evidence. Used for cluster generation. |
| `tier_2_review_likely` | Likely duplicate or same-facility candidate, but evidence is weaker or may represent a same-brand branch. Review before use. |
| `tier_3_review_possible` | Possible duplicate surfaced by moderate similarity and blocking context. Useful for queueing, not for canonical decisions. |

Tier labels are review priorities, not truth labels.

## Cluster Policy

`entity_resolution_clusters.csv` is built only from connected components of
`tier_1_high_confidence` pairs.

The `canonical_candidate_*` columns identify the row that is most complete within
the component. The tie-break is:

1. highest `data_readiness_score`
2. highest local completeness over name, address, PIN, city/state, coordinates,
   phone, and email
3. longest facility name
4. deterministic `unique_id` order

This is a suggested review anchor only. No canonical facility table is changed.

## Current Artifact Snapshot

The current local run over 10,077 facility rows produced:

| Metric | Count |
|---|---:|
| Candidate pairs | 902 |
| `tier_1_high_confidence` pairs | 35 |
| `tier_2_review_likely` pairs | 245 |
| `tier_3_review_possible` pairs | 622 |
| High-confidence clusters | 35 |
| Facilities in high-confidence clusters | 70 |

## Review Guidance

Start with `entity_resolution_clusters.csv`, then inspect supporting pair IDs in
`entity_resolution_candidate_pairs.csv`. Treat shared central phone numbers or
brand emails as same-organization evidence unless local address/PIN/coordinate
signals also agree. Keep accepted merges in a separate review artifact; do not
overwrite `facility_health_cleaned.csv` from this script.
