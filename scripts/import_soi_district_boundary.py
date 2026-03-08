#!/usr/bin/env python3
"""Convert Survey of India DISTRICT_BOUNDARY shapefile to simplified WGS84 GeoJSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import shapefile
from pyproj import CRS, Transformer

STATE_FIX = {
    "ANDAMAN & NICOBAR": "Andaman and Nicobar",
    "DADRA & NAGAR HAVELI & DAMAN & DIU": "Dadra and Nagar Haveli and Daman and Diu",
    "JAMMU AND KASHMIR": "Jammu and Kashmir",
    "ODISHA": "Odisha",
}


def sq_dist(a, b):
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return dx * dx + dy * dy


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


def split_parts(shape):
    points = shape.points
    parts = list(shape.parts) + [len(points)]
    for i in range(len(parts) - 1):
        ring = points[parts[i] : parts[i + 1]]
        if len(ring) >= 4:
            yield ring


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--shp", required=True)
    ap.add_argument("--prj", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--epsilon", type=float, default=0.01, help="Simplification tolerance in degrees")
    args = ap.parse_args()

    source_crs = CRS.from_wkt(Path(args.prj).read_text(encoding="utf-8"))
    tx = Transformer.from_crs(source_crs, CRS.from_epsg(4326), always_xy=True)

    reader = shapefile.Reader(args.shp, encoding="utf-8")
    features = []

    for sr in reader.shapeRecords():
        state_raw = str(sr.record["STATE_UT"] or "").strip()
        district = str(sr.record["DISTRICT"] or "").strip()
        if not state_raw or state_raw.startswith("DISPUTED"):
            continue

        polygons = []
        for ring in split_parts(sr.shape):
            coords = [[*tx.transform(x, y)] for x, y in ring]
            if len(coords) > 6:
                coords = rdp(coords, args.epsilon)
            if len(coords) < 4:
                continue
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            polygons.append([coords])

        if not polygons:
            continue

        features.append(
            {
                "type": "Feature",
                "properties": {
                    "state": STATE_FIX.get(state_raw, state_raw.title()),
                    "district": district.title(),
                },
                "geometry": {"type": "MultiPolygon", "coordinates": polygons},
            }
        )

    out = Path(args.out)
    out.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {len(features)} district features -> {out}")


if __name__ == "__main__":
    main()
