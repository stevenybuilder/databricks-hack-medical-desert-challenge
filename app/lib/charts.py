"""Tableau-grade Altair charts (dark theme) for the CareGap app.

Grammar-of-graphics replacements for the basic st.dataframe / st.bar_chart pieces:
layered bars with benchmark reference marks, Δ-vs-national coloring, and direct
value labels — the Superstore-style finish. All charts share one dark theme.
"""
from __future__ import annotations
import altair as alt
import pandas as pd

# Palette (matches the app's dark tokens).
INK = "#eaf2ff"
MUTE = "#93a4b8"
GRID = "rgba(148,163,184,.12)"
TEAL = "#2eccc1"
AMBER = "#ffbe48"
RED = "#ff5252"
SLATE = "#64748b"
BLUE = "#66d9ff"

ACTION_COLORS = {
    "Deploy": TEAL, "Verify first": AMBER, "Fix records": RED,
    "Refer": BLUE, "Monitor": SLATE,
}


def _dark(chart: alt.Chart) -> alt.Chart:
    """Apply the shared dark theme to a top-level (already-layered) chart."""
    return (
        chart
        .configure(background="rgba(0,0,0,0)")
        .configure_view(strokeWidth=0, fill="rgba(0,0,0,0)")
        .configure_axis(labelColor="#c9d8ea", titleColor=MUTE, gridColor=GRID,
                        domainColor="rgba(148,163,184,.25)", tickColor="rgba(148,163,184,.25)",
                        labelFontSize=12, titleFontSize=11)
        .configure_legend(labelColor="#c9d8ea", titleColor=MUTE)
    )


def condition_gaps(conds: pd.DataFrame) -> alt.Chart:
    """District medical-condition gaps as horizontal bars with a national reference tick.

    Bar = district value; gray tick = national median (the benchmark); bar color =
    Δ vs national (deeper red = worse). Mirrors a Tableau 'vs benchmark' view.
    """
    d = conds.rename(columns={
        "Condition": "condition", "District %": "district_pct",
        "National %": "national_pct", "Δ vs national": "delta"}).copy()
    order = d["condition"].tolist()  # already severity-sorted

    base = alt.Chart(d).encode(
        y=alt.Y("condition:N", sort=order, title=None,
                axis=alt.Axis(labelLimit=180)))
    bars = base.mark_bar(height=16, cornerRadiusEnd=3).encode(
        x=alt.X("district_pct:Q", title="District %", scale=alt.Scale(domain=[0, 100])),
        color=alt.Color("delta:Q", scale=alt.Scale(scheme="reds", domainMin=0),
                        legend=None),
        tooltip=[alt.Tooltip("condition:N", title="Condition"),
                 alt.Tooltip("district_pct:Q", title="District %", format=".1f"),
                 alt.Tooltip("national_pct:Q", title="National %", format=".1f"),
                 alt.Tooltip("delta:Q", title="Δ vs national", format="+.1f")])
    ref = base.mark_tick(color="#cbd5e1", thickness=2, size=20).encode(
        x="national_pct:Q",
        tooltip=[alt.Tooltip("national_pct:Q", title="National median %", format=".1f")])
    labels = base.mark_text(align="left", dx=4, color=INK, fontSize=11).encode(
        x="district_pct:Q", text=alt.Text("district_pct:Q", format=".0f"))
    return _dark((bars + ref + labels).properties(height=max(150, 26 * len(d))))


def care_gap_contributions(breakdown: pd.DataFrame) -> alt.Chart:
    """The additive care-gap score as horizontal contribution bars (sums to the score)."""
    d = breakdown.rename(columns={"Component": "component", "Contribution": "contribution"}).copy()
    order = d["component"].tolist()
    base = alt.Chart(d).encode(
        y=alt.Y("component:N", sort=order, title=None, axis=alt.Axis(labelLimit=220)))
    bars = base.mark_bar(height=18, cornerRadiusEnd=3).encode(
        x=alt.X("contribution:Q", title="Contribution to care-gap score",
                scale=alt.Scale(domain=[0, 0.6])),
        color=alt.Color("contribution:Q", scale=alt.Scale(scheme="yelloworangered"), legend=None),
        tooltip=[alt.Tooltip("component:N", title="Component"),
                 alt.Tooltip("contribution:Q", title="Contribution", format=".3f")])
    labels = base.mark_text(align="left", dx=4, color=INK, fontSize=11).encode(
        x="contribution:Q", text=alt.Text("contribution:Q", format=".2f"))
    return _dark((bars + labels).properties(height=max(120, 30 * len(d))))


PLANNING_COLORS = {
    "real_desert_candidate": RED,
    "phantom_desert_or_verification_gap": AMBER,
    "supply_record_quality_problem": "#fb923c",
    "referral_or_capacity_candidate": TEAL,
    "mixed_or_monitor": SLATE,
}
PLANNING_LABELS = {
    "real_desert_candidate": "Verifiable desert",
    "phantom_desert_or_verification_gap": "Data-poor / verify",
    "supply_record_quality_problem": "Record-quality problem",
    "referral_or_capacity_candidate": "Has capacity",
    "mixed_or_monitor": "Monitor",
}


def desert_quadrant(districts: pd.DataFrame) -> alt.Chart:
    """Care gap (y) vs confidence (x), so planners separate REAL deserts from DATA-POOR
    regions. Top-right = high gap + well-evidenced (act now); top-left = high gap but
    low confidence (verify first). The core 'how sure are we?' view for Track 2."""
    src = districts[["district_data_quality_score", "care_gap_score",
                     "planning_category", "district_name", "state_ut"]].copy()
    d = pd.DataFrame({
        "confidence": pd.to_numeric(src["district_data_quality_score"], errors="coerce"),
        "gap": pd.to_numeric(src["care_gap_score"], errors="coerce"),
        "Category": src["planning_category"].map(PLANNING_LABELS).fillna("Monitor"),
        "name": src["district_name"].astype(str) + ", " + src["state_ut"].astype(str),
    }).dropna(subset=["confidence", "gap"])
    dom = [PLANNING_LABELS[k] for k in PLANNING_COLORS]
    rng = list(PLANNING_COLORS.values())

    pts = alt.Chart(d).mark_circle(size=46, opacity=0.7).encode(
        x=alt.X("confidence:Q", title="Confidence (district data quality)",
                scale=alt.Scale(domain=[0, 1])),
        y=alt.Y("gap:Q", title="Care-gap score", scale=alt.Scale(domain=[0, 1])),
        color=alt.Color("Category:N", scale=alt.Scale(domain=dom, range=rng),
                        legend=alt.Legend(orient="bottom", title=None, columns=3)),
        tooltip=[alt.Tooltip("name:N", title="District"),
                 alt.Tooltip("gap:Q", title="Care gap", format=".2f"),
                 alt.Tooltip("confidence:Q", title="Confidence", format=".2f"),
                 alt.Tooltip("Category:N", title="Class")])
    vline = alt.Chart(pd.DataFrame({"x": [0.5]})).mark_rule(
        color="#64748b", strokeDash=[4, 4]).encode(x="x:Q")
    hline = alt.Chart(pd.DataFrame({"y": [0.6]})).mark_rule(
        color="#64748b", strokeDash=[4, 4]).encode(y="y:Q")
    return _dark((pts + vline + hline).properties(height=340))


def sparkline(values: list[float], color: str = BLUE) -> alt.Chart:
    """Tiny inline trend line for KPI cards / small multiples."""
    d = pd.DataFrame({"i": list(range(len(values))), "v": values})
    return _dark(alt.Chart(d).mark_line(color=color, strokeWidth=2).encode(
        x=alt.X("i:Q", axis=None), y=alt.Y("v:Q", axis=None)).properties(height=44))


def trust_distribution_bar(high: int, medium: int, verify: int) -> alt.Chart:
    """A single horizontal stacked bar showing the High/Medium/Verify trust split.

    Replaces three separate st.metric numbers with one legible distribution bar:
    each segment is sized by its share of the total, colored TEAL/AMBER/SLATE, with a
    bottom legend. Compact (height ~60). Degrades to an empty band on zero/NaN input.
    """
    def _safe(x: int) -> float:
        v = pd.to_numeric(x, errors="coerce")
        return 0.0 if pd.isna(v) or v < 0 else float(v)

    h, m, v = _safe(high), _safe(medium), _safe(verify)
    total = h + m + v
    bands = ["High", "Medium", "Verify"]
    colors = {"High": TEAL, "Medium": AMBER, "Verify": SLATE}
    if total <= 0:
        d = pd.DataFrame({"band": bands, "count": [0.0, 0.0, 0.0],
                          "share": [0.0, 0.0, 0.0], "row": ["Trust"] * 3})
    else:
        counts = [h, m, v]
        d = pd.DataFrame({"band": bands, "count": counts,
                          "share": [c / total for c in counts], "row": ["Trust"] * 3})

    chart = alt.Chart(d).mark_bar(height=22, cornerRadius=2).encode(
        x=alt.X("share:Q", title=None, stack="normalize",
                axis=alt.Axis(format="%", values=[0, 0.25, 0.5, 0.75, 1.0]),
                scale=alt.Scale(domain=[0, 1])),
        y=alt.Y("row:N", title=None, axis=None),
        color=alt.Color("band:N",
                        scale=alt.Scale(domain=bands, range=[colors[b] for b in bands]),
                        sort=bands,
                        legend=alt.Legend(orient="bottom", title=None, direction="horizontal")),
        order=alt.Order("band:N", sort="ascending"),
        tooltip=[alt.Tooltip("band:N", title="Trust"),
                 alt.Tooltip("count:Q", title="Facilities", format=".0f"),
                 alt.Tooltip("share:Q", title="Share", format=".1%")],
    ).properties(height=60)
    return _dark(chart)


def small_multiples_deserts(districts: pd.DataFrame, top_conditions_fn,
                            n: int = 6) -> alt.Chart:
    """Small-multiples (faceted) view of the top `n` districts by care-gap score.

    For each of the worst districts, a tiny horizontal bar chart of its top ~4
    medical-condition gaps, colored by Δ vs national (reds). `top_conditions_fn` is a
    callable (row, districts) -> DataFrame with columns "Condition", "District %",
    "Δ vs national". A "top deserts at a glance" panel. Degrades to an empty chart.
    """
    empty = _dark(alt.Chart(pd.DataFrame({"x": [0]})).mark_point(opacity=0).encode(
        x=alt.X("x:Q", axis=None)).properties(height=80))
    if districts is None or len(districts) == 0:
        return empty

    src = districts.copy()
    src["_gap"] = pd.to_numeric(src.get("care_gap_score"), errors="coerce")
    src = src.dropna(subset=["_gap"]).sort_values("_gap", ascending=False).head(int(n))
    if src.empty:
        return empty

    rows = []
    for _, row in src.iterrows():
        name = f"{row.get('district_name', '—')}, {row.get('state_ut', '')}".strip(", ")
        try:
            conds = top_conditions_fn(row, districts)
        except Exception:
            conds = None
        if conds is None or len(conds) == 0:
            continue
        top4 = conds.head(4)
        for _, c in top4.iterrows():
            pct = pd.to_numeric(c.get("District %"), errors="coerce")
            delta = pd.to_numeric(c.get("Δ vs national"), errors="coerce")
            rows.append({
                "district": name,
                "condition": str(c.get("Condition", "—")),
                "district_pct": None if pd.isna(pct) else float(pct),
                "delta": 0.0 if pd.isna(delta) else float(delta),
            })
    if not rows:
        return empty

    d = pd.DataFrame(rows)[["district", "condition", "district_pct", "delta"]]

    bars = alt.Chart(d).mark_bar(height=12, cornerRadiusEnd=2).encode(
        x=alt.X("district_pct:Q", title=None, scale=alt.Scale(domain=[0, 100]),
                axis=alt.Axis(labelFontSize=9)),
        y=alt.Y("condition:N", title=None, sort="-x",
                axis=alt.Axis(labelLimit=120, labelFontSize=9)),
        color=alt.Color("delta:Q", scale=alt.Scale(scheme="reds", domainMin=0),
                        legend=alt.Legend(orient="bottom", title="Δ vs national")),
        tooltip=[alt.Tooltip("district:N", title="District"),
                 alt.Tooltip("condition:N", title="Condition"),
                 alt.Tooltip("district_pct:Q", title="District %", format=".1f"),
                 alt.Tooltip("delta:Q", title="Δ vs national", format="+.1f")],
    ).properties(width=180, height=90)

    faceted = bars.facet(
        facet=alt.Facet("district:N", title=None, header=alt.Header(
            labelColor="#c9d8ea", labelFontSize=11, labelFontWeight="bold")),
        columns=3,
    ).resolve_scale(y="independent")
    return _dark(faceted)


def kpi_sparkline(values: list[float], label: str, value: str,
                  color: str = BLUE) -> alt.Chart:
    """Sparkline with the latest point emphasized, plus an inline label/value caption.

    Enhancement of `sparkline` for KPI cards: a slim trend line with a dot on the most
    recent value and the headline `value`/`label` printed at top-left. Degrades to a
    minimal valid chart when given no data.
    """
    clean = []
    for x in (values or []):
        v = pd.to_numeric(x, errors="coerce")
        if not pd.isna(v):
            clean.append(float(v))
    if not clean:
        d = pd.DataFrame({"i": [0], "v": [0.0]})
        return _dark(alt.Chart(d).mark_text(
            text=f"{value}  {label}".strip(), color=INK, align="left", dx=2,
            fontSize=12).encode().properties(height=48))

    d = pd.DataFrame({"i": list(range(len(clean))), "v": clean})
    last = d.iloc[[-1]]

    line = alt.Chart(d).mark_line(color=color, strokeWidth=2).encode(
        x=alt.X("i:Q", axis=None), y=alt.Y("v:Q", axis=None),
        tooltip=[alt.Tooltip("v:Q", title=label, format=".2f")])
    dot = alt.Chart(last).mark_circle(color=color, size=46).encode(
        x="i:Q", y="v:Q",
        tooltip=[alt.Tooltip("v:Q", title=f"{label} (latest)", format=".2f")])
    caption = alt.Chart(pd.DataFrame({"t": [f"{value}  {label}".strip()]})).mark_text(
        align="left", baseline="top", color=INK, fontSize=12, fontWeight="bold",
        dx=2, dy=2).encode(
        x=alt.value(0), y=alt.value(0), text="t:N")
    return _dark((line + dot + caption).properties(height=56))


def action_mix(mix: pd.DataFrame) -> alt.Chart:
    """Action distribution as a sorted horizontal bar with semantic per-action color."""
    d = mix.copy()
    d.columns = ["action", "districts"]
    domain = list(ACTION_COLORS.keys())
    rng = [ACTION_COLORS[a] for a in domain]
    chart = alt.Chart(d).mark_bar(height=18, cornerRadiusEnd=3).encode(
        x=alt.X("districts:Q", title="Districts"),
        y=alt.Y("action:N", sort="-x", title=None),
        color=alt.Color("action:N", scale=alt.Scale(domain=domain, range=rng), legend=None),
        tooltip=[alt.Tooltip("action:N", title="Action"),
                 alt.Tooltip("districts:Q", title="Districts")],
    ).properties(height=170)
    return _dark(chart)
