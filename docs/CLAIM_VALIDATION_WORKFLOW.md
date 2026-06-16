# Facility Claim Validation Workflow

This lane normalizes facility service claims from `output/data/facility_health_cleaned.csv` into a reviewer queue. It is local-only: it does not call websites, APIs, LLMs, or external validation services.

## Outputs

- `output/data/claim_validation_queue.csv`: one row per facility and controlled claim category, sorted by `priority_score` descending.
- `output/data/claim_validation_summary.json`: row counts, status counts, action counts, reason counts, and top-priority examples.

Run:

```bash
python3 scripts/build_claim_validation_queue.py
```

For a smoke test:

```bash
python3 scripts/build_claim_validation_queue.py --limit 100
```

## Controlled Categories

The script uses transparent keyword and regex rules over the local `claim_text` evidence sections:

- `maternity`
- `emergency`
- `diagnostic`
- `surgery`
- `cardiology`
- `oncology`
- `ophthalmology`
- `dental`
- `pharmacy`
- `lab/imaging`
- `blood bank`
- `ICU/critical care`

Camel-case claim tokens such as `criticalCareMedicine` are normalized before matching.

## Status Semantics

- `observed`: the category has local keyword evidence in `claim_text`.
- `missing`: the category was not observed in the local claim evidence. This is not proof the facility lacks the service.
- `broad_or_ambiguous`: the category is observed only through generic, indirect, or broad language such as directory listings, affiliation mentions, broad multispecialty claims, or capped/noisy claim lists.
- `high_impact_claim`: true for critical or high-impact categories such as maternity, emergency, diagnostics, surgery, cardiology, oncology, lab/imaging, blood bank, and ICU/critical care.
- `needs_verification`: true when the claim is high-impact, broad/ambiguous, locally flagged for human review, lacks source/contact evidence, has low semantic quality, or is a missing high-impact claim in a high-need context.

## Priority Score

`priority_score` is a deterministic rule score from 0 to 100. It increases for:

- high-impact categories,
- observed claims that need verification,
- broad or ambiguous evidence,
- missing high-impact categories in high-need or medical-desert-priority contexts,
- rows already marked `needs_human_review`,
- rows without trustworthy supply signals,
- missing source URL, official website, or contact evidence,
- low `semantic_data_quality_score`,
- higher `medical_desert_priority_score` and `health_need_score`.

The score is a triage order, not a confidence score.

## Reviewer Actions

- `verify_observed_high_impact_claim`: cite and confirm a high-impact observed claim before operational use.
- `verify_or_fill_missing_high_impact_claim`: check whether a high-impact service is truly absent or just missing from local evidence.
- `resolve_broad_or_ambiguous_claim`: replace broad language with specific service evidence or downgrade the claim.
- `verify_source_evidence`: enrich or inspect local source/contact evidence.
- `monitor_missing_local_evidence`: low-priority missing category; no immediate action unless required by a downstream use case.
- `accept_observed_proxy`: observed local proxy claim with no current verification blocker.

## Evidence Fields

The queue preserves review context from the cleaned dataset:

- facility identifiers and address fields,
- `claim_text_excerpt` and category-level `evidence_excerpt`,
- `source_urls`, `primary_source_url`, `source_url_count`, `officialWebsite`,
- phone and email evidence fields,
- specialties/procedure/equipment/capability statuses and counts,
- `semantic_data_quality_score`, `needs_human_review`, `trustworthy_supply_signal`,
- `medical_desert_priority_score` and `health_need_score`.

Use `review_reasons`, `matched_evidence_fields`, and `matched_keywords` to understand why a row was queued and how the category was normalized.

## Limits

This lane normalizes local evidence only. It does not verify that services are currently available, licensed, staffed, or geographically correct. All high-impact observed claims remain claims until confirmed against authoritative or current sources.
