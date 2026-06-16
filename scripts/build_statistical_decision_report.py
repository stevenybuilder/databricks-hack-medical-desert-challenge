#!/usr/bin/env python3
"""Build category-volume and statistical decision-policy artifacts.

The report is deliberately descriptive. It quantifies the current proxy and seed
decision categories, then documents which statistical ideas are valid now versus
which require future gold/silver labels or longitudinal outcomes.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    from scipy.stats import beta as beta_dist
except ImportError:  # pragma: no cover - scipy is available in the project env
    beta_dist = None


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "output" / "data"
DOCS_DIR = ROOT / "docs"

FACILITY_PATH = DATA_DIR / "facility_health_cleaned.csv"
DISTRICT_PATH = DATA_DIR / "district_health_facility_cleaned.csv"
GOLDEN_TRAINING_PATH = DATA_DIR / "golden_facility_training_set_seed.csv"
PREDICTION_PATH = DATA_DIR / "facility_prediction_outputs_seed.csv"
SOURCE_MATCHES_PATH = DATA_DIR / "golden_facility_source_matches_seed.csv"
FACILITY_QUEUE_PATH = DATA_DIR / "active_learning_facility_queue.csv"
DISTRICT_QUEUE_PATH = DATA_DIR / "active_learning_district_queue.csv"

VOLUME_SUMMARY_PATH = DATA_DIR / "decision_category_volume_summary.csv"
POLICY_REPORT_PATH = DATA_DIR / "statistical_decision_policy_report.json"
MARKDOWN_REPORT_PATH = DOCS_DIR / "STATISTICAL_DECISION_FRAMEWORK.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--docs-dir", type=Path, default=DOCS_DIR)
    return parser.parse_args()


def read_csv(path: Path, usecols: list[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    kwargs: dict[str, Any] = {"low_memory": False}
    if usecols is not None:
        header = pd.read_csv(path, nrows=0).columns.tolist()
        kwargs["usecols"] = [col for col in usecols if col in header]
    return pd.read_csv(path, **kwargs)


def coerce_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype("string").fillna("").str.lower().str.strip().isin({"true", "1", "yes", "y"})


def clean_category(value: object) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "missing"
    text = str(value).strip()
    return text if text else "blank"


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (np.nan, np.nan)
    p = successes / n
    denom = 1 + (z**2 / n)
    center = (p + z**2 / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) / n) + (z**2 / (4 * n**2)))) / denom
    return center - margin, center + margin


def beta_jeffreys_interval(successes: int, n: int) -> tuple[float, float, float]:
    if n <= 0:
        return (np.nan, np.nan, np.nan)
    alpha = successes + 0.5
    beta = (n - successes) + 0.5
    mean = alpha / (alpha + beta)
    if beta_dist is None:
        return (mean, np.nan, np.nan)
    return (
        mean,
        float(beta_dist.ppf(0.025, alpha, beta)),
        float(beta_dist.ppf(0.975, alpha, beta)),
    )


def category_row(
    *,
    group: str,
    category: str,
    rows: int,
    denominator: int,
    grain: str,
    source_file: str,
    exclusive: bool,
    method_note: str,
) -> dict[str, object]:
    pct = rows / denominator if denominator else np.nan
    wilson_low, wilson_high = wilson_interval(rows, denominator)
    bayes_mean, bayes_low, bayes_high = beta_jeffreys_interval(rows, denominator)
    return {
        "category_group": group,
        "grain": grain,
        "category": category,
        "rows": int(rows),
        "denominator": int(denominator),
        "pct": round(float(pct), 6) if pd.notna(pct) else np.nan,
        "wilson_95_low": round(float(wilson_low), 6) if pd.notna(wilson_low) else np.nan,
        "wilson_95_high": round(float(wilson_high), 6) if pd.notna(wilson_high) else np.nan,
        "bayes_jeffreys_mean": round(float(bayes_mean), 6) if pd.notna(bayes_mean) else np.nan,
        "bayes_95_low": round(float(bayes_low), 6) if pd.notna(bayes_low) else np.nan,
        "bayes_95_high": round(float(bayes_high), 6) if pd.notna(bayes_high) else np.nan,
        "exclusive": exclusive,
        "source_file": source_file,
        "method_note": method_note,
    }


def add_distribution(
    rows: list[dict[str, object]],
    df: pd.DataFrame,
    *,
    column: str,
    group: str,
    grain: str,
    source_file: str,
    method_note: str = "Exclusive category share; intervals quantify finite-row proportion uncertainty.",
) -> None:
    if df.empty or column not in df:
        return
    denominator = len(df)
    counts = df[column].map(clean_category).value_counts(dropna=False)
    for category, count in counts.items():
        rows.append(
            category_row(
                group=group,
                category=str(category),
                rows=int(count),
                denominator=denominator,
                grain=grain,
                source_file=source_file,
                exclusive=True,
                method_note=method_note,
            )
        )


def add_boolean_flags(
    rows: list[dict[str, object]],
    df: pd.DataFrame,
    *,
    columns: list[tuple[str, str]],
    group: str,
    grain: str,
    source_file: str,
) -> None:
    if df.empty:
        return
    denominator = len(df)
    for column, label in columns:
        if column not in df:
            continue
        count = int(coerce_bool(df[column]).sum())
        rows.append(
            category_row(
                group=group,
                category=label,
                rows=count,
                denominator=denominator,
                grain=grain,
                source_file=source_file,
                exclusive=False,
                method_note="Overlapping boolean signal; percentages do not sum to 100%.",
            )
        )


def add_confidence_bins(rows: list[dict[str, object]], predictions: pd.DataFrame) -> None:
    if predictions.empty or "prediction_confidence" not in predictions:
        return
    values = pd.to_numeric(predictions["prediction_confidence"], errors="coerce")
    denominator = int(values.notna().sum())
    if denominator == 0:
        return
    bins = [-np.inf, 0.50, 0.70, 0.80, 0.90, np.inf]
    labels = ["<0.50", "0.50-0.69", "0.70-0.79", "0.80-0.89", ">=0.90"]
    cut = pd.cut(values.dropna(), bins=bins, labels=labels, right=False)
    for category, count in cut.value_counts(sort=False).items():
        rows.append(
            category_row(
                group="Rule-baseline confidence band",
                category=str(category),
                rows=int(count),
                denominator=denominator,
                grain="facility prediction seed row",
                source_file=PREDICTION_PATH.name,
                exclusive=True,
                method_note="Rule-proxy confidence band; not calibrated accuracy without gold/silver labels.",
            )
        )
    for threshold in [0.50, 0.70, 0.80, 0.90]:
        count = int(values.ge(threshold).sum())
        rows.append(
            category_row(
                group="Rule-baseline confidence coverage",
                category=f">= {threshold:.2f}",
                rows=count,
                denominator=denominator,
                grain="facility prediction seed row",
                source_file=PREDICTION_PATH.name,
                exclusive=False,
                method_note="Coverage above confidence threshold; currently all seed predictions still abstain.",
            )
        )


def build_volume_summary(data_dir: Path) -> pd.DataFrame:
    facilities = read_csv(
        data_dir / FACILITY_PATH.name,
        usecols=[
            "needs_human_review",
            "trustworthy_supply_signal",
            "contradicted_or_geo_invalid_signal",
            "has_source_urls",
            "has_contact_evidence",
            "capacity_is_estimated",
            "doctor_count_is_estimated",
            "critical_supply_gap_flag",
            "geo_quality",
            "join_strategy",
            "capacity_status",
            "doctor_count_status",
            "recency_status",
        ],
    )
    districts = read_csv(data_dir / DISTRICT_PATH.name, usecols=["planning_category", "district_uncertainty_level"])
    golden = read_csv(
        data_dir / GOLDEN_TRAINING_PATH.name,
        usecols=[
            "evidence_tier",
            "trust_posture",
            "recommended_action",
            "abstain_reason",
            "capacity_band",
            "doctor_count_band",
            "trainable_supervised_label",
        ],
    )
    predictions = read_csv(
        data_dir / PREDICTION_PATH.name,
        usecols=["prediction_confidence", "evidence_tier", "abstain", "recommended_action"],
    )
    source_matches = read_csv(
        data_dir / SOURCE_MATCHES_PATH.name,
        usecols=["source_system", "source_tier", "source_agreement_status", "can_promote_label"],
    )
    facility_queue = read_csv(
        data_dir / FACILITY_QUEUE_PATH.name,
        usecols=["active_learning_action", "external_validation_action"],
    )
    district_queue = read_csv(data_dir / DISTRICT_QUEUE_PATH.name, usecols=["active_learning_action"])

    rows: list[dict[str, object]] = []
    add_distribution(rows, golden, column="evidence_tier", group="Golden seed evidence tier", grain="facility seed row", source_file=GOLDEN_TRAINING_PATH.name)
    add_distribution(rows, golden, column="trust_posture", group="Golden seed trust posture", grain="facility seed row", source_file=GOLDEN_TRAINING_PATH.name)
    add_distribution(rows, golden, column="recommended_action", group="Golden seed recommended action", grain="facility seed row", source_file=GOLDEN_TRAINING_PATH.name)
    add_distribution(rows, golden, column="abstain_reason", group="Golden seed abstain reason", grain="facility seed row", source_file=GOLDEN_TRAINING_PATH.name)
    add_distribution(rows, golden, column="capacity_band", group="Predicted capacity band seed", grain="facility seed row", source_file=GOLDEN_TRAINING_PATH.name)
    add_distribution(rows, golden, column="doctor_count_band", group="Predicted doctor-count band seed", grain="facility seed row", source_file=GOLDEN_TRAINING_PATH.name)
    add_boolean_flags(
        rows,
        golden,
        columns=[("trainable_supervised_label", "Trainable supervised label")],
        group="Golden seed training readiness",
        grain="facility seed row",
        source_file=GOLDEN_TRAINING_PATH.name,
    )
    add_distribution(rows, districts, column="planning_category", group="District planning category", grain="district row", source_file=DISTRICT_PATH.name)
    add_distribution(rows, districts, column="district_uncertainty_level", group="District uncertainty level", grain="district row", source_file=DISTRICT_PATH.name)
    add_distribution(rows, facilities, column="geo_quality", group="Facility geo quality", grain="facility row", source_file=FACILITY_PATH.name)
    add_distribution(rows, facilities, column="join_strategy", group="Facility-health join strategy", grain="facility row", source_file=FACILITY_PATH.name)
    add_distribution(rows, facilities, column="capacity_status", group="Capacity status", grain="facility row", source_file=FACILITY_PATH.name)
    add_distribution(rows, facilities, column="doctor_count_status", group="Doctor-count status", grain="facility row", source_file=FACILITY_PATH.name)
    add_distribution(rows, facilities, column="recency_status", group="Source recency status", grain="facility row", source_file=FACILITY_PATH.name)
    add_boolean_flags(
        rows,
        facilities,
        columns=[
            ("needs_human_review", "Needs human review"),
            ("trustworthy_supply_signal", "Passed proxy checks"),
            ("contradicted_or_geo_invalid_signal", "Contradicted or geo-invalid"),
            ("has_source_urls", "Has source URL"),
            ("has_contact_evidence", "Has contact evidence"),
            ("capacity_is_estimated", "Capacity estimated/missing"),
            ("doctor_count_is_estimated", "Doctor count estimated/missing"),
            ("critical_supply_gap_flag", "Critical supply gap"),
        ],
        group="Facility quality flags",
        grain="facility row",
        source_file=FACILITY_PATH.name,
    )
    add_distribution(rows, source_matches, column="source_system", group="Golden source-match system", grain="source-match row", source_file=SOURCE_MATCHES_PATH.name)
    add_distribution(rows, source_matches, column="source_tier", group="Golden source-match source tier", grain="source-match row", source_file=SOURCE_MATCHES_PATH.name)
    add_distribution(rows, source_matches, column="source_agreement_status", group="Golden source agreement status", grain="source-match row", source_file=SOURCE_MATCHES_PATH.name)
    add_boolean_flags(
        rows,
        source_matches,
        columns=[("can_promote_label", "Can promote label now")],
        group="Golden source-match promotion readiness",
        grain="source-match row",
        source_file=SOURCE_MATCHES_PATH.name,
    )
    add_confidence_bins(rows, predictions)
    add_distribution(rows, facility_queue, column="active_learning_action", group="Facility active-learning action", grain="facility queue row", source_file=FACILITY_QUEUE_PATH.name)
    add_distribution(rows, facility_queue, column="external_validation_action", group="Facility external-validation action", grain="facility queue row", source_file=FACILITY_QUEUE_PATH.name)
    add_distribution(rows, district_queue, column="active_learning_action", group="District active-learning action", grain="district queue row", source_file=DISTRICT_QUEUE_PATH.name)

    summary = pd.DataFrame(rows)
    if summary.empty:
        return summary
    return summary.sort_values(["category_group", "rows", "category"], ascending=[True, False, True]).reset_index(drop=True)


def statistical_policy() -> dict[str, object]:
    return {
        "current_scope": (
            "The current system is proxy decision support. It quantifies evidence "
            "quality and finite-row uncertainty, but it does not claim causal impact "
            "or measured supervised accuracy until gold/silver labels exist."
        ),
        "decision_rules_already_in_pipeline": [
            {
                "decision": "needs_human_review",
                "rule": (
                    "data_readiness_score < 0.65 OR semantic_data_quality_score < 0.45 "
                    "OR critical_supply_gap_flag OR join_confidence < 0.80 OR geo_quality != plausible "
                    "OR capacity/doctor outlier OR claim_field_count < 2"
                ),
                "statistical_role": "High-recall uncertainty gate; routes weak or conflicting rows to review.",
            },
            {
                "decision": "passed_proxy_checks",
                "rule": (
                    "data_readiness_score >= 0.80 AND join_confidence >= 0.80 AND geo_quality == plausible "
                    "AND has_source_urls AND claim_field_count >= 3 AND supply_data_confidence_score >= 0.65 "
                    "AND no capacity/doctor outlier AND no invalid recency"
                ),
                "statistical_role": "Proxy precision gate; not a verified facility label.",
            },
            {
                "decision": "contradicted_or_geo_invalid",
                "rule": "outside-India or far-from-PIN coordinates, or extreme capacity/doctor outlier.",
                "statistical_role": "Conflict gate; excludes rows from training and sends them to location/source review.",
            },
            {
                "decision": "real_desert_candidate",
                "rule": (
                    "care_gap_score >= 0.70, top-quartile health_need_score, and <= 2 trustworthy supply rows."
                ),
                "statistical_role": "High-need, low-trustworthy-supply planning segment; still needs sensitivity checks.",
            },
        ],
        "concepts": [
            {
                "concept": "Wilson confidence intervals",
                "use_now": True,
                "where_applied": "District/facility/category rates, especially small district samples.",
                "why_relevant": "Better behaved than naive normal intervals for bounded proportions.",
            },
            {
                "concept": "Bayesian beta-binomial rates",
                "use_now": True,
                "where_applied": "Category-volume report uses Jeffreys Beta(0.5, 0.5) posterior intervals.",
                "why_relevant": "Gives stable rate uncertainty for rare categories without pretending labels are truth.",
            },
            {
                "concept": "Bayesian source-agreement update",
                "use_now": True,
                "where_applied": "Proxy trust bands for source corroboration.",
                "why_relevant": (
                    "Use internal evidence as prior and update with likelihood-style evidence from HFR/PM-JAY, "
                    "Overture/OSM, India Post/admin agreement, and geocoder metadata."
                ),
                "formula": "logit(posterior_proxy) = logit(prior_proxy) + sum(log_likelihood_ratios) - conflict_penalties",
            },
            {
                "concept": "Expected utility / expected value",
                "use_now": True,
                "where_applied": "Recommend versus verify-first versus abstain actions.",
                "why_relevant": "A deployment decision should depend on benefit, harm/cost, and uncertainty, not probability alone.",
                "formula": "EV(action) = P(correct) * benefit - P(wrong) * harm - operating_cost",
            },
            {
                "concept": "Value of information",
                "use_now": True,
                "where_applied": "Active uncertainty queues.",
                "why_relevant": "Ranks rows where one more source check is likely to change the decision.",
                "formula": "VOI = expected_utility_after_review - expected_utility_before_review - review_cost",
            },
            {
                "concept": "Calibration, Brier score, log loss, coverage at thresholds",
                "use_now": False,
                "where_applied": "Supervised model report after gold/silver labels exist.",
                "why_relevant": "Only valid when predictions can be evaluated against held-out corroborated labels.",
            },
            {
                "concept": "Hierarchical shrinkage",
                "use_now": True,
                "where_applied": "Capacity and doctor-count estimates.",
                "why_relevant": "Sparse cohorts borrow strength from broader facility/operator/type groups.",
            },
            {
                "concept": "Markov chains",
                "use_now": False,
                "where_applied": "Future repeated observations of facility status over time.",
                "why_relevant": "The current dataset is cross-sectional, so there are no observed transition probabilities.",
            },
            {
                "concept": "Regime switching",
                "use_now": False,
                "where_applied": "Future time-series data with policy, outbreak, or seasonal regimes.",
                "why_relevant": "Not identifiable from the current one-time snapshot.",
            },
            {
                "concept": "Backdoor adjustment / causal inference",
                "use_now": False,
                "where_applied": "Future evaluation of whether sending a doctor caused better outcomes.",
                "why_relevant": (
                    "Current rankings are predictive/decision-support scores. Causal claims would need outcomes "
                    "and adjustment for baseline burden, existing supply, rurality, poverty, travel time, state effects, "
                    "data quality, and volunteer-selection bias."
                ),
            },
        ],
        "expected_value_policy": {
            "probability_source_now": "proxy trust/confidence band midpoint plus evidence tier and conflict gates",
            "probability_source_after_labels": "calibrated supervised probabilities on held-out gold/silver labels",
            "action_policy": [
                {
                    "action": "recommend_or_deploy",
                    "condition": "High expected utility, no conflict flag, robust district need/gap, and sufficient evidence tier.",
                },
                {
                    "action": "verify_first",
                    "condition": "Potential impact is high but source/geo uncertainty can change the decision.",
                },
                {
                    "action": "enrich_sources",
                    "condition": "Missingness or source gaps dominate the uncertainty score.",
                },
                {
                    "action": "abstain",
                    "condition": "Conflict, bronze-only evidence for a high-stakes action, or model confidence below policy threshold.",
                },
            ],
        },
    }


def pct_text(value: object, digits: int = 1) -> str:
    num = pd.to_numeric(value, errors="coerce")
    if pd.isna(num):
        return "n/a"
    return f"{float(num) * 100:.{digits}f}%"


def df_to_markdown(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows available._"
    clean = df.copy()
    for col in clean.columns:
        clean[col] = clean[col].map(lambda value: "" if pd.isna(value) else str(value).replace("|", "\\|"))
    header = "| " + " | ".join(clean.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(clean.columns)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in clean.to_numpy(dtype=str)]
    return "\n".join([header, separator, *body])


def markdown_table(df: pd.DataFrame, groups: list[str]) -> str:
    subset = df[df["category_group"].isin(groups)].copy()
    if subset.empty:
        return "_No rows available._"
    subset["Pct"] = subset["pct"].map(pct_text)
    subset["Wilson 95%"] = subset.apply(
        lambda row: f"{pct_text(row['wilson_95_low'])}-{pct_text(row['wilson_95_high'])}",
        axis=1,
    )
    cols = ["category_group", "grain", "category", "rows", "denominator", "Pct", "Wilson 95%"]
    return df_to_markdown(subset[cols])


def write_markdown(summary: pd.DataFrame, policy: dict[str, object], path: Path) -> None:
    concepts = pd.DataFrame(policy["concepts"])
    concepts["use_now"] = concepts["use_now"].map(lambda value: "yes" if value else "not yet")
    concept_table = df_to_markdown(concepts[["concept", "use_now", "where_applied", "why_relevant"]])

    text = f"""# Statistical Decision Framework

_Last updated: 2026-06-15_

This report is generated by `scripts/build_statistical_decision_report.py`.

## Current scope

{policy["current_scope"]}

## Main category volumes

{markdown_table(summary, [
    "Golden seed evidence tier",
    "Golden seed trust posture",
    "Golden seed recommended action",
    "District planning category",
])}

## Data-quality and uncertainty volumes

{markdown_table(summary, [
    "Facility quality flags",
    "Facility geo quality",
    "Facility-health join strategy",
    "Rule-baseline confidence band",
    "Rule-baseline confidence coverage",
])}

## Active uncertainty queues

{markdown_table(summary, [
    "Facility active-learning action",
    "Facility external-validation action",
    "District active-learning action",
])}

## Statistical concepts

{concept_table}

## Expected value policy

Use expected utility for decisions, not confidence alone:

```text
EV(action) = P(correct) * benefit - P(wrong) * harm - operating_cost
VOI = expected_utility_after_review - expected_utility_before_review - review_cost
```

For the current hackathon data, `P(correct)` is a proxy evidence probability, not
measured accuracy. After gold/silver labels exist, replace the proxy with calibrated
held-out model probabilities and report Brier/log-loss/coverage.

## Causal inference boundary

Backdoor adjustment and other causal methods are relevant only for a future impact
study, for example estimating whether sending a doctor caused better health access
or outcomes. The current ranking is not causal. A future causal design would need
outcomes plus confounders such as baseline disease burden, existing supply, rurality,
poverty, travel time, state program effects, data quality, and volunteer-selection
bias.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    global DATA_DIR, DOCS_DIR, VOLUME_SUMMARY_PATH, POLICY_REPORT_PATH, MARKDOWN_REPORT_PATH
    DATA_DIR = args.data_dir
    DOCS_DIR = args.docs_dir
    VOLUME_SUMMARY_PATH = DATA_DIR / VOLUME_SUMMARY_PATH.name
    POLICY_REPORT_PATH = DATA_DIR / POLICY_REPORT_PATH.name
    MARKDOWN_REPORT_PATH = DOCS_DIR / MARKDOWN_REPORT_PATH.name

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    summary = build_volume_summary(DATA_DIR)
    policy = statistical_policy()
    summary.to_csv(VOLUME_SUMMARY_PATH, index=False)
    POLICY_REPORT_PATH.write_text(json.dumps(policy, indent=2), encoding="utf-8")
    write_markdown(summary, policy, MARKDOWN_REPORT_PATH)

    report = {
        "created_outputs": {
            "volume_summary": str(VOLUME_SUMMARY_PATH.relative_to(ROOT)),
            "policy_report": str(POLICY_REPORT_PATH.relative_to(ROOT)),
            "markdown_report": str(MARKDOWN_REPORT_PATH.relative_to(ROOT)),
        },
        "category_groups": int(summary["category_group"].nunique()) if not summary.empty else 0,
        "category_rows": int(len(summary)),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
