#!/usr/bin/env python
"""Build a split-conformal calibration for the facility validity posterior.

WHAT THIS CALIBRATES (and the honest caveat)
--------------------------------------------
There are NO human-verified gold labels in this dataset. So we calibrate the
conformal predictor against a transparent, documented PROXY pseudo-label:

    proxy_valid := trustworthy_supply_signal == True

This means the resulting coverage is "coverage against an automated proxy",
NOT measured accuracy against human-verified ground truth. The artifact is
explicitly labelled provisional so the app never overclaims. When real
gold/silver labels exist, swap the pseudo-label for verified labels and the same
machinery yields a genuine calibration.

METHOD (split conformal, Concept 3)
-----------------------------------
1. Compute the Bayesian validity posterior for every facility (trust.py).
2. Split rows into calibration / evaluation halves (deterministic seed).
3. On the calibration half, restricted to proxy-valid rows, compute the
   nonconformity score s = 1 - posterior, and take the (1 - alpha) empirical
   quantile q_hat (with the finite-sample conformal correction
   ceil((n+1)(1-alpha)) / n).
4. Also derive a wider "stale" quantile for the {valid, stale, uncertain} set.
5. Report empirical coverage of the proxy-valid class on the evaluation half.

OUTPUTS (idempotent)
--------------------
- output/data/conformal_calibration.json  (q_hat, stale_q_hat, alpha, coverage,
  n_calibration, method notes, provisional flag)
- output/data/conformal_facility_sets.csv  (unique_id, validity_posterior,
  conformal_set, conformal_decision)

Run:
    .venv/bin/python scripts/build_conformal_calibration.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

# Make `app/lib` importable when run from the repo root.
ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from lib import config, data, trust  # noqa: E402

ALPHA = 0.10            # target miscoverage for the "valid" proxy class
CAL_FRACTION = 0.5      # split-conformal calibration share
SEED = 13


def _conformal_quantile(scores: np.ndarray, alpha: float) -> float:
    """Finite-sample conformal quantile of nonconformity scores."""
    n = len(scores)
    if n == 0:
        return float(trust.DEFAULT_CALIBRATION["q_hat"])
    level = math.ceil((n + 1) * (1.0 - alpha)) / n
    level = min(max(level, 0.0), 1.0)
    return float(np.quantile(np.sort(scores), level, method="higher"))


def main() -> int:
    out_dir = Path(config.data_dir())
    out_dir.mkdir(parents=True, exist_ok=True)

    facilities = data.load_facilities()
    scored = trust.facility_validity_posterior(facilities)

    posterior = scored["validity_posterior"].to_numpy(dtype=float)
    proxy_valid = (
        scored.get("trustworthy_supply_signal", False)
        .astype("boolean").fillna(False).to_numpy(dtype=bool)
    )
    n_total = len(scored)

    # Deterministic split.
    rng = np.random.default_rng(SEED)
    idx = np.arange(n_total)
    rng.shuffle(idx)
    cut = int(round(n_total * CAL_FRACTION))
    cal_idx, eval_idx = idx[:cut], idx[cut:]

    # Calibration: proxy-valid rows only (the conformal "true class").
    cal_valid_mask = proxy_valid[cal_idx]
    cal_scores = (1.0 - posterior[cal_idx])[cal_valid_mask]  # nonconformity s = 1 - p
    n_cal = int(cal_scores.size)

    q_hat = _conformal_quantile(cal_scores, ALPHA)
    # Wider band for the {valid, stale, uncertain} set: the (1 - alpha/2) quantile.
    stale_q_hat = _conformal_quantile(cal_scores, ALPHA / 2.0)
    # Keep within sensible bounds.
    q_hat = float(np.clip(q_hat, 0.05, 0.95))
    stale_q_hat = float(np.clip(max(stale_q_hat, q_hat + 0.05), q_hat, 0.99))

    # Evaluation: empirical coverage of the proxy-valid class.
    eval_valid_mask = proxy_valid[eval_idx]
    eval_scores_valid = (1.0 - posterior[eval_idx])[eval_valid_mask]
    n_eval_valid = int(eval_scores_valid.size)
    coverage = float((eval_scores_valid <= q_hat).mean()) if n_eval_valid else float("nan")

    calibration = {
        "alpha": ALPHA,
        "target_coverage": round(1.0 - ALPHA, 4),
        "q_hat": round(q_hat, 4),
        "stale_q_hat": round(stale_q_hat, 4),
        "empirical_coverage_on_proxy": round(coverage, 4) if not math.isnan(coverage) else None,
        "n_calibration": n_cal,
        "n_eval_valid": n_eval_valid,
        "n_total": n_total,
        "method": "split_conformal_proxy",
        "nonconformity": "s = 1 - validity_posterior; valid in set iff s <= q_hat",
        "calibration_target": "trustworthy_supply_signal (PROXY pseudo-label, not human-verified gold)",
        "seed": SEED,
        "cal_fraction": CAL_FRACTION,
        "provisional": True,
        "notes": (
            "Calibrated against an AUTOMATED PROXY pseudo-label, not human-verified "
            "ground truth. Coverage is coverage of the proxy-valid class, not measured "
            "accuracy. Replace the pseudo-label with verified gold/silver labels to get "
            "a genuine calibration; the split-conformal machinery is unchanged."
        ),
    }

    cal_path = out_dir / "conformal_calibration.json"
    cal_path.write_text(json.dumps(calibration, indent=2), encoding="utf-8")

    # Per-facility conformal sets using the freshly built calibration.
    sets_df = trust.conformal_label_sets(scored, calibration=calibration)
    cols = ["unique_id", "validity_posterior", "validity_action",
            "conformal_set", "conformal_decision"]
    cols = [c for c in cols if c in sets_df.columns]
    sets_path = out_dir / "conformal_facility_sets.csv"
    sets_df[cols].to_csv(sets_path, index=False)

    print(f"Wrote {cal_path}")
    print(json.dumps(calibration, indent=2))
    print(f"Wrote {sets_path} ({len(sets_df):,} rows)")
    print("Conformal decision mix:")
    print(sets_df["conformal_decision"].value_counts().to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
