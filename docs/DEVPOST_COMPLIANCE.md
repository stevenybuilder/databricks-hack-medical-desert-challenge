# Devpost Compliance — Databricks Apps & Agents for Good Hackathon 2026

_Last updated: 2026-06-15 · Source: https://dais-for-good-2026.devpost.com/_

Event: Databricks Apps & Agents for Good Hackathon 2026 (DAIS, Moscone South, SF).
Deadline: **June 16, 2026 @ 2:30pm PDT**. Prizes: $10k / $5k / $2.5k.
Our track: **#2 Medical Desert Planner** — "Aggregate trust-weighted evidence across geography to identify care gaps."

Legend: ✅ done · 🟡 in progress · ⬜ planned (phase noted)

## Core requirements

| # | Requirement | Status | Where / how |
|---|---|---|---|
| 1 | Run as a Databricks App on **Free Edition** | 🟡 | `app/app.yaml` + Streamlit ready; cleaned tables now in UC (`workspace.default.hackathon_*`); `DATA_BACKEND=warehouse` path wired. Deploy = Phase 5. |
| 2 | Use the provided facility dataset (10k records, 51 cols) | ✅ | Built on the cleaned FDR facilities + India Post + NFHS-5. |
| 3 | Support non-technical workflows | 🟡 | Persona "Dr. Amara"; Map tab (specialty → hexbins + clickable facilities, click-to-fly) + Top Care Gaps tab (leaderboard → region detail). Save/persist remains (Phase 3). |
| 4 | **Cite the underlying facility text** for any important claim/score/ranking | 🟡 | Facility detail card cites `source_urls` + `claim_text`; region detail cites `sample_source_urls`/`sample_claim_evidence`. Per-claim verification deepens in Phase 4. |
| 5 | **Communicate uncertainty** instead of presenting weak evidence as fact | 🟡 | Honest labels ("passed checks" ≠ "verified"), needs-review %, contradicted count, grey=unknown hexes, scores labeled proxies, semantic missingness, confidence intervals, active uncertainty queues, and geocoder/source-agreement reason codes. |
| 6 | **Persist user actions** (notes, overrides, shortlists, scenarios, review decisions) | ⬜ (Phase 3) | Write shortlists/notes plus active uncertainty queue decisions to Delta tables in `workspace.default`. |

## Judging criteria (exact wording → our answer)

| Criterion | Our answer |
|---|---|
| "Is the user clear? Are the workflow and tradeoffs thoughtful?" | Single persona (visiting/volunteer clinician); one decision per screen; build-vs-verify tradeoff surfaced via `planning_category`. |
| "Are outputs grounded in citations? Is uncertainty handled honestly?" | Every claim cites `source_urls`/`claim_text`; uncertainty is first-class (needs-review, contradicted, CIs, semantic missingness, active uncertainty queue, Google/Mappls metadata). Never call proxy claims "verified." |
| "Does the app work reliably in a live demo? Are Databricks capabilities used well?" | Databricks App + Unity Catalog Delta tables + SQL warehouse + (Phase 4) Foundation Model API. Fast-fallback build order = always demoable. |
| "Did the team go beyond the minimum workflow in a meaningful way?" | Trust/uncertainty engine today, plus a planned golden facility prediction layer for new map-selected locations; condition-aware specialty matching; build/verify/refer recommendations. |

## Submission checklist

| Item | Status | Note |
|---|---|---|
| Public **Git repository** | ⬜ | Init repo; include `app/`, `docs/`, pipeline notebooks. |
| **Live Databricks App** URL | ⬜ (Phase 5) | Deploy on Free Edition reading UC tables. |
| **3-minute demo** (video/live) | ⬜ (Phase 5) | Script: leaderboard → real-desert district → ocean-hospital "do not trust blindly" → uncertainty queue + confidence intervals. |

## Databricks capabilities we use (for the "uses Databricks well" criterion)

- **Unity Catalog** — canonical cleaned Delta tables `workspace.default.hackathon_*` + Volume `hackathon_cleaned`.
- **SQL Warehouse** — app reads via `databricks-sql-connector` when `DATA_BACKEND=warehouse`.
- **Databricks Apps** — Streamlit app (`app.yaml`) on Free Edition.
- **Foundation Model API** — (Phase 4) optional claim summarization / "Ask AI".
- **Delta** — persistence of user actions, uncertainty queue decisions, trust model versions, and predictive scores.

## Gaps to close before submission (priority order)
1. Phase 2: citations in region/facility detail (req #4) — highest unmet requirement.
2. Phase 3: persistence + active uncertainty queue (req #6 and uncertainty story).
3. Phase 5: deploy live app (req #1) + 3-min demo + git repo.
4. Phase 4: proxy trust/uncertainty engine with confidence intervals and sensitivity checks (the "beyond minimum" criterion).
