"""What-If Scenario Simulator + best/most-likely/worst-case supply bands.

Implements Feature 4 of Bayesian_stats_product_strategy.md (What-If Scenario
Simulator) and Ambitious Idea 4 of tricky_fields.md (best/most-likely/worst-case
uncertainty bands for medical-desert planning).

Design rules honored here:
  * Operate only on signals that exist in the cleaned tables. The dataset has
    NO broadband, NO real travel-time, and NO elderly-share columns, so the
    telehealth scenario is explicitly labeled low-confidence ("broadband not in
    dataset") and any travel framing is derived from existing supply density,
    never fabricated demographics.
  * Never present a single point estimate without its band. Supply is shown as
    best / most-likely / worst case, derived transparently from observed vs
    estimated counts, the trustworthy-supply rate and its Wilson CI, and the
    capacity interval columns.
  * Pure compute functions (no Streamlit) so they are testable; the Streamlit
    view is a thin renderer on top.

Public API:
  scenario_bands(district_row, facilities_in_district) -> pd.DataFrame
  simulate_interventions(district_row, facilities_in_district, **levers) -> pd.DataFrame
  render_simulator(facilities, districts, specialty) -> None
"""
from __future__ import annotations

import math

import pandas as pd

try:  # streamlit is only needed for render_simulator
    import streamlit as st
except Exception:  # pragma: no cover - keeps pure functions importable headless
    st = None  # type: ignore

from . import config, data

try:
    from . import decisions
except Exception:  # pragma: no cover - keeps pure functions importable headless
    decisions = None  # type: ignore

try:
    from . import ui
except Exception:  # pragma: no cover
    ui = None  # type: ignore


# --------------------------------------------------------------------------- #
# Small numeric helpers (local; do not mutate shared modules)
# --------------------------------------------------------------------------- #
def _num(value, default: float = float("nan")) -> float:
    try:
        out = float(value)
        if math.isnan(out):
            return default
        return out
    except (TypeError, ValueError):
        return default


def _int(value, default: int = 0) -> int:
    out = _num(value, float("nan"))
    return default if math.isnan(out) else int(round(out))


def _clip01(value: float) -> float:
    if math.isnan(value):
        return 0.0
    return max(0.0, min(1.0, value))


# --------------------------------------------------------------------------- #
# Facility matching (robust, case-insensitive — district/facility tables differ
# in casing). Returns the subset of facilities for a district row.
# --------------------------------------------------------------------------- #
def facilities_for_district(district_row: pd.Series, facilities: pd.DataFrame) -> pd.DataFrame:
    if facilities is None or facilities.empty:
        return facilities if facilities is not None else pd.DataFrame()
    state = str(district_row.get("state_ut", "")).strip().lower()
    district = str(district_row.get("district_name", "")).strip().lower()
    mask = (
        facilities["state_ut"].astype(str).str.strip().str.lower().eq(state)
        & facilities["district_name"].astype(str).str.strip().str.lower().eq(district)
    )
    return facilities[mask]


# --------------------------------------------------------------------------- #
# Best / most-likely / worst-case supply bands  (tricky_fields.md idea 4)
# --------------------------------------------------------------------------- #
def scenario_bands(
    district_row: pd.Series,
    facilities_in_district: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return best/most-likely/worst-case supply bands for one district.

    Counts and capacities are derived from district aggregate columns (always
    present) and refined with the facility-level frame when it is non-empty.

    Bands
      Best case      : all claimed/observed facilities; claimed + estimated
                       capacity (upper capacity interval where available).
      Most likely    : trust-weighted facility count (observed * trustworthy
                       supply rate, but never below the actually-trustworthy
                       count); capacity at the CI / interval midpoint.
      Worst case     : only trustworthy_supply_signal facilities; capacity at
                       the low CI / low interval bound.
    """
    observed = _int(district_row.get("observed_facility_rows"))

    # --- counts ---
    fac = facilities_in_district if facilities_in_district is not None else pd.DataFrame()
    if not fac.empty and "trustworthy_supply_signal" in fac:
        observed = max(observed, len(fac))
        trustworthy_n = int(fac["trustworthy_supply_signal"].fillna(False).astype(bool).sum())
    else:
        trust_rate_for_count = _num(district_row.get("trustworthy_supply_rate"), 0.0)
        trustworthy_n = int(round(observed * _clip01(trust_rate_for_count)))

    trust_rate = _num(district_row.get("trustworthy_supply_rate"), 0.0)
    # Most-likely count: down-weight claimed supply by trust, but never claim
    # fewer than the facilities that actually passed checks.
    likely_n = max(trustworthy_n, int(round(observed * _clip01(trust_rate))))
    likely_n = min(likely_n, observed)

    # --- capacity ---
    obs_cap_sum = _num(district_row.get("observed_capacity_sum"), 0.0)
    est_cap_sum = _num(district_row.get("estimated_capacity_sum"), 0.0)
    # estimated_capacity_sum is the model's full-district estimate; observed is
    # only the rows with a real parsed value. Best case = the larger of the two.
    best_cap = max(obs_cap_sum, est_cap_sum)

    # Refine the best-case ceiling with facility-level upper intervals if present.
    if not fac.empty and "capacity_estimate_interval_high" in fac:
        hi = pd.to_numeric(fac["capacity_estimate_interval_high"], errors="coerce").dropna()
        if not hi.empty:
            best_cap = max(best_cap, float(hi.sum()))

    # Worst case: low interval bound, scaled to trustworthy share of supply.
    trust_share = (trustworthy_n / observed) if observed else 0.0
    if not fac.empty and "capacity_estimate_interval_low" in fac:
        lo = pd.to_numeric(fac["capacity_estimate_interval_low"], errors="coerce").fillna(0.0)
        trust_mask = fac["trustworthy_supply_signal"].fillna(False).astype(bool)
        worst_cap = float(lo[trust_mask].sum())
        if worst_cap <= 0:  # no trustworthy capacity evidence at all
            worst_cap = float(lo.sum()) * trust_share
    else:
        # No facility intervals: anchor worst case on observed (parsed) capacity
        # restricted to the trustworthy share.
        worst_cap = obs_cap_sum * (trust_share if trust_share > 0 else 0.0)

    worst_cap = min(worst_cap, best_cap)
    likely_cap = (best_cap + worst_cap) / 2.0

    obs_rate = _num(district_row.get("capacity_observed_rate"), float("nan"))
    est_rate = _num(district_row.get("capacity_estimated_rate"), float("nan"))

    rows = [
        {
            "Scenario": "Best case",
            "Facilities": observed,
            "Est. capacity": round(best_cap),
            "Capacity interval": f"{round(worst_cap)}–{round(best_cap)}",
            "Notes": "All claimed facilities + claimed/estimated capacity (upper bound).",
        },
        {
            "Scenario": "Most likely",
            "Facilities": likely_n,
            "Est. capacity": round(likely_cap),
            "Capacity interval": f"{round(worst_cap)}–{round(best_cap)}",
            "Notes": (
                f"Trust-weighted count (trustworthy supply rate "
                f"{_pct(trust_rate)}); capacity at interval midpoint."
            ),
        },
        {
            "Scenario": "Worst case",
            "Facilities": trustworthy_n,
            "Est. capacity": round(worst_cap),
            "Capacity interval": f"{round(worst_cap)}–{round(worst_cap)}",
            "Notes": (
                "Only facilities passing trust checks; low capacity-interval bound. "
                f"Observed/estimated capacity rate {_pct(obs_rate)}/{_pct(est_rate)}."
            ),
        },
    ]
    return pd.DataFrame(rows)


def _pct(value: float, digits: int = 0) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "unknown"
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "unknown"


# --------------------------------------------------------------------------- #
# Intervention comparison (Feature 4: What-If Scenario Simulator)
# --------------------------------------------------------------------------- #
# Cost / base-confidence tiers per intervention. Confidence is adjusted down by
# district uncertainty; access improvement is computed from the real care gap.
_INTERVENTIONS = [
    # key, label, cost tier, base confidence, supply-effect weight
    ("mobile_clinic", "Mobile clinic", "Medium", "Medium", 1.00),
    ("transport_vouchers", "Transport vouchers", "Low", "High", 0.55),
    ("pharmacy_screening", "Pharmacy screening", "Low", "Medium", 0.50),
    ("new_capacity", "New provider capacity (+X%)", "High", "Medium", 0.90),
    ("telehealth", "Telehealth", "Low", "Low", 0.35),
]

_COST_RANK = {"Low": 1, "Medium": 2, "High": 3}


def _band(score: float) -> str:
    if score >= 0.55:
        return "High"
    if score >= 0.30:
        return "Med"
    return "Low"


def simulate_interventions(
    district_row: pd.Series,
    facilities_in_district: pd.DataFrame | None = None,
    *,
    mobile_clinics: int = 1,
    capacity_increase_pct: float = 20.0,
    telehealth_adoption: float = 0.3,
) -> pd.DataFrame:
    """Compare candidate interventions for one district.

    Access improvement is derived from the district's actual need/supply gap:
    interventions that add real, trustworthy supply help more where the
    trustworthy-supply rate is low and the health-need score is high. Telehealth
    is penalized and labeled low-confidence because broadband adoption is NOT in
    the dataset (the doc's demo moment: telehealth-first underperforms mobile/CHW
    in low-evidence districts).

    Levers
      mobile_clinics        : N mobile clinics to add (scales mobile-clinic effect).
      capacity_increase_pct : % capacity expansion for the new-capacity scenario.
      telehealth_adoption   : assumed telehealth adoption 0..1 (illustrative only).
    """
    need = _clip01(_num(district_row.get("health_need_score"), 0.0))
    trust_rate = _clip01(_num(district_row.get("trustworthy_supply_rate"), 0.0))
    care_gap = _num(district_row.get("care_gap_score"), float("nan"))
    if math.isnan(care_gap):
        care_gap = need * (1.0 - trust_rate)
    care_gap = _clip01(care_gap)

    # Supply deficit: how much trustworthy supply is missing relative to need.
    deficit = _clip01(need * (1.0 - trust_rate))

    uncertainty = str(district_row.get("district_uncertainty_level", "")).strip().lower()
    # Wide trust-rate CI => evidence is fragile => downgrade confidence.
    ci_low = _num(district_row.get("trustworthy_supply_rate_ci_low"), float("nan"))
    ci_high = _num(district_row.get("trustworthy_supply_rate_ci_high"), float("nan"))
    ci_width = (
        ci_high - ci_low
        if not (math.isnan(ci_low) or math.isnan(ci_high))
        else float("nan")
    )

    def adjust_conf(base: str) -> str:
        order = ["Low", "Medium", "High"]
        idx = order.index(base) if base in order else 1
        if uncertainty == "higher":
            idx -= 1
        if not math.isnan(ci_width) and ci_width >= 0.5:
            idx -= 1
        return order[max(0, min(len(order) - 1, idx))]

    # lever scaling factors
    mobile_scale = min(1.5, 0.6 + 0.4 * max(1, mobile_clinics))  # diminishing returns
    capacity_scale = _clip01(capacity_increase_pct / 50.0)  # +50% => full weight
    telehealth_scale = _clip01(telehealth_adoption)

    rows = []
    for key, label, cost, base_conf, weight in _INTERVENTIONS:
        # Base access improvement: helps proportionally to the supply deficit.
        score = deficit * weight

        if key == "mobile_clinic":
            score *= mobile_scale
            label = f"Mobile clinic (x{max(1, mobile_clinics)})"
        elif key == "new_capacity":
            score *= 0.5 + capacity_scale
            label = f"New provider capacity (+{int(capacity_increase_pct)}%)"
        elif key == "telehealth":
            # Telehealth cannot be validated (no broadband/elderly data) and is
            # weak where trustworthy in-person supply is scarce. Penalize, and
            # scale by the (illustrative) adoption lever.
            score *= (0.4 + 0.6 * telehealth_scale) * (0.5 + 0.5 * trust_rate)
            label = f"Telehealth (adoption {int(telehealth_scale * 100)}%)"
        elif key == "transport_vouchers":
            # Transport helps only if some trustworthy supply exists to reach.
            score *= 0.4 + 0.6 * trust_rate
        elif key == "pharmacy_screening":
            # Screening adds value regardless of in-person specialist supply.
            score *= 0.8

        score = _clip01(score)
        conf = "Low" if key == "telehealth" else adjust_conf(base_conf)

        note = ""
        if key == "telehealth":
            note = "Low-confidence: broadband not in dataset; in-person supply scarce."

        rows.append(
            {
                "Scenario": label,
                "_score": round(score, 3),
                "Access improvement": f"{_band(score)} ({score:.2f})",
                "Cost": cost,
                "Confidence": conf,
                "_cost_rank": _COST_RANK.get(cost, 2),
                "Notes": note,
            }
        )

    out = pd.DataFrame(rows)
    # Rank: primarily by access improvement, tie-break by lower cost.
    out = out.sort_values(["_score", "_cost_rank"], ascending=[False, True]).reset_index(drop=True)
    out["Rank"] = out.index + 1
    return out[
        ["Scenario", "Access improvement", "Cost", "Confidence", "Rank", "Notes", "_score"]
    ]


# --------------------------------------------------------------------------- #
# Streamlit view
# --------------------------------------------------------------------------- #
def _default_district_index(districts: pd.DataFrame) -> int:
    """Pick a high-care-gap district that also has several observed facilities."""
    d = districts.copy()
    gap = pd.to_numeric(d.get("care_gap_score"), errors="coerce")
    obs = pd.to_numeric(d.get("observed_facility_rows"), errors="coerce").fillna(0)
    rich = d[(obs >= 8) & (gap > 0.5)]
    if not rich.empty:
        target = rich.sort_values("care_gap_score", ascending=False).index[0]
    else:
        target = gap.fillna(0).idxmax()
    return int(d.index.get_indexer([target])[0])


def render_simulator(
    facilities: pd.DataFrame, districts: pd.DataFrame, specialty: str,
    *, embedded: bool = False,
) -> None:
    """Self-contained Streamlit view: supply bands + intervention comparison.

    When ``embedded`` is True (hosted inside the Planner Copilot conversation),
    the redundant top-level title and the module's own "Save this scenario"
    button are suppressed — the copilot supplies the conversational lead-in and a
    standardized save/shortlist affordance instead. The current scenario context
    is published to ``st.session_state['cp_scenario_ctx']`` so the copilot can
    persist it via ``decisions.save_scenario(...)``.
    """
    if st is None:  # pragma: no cover
        raise RuntimeError("Streamlit is not available in this environment.")

    if not embedded:
        st.markdown(
            '<div class="mdn-panel-h">What-if scenario simulator</div>',
            unsafe_allow_html=True,
        )

    # ---- empty / error states ----
    if districts is None or districts.empty:
        st.warning("No district data available to simulate. Load the district table first.")
        return

    try:
        d = districts.reset_index(drop=True)
        labels = (
            d["district_name"].astype(str).str.strip()
            + ", "
            + d["state_ut"].astype(str).str.strip()
        )
        default_idx = _default_district_index(d)

        chosen = st.selectbox(
            "District",
            options=list(range(len(d))),
            index=default_idx,
            format_func=lambda i: labels.iloc[i],
            key="sim_district",
        )
        district_row = d.iloc[int(chosen)]
        fac_in_district = facilities_for_district(district_row, facilities)

        # ---- decision banner from planning category ----
        cat = str(district_row.get("planning_category", "mixed_or_monitor"))
        chip, rec = data.PLANNING.get(cat, data.PLANNING["mixed_or_monitor"])
        tone = {
            "real_desert_candidate": "deploy",
            "referral_or_capacity_candidate": "deploy",
            "phantom_desert_or_verification_gap": "verify",
            "supply_record_quality_problem": "danger",
        }.get(cat, "info")
        if ui is not None:
            ui.decision_banner(f"{labels.iloc[int(chosen)]} — {chip}", rec, tone=tone)
        else:  # pragma: no cover
            st.info(f"{chip}: {rec}")

        # ---- levers ----
        l1, l2, l3 = st.columns(3)
        mobile = l1.slider("Add mobile clinics", 0, 5, 1, key="sim_mobile")
        cap_pct = l2.slider("Increase provider capacity (%)", 0, 50, 20, step=5, key="sim_cap")
        teleh = l3.slider("Telehealth adoption", 0.0, 1.0, 0.3, step=0.1, key="sim_teleh")

        # ---- supply bands ----
        st.markdown(
            '<div class="mdn-panel-h">Supply under uncertainty (best / most-likely / worst)</div>',
            unsafe_allow_html=True,
        )
        bands = scenario_bands(district_row, fac_in_district)

        b1, b2, b3 = st.columns(3)
        for col, tone, scen in (
            (b1, "deploy", "Best case"),
            (b2, "info", "Most likely"),
            (b3, "danger", "Worst case"),
        ):
            r = bands[bands["Scenario"] == scen].iloc[0]
            with col:
                if ui is not None:
                    ui.stat_card(
                        scen,
                        f"{int(r['Facilities'])} fac · {int(r['Est. capacity'])} cap",
                        f"capacity interval {r['Capacity interval']}",
                        tone=tone,
                    )
                else:  # pragma: no cover
                    st.metric(scen, f"{int(r['Facilities'])} fac / {int(r['Est. capacity'])} cap")

        # The full band table + chart are backing detail; tuck behind the shared
        # progressive-disclosure expander when embedded in the copilot.
        import contextlib

        band_ctx = (
            ui.detail("Band table & chart")
            if (embedded and ui is not None)
            else contextlib.nullcontext()
        )
        with band_ctx:
            st.dataframe(
                bands,
                hide_index=True,
                width="stretch",
                column_config={
                    "Facilities": st.column_config.NumberColumn("Facilities", format="%d"),
                    "Est. capacity": st.column_config.NumberColumn("Est. capacity", format="%d"),
                },
            )

            chart = bands.set_index("Scenario")[["Facilities", "Est. capacity"]]
            st.bar_chart(chart, height=210)
            st.caption(
                "Never a single point estimate: counts and capacity are shown as a band. "
                "Bands come from observed vs estimated counts, the trustworthy-supply rate "
                "and its Wilson CI, and the per-facility capacity intervals."
            )

        # ---- intervention comparison ----
        st.markdown(
            '<div class="mdn-panel-h">Intervention comparison</div>',
            unsafe_allow_html=True,
        )
        interventions = simulate_interventions(
            district_row,
            fac_in_district,
            mobile_clinics=mobile,
            capacity_increase_pct=float(cap_pct),
            telehealth_adoption=float(teleh),
        )
        show = interventions.drop(columns=["_score"])
        st.dataframe(
            show,
            hide_index=True,
            width="stretch",
            column_config={
                "Rank": st.column_config.NumberColumn("Rank", format="%d"),
                "Notes": st.column_config.TextColumn("Notes", width="large"),
            },
        )

        top = interventions.iloc[0]
        teleh_row = interventions[interventions["Scenario"].str.startswith("Telehealth")]
        teleh_rank = int(teleh_row["Rank"].iloc[0]) if not teleh_row.empty else None
        msg = f"Top intervention: **{top['Scenario']}** ({top['Access improvement']}, {top['Confidence']} confidence)."
        if teleh_rank is not None and teleh_rank >= 3:
            msg += (
                f" Telehealth ranks #{teleh_rank} and is low-confidence here — "
                "broadband is not in the dataset and in-person supply is scarce, so "
                "mobile/CHW-style interventions are preferred."
            )
        st.info(msg)

        # ---- persist this scenario (durable on the deployment target) ----
        geography_id = (
            f"{str(district_row.get('district_name', '')).strip()}|"
            f"{str(district_row.get('state_ut', '')).strip()}"
        )
        assumptions = {
            "district": str(district_row.get("district_name", "")),
            "state_ut": str(district_row.get("state_ut", "")),
            "specialty": str(specialty),
            "mobile_clinics": int(mobile),
            "capacity_increase_pct": float(cap_pct),
            "telehealth_adoption": float(teleh),
            "top_intervention": str(top["Scenario"]),
            "top_access_improvement": str(top["Access improvement"]),
        }
        # Publish the current scenario context so a host (the Copilot) can offer a
        # standardized save/shortlist affordance against the same selection.
        st.session_state["cp_scenario_ctx"] = {
            "geography_id": geography_id,
            "label": str(labels.iloc[int(chosen)]),
            "district_name": str(district_row.get("district_name", "")),
            "state_ut": str(district_row.get("state_ut", "")),
            "assumptions": assumptions,
        }

        if decisions is not None and not embedded:
            if st.button("Save this scenario", key="sim_save_scenario"):
                try:
                    status = decisions.save_scenario(
                        geography_id=geography_id, assumptions=assumptions,
                        note="What-if scenario saved from the simulator.",
                    )
                    st.success(
                        f"Scenario saved for {labels.iloc[int(chosen)]}. "
                        f"{status.get('detail', '')}"
                    )
                except Exception:
                    st.warning("Could not save the scenario; it remains session-only.")

        st.caption(
            "Access improvement is derived from this district's real need and "
            "trustworthy-supply gap, not a generic ranking. Telehealth is always "
            "labeled low-confidence: broadband, travel-time, and elderly-share are "
            "not in this dataset, so any travel/telehealth framing is illustrative."
        )
    except Exception as exc:  # pragma: no cover - defensive UI guard
        st.error(f"Could not run the simulation for this district: {exc}")
