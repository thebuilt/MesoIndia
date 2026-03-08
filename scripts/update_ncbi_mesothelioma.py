#!/usr/bin/env python3
"""Fetch India mesothelioma literature from NCBI E-utilities and extract hospital-level records."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_QUERY = (
    '(mesothelioma[Title/Abstract] OR "mesothelioma"[MeSH Terms]) '
    'AND (india[Title/Abstract] OR indian[Title/Abstract])'
)

HOSPITAL_PATTERN = re.compile(
    r"\b("
    r"[A-Z][A-Za-z0-9&().,'/-]*"
    r"(?:\s+[A-Z][A-Za-z0-9&().,'/-]*){0,11}\s+"
    r"(?:Hospital|Medical College|Cancer Centre|Cancer Center|Institute|AIIMS|PGI|PGIMER|"
    r"Memorial Hospital|Research Centre|Research Center|Clinic|College|University)"
    r")\b"
)
PMID_RE = re.compile(r"\b(\d{5,9})\b")
PMCID_RE = re.compile(r"\b(PMC\d+)\b", re.IGNORECASE)
INDIA_TERMS = {
    "india", "indian", "new delhi", "delhi", "mumbai", "bombay", "chennai", "madras",
    "kolkata", "calcutta", "bengaluru", "bangalore", "hyderabad", "ahmedabad", "pune",
    "lucknow", "kanpur", "jaipur", "surat", "visakhapatnam", "vadodara", "coimbatore",
    "patna", "guwahati", "kochi", "kozhikode", "bhopal", "indore", "chandigarh", "raipur",
    "haryana", "assam", "gujarat", "maharashtra", "kerala", "tamil nadu", "karnataka",
    "uttar pradesh", "west bengal", "rajasthan", "odisha", "andhra pradesh", "telangana",
}
STATE_HINTS = {
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh", "goa", "gujarat",
    "haryana", "himachal pradesh", "jharkhand", "karnataka", "kerala", "madhya pradesh",
    "maharashtra", "manipur", "meghalaya", "mizoram", "nagaland", "odisha", "punjab",
    "rajasthan", "sikkim", "tamil nadu", "telangana", "tripura", "uttar pradesh",
    "uttarakhand", "west bengal", "delhi", "jammu", "kashmir", "ladakh", "puducherry"
}
NON_INDIA_COUNTRIES = {
    "usa", "u.s.a", "united states", "uk", "united kingdom", "saudi arabia", "taiwan",
    "china", "japan", "australia", "italy", "france", "germany", "canada", "singapore",
    "korea", "spain", "brazil", "iran", "qatar", "sweden", "norway", "russia"
}


def fetch_url(url: str, timeout: int = 60) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


def safe_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return "".join(node.itertext()).strip()


def chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def extract_hospital(*texts: str) -> str:
    corpus = " | ".join(normalize_space(t) for t in texts if t)
    for m in HOSPITAL_PATTERN.finditer(corpus):
        candidate = m.group(1).strip(" .,;")
        if 8 <= len(candidate) <= 120:
            return candidate
    return ""


def extract_city_state(affiliation: str) -> tuple[str, str]:
    parts = [p.strip() for p in affiliation.split(",") if p.strip()]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return "", ""
    city = parts[-2] if len(parts) >= 2 else ""
    state = parts[-1].replace("India", "").strip()
    if state.lower() in {"india", ""}:
        state = ""
    return city, state


def looks_india_record(title: str, abstract: str) -> bool:
    blob = normalize_space(f"{title} {abstract}").lower()
    if not blob:
        return False
    if any(t in blob for t in INDIA_TERMS):
        return True
    return False


def esearch(term: str, email: str, api_key: str, retmax: int) -> list[str]:
    params = {
        "db": "pubmed",
        "retmode": "json",
        "retmax": str(retmax),
        "term": term,
        "sort": "pub date",
        "email": email,
    }
    if api_key:
        params["api_key"] = api_key
    url = f"{BASE}/esearch.fcgi?{urllib.parse.urlencode(params)}"
    payload = json.loads(fetch_url(url).decode("utf-8"))
    return payload.get("esearchresult", {}).get("idlist", [])


def efetch_details(pmids: list[str], email: str, api_key: str, pause_s: float) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for batch in chunks(pmids, 80):
        params = {
            "db": "pubmed",
            "retmode": "xml",
            "id": ",".join(batch),
            "email": email,
        }
        if api_key:
            params["api_key"] = api_key
        url = f"{BASE}/efetch.fcgi?{urllib.parse.urlencode(params)}"
        root = ET.fromstring(fetch_url(url))

        for article in root.findall(".//PubmedArticle"):
            pmid = safe_text(article.find(".//MedlineCitation/PMID"))
            title = safe_text(article.find(".//ArticleTitle"))
            abstract = " ".join(safe_text(x) for x in article.findall(".//Abstract/AbstractText")).strip()
            journal = safe_text(article.find(".//Journal/Title"))
            year = safe_text(article.find(".//PubDate/Year"))
            if not year:
                medline_date = safe_text(article.find(".//PubDate/MedlineDate"))
                ym = re.search(r"(19|20)\d{2}", medline_date)
                year = ym.group(0) if ym else ""

            affs = [safe_text(a) for a in article.findall(".//AffiliationInfo/Affiliation")]
            affiliation = affs[0] if affs else ""
            if not looks_india_record(title, abstract):
                continue

            article_ids = [safe_text(x) for x in article.findall(".//ArticleId")]
            pmcid = ""
            doi = ""
            for aid in article.findall(".//ArticleId"):
                id_type = (aid.attrib.get("IdType") or "").lower()
                val = safe_text(aid)
                if id_type == "pmc" and val:
                    pmcid = val if val.upper().startswith("PMC") else f"PMC{val}"
                if id_type == "doi" and val:
                    doi = val

            hospital = extract_hospital(title, abstract)
            city, state = extract_city_state(affiliation)

            out.append(
                {
                    "record_id": f"LIT-PMID-{pmid or 'UNKNOWN'}",
                    "source_type": "NCBI Literature",
                    "source_name": "PubMed/PMC",
                    "pmid": pmid,
                    "pmcid": pmcid,
                    "title": normalize_space(title),
                    "hospital": hospital,
                    "city": city,
                    "state": state,
                    "icd10": "C45",
                    "meso_type": "All",
                    "case_count": "1",
                    "year_start": year,
                    "year_end": year,
                    "latitude": "",
                    "longitude": "",
                    "catchment_km": "90",
                    "provenance_url": (
                        f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
                        if pmcid
                        else (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "")
                    ),
                    "notes": f"doi:{doi}" if doi else "",
                }
            )

        time.sleep(pause_s)

    return out


def write_csv(rows: list[dict[str, str]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "record_id",
        "source_type",
        "source_name",
        "pmid",
        "pmcid",
        "title",
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

    dedup: dict[str, dict[str, str]] = {}
    for row in rows:
        key = row.get("pmid") or row.get("pmcid") or row.get("title", "").lower()
        dedup[key] = row

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sorted(dedup.values(), key=lambda r: (r.get("year_start", ""), r.get("pmid", "")), reverse=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--email", default="mesoindia@example.org")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--retmax", type=int, default=2500)
    parser.add_argument("--pause", type=float, default=0.35)
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parents[1] / "data" / "literature_cases.csv"),
    )
    args = parser.parse_args()

    pmids = esearch(args.query, args.email, args.api_key, args.retmax)
    rows = efetch_details(pmids, args.email, args.api_key, args.pause)
    write_csv(rows, Path(args.output))
    print(f"Fetched {len(rows)} records. Wrote {args.output} at {dt.datetime.utcnow().isoformat()}Z")


if __name__ == "__main__":
    main()
