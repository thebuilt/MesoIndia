#!/usr/bin/env python3
"""Convert Survey of India STATE_BOUNDARY shapefile to web GeoJSON (EPSG:4326)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import shapefile
from pyproj import CRS, Transformer

NAME_FIX = {
    "ANDAMAN & NICOBAR": "Andaman and Nicobar",
    "ANDHRA PRADESH": "Andhra Pradesh",
    "ARUNACHAL PRADESH": "Arunachal Pradesh",
    "ASSAM": "Assam",
    "BIHAR": "Bihar",
    "CHANDIGARH": "Chandigarh",
    "CHHATTISGARH": "Chhattisgarh",
    "DADRA & NAGAR HAVELI & DAMAN & DIU": "Dadra and Nagar Haveli and Daman and Diu",
    "DELHI": "Delhi",
    "GOA": "Goa",
    "GUJARAT": "Gujarat",
    "HARYANA": "Haryana",
    "HIMACHAL PRADESH": "Himachal Pradesh",
    "JAMMU AND KASHMIR": "Jammu and Kashmir",
    "JHARKHAND": "Jharkhand",
    "KARNATAKA": "Karnataka",
    "KERALA": "Kerala",
    "LADAKH": "Ladakh",
    "LAKSHADWEEP": "Lakshadweep",
    "MADHYA PRADESH": "Madhya Pradesh",
    "MAHARASHTRA": "Maharashtra",
    "MANIPUR": "Manipur",
    "MEGHALAYA": "Meghalaya",
    "MIZORAM": "Mizoram",
    "NAGALAND": "Nagaland",
    "ODISHA": "Odisha",
    "PUDUCHERRY": "Puducherry",
    "PUNJAB": "Punjab",
    "RAJASTHAN": "Rajasthan",
    "SIKKIM": "Sikkim",
    "TAMIL NADU": "Tamil Nadu",
    "TELANGANA": "Telangana",
    "TRIPURA": "Tripura",
    "UTTAR PRADESH": "Uttar Pradesh",
    "UTTARAKHAND": "Uttarakhand",
    "WEST BENGAL": "West Bengal",
}


def sq_seg_dist(p, a, b):
    x, y = a
    dx = b[0] - x
    dy = b[1] - y
    if dx != 0 or dy != 0:
        t = ((p[0] - x) * dx + (p[1] - y) * dy) / (dx * dx + dy * dy)
        if t > 1:
            x, y = b
        elif t > 0:
            x += dx * t
            y += dy * t
    dx = p[0] - x
    dy = p[1] - y
    return dx * dx + dy * dy


def rdp(points, eps):
    if len(points) <= 2:
        return points
    first, last = points[0], points[-1]
    max_dist = -1
    idx = 0
    for i in range(1, len(points) - 1):
        d = sq_seg_dist(points[i], first, last)
        if d > max_dist:
            max_dist = d
            idx = i
    if max_dist > eps * eps:
        left = rdp(points[: idx + 1], eps)
        right = rdp(points[idx:], eps)
        return left[:-1] + right
    return [first, last]


def split_parts(shape) -> list[list[tuple[float, float]]]:
    points = shape.points
    parts = list(shape.parts) + [len(points)]
    rings = []
    for i in range(len(parts) - 1):
        ring = points[parts[i] : parts[i + 1]]
        if len(ring) >= 4:
            rings.append(ring)
    return rings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shp", required=True)
    parser.add_argument("--prj", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--epsilon", type=float, default=0.01, help="Simplification tolerance in degrees")
    args = parser.parse_args()

    shp_path = Path(args.shp)
    prj_wkt = Path(args.prj).read_text(encoding="utf-8")
    out_path = Path(args.out)

    source_crs = CRS.from_wkt(prj_wkt)
    to_wgs84 = Transformer.from_crs(source_crs, CRS.from_epsg(4326), always_xy=True)

    reader = shapefile.Reader(str(shp_path), encoding="utf-8")
    features = []

    for sr in reader.shapeRecords():
        state_raw = str(sr.record["STATE"] or "").strip()
        if not state_raw or state_raw.startswith("DISPUTED"):
            continue

        rings = split_parts(sr.shape)
        if not rings:
            continue

        polygons = []
        for ring in rings:
            coords = []
            for x, y in ring:
                lon, lat = to_wgs84.transform(x, y)
                coords.append([lon, lat])
            if len(coords) > 6:
                coords = rdp(coords, args.epsilon)
            if len(coords) < 4:
                continue
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            polygons.append([coords])

        geom = {"type": "MultiPolygon", "coordinates": polygons}
        state_name = NAME_FIX.get(state_raw, state_raw.title())
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "NAME_1": state_name,
                    "STATE_RAW": state_raw,
                    "SOURCE": "Survey of India STATE_BOUNDARY",
                },
                "geometry": geom,
            }
        )

    fc = {"type": "FeatureCollection", "features": features}
    out_path.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {len(features)} features -> {out_path}")


if __name__ == "__main__":
    main()
