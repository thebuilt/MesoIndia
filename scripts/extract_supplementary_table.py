#!/usr/bin/env python3
"""Extract hospital rows from the supplementary mesothelioma PDF table into CSV."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from pypdf import PdfReader

STATE_HINTS = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat",
    "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh",
    "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab",
    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh",
    "Uttarakhand", "West Bengal", "Chandigarh", "Delhi", "Delhi-UT", "J&K-UT", "Puducherry",
    "Jammu and Kashmir",
]
STATE_CANON = {
    "Delhi-UT": "Delhi",
    "J&K-UT": "Jammu and Kashmir",
}


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def canonical_state(state: str) -> str:
    state = normalize_space(state)
    return STATE_CANON.get(state, state)


def fold_rows(table_text: str) -> list[str]:
    lines = [normalize_space(x) for x in table_text.splitlines() if normalize_space(x)]
    out: list[str] = []
    cur = ""
    for line in lines:
        if re.match(r"^\d{1,3}\s+", line):
            if cur:
                out.append(cur)
            cur = line
        else:
            cur = f"{cur} {line}".strip()
    if cur:
        out.append(cur)
    return out


def split_name_and_counts(row_text: str) -> tuple[str, list[int]]:
    m = re.search(r"((?:\s+\d+)+)\s*$", row_text)
    if not m:
        return row_text.strip(), []
    nums = [int(x) for x in re.findall(r"\d+", m.group(1))]
    left = row_text[: m.start()].strip()
    return left, nums


def extract_state(name_blob: str) -> tuple[str, str]:
    for s in sorted(STATE_HINTS, key=len, reverse=True):
        if name_blob.endswith(s):
            return name_blob[: -len(s)].strip(" ,"), canonical_state(s)
    return name_blob, ""


def parse_rows(text: str) -> list[dict[str, str]]:
    start = text.find("Supplementary Table S1")
    end = text.find("Table S1:")
    if start >= 0:
        text = text[start:end if end > start else None]

    rows: list[dict[str, str]] = []
    for row in fold_rows(text):
        m = re.match(r"^(\d{1,3})\s+(.*)$", row)
        if not m:
            continue
        row_id = m.group(1)
        payload = m.group(2)
        hospital_blob, nums = split_name_and_counts(payload)
        if not nums:
            # keep row with unknown total as 0 so the site is visible for manual completion
            total = 0
        else:
            total = nums[-1]
            # Guard against accidental capture of the table grand total (2213) in the last row.
            if total > 1500 and len(nums) > 1:
                total = nums[-2]

        hospital_plus_city, state = extract_state(hospital_blob)

        city = ""
        hospital = hospital_plus_city
        if "," in hospital_plus_city:
            left, right = hospital_plus_city.rsplit(",", 1)
            hospital = normalize_space(left)
            city = normalize_space(right)

        rows.append(
            {
                "record_id": f"REG-EXTRACT-{row_id.zfill(3)}",
                "source_type": "Hospital Registry",
                "source_name": "NCRP Supplementary Table S1",
                "study_or_registry": "iutld_pha_24.0003 supplementary table",
                "hospital": normalize_space(hospital),
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
