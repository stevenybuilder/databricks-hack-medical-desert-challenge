# Data Cleaning Execution Status

_Last updated: 2026-06-16_

## Baseline

The current cleaned facility table has 10,077 deduplicated facility rows from
10,088 raw rows. The audit artifact has been regenerated from the current CSV
and is upload-ready with one warning: 11 duplicate raw `unique_id` rows were
deduplicated into the cleaned table.

## Completed Lanes

| Lane | Output | Current result |
| --- | --- | --- |
| Baseline audit refresh | `output/data/cleaned_dataset_audit.json` | 10,077 rows, 7,812 need review, 4,004 have trustworthy supply signal |
| Remaining severe geo queue | `output/data/geo_validation_remaining_severe_candidates.csv` | 802 remaining severe geo rows queued after excluding the first 250 |
| Google evidence to corrections | `output/data/geo_coordinate_correction_candidates.csv` | 21 proposed corrections: 14 coordinate replacements, 7 H3-only candidates |
| Claims validation | `output/data/claim_validation_queue.csv` | 120,924 facility-category rows across 12 controlled categories |
| Entity resolution | `output/data/entity_resolution_candidate_pairs.csv` | 902 duplicate candidate pairs; 35 high-confidence clusters |
| Missing data and human seed | `output/data/human_verification_seed_queue.csv` | 150-row high-value human verification seed queue |

## Current Backlog Counts

| Backlog | Rows |
| --- | ---: |
| Rows needing human review | 7,812 |
| Strict ready-without-review rows | 1,999 |
| Severe geo backlog before first batch | 1,052 |
| Severe geo rows already selected in first batch | 250 |
| Remaining severe geo rows now queued | 802 |
| Moderate-or-worse geo rows still not externally resolved | 1,966 |
| Primary claims-verification remediation rows | 5,873 |
| Primary geocode remediation rows | 2,216 |
| Primary registry/source enrichment remediation rows | 1,276 |

## Security / Git Policy

Generated row-level queues are ignored by git because they can contain facility
names, addresses, contacts, source URLs, and review evidence. Scripts and docs
are safe to commit; local review queues should be exported intentionally.

## Interpretation

The dataset is structurally cleaned and auditable. The remaining work is truth
validation: externally verifying coordinates, claims, canonical facility
identity, reachability, and missing high-impact evidence.
