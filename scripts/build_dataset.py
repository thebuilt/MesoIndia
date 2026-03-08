#!/usr/bin/env python3
"""Merge source CSV files into a map-ready GeoJSON for the MesoIndia dashboard."""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

STATE_CENTROIDS = {
    "Andhra Pradesh": (15.9129, 79.74),
    "Arunachal Pradesh": (28.218, 94.7278),
    "Assam": (26.2006, 92.9376),
    "Bihar": (25.0961, 85.3131),
    "Chhattisgarh": (21.2787, 81.8661),
    "Delhi": (28.7041, 77.1025),
    "Goa": (15.2993, 74.124),
    "Gujarat": (22.2587, 71.1924),
    "Haryana": (29.0588, 76.0856),
    "Himachal Pradesh": (31.1048, 77.1734),
    "Jammu and Kashmir": (33.7782, 76.5762),
    "Jharkhand": (23.6102, 85.2799),
    "Karnataka": (15.3173, 75.7139),
    "Kerala": (10.8505, 76.2711),
    "Madhya Pradesh": (22.9734, 78.6569),
    "Maharashtra": (19.7515, 75.7139),
    "Manipur": (24.6637, 93.9063),
    "Meghalaya": (25.467, 91.3662),
    "Mizoram": (23.1645, 92.9376),
    "Nagaland": (26.1584, 94.5624),
    "Odisha": (20.9517, 85.0985),
    "Punjab": (31.1471, 75.3412),
    "Rajasthan": (27.0238, 74.2179),
    "Sikkim": (27.533, 88.5122),
    "Tamil Nadu": (11.1271, 78.6569),
    "Telangana": (18.1124, 79.0193),
    "Tripura": (23.9408, 91.9882),
    "Uttar Pradesh": (26.8467, 80.9462),
    "Uttarakhand": (30.0668, 79.0193),
    "West Bengal": (22.9868, 87.855),
}
VALID_STATES = set(STATE_CENTROIDS.keys()) | {"Puducherry", "Chandigarh", "Jammu and Kashmir"}
STATE_FIX = {
    "delhi-ut": "Delhi",
    "nct delhi": "Delhi",
    "j&k-ut": "Jammu and Kashmir",
    "orissa": "Odisha",
    "uttaranchal": "Uttarakhand",
}


def ffloat(val: str) -> float | None:
    try:
        return float(val)
    except Exception:
        return None


def iint(val: str, default: int = 0) -> int:
    try:
        return int(float(val))
    except Exception:
        return default


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def sanitize_state(raw: str) -> str:
    t = (raw or "").strip()
    t = t.replace("IND.", "").replace("India", "").strip(" ,.;")
    t = t.split(" Electronic address")[0].strip()
    if "@" in t:
        t = ""
    low = t.lower()
    if low in STATE_FIX:
        t = STATE_FIX[low]
    if t in VALID_STATES:
        return t
    return ""


def geocode_if_needed(row: dict[str, str], cache: dict[str, list[float]], pause_s: float) -> tuple[float | None, float | None]:
    lat = ffloat(row.get("latitude", ""))
    lon = ffloat(row.get("longitude", ""))
    if lat is not None and lon is not None:
        return lat, lon

    q = ", ".join(x for x in [row.get("hospital", ""), row.get("city", ""), row.get("state", ""), "India"] if x)
    key = q.lower().strip()
    if not key:
        return None, None

    if key in cache:
        return cache[key][0], cache[key][1]

    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": q, "format": "json", "limit": 1}
    )
    req = urllib.request.Request(url, headers={"User-Agent": "MesoIndia/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if payload:
            lat = float(payload[0]["lat"])
            lon = float(payload[0]["lon"])
            cache[key] = [lat, lon]
            time.sleep(pause_s)
            return lat, lon
    except Exception:
        return None, None

    return None, None


def build_features(rows: list[dict[str, str]], cache: dict[str, list[float]], geocode: bool, pause_s: float) -> list[dict]:
    feats: list[dict] = []
    for row in rows:
        row = dict(row)
        row["state"] = sanitize_state(row.get("state", ""))
        if not (row.get("state", "").strip() or row.get("city", "").strip()):
            continue
        lat = ffloat(row.get("latitude", ""))
        lon = ffloat(row.get("longitude", ""))
        if geocode and (lat is None or lon is None):
            lat, lon = geocode_if_needed(row, cache, pause_s)
        if lat is None or lon is None:
            state_name = (row.get("state") or "").strip()
            centroid = STATE_CENTROIDS.get(state_name)
            if centroid:
                lat, lon = centroid
            else:
                continue

        props = dict(row)
        props["case_count"] = iint(row.get("case_count", "1"), 1)
        props["year_start"] = iint(row.get("year_start", "0"), 0)
        props["year_end"] = iint(row.get("year_end", "0"), 0)
        props["catchment_km"] = iint(row.get("catchment_km", "0"), 0)

        feats.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": props,
            }
        )
    return feats


def state_summary(features: list[dict]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for f in features:
        p = f.get("properties", {})
        state = (p.get("state") or "Unknown").strip()
        if state == "":
            state = "Unknown"
        bucket = out.setdefault(state, {"case_count": 0, "sites": 0})
        bucket["case_count"] += iint(str(p.get("case_count", 0)), 0)
        bucket["sites"] += 1
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=str(Path(__file__).resolve().parents[1] / "data"))
    parser.add_argument("--geocode", action="store_true", help="Use Nominatim to geocode missing points")
    parser.add_argument("--pause", type=float, default=1.0)
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    inputs = [
        data_dir / "registry_cases.csv",
        data_dir / "literature_cases.csv",
        data_dir / "community_verified.csv",
    ]
    rows: list[dict[str, str]] = []
    for p in inputs:
        rows.extend(load_csv(p))

    cache_path = data_dir / "geocode_cache.json"
    cache = json.loads(cache_path.read_text("utf-8")) if cache_path.exists() else {}

    features = build_features(rows, cache, geocode=args.geocode, pause_s=args.pause)
    fc = {
        "type": "FeatureCollection",
        "meta": {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "record_count": len(features),
            "source_files": [p.name for p in inputs],
        },
        "features": features,
    }

    (data_dir / "meso_cases.geojson").write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (data_dir / "state_summary.json").write_text(json.dumps(state_summary(features), ensure_ascii=False), encoding="utf-8")
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    print(f"Built {len(features)} map features -> {data_dir / 'meso_cases.geojson'}")


if __name__ == "__main__":
    main()
