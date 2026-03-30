# Asbestos India

Interactive India map for asbestos case locations from:
- Hospital-level registry datasets
- PBCR registry sources
- NCBI literature (PubMed/PMC)
- Reviewed community submissions

The project is built as a static site + reproducible Python ETL scripts so you can host it on GitHub Pages and keep data refreshed daily.

## Disease coding note
This repository is configured for Asbestos tracking.

## Repository layout

- `index.html`, `app.js`, `styles.css`: Interactive Leaflet map UI
  - Includes toggleable catchment circles, district boundary overlay, and weighted heatmap
- `data/registry_cases.csv`: Hospital/PBCR rows from registry sources
- `data/candidate_literature.csv`: Broad PubMed candidate pool for manual review
- `data/literature_cases.csv`: NCBI-derived rows (auto-refreshed)
- `data/community_verified.csv`: Approved community submissions only
- `data/asbestos_cases.geojson`: Combined map dataset (generated)
- `scripts/update_ncbi_asbestos.py`: Pulls India asbestos records from NCBI API
- `scripts/extract_supplementary_table.py`: Extracts hospital rows from supplementary PDF table
- `scripts/build_dataset.py`: Merges CSVs into `asbestos_cases.geojson`
- `scripts/import_soi_state_boundary.py`: Imports SOI state boundary shapefile to map GeoJSON
- `scripts/import_soi_district_boundary.py`: Imports SOI district boundary shapefile to simplified overlay GeoJSON
- `.github/workflows/update-data.yml`: Daily data refresh automation

## Quick start (local)

```bash
cd app-pubmed-asbestos
python3 scripts/build_dataset.py --data-dir data
python3 -m http.server 8080
```

Then open `http://localhost:8080`.

## Data refresh commands

1) Update literature from NCBI:
```bash
python3 scripts/update_ncbi_asbestos.py \
  --email "you@example.org" \
  --api-key "<optional-ncbi-key>" \
  --output data/literature_cases.csv
```

This writes two files:
- `data/candidate_literature.csv`: broad retrieval + screening metadata
- `data/literature_cases.csv`: promoted higher-confidence records used by the map

2) Rebuild map dataset:
```bash
python3 scripts/build_dataset.py --data-dir data
```

3) Optional geocoding for missing coordinates:
```bash
python3 scripts/build_dataset.py --data-dir data --geocode --pause 1.0
```

## Supplementary PDF extraction (seed hospital rows)

```bash
python3 scripts/extract_supplementary_table.py \
  --pdf "/absolute/path/to/iutld_pha_24.0003_supplementarydata1-2.pdf" \
  --output data/registry_cases_extracted.csv
```

Review extracted rows manually before merging into `data/registry_cases.csv`.

## Continuous updates on GitHub

Workflow: `.github/workflows/update-data.yml`
- Runs daily and on manual trigger
- Pulls new NCBI records
- Rebuilds map dataset
- Commits updates automatically

Recommended repo secrets:
- `NCBI_EMAIL`
- `NCBI_API_KEY` (optional but useful for higher request limits)

## Community submission and review workflow

1. Visitors submit via map form (opens a prefilled GitHub issue).
2. Maintainer reviews evidence.
3. Approved rows are added to `data/community_verified.csv`.
4. Run `scripts/build_dataset.py` and commit.
5. Approved community entries appear in green on map.

## Source integration checklist

For each new source row, keep:
- `provenance_url` (paper, registry, or report link)
- `hospital`, `city`, `state`
- `icd10 = Asbestos`
- `case_count`, `year_start`, `year_end`

## PBCR / NCDIR integration

Primary PBCR annexure page:
- https://ncdirindia.org/All_Reports/PBCR_Annexures/Default.aspx

Current structure supports adding PBCR rows directly into `data/registry_cases.csv` as `source_type=PBCR`.

## Important quality note
Hospital extraction from PubMed metadata is pattern-based. The pipeline now separates broad candidate retrieval from promoted records, but some records still require manual verification before being trusted as asbestos case-site evidence.
