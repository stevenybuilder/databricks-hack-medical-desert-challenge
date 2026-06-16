"""Bayesian record-validity posterior, conformal calibration, and a transparent
additive trust decomposition for facility records.

WHAT THIS IS (and is NOT)
-------------------------
This module computes a **proxy** posterior probability that a facility record is
"valid enough to plan on", P(record valid | evidence), using a transparent,
auditable Bayesian log-odds update over the cleaned-table evidence signals
(geo plausibility, district/PIN join confidence, source URL presence, contact
evidence, recency, contradiction flags, extreme-outlier flags, and semantic
completeness).

It is explicitly NOT a measured-accuracy claim. There are no human-verified gold
labels in this dataset (see docs/STATISTICAL_DECISION_FRAMEWORK.md: calibration /
coverage are marked "not yet" until gold/silver labels exist). The "evidence
model" treats each FDR field as a *claim*, and the weights below are product
judgments, not fitted coefficients. The posterior is a calibrated-against-a-proxy
evidence-quality score, surfaced so the app knows when NOT to overclaim.

The conformal layer (Concept 3) wraps the posterior with a split-conformal
prediction set. The calibration target is a documented *proxy* pseudo-label
(`trustworthy_supply_signal`), not human ground truth, so the conformal sets are
labelled provisional unless an external calibration artifact says otherwise.

Public API
----------
- ``facility_validity_posterior(facilities) -> DataFrame``
- ``trust_decomposition(row) -> DataFrame``
- ``conformal_label_sets(facilities, calibration=None) -> DataFrame``
- ``render_trust(facilities, districts, specialty) -> None``  (Streamlit view)

Also exported for auditability / reuse by scripts:
- ``EVIDENCE_WEIGHTS`` (dict), ``POSTERIOR_ACTIONS`` (thresholds),
  ``DEFAULT_CALIBRATION`` (provisional conformal fallback),
  ``load_calibration()``.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

try:  # config/data only needed for the Streamlit view + calibration path
    from . import config, data, ui
except Exception:  # pragma: no cover - allows standalone import in scripts
    config = data = ui = None  # type: ignore


# ---------------------------------------------------------------------------
# 1. Bayesian record-validity posterior (Concept 1)
# ---------------------------------------------------------------------------
#
# Model: a transparent Bayesian update in LOG-ODDS space.
#
#   logit(posterior) = logit(prior) + sum_k w_k * indicator_k
#
# The prior is a Beta-style base rate by record family (facility type recognised
# + has any source citation). Each evidence signal contributes a fixed log-odds
# "nudge" (positive = corroborating, negative = undermining). All weights live in
# EVIDENCE_WEIGHTS so the whole model is auditable in one place. These are PRODUCT
# JUDGMENTS over a proxy evidence model, not fitted/measured coefficients.

# Prior P(valid) before looking at row-level evidence.
# Slightly above 0.5 if the facility type parsed cleanly and there is a citation;
# lower if neither holds. Expressed as a probability; converted to log-odds below.
PRIOR_BASE = 0.50              # uninformative-ish base rate (proxy)
PRIOR_TYPE_RECOGNISED = 0.06   # + if facilityTypeId looks like a real category, not a URL/number
PRIOR_HAS_ANY_SOURCE = 0.06    # + if the record carries a source URL at all

# Evidence weights are LOG-ODDS contributions (natural log scale).
# Positive => pushes toward "valid"; negative => pushes toward "invalid/uncertain".
# Documented, auditable, and intentionally interpretable.
EVIDENCE_WEIGHTS: dict[str, float] = {
    # --- Strong corroboration ---
    "geo_plausible": 0.85,              # geo_quality == plausible AND inside India bbox
    "geo_moderate": 0.10,               # moderate distance from PIN centroid (weakly ok)
    "join_confidence_high": 0.70,       # join_confidence >= 0.85
    "join_confidence_mid": 0.20,        # 0.65 <= join_confidence < 0.85
    "has_source_urls": 0.55,            # at least one cited source page
    "has_contact_evidence": 0.35,       # phone/email/site present
    "recency_observed": 0.45,           # recency_status == observed_valid
    "trustworthy_supply_signal": 0.60,  # passed the pipeline's proxy supply checks
    "semantic_complete": 0.40,          # 0 critical semantic gaps
    "semantic_partial": 0.10,           # 1 critical semantic gap
    "capacity_observed": 0.20,          # capacity_status == observed_valid (real number)
    "doctor_count_observed": 0.20,      # doctor_count_status == observed_valid

    # --- Strong undermining ---
    "contradicted_or_geo_invalid": -1.40,  # explicit contradiction / invalid geo flag
    "geo_outside_india": -1.20,            # coordinates outside India bbox
    "geo_missing": -0.55,                  # missing coordinates
    "geo_far": -0.45,                      # far from PIN centroid
    "join_confidence_low": -0.55,          # join_confidence < 0.65
    "needs_human_review": -0.40,           # pipeline routed it to review
    "no_source_urls": -0.55,               # no citation at all
    "no_contact_evidence": -0.20,          # no phone/email/site
    "recency_stale": -0.45,                # recency stale_over_2y
    "recency_invalid": -0.55,              # future/invalid recency parse
    "capacity_extreme_outlier": -0.70,     # implausible capacity (e.g. 200k beds)
    "doctor_count_extreme_outlier": -0.70, # implausible doctor count
    "semantic_severe_gap": -0.45,          # 3+ critical semantic gaps
}

# Posterior -> confidence label -> action. Mirrors the Concept 1 table:
#   auto-accept / merge-or-review / quarantine-or-verify / human-review.
# Quarantine is reserved for records that are BOTH low-posterior AND carry a hard
# contradiction/geo-invalid flag (the "invalid/stale" row in the doc); otherwise a
# low posterior is sent to human review.
POSTERIOR_ACTIONS = {
    "auto_accept_threshold": 0.85,    # >= -> High confidence, auto-accept
    "review_threshold": 0.60,         # >= -> Medium confidence, merge or review
    # < review_threshold -> Low confidence; quarantine-or-verify if contradicted,
    #                       else human-review.
}


def _safe_logit(p: float) -> float:
    p = min(max(float(p), 1e-6), 1 - 1e-6)
    return math.log(p / (1.0 - p))


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _type_recognised(series: pd.Series) -> pd.Series:
    """Heuristic: a facilityTypeId is 'recognised' if it is non-empty, not a URL,
    not a bare number, and not an obvious hash/coordinate artifact."""
    s = series.fillna("").astype(str).str.strip()
    looks_url = s.str.contains("http", case=False, na=False)
    looks_number = s.str.fullmatch(r"[-+]?\d+(\.\d+)?", na=False)
    # 32-char hex hashes (entity-resolution ids) still count as a usable category key.
    empty = s.eq("") | s.str.lower().isin(["nan", "none", "unknown"])
    return ~(looks_url | looks_number | empty)


def facility_validity_posterior(facilities: pd.DataFrame) -> pd.DataFrame:
    """Return ``facilities`` plus a transparent Bayesian validity posterior.

    Added columns:
      - ``validity_prior``        Beta-style prior P(valid) from type + source presence.
      - ``validity_posterior``    P(record valid | evidence) in [0, 1] (PROXY, not
                                  measured accuracy) via a log-odds evidence update.
      - ``validity_log_odds``     The summed log-odds (for debugging / audit).
      - ``validity_confidence_label``  Low / Medium / High.
      - ``validity_action``       auto-accept / merge-or-review /
                                  quarantine-or-verify / human-review.

    NOTE: This is a posterior over a PROXY evidence model. It quantifies how well
    a record is corroborated by available signals; it does not claim the record is
    factually true. There are no gold labels, so this is decision support, not a
    measured-accuracy score.
    """
    df = facilities.copy()
    n = len(df)
    if n == 0:
        for col in ["validity_prior", "validity_posterior", "validity_log_odds"]:
            df[col] = pd.Series(dtype="float64")
        df["validity_confidence_label"] = pd.Series(dtype="object")
        df["validity_action"] = pd.Series(dtype="object")
        return df

    def col_bool(name: str) -> np.ndarray:
        if name not in df:
            return np.zeros(n, dtype=bool)
        return df[name].astype("boolean").fillna(False).to_numpy(dtype=bool)

    def col_num(name: str) -> np.ndarray:
        if name not in df:
            return np.full(n, np.nan)
        return pd.to_numeric(df[name], errors="coerce").to_numpy(dtype=float)

    def col_str(name: str) -> pd.Series:
        if name not in df:
            return pd.Series([""] * n, index=df.index)
        return df[name].fillna("").astype(str).str.lower()

    # --- Prior -----------------------------------------------------------------
    type_ok = _type_recognised(df.get("facilityTypeId", pd.Series([""] * n, index=df.index))).to_numpy(dtype=bool)
    has_src = col_bool("has_source_urls")
    prior = (
        PRIOR_BASE
        + np.where(type_ok, PRIOR_TYPE_RECOGNISED, 0.0)
        + np.where(has_src, PRIOR_HAS_ANY_SOURCE, 0.0)
    )
    prior = np.clip(prior, 0.05, 0.95)
    prior_logit = np.array([_safe_logit(p) for p in prior])

    # --- Evidence indicators ---------------------------------------------------
    geo_q = col_str("geo_quality")
    in_bbox = col_bool("geo_in_india_bbox")
    join = col_num("join_confidence")
    recency = col_str("recency_status")
    missing_crit = col_num("semantic_missing_critical_count")
    cap_status = col_str("capacity_status")
    doc_status = col_str("doctor_count_status")

    contributions = np.zeros(n)
    w = EVIDENCE_WEIGHTS

    # Geography
    geo_plausible = geo_q.str.contains("plausible", na=False).to_numpy() & in_bbox
    geo_moderate = geo_q.str.contains("moderate", na=False).to_numpy()
    geo_far = geo_q.str.contains("far", na=False).to_numpy()
    geo_missing = geo_q.str.contains("missing", na=False).to_numpy()
    geo_outside = geo_q.str.contains("outside", na=False).to_numpy() | (~in_bbox & ~geo_missing)
    contributions += np.where(geo_plausible, w["geo_plausible"], 0.0)
    contributions += np.where(geo_moderate & ~geo_plausible, w["geo_moderate"], 0.0)
    contributions += np.where(geo_far, w["geo_far"], 0.0)
    contributions += np.where(geo_missing, w["geo_missing"], 0.0)
    contributions += np.where(geo_outside & ~geo_plausible, w["geo_outside_india"], 0.0)

    # Join confidence
    contributions += np.where(np.nan_to_num(join, nan=0.0) >= 0.85, w["join_confidence_high"], 0.0)
    contributions += np.where((join >= 0.65) & (join < 0.85), w["join_confidence_mid"], 0.0)
    contributions += np.where(np.nan_to_num(join, nan=1.0) < 0.65, w["join_confidence_low"], 0.0)

    # Provenance / contact
    contributions += np.where(has_src, w["has_source_urls"], w["no_source_urls"])
    contributions += np.where(col_bool("has_contact_evidence"), w["has_contact_evidence"], w["no_contact_evidence"])

    # Recency
    contributions += np.where(recency.str.contains("observed_valid", na=False).to_numpy(), w["recency_observed"], 0.0)
    contributions += np.where(recency.str.contains("stale", na=False).to_numpy(), w["recency_stale"], 0.0)
    contributions += np.where(
        recency.str.contains("invalid|future", na=False).to_numpy(), w["recency_invalid"], 0.0
    )

    # Pipeline proxy signals
    contributions += np.where(col_bool("trustworthy_supply_signal"), w["trustworthy_supply_signal"], 0.0)
    contributions += np.where(col_bool("needs_human_review"), w["needs_human_review"], 0.0)
    contributions += np.where(col_bool("contradicted_or_geo_invalid_signal"), w["contradicted_or_geo_invalid"], 0.0)

    # Operational outlier flags
    contributions += np.where(col_bool("capacity_num_extreme_outlier"), w["capacity_extreme_outlier"], 0.0)
    contributions += np.where(col_bool("number_doctors_num_extreme_outlier"), w["doctor_count_extreme_outlier"], 0.0)
    contributions += np.where(cap_status.str.contains("observed_valid", na=False).to_numpy(), w["capacity_observed"], 0.0)
    contributions += np.where(doc_status.str.contains("observed_valid", na=False).to_numpy(), w["doctor_count_observed"], 0.0)

    # Semantic completeness (capacity/doctors/equipment/specialties/procedure gaps)
    mc = np.nan_to_num(missing_crit, nan=5.0)
    contributions += np.where(mc <= 0, w["semantic_complete"], 0.0)
    contributions += np.where(mc == 1, w["semantic_partial"], 0.0)
    contributions += np.where(mc >= 3, w["semantic_severe_gap"], 0.0)

    log_odds = prior_logit + contributions
    posterior = _sigmoid(log_odds)
    posterior = np.clip(posterior, 0.0, 1.0)

    df["validity_prior"] = prior
    df["validity_log_odds"] = log_odds
    df["validity_posterior"] = posterior

    auto = POSTERIOR_ACTIONS["auto_accept_threshold"]
    review = POSTERIOR_ACTIONS["review_threshold"]
    label = np.where(posterior >= auto, "High", np.where(posterior >= review, "Medium", "Low"))
    df["validity_confidence_label"] = label

    contradicted = col_bool("contradicted_or_geo_invalid_signal") | geo_outside
    action = np.where(
        posterior >= auto,
        "auto-accept",
        np.where(
            posterior >= review,
            "merge-or-review",
            np.where(contradicted, "quarantine-or-verify", "human-review"),
        ),
    )
    df["validity_action"] = action
    return df


# ---------------------------------------------------------------------------
# 2. Transparent additive trust decomposition (Ambitious Idea 1)
# ---------------------------------------------------------------------------
#
# A per-facility breakdown that SUMS to a displayed trust score out of 100.
# Each of the eight dimensions starts from a baseline allocation and earns or
# loses points based on the row's evidence, with a short human-readable reason.
# The base allocations sum to 100; deductions are bounded so the total stays in
# [0, 100]. The displayed total is the sum of the component contributions.

# (dimension, max points it can contribute when fully satisfied)
TRUST_DIMENSIONS: list[tuple[str, int]] = [
    ("Data completeness", 18),
    ("Evidence support", 16),
    ("Cross-field consistency", 14),
    ("Geographic validity", 16),
    ("Temporal validity", 10),
    ("Provenance quality", 12),
    ("Digital trust signals", 6),
    ("Human review status", 8),
]


def _b(row: pd.Series, name: str) -> bool:
    val = row.get(name, False)
    if isinstance(val, float) and math.isnan(val):
        return False
    return bool(val)


def _f(row: pd.Series, name: str, default: float = float("nan")) -> float:
    try:
        v = pd.to_numeric(row.get(name), errors="coerce")
        return default if pd.isna(v) else float(v)
    except Exception:
        return default


def _s(row: pd.Series, name: str) -> str:
    v = row.get(name, "")
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    return str(v).strip().lower()


def trust_decomposition(row: pd.Series) -> pd.DataFrame:
    """Additive trust breakdown for a single facility (Ambitious Idea 1).

    Returns a DataFrame with columns: ``Dimension``, ``Points`` (signed
    contribution), ``Max``, ``Reason``. The ``Points`` column SUMS to the
    displayed trust score (0-100). A higher score = more trustworthy / less
    uncertain. (Uncertainty = 100 - trust score, to mirror the doc's
    "Uncertainty: 65/100" framing.)
    """
    rows = []

    # 1. Data completeness ----------------------------------------------------
    mc = _f(row, "semantic_missing_critical_count", 5.0)
    dmax = 18
    if mc <= 0:
        pts, reason = dmax, "All critical supply fields present (capacity, doctors, equipment, specialties, procedure)."
    elif mc == 1:
        pts, reason = 13, "1 critical supply field missing or estimated."
    elif mc == 2:
        pts, reason = 8, "2 critical supply fields missing or estimated."
    else:
        pts, reason = 2, f"{int(mc)} critical supply fields missing or estimated."
    rows.append(("Data completeness", pts, dmax, reason))

    # 2. Evidence support -----------------------------------------------------
    dmax = 16
    trust_signal = _b(row, "trustworthy_supply_signal")
    readiness = _f(row, "data_readiness_score", 0.0)
    if trust_signal:
        pts, reason = dmax, "Passed the pipeline's proxy supply checks; claim is corroborated by available evidence."
    elif readiness >= 0.6:
        pts, reason = 10, "Partial evidence support; data readiness is moderate but proxy checks not fully passed."
    else:
        pts, reason = 4, "Weak evidence support; claims are largely unverified."
    rows.append(("Evidence support", pts, dmax, reason))

    # 3. Cross-field consistency ---------------------------------------------
    dmax = 14
    cap_out = _b(row, "capacity_num_extreme_outlier")
    doc_out = _b(row, "number_doctors_num_extreme_outlier")
    contradicted = _b(row, "contradicted_or_geo_invalid_signal")
    if contradicted:
        pts, reason = 0, "Cross-source contradiction or invalid-geo flag set."
    elif cap_out and doc_out:
        pts, reason = 2, "Both capacity and doctor-count are implausible outliers."
    elif cap_out or doc_out:
        pts, reason = 7, "One operational field (capacity or doctor count) is an implausible outlier."
    else:
        pts, reason = dmax, "No contradictions; capacity/doctor/type signals are mutually plausible."
    rows.append(("Cross-field consistency", pts, dmax, reason))

    # 4. Geographic validity --------------------------------------------------
    dmax = 16
    geo = _s(row, "geo_quality")
    in_bbox = _b(row, "geo_in_india_bbox")
    if "outside" in geo or (not in_bbox and "missing" not in geo and geo):
        pts, reason = 0, "Coordinates fall outside India."
    elif "missing" in geo:
        pts, reason = 5, "Coordinates missing; geography unverified."
    elif "far" in geo:
        pts, reason = 6, "Coordinates far from the PIN centroid."
    elif "moderate" in geo:
        pts, reason = 11, "Coordinates a moderate distance from the PIN centroid."
    elif "plausible" in geo:
        pts, reason = dmax, "Coordinates plausible and inside India."
    else:
        pts, reason = 8, "Geography partially validated."
    rows.append(("Geographic validity", pts, dmax, reason))

    # 5. Temporal validity ----------------------------------------------------
    dmax = 10
    rec = _s(row, "recency_status")
    if "observed_valid" in rec:
        pts, reason = dmax, "Source page recency observed and valid."
    elif "stale" in rec:
        pts, reason = 4, "Source last updated over 2 years ago."
    elif "invalid" in rec or "future" in rec:
        pts, reason = 2, "Recency value is invalid or a future date (extraction artifact)."
    else:
        pts, reason = 5, "Recency unknown; freshness could not be established."
    rows.append(("Temporal validity", pts, dmax, reason))

    # 6. Provenance quality ---------------------------------------------------
    dmax = 12
    has_src = _b(row, "has_source_urls")
    join = _f(row, "join_confidence", 0.0)
    if has_src and join >= 0.85:
        pts, reason = dmax, "Cited source URL and a high-confidence district/PIN join."
    elif has_src:
        pts, reason = 8, "Cited source URL present, but join confidence is moderate or low."
    else:
        pts, reason = 2, "No source URL citation."
    rows.append(("Provenance quality", pts, dmax, reason))

    # 7. Digital trust signals (weak evidence only) --------------------------
    dmax = 6
    contact = _b(row, "has_contact_evidence")
    if contact:
        pts, reason = dmax, "Phone/email/website present (weak supporting signal only)."
    else:
        pts, reason = 1, "No contact evidence (phone/email/site)."
    rows.append(("Digital trust signals", pts, dmax, reason))

    # 8. Human review status --------------------------------------------------
    dmax = 8
    needs_review = _b(row, "needs_human_review")
    if not needs_review:
        pts, reason = dmax, "Not flagged for manual review by the pipeline."
    else:
        pts, reason = 2, "Flagged for human review (weak join, geo, missingness, or contradiction)."
    rows.append(("Human review status", pts, dmax, reason))

    out = pd.DataFrame(rows, columns=["Dimension", "Points", "Max", "Reason"])
    return out


def trust_score_total(row: pd.Series) -> int:
    """Convenience: the displayed 0-100 trust score (sum of decomposition points)."""
    return int(trust_decomposition(row)["Points"].sum())


# ---------------------------------------------------------------------------
# 3. Conformal prediction sets (Concept 3)
# ---------------------------------------------------------------------------
#
# Split conformal over the validity posterior. We treat the posterior as a score
# for the pseudo-class "valid". The nonconformity score for a calibration point
# (whose proxy pseudo-label is "valid") is s = 1 - posterior. We take the
# (1 - alpha) empirical quantile q_hat of those scores. At inference, a label L is
# INCLUDED in the prediction set if its nonconformity score <= q_hat.
#
# Because there are NO gold labels, the calibration target is the proxy
# pseudo-label `trustworthy_supply_signal`. This calibrates against an automated
# proxy, not human-verified truth, so without an external artifact the sets are
# PROVISIONAL.
#
# Decision mapping mirrors the Concept 3 table:
#   {valid}                       -> auto-accept
#   {valid, uncertain}            -> review
#   {valid, stale, uncertain} / {uncertain,...} (valid excluded) -> low-confidence

DEFAULT_CALIBRATION: dict = {
    "alpha": 0.10,
    # Provisional q_hat for nonconformity s = 1 - posterior. Chosen so that a
    # posterior >= ~0.60 is confidently "valid". Replaced by the calibration
    # artifact when available.
    "q_hat": 0.40,
    # Secondary band: posteriors between (1 - q_hat) and a stricter "stale" cut
    # get the wider {valid, stale, uncertain} set. Documented default.
    "stale_q_hat": 0.55,
    "method": "split_conformal_proxy",
    "calibration_target": "trustworthy_supply_signal (PROXY pseudo-label, not gold)",
    "n_calibration": 0,
    "provisional": True,
    "notes": (
        "Provisional default. No external conformal_calibration.json found. "
        "Run scripts/build_conformal_calibration.py to calibrate q_hat against the "
        "proxy pseudo-label on the real facility data."
    ),
}


def load_calibration() -> dict:
    """Load output/data/conformal_calibration.json if present, else the provisional
    default. Always returns a dict with q_hat, stale_q_hat, alpha, provisional."""
    if config is None:
        return dict(DEFAULT_CALIBRATION)
    try:
        path = Path(config.data_dir()) / "conformal_calibration.json"
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            cal = dict(DEFAULT_CALIBRATION)
            cal.update(loaded)
            cal["provisional"] = bool(loaded.get("provisional", False))
            cal.setdefault("stale_q_hat", DEFAULT_CALIBRATION["stale_q_hat"])
            return cal
    except Exception:
        pass
    return dict(DEFAULT_CALIBRATION)


def conformal_label_sets(facilities: pd.DataFrame, calibration: dict | None = None) -> pd.DataFrame:
    """Attach split-conformal prediction sets over the validity posterior.

    Added columns:
      - ``conformal_set``       e.g. ``{valid}`` / ``{valid, uncertain}`` /
                                ``{valid, stale, uncertain}`` / ``{uncertain}``.
      - ``conformal_decision``  auto-accept / review / low-confidence.
      - ``conformal_provisional``  True if calibrated only against a proxy default.

    Requires ``validity_posterior`` (call ``facility_validity_posterior`` first);
    if missing it is computed on the fly.
    """
    df = facilities.copy()
    if "validity_posterior" not in df:
        df = facility_validity_posterior(df)

    cal = calibration if calibration is not None else load_calibration()
    q_hat = float(cal.get("q_hat", DEFAULT_CALIBRATION["q_hat"]))
    stale_q = float(cal.get("stale_q_hat", DEFAULT_CALIBRATION["stale_q_hat"]))
    provisional = bool(cal.get("provisional", True))

    post = pd.to_numeric(df["validity_posterior"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    nonconf_valid = 1.0 - post  # nonconformity for the "valid" label

    contradicted = (
        df.get("contradicted_or_geo_invalid_signal", pd.Series(False, index=df.index))
        .astype("boolean").fillna(False).to_numpy(dtype=bool)
    )
    recency = df.get("recency_status", pd.Series("", index=df.index)).fillna("").astype(str).str.lower()
    is_stale = recency.str.contains("stale|invalid|future", na=False).to_numpy()

    sets: list[str] = []
    decisions: list[str] = []
    for s_valid, stale_flag, contra in zip(nonconf_valid, is_stale, contradicted):
        valid_in = s_valid <= q_hat
        # "uncertain" enters whenever we are not in the confident-valid region.
        if valid_in and s_valid <= (q_hat * 0.5) and not contra:
            sets.append("{valid}")
            decisions.append("auto-accept")
        elif valid_in and not contra:
            sets.append("{valid, uncertain}")
            decisions.append("review")
        else:
            # valid excluded (or contradicted): widen the set.
            labels = ["uncertain"]
            if not contra:
                labels.insert(0, "valid")
            if stale_flag or s_valid >= stale_q:
                labels.insert(-0 if contra else 1, "stale")
            # order: valid?, stale?, uncertain
            ordered = [l for l in ["valid", "stale", "uncertain"] if l in labels]
            sets.append("{" + ", ".join(ordered) + "}")
            decisions.append("low-confidence")

    df["conformal_set"] = sets
    df["conformal_decision"] = decisions
    df["conformal_provisional"] = provisional
    return df


# ---------------------------------------------------------------------------
# 4. Streamlit view
# ---------------------------------------------------------------------------

def _trust_chart_data(posterior: pd.Series) -> pd.DataFrame:
    edges = np.linspace(0.0, 1.0, 11)
    counts, _ = np.histogram(posterior.dropna().to_numpy(dtype=float), bins=edges)
    labels = [f"{edges[i]:.1f}-{edges[i+1]:.1f}" for i in range(len(edges) - 1)]
    return pd.DataFrame({"Posterior band": labels, "Facilities": counts}).set_index("Posterior band")


def render_trust(facilities: pd.DataFrame, districts: pd.DataFrame, specialty: str) -> None:
    """Self-contained Streamlit view: validity posterior distribution, action mix,
    a selectable facility's trust decomposition, posterior, conformal set, and
    cited sources. Frames the app's honest 'know when not to overclaim' posture.

    Add to app.py with: ``trust.render_trust(facilities, districts, specialty)``
    """
    import streamlit as st

    st.subheader("Record-validity confidence")
    st.caption(
        "Bayesian validity posterior + conformal prediction sets over a transparent "
        "evidence model. This is a PROXY confidence score, not measured accuracy: "
        "there are no human-verified gold labels, so the app says what it can and "
        "cannot claim rather than overclaiming."
    )

    if facilities is None or len(facilities) == 0:
        st.info("No facilities loaded for the current selection.")
        return

    try:
        scored = facility_validity_posterior(facilities)
        scored = conformal_label_sets(scored)
    except Exception as exc:  # pragma: no cover - defensive UI guard
        st.error(f"Could not compute validity posterior: {exc}")
        return

    cal = load_calibration()
    if cal.get("provisional", True):
        st.warning(
            "Conformal sets are PROVISIONAL: calibrated against an automated proxy "
            "pseudo-label (trustworthy_supply_signal), not human-verified ground "
            f"truth. Run scripts/build_conformal_calibration.py to calibrate "
            f"(current q_hat={cal.get('q_hat')}, target alpha={cal.get('alpha')})."
        )

    # --- Action mix summary ---------------------------------------------------
    action_counts = scored["validity_action"].value_counts()
    total = len(scored)
    cols = st.columns(4)
    order = ["auto-accept", "merge-or-review", "quarantine-or-verify", "human-review"]
    tones = {"auto-accept": "deploy", "merge-or-review": "info",
             "quarantine-or-verify": "danger", "human-review": "verify"}
    for c, action in zip(cols, order):
        n = int(action_counts.get(action, 0))
        with c:
            if ui is not None:
                ui.stat_card(action.replace("-", " ").title(), f"{n:,}",
                             f"{n/total:.0%} of records", tone=tones[action])
            else:
                st.metric(action, f"{n:,}", f"{n/total:.0%}")

    # --- Posterior distribution ----------------------------------------------
    st.markdown("**Distribution of P(record valid | evidence)**")
    st.caption(
        "Proxy posterior across the selected facilities. Mass near 1.0 = well "
        "corroborated; mass near 0 = contradicted / sparse / geo-invalid."
    )
    st.bar_chart(_trust_chart_data(scored["validity_posterior"]), height=220)

    conf_mix = scored["conformal_decision"].value_counts()
    st.caption(
        "Conformal decision mix — "
        + " · ".join(f"{k}: {int(v):,}" for k, v in conf_mix.items())
    )

    # --- Selectable facility detail ------------------------------------------
    st.markdown("**Inspect a facility's trust decomposition**")
    names = scored["facility_name"].fillna("Unnamed facility").astype(str)
    # Make labels unique-ish by suffixing index.
    options = list(scored.index)
    label_map = {
        idx: f"{names.loc[idx]} · {str(scored.loc[idx].get('district_name', '') or '—')}"
        for idx in options
    }
    if not options:
        st.info("No facilities available to inspect.")
        return
    chosen = st.selectbox(
        "Facility",
        options=options,
        format_func=lambda i: label_map.get(i, str(i)),
        key="trust_facility_select",
    )
    row = scored.loc[chosen]

    decomp = trust_decomposition(row)
    score = int(decomp["Points"].sum())
    uncertainty = 100 - score
    post = float(row.get("validity_posterior", float("nan")))
    label = str(row.get("validity_confidence_label", "—"))
    action = str(row.get("validity_action", "—"))
    cset = str(row.get("conformal_set", "—"))
    cdec = str(row.get("conformal_decision", "—"))

    top = st.columns(3)
    with top[0]:
        if ui is not None:
            ui.stat_card("Trust score", f"{score}/100",
                         f"Uncertainty: {uncertainty}/100", tone="info")
        else:
            st.metric("Trust score", f"{score}/100", f"Uncertainty {uncertainty}/100")
    with top[1]:
        if ui is not None:
            ui.stat_card("Validity posterior", f"{post:.2f}",
                         f"{label} confidence · {action}", tone="info")
        else:
            st.metric("Validity posterior", f"{post:.2f}", f"{label} · {action}")
    with top[2]:
        if ui is not None:
            ui.stat_card("Conformal set", cset, f"Decision: {cdec}", tone="verify")
        else:
            st.metric("Conformal set", cset, cdec)

    st.caption(
        f"Trust score is the sum of the components below (it equals {score}). "
        f"Uncertainty = 100 - trust = {uncertainty}/100."
    )
    st.dataframe(
        decomp.assign(Contribution=decomp["Points"].map(lambda p: f"+{p}" if p >= 0 else str(p)))[
            ["Dimension", "Contribution", "Max", "Reason"]
        ],
        hide_index=True,
        width="stretch",
    )

    # Cited sources
    src_raw = row.get("source_urls", "")
    urls = data._json_list(src_raw) if data is not None else []
    st.markdown("**Cited sources**")
    if urls:
        for u in urls[:6]:
            st.markdown(f"- [{u}]({u})")
    else:
        st.caption("No source URL cited for this record — provenance quality is low.")

    st.caption(
        "What the app can say: this record is well/weakly corroborated by available "
        "evidence. What it cannot say: that the record is factually true — that needs "
        "human verification or an authoritative registry match."
    )
