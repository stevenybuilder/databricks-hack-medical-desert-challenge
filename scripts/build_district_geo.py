"""Stage 1 of the VF-Match-style redesign — the data foundation.

1. District CENTROIDS (lat/lon) for all 706 districts, derived from the India Post
   PIN directory (independent of facilities, so the 212 zero-facility deserts get
   coordinates too). This lets us finally render districts — including deserts — as
   hexes on the map, mirroring VF Match's "uncovered population" layer.

2. TIERED TRUST on facilities (High / Medium / Verify) to replace the misleading
   binary "77% need review". Tiers come from the same signals, just graduated.

Run after add_zero_facility_districts.py:
    .venv/bin/python scripts/build_district_geo.py
"""
from __future__ import annotations
import sys, types
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
for _m in ("matplotlib", "matplotlib.pyplot", "seaborn"):
    sys.modules.setdefault(_m, types.ModuleType(_m))
from build_hackathon_dataset import normalize_state, normalize_district  # noqa: E402

DATA = REPO / "output" / "data"
DISTRICT_CSV = DATA / "district_health_facility_cleaned.csv"
FACILITY_CSV = DATA / "facility_health_cleaned.csv"
INDIA_POST = DATA / "raw_india_post_pincode_directory.csv"


def _key(state, district):
    return f"{normalize_state(state)}|{normalize_district(district, state)}"


def build_district_centroids() -> pd.DataFrame:
    ip = pd.read_csv(INDIA_POST, low_memory=False)
    ip["lat"] = pd.to_numeric(ip["latitude"], errors="coerce")
    ip["lon"] = pd.to_numeric(ip["longitude"], errors="coerce")
    # India bbox guard (drops bad geocodes before averaging).
    ok = ip["lat"].between(6, 38) & ip["lon"].between(68, 98)
    ip = ip[ok].copy()
    ip["dkey"] = ip.apply(lambda r: _key(r["statename"], r["district"]), axis=1)
    cen = ip.groupby("dkey").agg(
        district_latitude=("lat", "median"),   # median = robust to outlier offices
        district_longitude=("lon", "median"),
        district_pincode_points=("pincode", "nunique"),
    ).reset_index()
    return cen


def add_centroids():
    d = pd.read_csv(DISTRICT_CSV, low_memory=False)
    d["dkey"] = d.apply(lambda r: _key(r["state_ut"], r["district_name"]), axis=1)
    cen = build_district_centroids()
    drop = [c for c in ("district_latitude", "district_longitude", "district_pincode_points") if c in d.columns]
    d = d.drop(columns=drop)
    d = d.merge(cen, on="dkey", how="left").drop(columns=["dkey"])
    d.to_csv(DISTRICT_CSV, index=False)
    matched = int(d["district_latitude"].notna().sum())
    desert_matched = int(d.loc[d.get("zero_facility_desert", False) == True,  # noqa: E712
                               "district_latitude"].notna().sum()) if "zero_facility_desert" in d else 0
    print(f"District centroids: {matched}/{len(d)} matched "
          f"({desert_matched} of the zero-facility deserts now mappable)")


def add_trust_tiers():
    f = pd.read_csv(FACILITY_CSV, low_memory=False)
    readiness = pd.to_numeric(f.get("data_readiness_score"), errors="coerce")
    join_conf = pd.to_numeric(f.get("join_confidence"), errors="coerce")
    geo_ok = f.get("geo_quality").eq("plausible")
    strict = f.get("trustworthy_supply_signal").fillna(False).astype(bool)
    medium = (readiness >= 0.65) & (join_conf >= 0.80) & geo_ok
    f["trust_tier"] = np.where(strict, "High",
                       np.where(medium, "Medium", "Verify"))
    f.to_csv(FACILITY_CSV, index=False)
    counts = f["trust_tier"].value_counts()
    n = len(f)
    print("Trust tiers:", {k: f"{int(v)} ({v/n*100:.0f}%)" for k, v in counts.items()})


if __name__ == "__main__":
    add_centroids()
    add_trust_tiers()
