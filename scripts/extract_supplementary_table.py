#!/usr/bin/env python3
"""Extract hospital rows from the supplementary mesothelioma PDF table into CSV."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from pypdf import PdfReader

STATE_HINTS = [
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chhattisgarh",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
    "Delhi",
    "Jammu and Kashmir",
]

ROW_RE = re.compile(r"\b(\d{1,3})\s+([A-Za-z][A-Za-z0-9 .,&()'/-]{6,}?)\s+(" + "|".join(re.escape(s) for s in STATE_HINTS) + r")\s+([0-9\s]{1,80})")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for m in ROW_RE.finditer(text):
        row_id = m.group(1)
        hospital_blob = normalize_space(m.group(2))
        state = normalize_space(m.group(3))
        nums = [int(x) for x in re.findall(r"\d+", m.group(4))]
        if not nums:
            continue
        total = nums[-1]

        city = ""
        hospital = hospital_blob
        if "," in hospital_blob:
            left, right = hospital_blob.rsplit(",", 1)
            hospital = normalize_space(left)
            city = normalize_space(right)

        rows.append(
            {
                "record_id": f"REG-EXTRACT-{row_id.zfill(3)}",
                "source_type": "Hospital Registry",
                "source_name": "NCRP Supplementary Table S1",
                "study_or_registry": "iutld_pha_24.0003 supplementary table",
                "hospital": hospital,
                "city": city,
                "state": state,
                "icd10": "C45",
                "meso_type": "All",
                "case_count": str(total),
                "year_start": "2012",
                "year_end": "2023",
                "latitude": "",
                "longitude": "",
                "catchment_km": "120",
                "provenance_url": "https://doi.org/10.5588/pha.24.0003",
                "notes": "Auto-extracted row, verify manually before publication",
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    reader = PdfReader(args.pdf)
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    rows = parse_rows(text)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "record_id",
        "source_type",
        "source_name",
        "study_or_registry",
        "hospital",
        "city",
        "state",
        "icd10",
        "meso_type",
        "case_count",
        "year_start",
        "year_end",
        "latitude",
        "longitude",
        "catchment_km",
        "provenance_url",
        "notes",
    ]

    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"Extracted {len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
