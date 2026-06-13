# SA Geospatial Feature ETL

A Python ETL pipeline that ingests South Australia geospatial planning and hazard layers from ArcGIS REST APIs and public data portals into local GeoJSON files.

---

## Overview

The pipeline pulls spatial data from two sources:

- **ArcGIS REST APIs** on `location.sa.gov.au/server6` — paginated feature extraction with automatic retry
- **ZIP archives** on `dptiapps.com.au` (data.sa.gov.au mirror) — direct download and extraction

All output is written to `output/` as standard GeoJSON FeatureCollections, making it easy to load into QGIS, GeoPandas, PostGIS, or any GIS tool.

---

## Project Structure

```
SAGeoSpatialFeatureETL/
├── run.py                        # CLI entry point
├── pyproject.toml                # Package metadata and dependencies
├── .env.example                  # Environment variable template
├── config/
│   └── layers.yaml               # Layer definitions and source URLs
├── src/sa_etl/
│   ├── config.py                 # Pydantic config models + settings loader
│   ├── arcgis_client.py          # ArcGIS REST HTTP client with retry logic
│   ├── extractor.py              # ArcGIS feature extraction with progress bar
│   ├── zip_downloader.py         # ZIP archive downloader (browser UA bypass)
│   ├── loader.py                 # Streaming GeoJSON file writer
│   └── pipeline.py               # Orchestrator + Click CLI
├── scripts/
│   ├── discover_services.py      # Scan server6 public catalog for new layers
│   └── split_pdc_overlays.py     # Split combined PDC overlays by overlay NAME
├── output/                       # GeoJSON output files (git-ignored)
└── logs/                         # Rotating debug logs (git-ignored)
```

---

## Installation

```bash
# Create and activate a conda/virtual environment (Python 3.9+)
conda create -n sagis python=3.9
conda activate sagis

# Install the package and dependencies
pip install -e .
```

---

## Configuration

### Environment variables

Copy `.env.example` to `.env` and adjust if needed:

```bash
SA_ETL_OUTPUT_DIR=output        # Where GeoJSON files are written
SA_ETL_LOG_DIR=logs             # Where rotating log files are written
SA_ETL_REQUEST_TIMEOUT=120      # HTTP timeout in seconds
SA_ETL_MAX_RETRIES=5            # Retry attempts per failed request
SA_ETL_TOKEN=                   # ArcGIS token (only for auth-required services)
```

### Layer configuration

All layers are defined in `config/layers.yaml`. Each entry supports:

| Field | Description |
|-------|-------------|
| `name` | Unique layer identifier used in CLI |
| `description` | Human-readable description |
| `source` | `arcgis` (default) or `zip_download` |
| `service_url` | ArcGIS REST layer URL (arcgis source only) |
| `download_url` | ZIP archive URL (zip_download source only) |
| `output_file` | Output filename in `output/` |
| `where` | ArcGIS SQL filter (default: `1=1`) |
| `out_fields` | Fields to fetch (default: `*`) |
| `page_size` | Features per page (arcgis only) |
| `page_delay` | Seconds between pages to avoid rate limiting |
| `geometry_precision` | Decimal places for coordinates (reduces file size) |
| `enabled` | `true` / `false` |

---

## Usage

```bash
# Run all enabled layers
python run.py

# Run specific layers
python run.py --layer zones
python run.py --layer heritage --layer fire_ban_districts

# Use a custom config file
python run.py --config staging/layers.yaml
```

After `pip install -e .`, the `sa-etl` command is also available:

```bash
sa-etl --layer zones
```

---

## Layers

### Enabled — ArcGIS REST (location.sa.gov.au/server6)

| Layer | Description | Features | Source |
|-------|-------------|----------|--------|
| `zones` | Planning and Design Code zone boundaries (APL, GN, CW, etc.) | ~5,391 | GrowthManagementPublic / CodeAmendments_BaseLayers_plansadb / FeatureServer/2 |
| `lgas` | Local Government Area boundaries | — | Same FeatureServer / layer 0 |
| `suburbs` | SA suburb and locality boundaries | — | Same FeatureServer / layer 1 |
| `flood` | Hazards (Flooding) — main PDC flood hazard overlay | ~29,721 | ePlanningPublic / ConsultFlooding / MapServer/6 |
| `flood_general` | Hazards (Flooding - General) sub-overlay | — | ConsultFlooding / MapServer/7 |
| `flood_evidence` | Hazards (Flooding - Evidence Required) sub-overlay | ~119,126 | ConsultFlooding / MapServer/8 |

> **flood_evidence** is a large layer (119K features). Page size is reduced to 500 with a 1.5s delay to avoid 502 errors from the server.

### Enabled — ZIP Downloads (dptiapps.com.au via data.sa.gov.au)

These downloads require a browser User-Agent header (the server blocks bots); `ZipDownloader` handles this automatically. All data is licensed **CC BY 4.0** and uses the **GDA2020** datum.

| Layer | Description | ZIP Size | Source |
|-------|-------------|----------|--------|
| `heritage` | SA Heritage Places — State and Local Heritage Register items | 14.4 MB | [data.sa.gov.au](https://data.sa.gov.au/data/dataset/sa-heritage-places) |
| `fire_ban_districts` | CFS Fire Ban District boundaries | 4 MB | [data.sa.gov.au](https://data.sa.gov.au/data/dataset/south-australian-fire-ban-districts) |

### Disabled — Opt-in (large downloads)

| Layer | Description | ZIP Size | To enable |
|-------|-------------|----------|-----------|
| `land_use` | SA Land Use Generalised 2025 — parcel-based land use from valuation data | 134.6 MB | Set `enabled: true` in layers.yaml |
| `pdc_overlays` | All 69 Planning and Design Code overlays combined (see below) | 1,052 MB | Set `enabled: true` in layers.yaml |

### Disabled — Auth required

| Layer | Description | Auth needed |
|-------|-------------|-------------|
| `cadastre` | SA Cadastre — lot boundaries, PIDs, parcel area | Land Services SA commercial account ($250+ min). Register at [landservices.com.au](https://www.landservices.com.au) |
| `fsr_height` | FSR / Building Height overlays | **Not available as a spatial layer.** In SA's PDC, height limits are policy rules per zone type, not GIS polygons. Derive from zone codes in `zones.geojson` using PDC policy tables. |
| `heritage` (PDC live) | Live ePlanning/CurrentOverlays heritage layers | SLIP credentials — register at [location.sa.gov.au](https://location.sa.gov.au/) |
| `bushfire` (PDC live) | Live ePlanning/CurrentOverlays bushfire layers | SLIP credentials (same as above) |

---

## PDC Overlays

The `pdc_overlays` layer (when enabled) downloads a 1 GB ZIP containing all 74 Planning and Design Code overlays as a single combined GeoJSON (380,855 features total). Features are distinguished by the `name` property.

### Split into individual files

```bash
# List all overlay names and feature counts
python scripts/split_pdc_overlays.py --list

# Extract specific overlays
python scripts/split_pdc_overlays.py --only "State Heritage Place" "Local Heritage Place"

# Extract all overlays into separate files
python scripts/split_pdc_overlays.py
```

### Available overlay names (74 total, selection)

| Category | Overlay Names |
|----------|---------------|
| **Bushfire** | Hazards (Bushfire - General), Hazards (Bushfire - High Risk), Hazards (Bushfire - Medium Risk), Hazards (Bushfire - Urban Interface), Hazards (Bushfire - Regional), Hazards (Bushfire - Outback) |
| **Flooding** | Hazards (Flooding), Hazards (Flooding - General), Hazards (Flooding - Evidence Required) |
| **Heritage** | State Heritage Place, State Heritage Area, Local Heritage Place, Heritage Adjacency, Historic Area, Historic Shipwrecks |
| **Environment** | Native Vegetation, State Significant Native Vegetation, Ramsar Wetlands, Marine Parks (Managed Use), Marine Parks (Restricted Use), Coastal Areas, Water Protection Area |
| **Transport** | Future Road Widening, Future Local Road Widening, Key Outback and Rural Routes, Urban Transport Routes, Airport Building Heights (Regulated) |
| **Water** | Prescribed Surface Water Areas, Prescribed Watercourses, Prescribed Wells Area, Mount Lofty Ranges Water Supply Catchment (Area 1 & 2) |

---

## Architecture

### ArcGIS REST pipeline

```
LayerConfig (layers.yaml)
    → ArcGISClient._get_json()          # HTTP GET with exponential backoff retry
        retries on: Timeout, ConnectionError, ChunkedEncodingError, 5xx, empty/malformed JSON
    → fetch_features_paginated()
        offset-based pagination (modern services)
        OID-based pagination (fallback for older services)
    → LayerExtractor.extract()          # yields individual features with tqdm progress bar
    → GeoJSONLoader.write_layer()       # streams features into output GeoJSON
```

### ZIP download pipeline

```
LayerConfig (source: zip_download)
    → ZipDownloader.download_features() # streams ZIP with browser User-Agent
    → _extract_features()               # opens ZIP, selects _GDA2020.geojson, yields features
    → GeoJSONLoader.write_layer()       # same writer as ArcGIS path
```

### Retry logic

The ArcGIS client retries up to 5 times with exponential backoff (4s → 8s → 16s → 32s → 120s max) on:
- `requests.Timeout`
- `requests.ConnectionError`
- `requests.exceptions.ChunkedEncodingError` (mid-transfer drops)
- HTTP 5xx responses
- Empty or malformed JSON responses

---

## Utility Scripts

### Service discovery

Scans the full `location.sa.gov.au/server6` public ArcGIS REST catalog and writes a Markdown report of every accessible service and layer with feature counts.

```bash
python scripts/discover_services.py
# Output: output/service_discovery.md
```

### PDC overlay splitter

Splits the combined `pdc_overlays.geojson` into one file per overlay type.

```bash
python scripts/split_pdc_overlays.py --list
python scripts/split_pdc_overlays.py --only "Hazards (Bushfire - High Risk)"
python scripts/split_pdc_overlays.py   # writes all 74 overlays
```

---

## Data Sources

| Source | URL | Notes |
|--------|-----|-------|
| location.sa.gov.au/server6 | ArcGIS REST catalog | Primary public server for SA spatial data |
| data.sa.gov.au | SA Government Open Data Portal | CC BY 4.0 licensed datasets |
| dptiapps.com.au | DPTI data download portal | Requires browser User-Agent; no credentials |
| plan.sa.gov.au | SA Planning and Design Code portal | Requires SLIP auth for ArcGIS REST access |
| landservices.com.au | Land Services SA (cadastre) | Commercial; $250 minimum fee |

### Auth paths for locked services

- **SLIP credentials** (for `ePlanning/CurrentOverlays` on server6): Register at [location.sa.gov.au](https://location.sa.gov.au/) → Data → Request access
- **plan.sa.gov.au ArcGIS REST**: Contact `DIT.DataRequestsORG@sa.gov.au` or register at the SAPPA portal
- **Cadastre**: Register at [landservices.com.au](https://www.landservices.com.au) (commercial/government)

---

## Output Files

All GeoJSON files are written to `output/` (git-ignored due to size). Coordinate system is **WGS 84 (EPSG:4326)** for ArcGIS layers and **GDA2020** for ZIP downloads.

| File | Layer | Description |
|------|-------|-------------|
| `zones.geojson` | zones | PDC zone boundaries |
| `lgas.geojson` | lgas | LGA boundaries |
| `suburbs.geojson` | suburbs | Suburb/locality boundaries |
| `flood.geojson` | flood | Main flood hazard overlay |
| `flood_general.geojson` | flood_general | General flood sub-overlay |
| `flood_evidence.geojson` | flood_evidence | Evidence-required flood sub-overlay |
| `heritage.geojson` | heritage | State and Local Heritage Register places |
| `fire_ban_districts.geojson` | fire_ban_districts | CFS fire ban districts |
| `pdc_overlays.geojson` | pdc_overlays | All 74 PDC overlays combined (1.75 GB) |
| `pdc_*.geojson` | — | Individual overlays split from pdc_overlays |

---

## Logs

Logs are written to `logs/etl_YYYYMMDD_HHmmss.log` (rotating, 50 MB per file, 10 files retained). DEBUG level is logged to file; INFO and above is printed to stderr.
