#!/usr/bin/env python3
"""Fetch India asbestos literature from NCBI E-utilities and extract hospital-level records."""

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
    '(asbestos[Title/Abstract] OR "asbestos"[MeSH Terms]) '
    'AND (india[Title/Abstract] OR indian[Title/Abstract])'
)
QUERY_BUCKETS = [
    DEFAULT_QUERY,
    '("asbestosis"[Title/Abstract] OR "asbestos exposure"[Title/Abstract] '
    'OR "asbestos-related"[Title/Abstract]) '
    'AND (india[Title/Abstract] OR indian[Title/Abstract])',
    '(asbestos[Title/Abstract] OR asbestosis[Title/Abstract]) AND '
    '(rajasthan[Title/Abstract] OR gujarat[Title/Abstract] OR maharashtra[Title/Abstract] '
    'OR delhi[Title/Abstract] OR tamil nadu[Title/Abstract] OR karnataka[Title/Abstract] '
    'OR kerala[Title/Abstract] OR telangana[Title/Abstract] OR haryana[Title/Abstract] '
    'OR punjab[Title/Abstract] OR west bengal[Title/Abstract] OR andhra pradesh[Title/Abstract])',
    '(asbestos[Title/Abstract] OR asbestosis[Title/Abstract]) AND '
    '("case report"[Title/Abstract] OR "case series"[Title/Abstract] OR clinicopathological[Title/Abstract] '
    'OR histomorphological[Title/Abstract] OR immunohistochemical[Title/Abstract]) AND '
    '(india[Affiliation] OR india[Title/Abstract] OR indian[Title/Abstract])',
]

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
INDIA_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Delhi",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Jammu and Kashmir",
    "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
    "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal", "Puducherry",
]
STATE_ALIASES = {
    "j&k-ut": "Jammu and Kashmir",
    "jammu kashmir": "Jammu and Kashmir",
    "delhi-ut": "Delhi",
    "nct delhi": "Delhi",
    "orissa": "Odisha",
}
CITY_TO_STATE = {
    "mumbai": "Maharashtra", "chennai": "Tamil Nadu", "new delhi": "Delhi", "delhi": "Delhi",
    "kolkata": "West Bengal", "bengaluru": "Karnataka", "bangalore": "Karnataka",
    "hyderabad": "Telangana", "ahmedabad": "Gujarat", "jaipur": "Rajasthan",
    "lucknow": "Uttar Pradesh", "coimbatore": "Tamil Nadu", "visakhapatnam": "Andhra Pradesh",
    "guwahati": "Assam", "raipur": "Chhattisgarh", "varanasi": "Uttar Pradesh",
}
EXCLUDE_GEO_TERMS = {
    "hong kong", "china", "united states", " usa", "u.s.a", "united kingdom", "uk ",
    "saudi arabia", "taiwan", "italy", "germany", "singapore", "australia", "japan",
}
MESO_TERMS = (
    "asbestos",
    "asbestosis",
    "asbestos-related",
    "occupational exposure",
    "chrysotile",
    "tremolite",
)
PRIMARY_STUDY_CUES = (
    "case report",
    "case series",
    "clinicopathological study",
    "histomorphological",
    "retrospective",
    "prospective",
    "single-center",
    "single centre",
    "tertiary care hospital",
    "tertiary cancer care center",
    "experience from",
    "outcomes from",
    "study of",
    "our experience",
    "institutional experience",
    "consecutive",
    "patients with",
    "diagnosed with",
)
NON_PRIMARY_CUES = (
    "commentary",
    "consensus",
    "guideline",
    "guidelines",
    "review of literature",
    "review article",
    "narrative review",
    "systematic review",
    "meta-analysis",
    "analysis of",
    "mortality trends",
    "epidemiological surveillance",
    "surveillance systems",
    "future burden",
    "overview",
    "perspective",
    "health effects",
    "ban asbestos",
    "time for action",
    "scientific controversy",
    "risk factors",
    "treatment failure",
    "proteasome activity",
    "apoptosis",
    "in vitro",
    "in vivo",
    "cell line",
    "mouse model",
    "molecular dynamics",
    "network pharmacology",
    "machine learning",
)
NON_MESO_DISEASE_CUES = (
    "pleural effusion",
    "cancer patients",
    "talcum powder",
    "smoking",
    "tuberculosis",
)


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


def affiliation_looks_indian(affiliation: str) -> bool:
    aff = clean_affiliation(affiliation).lower()
    if "india" in aff:
        return True
    for st in INDIA_STATES:
        if st.lower() in aff:
            return True
    return False


def clean_affiliation(text: str) -> str:
    text = normalize_space(text)
    text = re.sub(r"\b\S+@\S+\b", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ,.;")
    return text


def extract_india_location(title: str, abstract: str, affiliation: str) -> tuple[str, str]:
    blob = f"{normalize_space(title)} {normalize_space(abstract)}".lower()
    state = ""
    city = ""

    matches = []
    for st in INDIA_STATES:
        s = st.lower()
        idx = blob.find(s)
        if idx >= 0:
            matches.append((idx, st))
    for alias, canonical in STATE_ALIASES.items():
        idx = blob.find(alias)
        if idx >= 0:
            matches.append((idx, canonical))
    if matches:
        matches.sort(key=lambda x: x[0])
        state = matches[0][1]

    city_hits = []
    for c, s in CITY_TO_STATE.items():
        idx = blob.find(c)
        if idx >= 0:
            city_hits.append((idx, c.title(), s))
    if city_hits:
        city_hits.sort(key=lambda x: x[0])
        city = city_hits[0][1]
        if not state:
            state = city_hits[0][2]

    # affiliation is only fallback and still sanitized/India-gated
    aff = clean_affiliation(affiliation).lower()
    if not state and aff:
        for st in INDIA_STATES:
            if st.lower() in aff:
                state = st
                break
        if not city:
            for c, s in CITY_TO_STATE.items():
                if c in aff:
                    city = c.title()
                    if not state:
                        state = s
                    break
    return city, state


def estimate_case_count(title: str, abstract: str) -> str:
    text = normalize_space(f"{title} {abstract}").lower()

    # Only accept counts that are explicitly tied to asbestos or the paper's own series.
    meso_count_patterns = [
        r"asbestos[^.]{0,80}?\b(?:in|of|among)?\s*(\d{1,4})\s+(?:cases|patients)\b",
        r"asbestosis[^.]{0,80}?\b(?:in|of|among)?\s*(\d{1,4})\s+(?:cases|patients)\b",
        r"\b(\d{1,4})\s+(?:cases|patients)\b[^.]{0,80}?asbestos",
        r"\bstudy of\s+(\d{1,4})\s+cases\b[^.]{0,80}?asbestos",
        r"\bclinicopathological study of\s+(\d{1,4})\s+cases\b",
        r"\bhistomorphological[^.]{0,80}?\bof\s+(\d{1,4})\s+cases\b",
        r"\blargest study from india\b[^.]{0,80}?\b(\d{1,4})\b",
        r"\boutcomes from[^.]{0,80}?\b(\d{1,4})\b[^.]{0,80}?asbestos",
    ]
    for rgx in meso_count_patterns:
        m = re.search(rgx, text)
        if m:
            return m.group(1)

    if "case report" in text or "a rare case of" in text or "posthumous report" in text:
        return "1"
    return "0"


def is_mesothelioma_primary_paper(title: str, abstract: str) -> bool:
    text = normalize_space(f"{title} {abstract}").lower()
    if not any(term in text for term in MESO_TERMS):
        return False

    # Hard exclusions first.
    if any(cue in text for cue in NON_PRIMARY_CUES):
        return False

    # Exclude broad non-mesothelioma cohorts unless mesothelioma itself is the study target.
    if any(cue in text for cue in NON_MESO_DISEASE_CUES):
        meso_in_title = "asbestos" in normalize_space(title).lower() or "asbestosis" in normalize_space(title).lower()
        if not meso_in_title:
            return False

    if any(cue in text for cue in PRIMARY_STUDY_CUES):
        return True

    # Accept mesothelioma-specific titles that clearly describe institutional patient material.
    title_l = normalize_space(title).lower()
    if ("asbestos" in title_l or "asbestosis" in title_l) and re.search(r"\b\d{1,4}\s+(cases|patients)\b", text):
        return True
    if ("asbestos" in title_l or "asbestosis" in title_l) and any(cue in title_l for cue in ("case report", "study", "experience", "outcomes")):
        return True
    return False


def looks_india_record(title: str, abstract: str) -> bool:
    blob = normalize_space(f"{title} {abstract}").lower()
    if not blob:
        return False
    has_india = any(t in blob for t in INDIA_TERMS)
    has_excluded_geo = any(t in blob for t in EXCLUDE_GEO_TERMS)
    if has_excluded_geo and not has_india:
        return False
    return has_india


def score_record(title: str, abstract: str, hospital: str, city: str, state: str, case_count: str) -> tuple[int, str]:
    text = normalize_space(f"{title} {abstract}").lower()
    score = 0
    reasons: list[str] = []

    if any(term in text for term in MESO_TERMS):
        score += 3
        reasons.append("mesothelioma-term")
    if looks_india_record(title, abstract):
        score += 2
        reasons.append("india-signal")
    if any(cue in text for cue in PRIMARY_STUDY_CUES):
        score += 3
        reasons.append("primary-study-cue")
    if hospital:
        score += 2
        reasons.append("hospital-detected")
    if city or state:
        score += 1
        reasons.append("india-location")
    if str(case_count).isdigit() and int(case_count) > 0:
        score += 2
        reasons.append("cohort-count")
    if any(cue in text for cue in NON_PRIMARY_CUES):
        score -= 6
        reasons.append("non-primary-cue")
    if any(cue in text for cue in NON_MESO_DISEASE_CUES):
        score -= 4
        reasons.append("non-meso-cohort-cue")

    return score, ",".join(reasons)


def esearch(term: str, email: str, api_key: str, retmax: int, start_year: int) -> list[str]:
    params = {
        "db": "pubmed",
        "retmode": "json",
        "retmax": str(retmax),
        "term": term,
        "sort": "pub date",
        "datetype": "pdat",
        "mindate": str(start_year),
        "email": email,
    }
    if api_key:
        params["api_key"] = api_key
    url = f"{BASE}/esearch.fcgi?{urllib.parse.urlencode(params)}"
    payload = json.loads(fetch_url(url).decode("utf-8"))
    return payload.get("esearchresult", {}).get("idlist", [])


def collect_pmids(email: str, api_key: str, retmax: int, start_year: int, query: str) -> list[str]:
    if query:
        return esearch(query, email, api_key, retmax, start_year)

    all_pmids: list[str] = []
    for term in QUERY_BUCKETS:
        all_pmids.extend(esearch(term, email, api_key, retmax, start_year))
        time.sleep(0.2)
    return sorted(set(all_pmids))


def efetch_details(pmids: list[str], email: str, api_key: str, pause_s: float, start_year: int) -> list[dict[str, str]]:
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
            if year and year.isdigit() and int(year) < start_year:
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
            if not hospital and affiliation_looks_indian(affiliation):
                hospital = extract_hospital(affiliation)
            city, state = extract_india_location(title, abstract, affiliation)
            case_count = estimate_case_count(title, abstract)
            score, reasons = score_record(title, abstract, hospital, city, state, case_count)
            primary_ok = is_mesothelioma_primary_paper(title, abstract)
            india_ok = looks_india_record(title, abstract)

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
                    "icd10": "Asbestos",
                    "meso_type": "All",
                    "case_count": case_count,
                    "year_start": year,
                    "year_end": year,
                    "latitude": "",
                    "longitude": "",
                    "catchment_km": "90",
                    "journal": normalize_space(journal),
                    "affiliation": clean_affiliation(affiliation),
                    "screen_score": str(score),
                    "screen_reasons": reasons,
                    "screen_status": "promote" if (india_ok and primary_ok and score >= 6) else "review",
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


def write_csv(rows: list[dict[str, str]], out_path: Path, *, candidates: bool = False) -> None:
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
        "journal",
        "affiliation",
        "screen_score",
        "screen_reasons",
        "screen_status",
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
        rows_out = sorted(dedup.values(), key=lambda r: (r.get("year_start", ""), r.get("pmid", "")), reverse=True)
        if not candidates:
            rows_out = [r for r in rows_out if r.get("screen_status") == "promote"]
        writer.writerows(rows_out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="")
    parser.add_argument("--email", default="asbestosindia@example.org")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--retmax", type=int, default=2500)
    parser.add_argument("--start-year", type=int, default=1990)
    parser.add_argument("--pause", type=float, default=0.35)
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parents[1] / "data" / "literature_cases.csv"),
    )
    parser.add_argument(
        "--candidate-output",
        default=str(Path(__file__).resolve().parents[1] / "data" / "candidate_literature.csv"),
    )
    args = parser.parse_args()

    pmids = collect_pmids(args.email, args.api_key, args.retmax, args.start_year, args.query)
    rows = efetch_details(pmids, args.email, args.api_key, args.pause, args.start_year)
    write_csv(rows, Path(args.candidate_output), candidates=True)
    write_csv(rows, Path(args.output), candidates=False)
    promoted = sum(1 for r in rows if r.get("screen_status") == "promote")
    print(
        f"Fetched {len(rows)} candidate records; promoted {promoted}. "
        f"Wrote {args.candidate_output} and {args.output} at {dt.datetime.utcnow().isoformat()}Z"
    )


if __name__ == "__main__":
    main()
