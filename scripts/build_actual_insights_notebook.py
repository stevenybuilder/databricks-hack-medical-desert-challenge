#!/usr/bin/env python3
"""Create actual district/facility insight visuals and notebook."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "output" / "data"
PLOT_DIR = ROOT / "output" / "plots" / "actual_insights"
NOTEBOOK_PATH = ROOT / "output" / "jupyter-notebook" / "actual_facility_district_insights.ipynb"


def md(text: str) -> dict[str, Any]:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip() + "\n"}


def code(text: str) -> dict[str, Any]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text.strip() + "\n",
    }


def save_bar(df: pd.DataFrame, x: str, y: str, title: str, path: Path, xlabel: str = "") -> None:
    plt.figure(figsize=(11, 6.5))
    sns.barplot(data=df, x=x, y=y, color="#4c78a8")
    plt.xlabel(xlabel or x)
    plt.ylabel("")
    plt.title(title)
    plt.tight_layout()
    plt.savefig(path, dpi=170)
    plt.close()


def build_plots(district: pd.DataFrame, facility: pd.DataFrame) -> dict[str, str]:
    sns.set_theme(style="whitegrid", context="notebook")
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    plots: dict[str, str] = {}

    district = district.copy()
    district["region_label"] = district["state_ut"].astype(str).str.strip() + " - " + district["district_name"].astype(str).str.strip()

    top_care_gap = district.sort_values("care_gap_score", ascending=False).head(20)
    path = PLOT_DIR / "top_care_gaps.png"
    save_bar(top_care_gap, "care_gap_score", "region_label", "Worst District Care Gap Candidates", path, "Care gap score")
    plots["top_care_gaps"] = str(path.relative_to(ROOT))

    top_deserts = district.sort_values("district_medical_desert_priority_score", ascending=False).head(20)
    path = PLOT_DIR / "top_medical_desert_candidates.png"
    save_bar(
        top_deserts,
        "district_medical_desert_priority_score",
        "region_label",
        "Medical Desert Candidates: High Need + Low Observed Trustworthy Supply",
        path,
        "Medical desert priority score",
    )
    plots["top_medical_deserts"] = str(path.relative_to(ROOT))

    least_trust = district.sort_values("trust_gap_score", ascending=False).head(20)
    path = PLOT_DIR / "least_trustworthy_regions.png"
    save_bar(least_trust, "trust_gap_score", "region_label", "Least Trustworthy District Records", path, "Trust gap score")
    plots["least_trustworthy"] = str(path.relative_to(ROOT))

    best_care = district.sort_values("best_care_signal_score", ascending=False).head(20)
    path = PLOT_DIR / "best_care_signal_regions.png"
    save_bar(best_care, "best_care_signal_score", "region_label", "Best Care Signal Districts", path, "Best care signal score")
    plots["best_care"] = str(path.relative_to(ROOT))

    path = PLOT_DIR / "planning_category_counts.png"
    counts = district["planning_category"].value_counts().rename_axis("planning_category").reset_index(name="districts")
    plt.figure(figsize=(10, 5.5))
    sns.barplot(data=counts, x="districts", y="planning_category", color="#59a14f")
    plt.xlabel("Districts")
    plt.ylabel("")
    plt.title("Decision Categories From District Evidence")
    plt.tight_layout()
    plt.savefig(path, dpi=170)
    plt.close()
    plots["planning_categories"] = str(path.relative_to(ROOT))

    scatter = district.dropna(subset=["observed_facility_rows", "health_need_score", "trustworthy_supply_rate"]).copy()
    path = PLOT_DIR / "need_vs_trustworthy_supply.png"
    plt.figure(figsize=(10, 7))
    sns.scatterplot(
        data=scatter,
        x="observed_facility_rows",
        y="health_need_score",
        hue="planning_category",
        size="trustworthy_supply_rate",
        sizes=(20, 220),
        alpha=0.78,
    )
    plt.xscale("log")
    plt.xlabel("Observed FDR facility rows in district (log)")
    plt.ylabel("NFHS health need score")
    plt.title("Need vs Observed Facility Supply, Colored by Recommendation Category")
    plt.tight_layout()
    plt.savefig(path, dpi=170)
    plt.close()
    plots["need_vs_supply"] = str(path.relative_to(ROOT))

    heat_cols = [
        "maternity_signal_rate",
        "emergency_signal_rate",
        "diagnostic_signal_rate",
        "ncd_signal_rate",
        "trustworthy_supply_rate",
    ]
    heat = district.sort_values("care_gap_score", ascending=False).head(30).set_index("region_label")[heat_cols]
    path = PLOT_DIR / "care_signal_heatmap_top_gaps.png"
    plt.figure(figsize=(10, 10))
    sns.heatmap(heat, cmap="viridis", vmin=0, vmax=1, cbar_kws={"label": "Share of district facility rows"})
    plt.xlabel("")
    plt.ylabel("")
    plt.title("Claimed Care Signals in Top Gap Districts")
    plt.tight_layout()
    plt.savefig(path, dpi=170)
    plt.close()
    plots["care_signal_heatmap"] = str(path.relative_to(ROOT))

    if {"facility_longitude", "facility_latitude", "trustworthy_supply_signal"}.issubset(facility.columns):
        sample = facility.dropna(subset=["facility_longitude", "facility_latitude"]).copy()
        sample = sample[sample["facility_latitude"].between(4, 40) & sample["facility_longitude"].between(65, 100)]
        sample = sample.sample(min(len(sample), 8000), random_state=42)
        path = PLOT_DIR / "facility_trustworthy_supply_map_scatter.png"
        plt.figure(figsize=(8, 8))
        sns.scatterplot(
            data=sample,
            x="facility_longitude",
            y="facility_latitude",
            hue="trustworthy_supply_signal",
            s=12,
            linewidth=0,
            alpha=0.65,
        )
        plt.xlabel("Longitude")
        plt.ylabel("Latitude")
        plt.title("Facility Evidence Points: Trustworthy Supply Signal vs Unverified")
        plt.tight_layout()
        plt.savefig(path, dpi=170)
        plt.close()
        plots["facility_trust_scatter"] = str(path.relative_to(ROOT))

    return plots


def make_rankings(district: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    cols = [
        "state_ut",
        "district_name",
        "planning_category",
        "observed_facility_rows",
        "trustworthy_supply_rows",
        "trustworthy_supply_rate",
        "health_need_score",
        "care_gap_score",
        "district_medical_desert_priority_score",
        "trust_gap_score",
        "best_care_signal_score",
        "district_data_quality_score",
        "sample_facility_names",
    ]
    return {
        "top_care_gaps": district.sort_values("care_gap_score", ascending=False).head(15)[cols].to_dict("records"),
        "top_medical_deserts": district.sort_values("district_medical_desert_priority_score", ascending=False).head(15)[cols].to_dict("records"),
        "least_trustworthy": district.sort_values("trust_gap_score", ascending=False).head(15)[cols].to_dict("records"),
        "best_care_signal": district.sort_values("best_care_signal_score", ascending=False).head(15)[cols].to_dict("records"),
    }


def write_notebook(plots: dict[str, str]) -> None:
    cells = [
        md(
            """
# Actual Facility and District Insights

This notebook focuses on planning findings from the cleaned district dataset: medical deserts, care gaps, trust gaps, and best-care signals. The earlier cleaning notebook explains metadata quality; this one uses the cleaned fields to answer where to act.
"""
        ),
        md(
            """
## What Counts as Ground Truth?

- NFHS district health indicators are treated as the most reliable district-level need signal in this dataset.
- India Post PIN-to-district mapping is treated as the geographic bridge, but it still has ambiguity and naming drift.
- Facility rows are not ground truth. They are FDR web-extracted claims with source text and URLs. They become an observed supply signal only after join, geography, source, and evidence-quality checks.
- The “medical desert” labels are triage categories, not final policy truth. They should drive verification, re-survey, referral planning, or deployment decisions.
"""
        ),
        code(
            """
from pathlib import Path
import json
import pandas as pd

ROOT = Path.cwd()
DATA_DIR = ROOT / "output" / "data"
district = pd.read_csv(DATA_DIR / "district_health_facility_cleaned.csv")
facility = pd.read_csv(DATA_DIR / "facility_health_cleaned.csv", low_memory=False)
summary = json.loads((DATA_DIR / "actual_insights_summary.json").read_text())
district.shape, facility.shape
"""
        ),
        md(
            """
## Decision Categories

These categories mirror the planning matrix:

- `real_desert_candidate`: high need, low trustworthy observed supply.
- `phantom_desert_or_verification_gap`: facilities exist, but trust/evidence is weak.
- `supply_record_quality_problem`: supply exists but records are contradicted, geo-invalid, or suspicious.
- `referral_or_capacity_candidate`: lower need, better trust, and observed supply that may support referrals while gaps are fixed.
- `mixed_or_monitor`: not cleanly classified.
"""
        ),
        code('district["planning_category"].value_counts().to_frame("districts")'),
        md(f"![Planning categories](../../{plots['planning_categories']})"),
        md("## Medical Deserts and Worst Care Gaps"),
        md(f"![Top care gaps](../../{plots['top_care_gaps']})"),
        md(f"![Medical desert candidates](../../{plots['top_medical_deserts']})"),
        code(
            """
cols = [
    "state_ut", "district_name", "planning_category", "observed_facility_rows",
    "trustworthy_supply_rows", "health_need_score", "care_gap_score",
    "district_medical_desert_priority_score", "sample_facility_names"
]
district.sort_values("care_gap_score", ascending=False)[cols].head(20)
"""
        ),
        md("## Least Trustworthy Regions"),
        md(f"![Least trustworthy](../../{plots['least_trustworthy']})"),
        code(
            """
cols = [
    "state_ut", "district_name", "planning_category", "observed_facility_rows",
    "trustworthy_supply_rate", "needs_human_review_rate",
    "contradicted_or_geo_invalid_rate", "trust_gap_score",
    "predominant_join_uncertainty"
]
district.sort_values("trust_gap_score", ascending=False)[cols].head(20)
"""
        ),
        md("## Best Care Signals"),
        md(f"![Best care signals](../../{plots['best_care']})"),
        code(
            """
cols = [
    "state_ut", "district_name", "observed_facility_rows",
    "trustworthy_supply_rows", "health_need_score",
    "district_data_quality_score", "best_care_signal_score",
    "sample_facility_names"
]
district.sort_values("best_care_signal_score", ascending=False)[cols].head(20)
"""
        ),
        md("## Need vs Supply"),
        md(f"![Need vs supply](../../{plots['need_vs_supply']})"),
        md("## Claimed Care Signals in Top Gap Districts"),
        md(f"![Care signal heatmap](../../{plots['care_signal_heatmap']})"),
        code(
            """
care_cols = [
    "state_ut", "district_name", "care_gap_score",
    "maternity_signal_rate", "emergency_signal_rate",
    "diagnostic_signal_rate", "ncd_signal_rate", "trustworthy_supply_rate"
]
district.sort_values("care_gap_score", ascending=False)[care_cols].head(30)
"""
        ),
    ]
    if "facility_trust_scatter" in plots:
        cells.extend(
            [
                md("## Facility Evidence Scatter"),
                md(f"![Facility trust scatter](../../{plots['facility_trust_scatter']})"),
            ]
        )
    cells.extend(
        [
            md(
                """
## Practical Interpretation

The highest-scoring “real desert” candidates should not immediately become capital build decisions. Use the category to choose the next action:

- Real desert candidate: verify with local knowledge, then plan mobile unit or permanent capacity.
- Phantom desert or verification gap: send a verification/re-survey team first.
- Supply record quality problem: fix records and geocoding before supply planning.
- Referral or capacity candidate: consider interim routing or referral networks while high-gap districts are reviewed.
"""
            ),
            code("pd.DataFrame(summary['rankings']['top_care_gaps']).head(15)"),
        ]
    )

    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    NOTEBOOK_PATH.write_text(json.dumps(notebook, indent=2), encoding="utf-8")


def main() -> None:
    district = pd.read_csv(DATA_DIR / "district_health_facility_cleaned.csv")
    facility = pd.read_csv(DATA_DIR / "facility_health_cleaned.csv", low_memory=False)
    plots = build_plots(district, facility)
    rankings = make_rankings(district)
    summary = {
        "ground_truth": {
            "need": "NFHS district health indicators are used as the strongest available ground truth for need.",
            "geography": "India Post PIN-to-district mappings are used as a geographic bridge with ambiguity retained.",
            "supply": "FDR facility rows are observed web-extracted supply claims, not ground truth.",
        },
        "planning_category_counts": district["planning_category"].value_counts().to_dict(),
        "rankings": rankings,
        "plots": plots,
    }
    (DATA_DIR / "actual_insights_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_notebook(plots)
    print(f"wrote {NOTEBOOK_PATH}")


if __name__ == "__main__":
    main()
