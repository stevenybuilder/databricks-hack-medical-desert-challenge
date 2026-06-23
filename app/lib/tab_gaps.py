"""Top care gaps tab: a calm first glance (wow stat + top action) with all
depth opt-in behind expanders.

Entry point: ``render(districts, specialty) -> None``.

Layout philosophy (see docs/DESIGN_SYSTEM.md density rule): the default view answers
"where is the worst gap and what do I do" — a calm wow-stat anchor, ≤2 KPIs, a
compact top-6, and the selected-district drill-down. Everything heavier lives
behind ONE ``st.segmented_control`` sub-nav (Ranking · At a glance · Method &
caveats · My Plan) that swaps a single panel in place, so depth is one click,
not three scrolls. The next-wave gaps agent edits this file only; new
chart/helper needs are LOCAL functions here.
"""
from __future__ import annotations

import html
import json
import re
from contextlib import contextmanager

import pandas as pd
import streamlit as st

from . import data, ui, decisions
from .tab_common import (
    ACTION_FILTERS,
    _action_label,
    _action_tone,
    _district_scope_control,
    _fmt_num,
    _fmt_pct,
    _ranked_districts,
    _selected_or_first,
)

# How many districts show in the calm default list before "Full ranking".
_SHORTLIST_N = 6

_CONDITION_HELP = {
    "Institutional births": (
        "Access marker",
        "Lower facility delivery usually means families cannot reliably reach staffed obstetric care.",
    ),
    "Skilled birth attendance": (
        "Maternal safety marker",
        "Low skilled attendance points to gaps in nurses, midwives, emergency referral, or delivery rooms.",
    ),
    "C-section deliveries": (
        "Surgical access marker",
        "Very low rates can signal missing emergency obstetric surgery; very high rates can signal overuse.",
    ),
    "Women 15-49 anaemic": (
        "Maternal risk marker",
        "High anaemia raises pregnancy, surgical, and chronic-care risk; prioritize primary and maternal teams.",
    ),
    "Women high BP": (
        "Chronic-care marker",
        "High blood pressure burden suggests recurring NCD screening and follow-up clinics.",
    ),
    "Men high BP": (
        "Chronic-care marker",
        "High blood pressure burden suggests recurring NCD screening and follow-up clinics.",
    ),
    "Women high blood sugar": (
        "Diabetes marker",
        "High blood sugar burden points to diagnostics, medication continuity, and chronic-care follow-up.",
    ),
    "Men high blood sugar": (
        "Diabetes marker",
        "High blood sugar burden points to diagnostics, medication continuity, and chronic-care follow-up.",
    ),
    "Cervical screening": (
        "Preventive-care marker",
        "Low screening suggests outreach camps, women's health staff, and referral pathways.",
    ),
    "Breast exam": (
        "Preventive-care marker",
        "Low exam coverage suggests outreach camps, women's health staff, and referral pathways.",
    ),
    "Oral cancer exam": (
        "Preventive-care marker",
        "Low exam coverage suggests outreach camps, dental/oral screening, and referral pathways.",
    ),
    "Health insurance coverage": (
        "Affordability marker",
        "Low coverage means referral plans should include enrollment support and low-cost public pathways.",
    ),
}

_SERVICE_SIGNALS = [
    ("Maternity / OB-GYN", "has_maternity_care_signal", "Maternity"),
    ("Emergency / Surgery", "has_emergency_care_signal", "Emergency"),
    ("Diagnostics / Imaging", "has_diagnostic_signal", "Diagnostics"),
    ("Chronic disease (NCD)", "has_ncd_care_signal", "NCD"),
]

_PHOTO_URL_HINTS = (
    "/photo",
    "/photos",
    "view-photo",
    "gallery",
    "/media",
    "/image",
    "/images",
    "album",
)

_PROVIDER_DISTRICT_EVIDENCE_COLS = ("facility_name", "address_city", "claim_text")


@contextmanager
def _glass_panel():
    """Group loose content into one frosted `.mdn-glass` surface.

    Streamlit can't wrap arbitrary widgets in a raw HTML div, so we scope the
    frosted-card recipe (radius/blur/shadow/padding from the design tokens) onto a
    bordered ``st.container`` and yield it. Keeps the "where to act next" block
    reading as one intentional card rather than loose floating elements."""
    box = st.container(border=True)
    box.markdown(
        """
        <style>
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.cg-glass-marker) {
          background: var(--glass-bg);
          border: 1px solid var(--glass-border);
          border-radius: var(--radius-card);
          box-shadow: var(--shadow-card);
          padding: var(--pad-card);
          -webkit-backdrop-filter: var(--glass-blur);
          backdrop-filter: var(--glass-blur);
        }
        </style>
        <div class="cg-glass-marker"></div>
        """,
        unsafe_allow_html=True,
    )
    with box:
        yield box


def _wow_stat(ranked_all: pd.DataFrame) -> tuple[int, int, float]:
    """Honest demo anchor, recomputed live (never hardcoded).

    Among the worst-N care-gap districts, how many have *no* rows passing the
    strict automated hard checks (``trustworthy_supply_rate`` <= 0). Returns
    ``(zero_trust_count, n, pct)``. Gracefully handles a missing column.
    """
    n = min(50, len(ranked_all))
    tsr = pd.to_numeric(
        ranked_all.head(n).get("trustworthy_supply_rate"), errors="coerce"
    ).fillna(0.0)
    zero_trust = int((tsr <= 0).sum())
    pct = (zero_trust / n * 100) if n else 0.0
    return zero_trust, n, pct


def _wow_banner(zero_trust: int, n: int, pct: float) -> None:
    """The single bold anchor of the first glance — a cohesive frosted card with a
    danger accent. Tokenized (radius/shadow/blur from the design system); the
    underlying stat is computed upstream and never touched here."""
    st.markdown(
        '<div class="mdn-glass" style="margin:.1rem 0 .2rem;'
        'border-color:rgba(255,82,82,.32);'
        'background:linear-gradient(100deg,rgba(255,82,82,.13),var(--glass-bg) 62%);'
        'display:flex;align-items:baseline;gap:.9rem;flex-wrap:wrap">'
        '<span style="font-size:2.3rem;font-weight:820;color:#ff8d8d;line-height:1;'
        'letter-spacing:-.02em;font-variant-numeric:tabular-nums">'
        f'{zero_trust}/{n}</span>'
        '<span style="color:var(--text);font-size:1.0rem;line-height:1.4;flex:1 1 16rem">'
        'of the worst care-gap districts have <strong>no hard-check-passing claims</strong>. '
        f'Prioritize these for call/verify before staffing.</span></div>',
        unsafe_allow_html=True,
    )


def _ranking_source_strip() -> None:
    """Compact citation/provenance line for headline rankings."""
    chips = [
        ("NFHS-5 need", "district health indicators"),
        ("FDR provider snapshot", "claim rows, not a verified census"),
        ("Wilson intervals", "in detail"),
    ]
    chip_html = "".join(
        '<span class="mdn-pill mdn-pill--muted" '
        f'title="{html.escape(tip, quote=True)}">{html.escape(label)}</span>'
        for label, tip in chips
    )
    st.markdown(
        '<div class="mdn-pill-row" style="margin:-.15rem 0 .35rem">'
        f'{chip_html}</div>',
        unsafe_allow_html=True,
    )


def _guide_steps() -> None:
    """A visible click path for non-technical planners."""
    steps = [
        ("1. Pick a service", "Choose the care team."),
        ("2. Choose a district", "Start with the ranked shortlist."),
        ("3. Check claims", "Card checkmark = automated checks passed."),
        ("4. Save the plan", "Shortlist and add a handoff note."),
    ]
    body = "".join(
        '<div class="mdn-guide-step">'
        f'<b>{html.escape(title)}</b><span>{html.escape(text)}</span></div>'
        for title, text in steps
    )
    st.markdown(f'<div class="mdn-guide">{body}</div>', unsafe_allow_html=True)


def _num(v, default: float = 0.0) -> float:
    value = pd.to_numeric(v, errors="coerce")
    return default if pd.isna(value) else float(value)


def _pct_text(v) -> str:
    value = pd.to_numeric(v, errors="coerce")
    return "unknown" if pd.isna(value) else f"{float(value):.0f}%"


def _condition_cards(row: pd.Series, districts: pd.DataFrame) -> None:
    """Plain-English condition cards; charts are opt-in below."""
    conds = data.district_top_conditions(row, districts, n=3)
    if conds.empty:
        st.caption("No NFHS condition indicators available for this district.")
        return
    cards = []
    for _, cond in conds.iterrows():
        label = str(cond.get("Condition", "Condition"))
        marker, meaning = _CONDITION_HELP.get(
            label,
            ("Health-need marker", "Use this as a local burden signal when deciding which doctors to deploy."),
        )
        district_pct = _pct_text(cond.get("District %"))
        national_pct = _pct_text(cond.get("National %"))
        delta = pd.to_numeric(cond.get("Δ vs national"), errors="coerce")
        gap = "" if pd.isna(delta) else f" · gap {abs(float(delta)):.1f} pts"
        cards.append(
            '<div class="mdn-condition-card">'
            f'<b>{html.escape(label)}</b>'
            f'<span>{html.escape(marker)}: {district_pct} district vs {national_pct} national{gap}.</span>'
            f'<span>{html.escape(meaning)}</span>'
            '</div>'
        )
    st.markdown('<div class="mdn-condition-grid">' + "".join(cards) + '</div>',
                unsafe_allow_html=True)


def _source_urls(raw) -> list[str]:
    """Return useful URLs from a JSON-ish source list."""
    text = "" if raw is None or (isinstance(raw, float) and pd.isna(raw)) else str(raw).strip()
    if not text or text.lower() == "nan":
        return []
    urls: list[str] = []

    def add_url(value) -> None:
        url = "" if value is None else str(value).strip().strip('"').strip("'")
        if url.lower() in {"", "nan", "none", "null"}:
            return
        if url.startswith(("http://", "https://")) and url not in urls:
            urls.append(url)

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            for item in parsed:
                add_url(item)
        else:
            add_url(parsed)
    except Exception:
        pass
    if urls:
        return urls
    for piece in text.replace("[", " ").replace("]", " ").replace('"', " ").split(","):
        add_url(piece)
    return urls


def _first_url(raw) -> str:
    """Return the first useful URL from a JSON-ish source list."""
    urls = _source_urls(raw)
    return urls[0] if urls else ""


def _source_domain(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    host = raw.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0]
    host = host.split("@", 1)[-1].split(":", 1)[0]
    return host[4:] if host.lower().startswith("www.") else host


def _looks_like_photo_page(url: str) -> bool:
    raw = (url or "").lower()
    return any(hint in raw for hint in _PHOTO_URL_HINTS)


def _claim_description(raw) -> str:
    text = "" if raw is None or (isinstance(raw, float) and pd.isna(raw)) else str(raw).strip()
    if not text or text.lower() == "nan":
        return ""
    description = " ".join(text.split(" | ", 1)[0].split())
    if len(description) > 150:
        stops = [description.find(stop) for stop in (". ", "; ", " - ") if description.find(stop) >= 60]
        if stops:
            description = description[:min(stops) + 1].rstrip()
    if len(description) > 145:
        description = description[:142].rstrip(" ,;.") + "..."
    return description


def _verified_claim(row: pd.Series) -> bool:
    """Automated verification badge: source-backed, not contradicted, no human-review flag."""
    return bool(row.get("trustworthy_supply_signal", False)) and not bool(
        row.get("needs_human_review", False)
    ) and not bool(row.get("contradicted_or_geo_invalid_signal", False))


def _service_badges(row: pd.Series, specialty: str, verified: bool) -> str:
    chips = []
    for short in _service_claims(row, specialty):
        tone = "mdn-pill--deploy" if verified else "mdn-pill--verify"
        chips.append(f'<span class="mdn-pill {tone}">{html.escape(short)} claim</span>')
    if not chips:
        chips.append('<span class="mdn-pill mdn-pill--muted">No service claim in this lens</span>')
    return '<div class="mdn-pill-row">' + "".join(chips[:4]) + '</div>'


def _service_claims(row: pd.Series, specialty: str) -> list[str]:
    relevant = [
        (label, col, short) for label, col, short in _SERVICE_SIGNALS
        if specialty == "All specialties" or specialty == label
    ]
    return [short for _, col, short in relevant if bool(row.get(col, False))]


def _claim_evidence_line(row: pd.Series, specialty: str, domain: str) -> str:
    claims = _service_claims(row, specialty)
    claim = ", ".join(claims[:2]) if claims else "facility listing"
    if len(claims) > 2:
        claim += " + more"
    source = domain or ("cited URL" if bool(row.get("has_source_urls", False)) else "claim text")
    return f"Claim: {claim} · Source: {source}"


def _clean_provider_evidence_text(raw) -> str:
    if raw is None:
        return ""
    try:
        if pd.isna(raw):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(raw).strip()
    return "" if text.casefold() in {"", "nan", "none", "null"} else text


def _normalize_district_phrase(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(text).casefold()).split())


def _district_phrase_in_text(district: str, text: str) -> bool:
    phrase = _normalize_district_phrase(district)
    haystack = _normalize_district_phrase(text)
    if not phrase or not haystack:
        return False
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", haystack))


def _state_district_names(districts: pd.DataFrame, selected: pd.Series) -> list[str]:
    if (
        districts is None
        or districts.empty
        or not {"district_name", "state_ut"}.issubset(districts.columns)
    ):
        return []
    state = str(selected.get("state_ut", "") or "").strip()
    if not state:
        return []
    same_state = districts[
        districts["state_ut"].astype(str).str.strip().eq(state)
    ]
    names = {
        str(name).strip()
        for name in same_state["district_name"].dropna()
        if str(name).strip()
    }
    return sorted(names, key=len, reverse=True)


def _provider_evidence_other_district(
    row: pd.Series,
    selected: pd.Series,
    district_names: list[str],
) -> str:
    """Return a strongly mentioned non-selected district, if visible evidence has one."""
    selected_key = _normalize_district_phrase(
        str(selected.get("district_name", "") or "")
    )
    if not selected_key or not district_names:
        return ""

    city_key = _normalize_district_phrase(
        _clean_provider_evidence_text(row.get("address_city"))
    )
    for district in district_names:
        district_key = _normalize_district_phrase(district)
        if not district_key or district_key == selected_key:
            continue
        if city_key and city_key == district_key:
            return district

    evidence = " ".join(
        _clean_provider_evidence_text(row.get(col))
        for col in _PROVIDER_DISTRICT_EVIDENCE_COLS
    )
    for district in district_names:
        district_key = _normalize_district_phrase(district)
        if not district_key or district_key == selected_key:
            continue
        if len(district_key.replace(" ", "")) < 5:
            continue
        if _district_phrase_in_text(district, evidence):
            return district
    return ""


def _provider_candidates(
    facilities: pd.DataFrame,
    selected: pd.Series,
    specialty: str,
    districts: pd.DataFrame,
    n: int = 2,
) -> tuple[pd.DataFrame, str, int]:
    """Return clean district providers, then state/national examples if local evidence conflicts."""
    if facilities is None or facilities.empty:
        return pd.DataFrame(), "Provider source unavailable", 0
    district = str(selected.get("district_name", "") or "").strip()
    state = str(selected.get("state_ut", "") or "").strip()
    exact = facilities[
        (facilities.get("district_name").astype(str).str.strip() == district)
        & (facilities.get("state_ut").astype(str).str.strip() == state)
    ].copy()
    quarantined_count = 0
    district_names = _state_district_names(districts, selected)
    if not exact.empty and district_names:
        other_district = exact.apply(
            lambda row: _provider_evidence_other_district(row, selected, district_names),
            axis=1,
        )
        quarantine_mask = other_district.astype(bool)
        quarantined_count = int(quarantine_mask.sum())
        exact = exact.loc[~quarantine_mask].copy()

    scope = "District-mapped provider claims"
    candidates = exact
    if candidates.empty and state:
        candidates = facilities[
            facilities.get("state_ut").astype(str).str.strip().eq(state)
        ].copy()
        scope = "State reference examples"
    if candidates.empty:
        candidates = facilities.copy()
        scope = "National reference examples"

    if specialty != "All specialties":
        signal = next((col for label, col, _ in _SERVICE_SIGNALS if label == specialty), None)
        if signal and signal in candidates.columns:
            service_matches = candidates[candidates[signal].fillna(False).astype(bool)]
            if not service_matches.empty:
                candidates = service_matches

    candidates["_verified_sort"] = candidates.apply(_verified_claim, axis=1).astype(int)
    trust = (
        candidates["trust_tier"].astype(str)
        if "trust_tier" in candidates
        else pd.Series("", index=candidates.index)
    )
    candidates["_trust_sort"] = trust.map(
        {"High": 3, "Medium": 2, "Verify": 1}
    ).fillna(0)
    source = (
        candidates["has_source_urls"]
        if "has_source_urls" in candidates
        else pd.Series(False, index=candidates.index)
    )
    candidates["_source_sort"] = source.fillna(False).astype(bool).astype(int)
    quality = (
        candidates["semantic_data_quality_score"]
        if "semantic_data_quality_score" in candidates
        else pd.Series(0, index=candidates.index)
    )
    candidates["_quality_sort"] = pd.to_numeric(quality, errors="coerce").fillna(0)
    candidates = candidates.sort_values(
        ["_verified_sort", "_trust_sort", "_source_sort", "_quality_sort"],
        ascending=False,
    ).head(n)
    return candidates, scope, quarantined_count


def _provider_cards(
    facilities: pd.DataFrame,
    selected: pd.Series,
    specialty: str,
    districts: pd.DataFrame,
) -> None:
    providers, scope, quarantined_count = _provider_candidates(
        facilities, selected, specialty, districts
    )
    ui.panel_header("Provider claims")
    if providers.empty:
        st.info("No provider claims available.")
        return
    cards = []
    for _, row in providers.iterrows():
        name = str(row.get("facility_name") or "Unnamed facility")
        ftype = str(row.get("facilityTypeId") or "facility").title()
        city = str(row.get("address_city") or row.get("district_name") or "").strip()
        state = str(row.get("state_ut") or row.get("address_stateOrRegion") or "").strip()
        verified = _verified_claim(row)
        status = "✓ Passed checks" if verified else "Call or verify"
        status_cls = "mdn-pill--deploy" if verified else "mdn-pill--verify"
        desc = _claim_description(row.get("claim_text")) or "Claim text pending."
        urls = _source_urls(row.get("source_urls"))
        official_url = str(row.get("officialWebsite") or "").strip()
        if not official_url.startswith(("http://", "https://")):
            official_url = ""
        primary_url = (urls[0] if urls else "") or official_url
        photo_url = next((url for url in urls if _looks_like_photo_page(url)), "")
        link_url = primary_url or photo_url
        domain = _source_domain(link_url)
        link_label = "Source page"
        source_link = (
            f' · <a href="{html.escape(link_url, quote=True)}" target="_blank" '
            f'rel="noopener noreferrer">{html.escape(link_label)}</a>'
            if link_url else ""
        )
        evidence = html.escape(_claim_evidence_line(row, specialty, domain)) + source_link
        art_hint = "Source page" if link_url else "Source pending"
        initials = "".join(part[:1] for part in name.split()[:2]).upper() or "P"
        cards.append(
            '<div class="mdn-provider-card">'
            '<div class="mdn-provider-art" style="flex-direction:column;gap:.18rem;text-align:center">'
            f'<span>{html.escape(initials[:2])}</span>'
            '<span style="font-size:.62rem;font-weight:650;color:var(--mdn-muted);'
            f'letter-spacing:0">{html.escape(art_hint)}</span></div>'
            '<div>'
            f'<div class="mdn-provider-name">{html.escape(name)}</div>'
            f'<div class="mdn-pill-row"><span class="mdn-pill {status_cls}">{status}</span>'
            f'<span class="mdn-pill mdn-pill--muted">{html.escape(ftype)}</span></div>'
            f'{_service_badges(row, specialty, verified)}'
            f'<div class="mdn-provider-desc">{html.escape(city)}{", " if city and state else ""}{html.escape(state)}</div>'
            f'<div class="mdn-provider-claim">{html.escape(desc)}</div>'
            f'<div class="mdn-provider-desc">{evidence}</div>'
            '</div></div>'
        )
    cards_html = '<div class="mdn-provider-grid">' + "".join(cards) + '</div>'
    if scope != "District-mapped provider claims":
        if quarantined_count:
            st.info(
                "District-keyed provider evidence names another district, so it is "
                "not counted as local provider evidence here."
            )
        else:
            st.info("No source-backed provider claims are mapped to this district yet.")
        with ui.detail(f"Show {scope.lower()} (not local evidence)"):
            st.caption(
                f"{scope}. These examples are dynamic, but they are not local evidence "
                "for the selected district."
            )
            st.markdown(cards_html, unsafe_allow_html=True)
        return

    st.caption("District-mapped claims. Source links open when available. ✓ Passed checks = automated checks passed.")
    st.markdown(cards_html, unsafe_allow_html=True)


def _planner_brief(
    selected: pd.Series,
    specialty: str,
    districts: pd.DataFrame,
) -> None:
    """Compact selected-district answer: action, why, and next click."""
    action = _action_label(selected.get("planning_category"))
    district = str(selected.get("district_name", "unknown"))
    state = str(selected.get("state_ut", "unknown"))
    is_zero = bool(selected.get("zero_facility_desert", False))
    trust_rate = pd.to_numeric(
        selected.get("provider_trust_score", selected.get("trustworthy_supply_rate")),
        errors="coerce",
    )
    supply = "No mapped provider" if is_zero else (
        "provider trust unknown" if pd.isna(trust_rate) else f"Provider trust {trust_rate * 100:.0f}%"
    )
    doctors = (
        "Deploy a mobile team; call or verify local provider gaps."
        if is_zero else
        "Call or verify provider claims before deploying."
    )
    ui.decision_banner(
        f"{action}: {district}, {state}",
        f"{supply} · {specialty} lens · uncertainty {str(selected.get('district_uncertainty_level', 'unknown')).title()}",
        _action_tone(selected.get("planning_category")),
    )
    with _glass_panel():
        ui.panel_header("Planner next step")
        st.markdown(
            f"**Next step:** {doctors}  \n"
            "Use condition cards for clinician type; provider cards for claim checks."
        )
        _condition_cards(selected, districts)


def _provider_trust_pct(rows: pd.DataFrame) -> pd.Series:
    score = pd.to_numeric(
        rows["provider_trust_score"] if "provider_trust_score" in rows else pd.Series(index=rows.index, dtype=float),
        errors="coerce",
    )
    fallback = pd.to_numeric(
        rows["trustworthy_supply_rate"] if "trustworthy_supply_rate" in rows else pd.Series(index=rows.index, dtype=float),
        errors="coerce",
    )
    return score.combine_first(fallback) * 100


def _shortlist_table(ranked: pd.DataFrame, gap_label: str) -> pd.DataFrame:
    """Compact, decision-first table: rank, place, action, gap, provider trust."""
    return pd.DataFrame({
        "Rank": ranked["Rank"],
        "District": ranked["district_name"],
        "State": ranked["state_ut"],
        "Action": ranked["Action"],
        gap_label: pd.to_numeric(ranked["gap"], errors="coerce"),
        "Provider trust %": _provider_trust_pct(ranked),
    })


def render(facilities: pd.DataFrame, districts: pd.DataFrame, specialty: str) -> None:
    ui.tab_intro(
        "Doctor deployment shortlist",
        f"{specialty} · highest need first; call or verify claims",
    )
    _guide_steps()
    _, scoped_districts = _district_scope_control(districts, "gaps_district_scope_filter")

    ranked_all, gap_label = _ranked_districts(scoped_districts, specialty)
    if ranked_all.empty:
        st.info("No district rows match this specialty and provider-claim filter.")
        return

    top = ranked_all.iloc[0]
    deploy_count = int(scoped_districts["planning_category"].eq("real_desert_candidate").sum())

    # ============================ FIRST GLANCE ===============================
    # 1) The wow stat — single bold anchor (honest, recomputed live).
    zero_trust, wow_n, wow_pct = _wow_stat(ranked_all)
    _wow_banner(zero_trust, wow_n, wow_pct)
    _ranking_source_strip()

    # 2) ≤2 KPI cards: where to act, and how big the deploy queue is.
    ui.kpi_row(
        [
            (
                "Top district",
                f"{top.get('district_name', 'unknown')}, {top.get('state_ut', 'unknown')}",
                f"{_action_label(top.get('planning_category'))} · {gap_label} {_fmt_num(top.get('gap'))}",
            ),
            ("Deploy candidates", f"{deploy_count:,}", "Strong unmet-need signal"),
        ],
        tone_each=[_action_tone(top.get("planning_category")), "deploy"],
    )

    # 3) Short ranked list — the calm "where to act next", grouped into one frosted
    #    panel (full table stays opt-in below).
    shortlist = ranked_all.head(_SHORTLIST_N).copy()
    with _glass_panel():
        ui.panel_header(f"Where to act next · top {_SHORTLIST_N}")
        ev = st.dataframe(
            _shortlist_table(shortlist, gap_label),
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "Rank": st.column_config.NumberColumn(format="%d"),
                gap_label: st.column_config.NumberColumn(
                    f"{gap_label} ▲ worse", format="%.2f",
                    help="Higher = more unmet need with weaker provider evidence."),
                "Provider trust %": st.column_config.ProgressColumn(
                    "Provider trust ▲ better", format="%d%%", min_value=0, max_value=100,
                    help="Calibrated provider-claim trust from Bayesian evidence plus smoothed checks."),
            },
        )
        st.caption("Select a row to inspect. More detail below.")

    # 4) Selected district → the one rich, but still calm, drill-down panel,
    #    with the inline "add to My Plan" affordances (E8).
    selected = _selected_or_first(ev, shortlist)
    if selected is not None:
        _planner_brief(selected, specialty, scoped_districts)
        _provider_cards(facilities, selected, specialty, districts)
        _plan_affordances(selected, gap_label)

    # ===================== DEPTH ON DEMAND ==================================
    # The planner-first default view stops here. Heavier tables, charts, methods,
    # and saved-work details are still available, but only after intent.
    st.markdown('<div style="margin-top:.55rem"></div>', unsafe_allow_html=True)
    with ui.detail("More detail: full ranking table"):
        _panel_ranking(ranked_all, gap_label)
    with ui.detail("More detail: condition chart"):
        _panel_at_a_glance(scoped_districts)
    with ui.detail("More detail: method and caveats"):
        _panel_method(scoped_districts, wow_n)
    with ui.detail("My Plan: saved districts and notes"):
        _panel_my_plan()


# =============================== SUB-VIEW PANELS =============================
# Each panel is the swapped-in content for one segmented choice. They hold the
# depth that used to live in three stacked ``ui.detail`` expanders.


def _plan_affordances(selected: pd.Series, gap_label: str) -> None:
    """Inline 'add to My Plan' row on the drill-down: shortlist pill + quick note.

    Persists via ``decisions.toggle_shortlist`` / ``decisions.save_note`` and
    surfaces the returned ``persistence_status()`` detail as a tiny caption."""
    district = str(selected.get("district_name", "") or "").strip()
    state = str(selected.get("state_ut", "") or "").strip()
    geography_id = f"{district}|{state}"
    label = f"{district}, {state}" if state else district
    key = geography_id.replace(" ", "_")

    try:
        shortlisted = decisions.is_shortlisted(geography_id)
    except Exception:
        shortlisted = False

    with _glass_panel():
        ui.panel_header("Add to My Plan")
        c1, c2 = st.columns([1.1, 1.9])
        with c1:
            verb = "★ Shortlisted" if shortlisted else "☆ Shortlist this district"
            if st.button(verb, key=f"gap_short_{key}", width="stretch"):
                status = decisions.toggle_shortlist(
                    geography_id, label=label,
                    reason=f"Flagged from the care-gap leaderboard · {gap_label} "
                           f"{_fmt_num(selected.get('gap'))}.",
                ) or {}
                st.toast("Shortlist updated.", icon="★")
                st.caption(status.get("detail", ""))
        with c2:
            with st.form(key=f"gap_note_{key}", clear_on_submit=True):
                note = st.text_input(
                    "Quick note", key=f"gap_note_in_{key}",
                    placeholder="e.g. call or verify before deploying",
                    label_visibility="collapsed",
                )
                if st.form_submit_button("Save note") and note.strip():
                    status = decisions.save_note(geography_id, note.strip()) or {}
                    st.toast("Note saved.", icon="📝")
                    st.caption(status.get("detail", ""))
        st.caption("Saved actions survive reload. Open My Plan below.")


def _panel_ranking(ranked_all: pd.DataFrame, gap_label: str) -> None:
    """Full leaderboard: action filter + compact counts + the 30-row table."""
    filter_choice = st.segmented_control(
        "Action filter",
        list(ACTION_FILTERS.keys()),
        default="All",
        label_visibility="collapsed",
        key="care_gap_action_filter",
        width="stretch",
    )
    filter_choice = filter_choice or "All"
    allowed = ACTION_FILTERS[filter_choice]
    ranked = (ranked_all if allowed is None
              else ranked_all[ranked_all["planning_category"].isin(allowed)])
    ranked = ranked.head(30).copy()

    if ranked.empty:
        st.info("No districts match this action filter.")
        return

    mix = (
        ranked_all["Action"].value_counts()
        .rename_axis("Action")
        .reset_index(name="Districts")
    )
    ui.panel_header("Action mix")
    st.dataframe(mix, hide_index=True, width="stretch", height=175)

    table = pd.DataFrame({
        "Rank": ranked["Rank"],
        "District": ranked["district_name"],
        "State": ranked["state_ut"],
        "Action": ranked["Action"],
        gap_label: pd.to_numeric(ranked["gap"], errors="coerce"),
        "Need": pd.to_numeric(ranked["health_need_score"], errors="coerce"),
        "Provider trust %": _provider_trust_pct(ranked),
        "Uncertainty": ranked["district_uncertainty_level"].astype(str).str.title(),
        "Decision logic": ranked["Decision logic"],
    })
    ui.panel_header("Action queue")
    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        height=430,
        column_config={
            "Rank": st.column_config.NumberColumn(format="%d"),
            gap_label: st.column_config.NumberColumn(
                f"{gap_label} ▲ worse", format="%.2f",
                help="Higher = more unmet need with weaker provider evidence."),
            "Need": st.column_config.ProgressColumn(
                "Need ▲ worse", format="%.2f", min_value=0, max_value=1,
                help="NFHS health-burden score. Higher is worse."),
            "Provider trust %": st.column_config.ProgressColumn(
                "Provider trust ▲ better", format="%d%%", min_value=0, max_value=100,
                help="Calibrated provider-claim trust from Bayesian evidence plus smoothed checks."),
        },
    )


def _panel_at_a_glance(districts: pd.DataFrame) -> None:
    """Desert fingerprints: table of the worst districts' top condition gap."""
    src = districts.copy()
    src["_gap"] = pd.to_numeric(src.get("care_gap_score"), errors="coerce")
    src = src.dropna(subset=["_gap"]).sort_values("_gap", ascending=False).head(8)
    rows = []
    for _, row in src.iterrows():
        conds = data.district_top_conditions(row, districts, n=1)
        if conds.empty:
            continue
        top = conds.iloc[0]
        rows.append({
            "District": f"{row.get('district_name', '—')}, {row.get('state_ut', '—')}",
            "Care gap": _num(row.get("care_gap_score")),
            "Top condition": top.get("Condition", "—"),
            "District %": top.get("District %", None),
            "National %": top.get("National %", None),
            "Gap pts": top.get("Δ vs national", None),
        })
    if not rows:
        st.caption("No condition indicators available for the current district scope.")
        return
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=320)
    st.caption("Top condition per high-gap district. Technical charts stay out of the default demo path.")


def _panel_method(districts: pd.DataFrame, wow_n: int) -> None:
    """Methodology / honesty note: how the ranking is built and what it is not."""
    _desert = districts.get("zero_facility_desert")
    if _desert is not None:
        n_desert = int(_desert.fillna(False).astype(bool).sum())
        top50 = districts.nlargest(50, "care_gap_score")
        n_top = int(top50.get("zero_facility_desert", pd.Series(False, index=top50.index))
                    .fillna(False).astype(bool).sum())
        st.markdown(
            f"**{n_desert} districts have zero mapped facilities** — and they hold "
            f"**{n_top} of the top 50** care gaps. Facility-count maps miss them; "
            "this ranking surfaces them by leading with NFHS health need and weak "
            "hard-check evidence."
        )
    st.markdown(
        "Care-gap score = **0.55 need · 0.25 supply scarcity · 0.20 low trust**. "
        f"The wow stat above recomputes live across the worst {wow_n} districts."
    )
    st.caption(
        "Source: NFHS-5 district health indicators (2019–21) + web-derived FDR facility "
        "snapshot · 706 districts · observed FDR rows are claims, not a verified facility "
        "census · scores are proxy decision-support, not gold-validated."
    )


def _panel_my_plan() -> None:
    """E8: the visible persistence surface — shortlisted districts, saved notes,
    and a 'Persisted to <backend> ✓' badge. Delegates to the reusable helper in
    ``decisions`` so the logic stays tidy and shared."""
    decisions.render_my_plan()
