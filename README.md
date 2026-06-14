# SA Geospatial Feature ETL

A Python ETL pipeline that ingests South Australia geospatial planning, cadastre, and hazard layers from ArcGIS REST APIs and public data portals into local GeoJSON files.

---

## Overview

The pipeline pulls spatial data from three sources:

- **ArcGIS REST API** on `location.sa.gov.au/server6` — SA planning and flood layers
- **ArcGIS REST API** on `lsa4.geohub.sa.gov.au` — LocationSA MapViewer backend; discovered via DevTools inspection. Contains cadastre (1.1M lots), building heights, bushfire, and 20+ planning layers — all publicly accessible without credentials
- **ZIP archives** on `dptiapps.com.au` (data.sa.gov.au mirror) — heritage, fire ban districts, land use, and PDC overlays

All output is written to `output/` as standard GeoJSON FeatureCollections, compatible with QGIS, GeoPandas, PostGIS, and Folium.

---

## Project Structure

```
SAGeoSpatialFeatureETL/
├── run.py                        # CLI entry point
├── pyproject.toml                # Package metadata and dependencies
├── .env.example                  # Environment variable template
├── config/
│   └── layers.yaml               # Layer definitions and source URLs (35 layers)
├── src/sa_etl/
│   ├── config.py                 # Pydantic config models + settings loader
│   ├── arcgis_client.py          # ArcGIS REST HTTP client with retry logic
│   ├── extractor.py              # ArcGIS feature extraction with progress bar
│   ├── zip_downloader.py         # ZIP archive downloader (browser UA bypass)
│   ├── loader.py                 # Streaming GeoJSON file writer
│   └── pipeline.py               # Orchestrator + Click CLI
├── scripts/
│   ├── visualize_layer.py        # Interactive HTML map viewer (Folium)
│   ├── discover_services.py      # Scan ArcGIS REST catalogs for new layers
│   └── split_pdc_overlays.py     # Split combined PDC overlays by overlay name
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

# Install visualizer dependency (optional)
pip install folium
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
python run.py --layer building_heights --layer bushfire

# Use a custom config file
python run.py --config staging/layers.yaml
```

After `pip install -e .`, the `sa-etl` command is also available:

```bash
sa-etl --layer zones
```

---

## Layers

35 layers total across 3 sources. 33 enabled by default; 2 disabled (opt-in due to size).

### Enabled — ArcGIS REST (location.sa.gov.au/server6)

| Layer | Description | Features | Source path |
|-------|-------------|----------|-------------|
| `lgas` | Local Government Area boundaries | — | GrowthManagementPublic/CodeAmendments_BaseLayers_plansadb/FeatureServer/0 |
| `suburbs` | Suburb and locality boundaries | — | same FeatureServer/1 |
| `zones` | P&D Code zone boundaries (APL, GN, CW, etc.) | ~5,391 | same FeatureServer/2 |
| `flood` | Hazards (Flooding) — main PDC flood overlay | ~29,721 | ePlanningPublic/ConsultFlooding/MapServer/6 |
| `flood_general` | Hazards (Flooding - General) sub-overlay | — | ConsultFlooding/MapServer/7 |
| `flood_evidence` | Hazards (Flooding - Evidence Required) | ~119,126 | ConsultFlooding/MapServer/8 |

> `flood_evidence` uses `page_size: 500` and `page_delay: 1.5s` to avoid 502 errors on this large layer.

### Enabled — ArcGIS REST (lsa4.geohub.sa.gov.au — LocationSA MapViewer)

Discovered 2026-06-14 by inspecting DevTools on [location.sa.gov.au/viewer](https://location.sa.gov.au/viewer/). All layers are publicly accessible — no credentials required.

**Cadastre & property**

| Layer | Description | Features | MapServer layer |
|-------|-------------|----------|-----------------|
| `building_heights` | Building Height Limits — `max_height_m`, `max_storeys` per zone/policy | 703 | /255 |
| `bushfire` | Bushfire Protection Areas (legacy dev plan zones) | 353 | /356 |
| `residential_broadhectare` | Greenfield residential land supply 2024 | 22,507 | /320 |
| `industrial_land` | Designated industrial land parcels 2018 | 15,514 | /260 |
| `land_management_agreements` | Conservation-bound LMA parcels | 37,124 | /262 |
| `residential_code` | Legacy dev plan residential policy areas | 1,524 | /120 |
| `development_plan_zones` | Legacy dev plan zone categories | 4,563 | /116 |

**Boundaries & regions**

| Layer | Description | Features | MapServer layer |
|-------|-------------|----------|-----------------|
| `sa_government_regions` | State administrative region boundaries | 12 | /20 |
| `planning_regions` | SA Planning Regions 2020 | 7 | /338 |
| `metro_adelaide_boundary` | Metropolitan Adelaide Boundary (Dev Act 1993) | 1 | /195 |
| `counties` | Historical county-level boundaries | 49 | /2 |
| `character_preservation_districts` | McLaren Vale, Barossa, etc. (Character Preservation Act) | 34 | /182 |

**Environment & planning controls**

| Layer | Description | Features | MapServer layer |
|-------|-------------|----------|-----------------|
| `energy_efficiency_zones` | NCC climate zones for building energy compliance | 11 | /212 |
| `energy_efficiency_concession` | Areas with modified NCC energy requirements | 96 | /214 |
| `corrosion_environments` | Coastal corrosion risk zones for construction | 2 | /211 |
| `electricity_regulations` | SA electricity supply district boundaries | 132 | /194 |
| `open_space_proclamation` | Proclaimed open space (Open Spaces Act) | 75 | /336 |
| `earthquake_hazard` | NCC seismic risk zones | 47 | /213 |
| `environment_food_production` | Primary production and environmental protection areas | 8 | /223 |
| `future_urban_growth` | Land identified for future urban development | 167 | /226 |
| `urban_boundary_2045` | Greater Adelaide planned urban growth boundary to 2045 | 111 | /227 |
| `state_heritage_areas` | State Heritage area polygons (distinct from individual heritage places) | 20 | /180 |

### Enabled — ZIP Downloads (dptiapps.com.au via data.sa.gov.au)

The server blocks non-browser User-Agents; `ZipDownloader` sets the correct header automatically. All data is licensed **CC BY 4.0** and uses the **GDA2020** datum.

| Layer | Description | ZIP Size | Source |
|-------|-------------|----------|--------|
| `heritage` | SA Heritage Places — State and Local Heritage Register items | 14.4 MB | [data.sa.gov.au](https://data.sa.gov.au/data/dataset/sa-heritage-places) |
| `fire_ban_districts` | CFS Fire Ban District boundaries | 4 MB | [data.sa.gov.au](https://data.sa.gov.au/data/dataset/south-australian-fire-ban-districts) |
| `land_use` | SA Land Use Generalised 2025 — parcel-based land use | 134.6 MB | [data.sa.gov.au](https://data.sa.gov.au/data/dataset/land-use-generalised) |
| `pdc_overlays` | All 74 P&D Code overlays combined (see PDC section) | 1,052 MB | [data.sa.gov.au](https://data.sa.gov.au/data/dataset/planning-and-design-code-overlays) |

### Disabled — Opt-in (large extracts)

| Layer | Description | Features | To enable |
|-------|-------------|----------|-----------|
| `cadastre` | **Parcel Cadastre** — lot boundaries, parcel ID, plan/parcel number, title vol/folio. Previously assumed to require a Land Services SA commercial account; confirmed publicly available via lsa4.geohub.sa.gov.au/MapServer/124. Expect 30–60 min to extract. | 1,139,259 | Set `enabled: true` |
| `valuation_cadastre` | Parcel boundaries linked to SA Valuation Office identifiers | 1,049,355 | Set `enabled: true` |

### Note on Floor Space Ratio (FSR)

FSR does **not** exist as a spatial GIS layer anywhere in SA's public data. The full 411-layer LocationSA MapViewer service was searched — there is no FSR polygon layer. In SA's Planning and Design Code, floor space ratio is a written policy number per zone type (e.g. "0.5:1 for General Neighbourhood Zone") documented in PDC Code text, not encoded as geometry. Use `building_heights.geojson` for the closest spatial equivalent (`max_height_m` / `max_storeys` fields per policy area).

---

## PDC Overlays

The `pdc_overlays` layer downloads a 1 GB ZIP containing all 74 Planning and Design Code overlays as a single combined GeoJSON (380,855 features). Features are distinguished by the `name` property.

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

### Layer visualizer

Renders one or more GeoJSON layers on an interactive South Australia map and opens it in your browser. Output is a self-contained HTML file — no server required.

```bash
# List all available GeoJSON files in output/
python scripts/visualize_layer.py --list

# Visualize a single layer
python scripts/visualize_layer.py --layer zones
python scripts/visualize_layer.py --layer building_heights

# Colour-code features by a property value
python scripts/visualize_layer.py --layer zones --color-by value
python scripts/visualize_layer.py --layer heritage --color-by HERITAGECLASS1
python scripts/visualize_layer.py --layer building_heights --color-by max_height_m

# Overlay multiple layers on the same map
python scripts/visualize_layer.py --layer zones --layer lgas
python scripts/visualize_layer.py --layer flood --layer bushfire

# Visualize a split PDC overlay file directly
python scripts/visualize_layer.py --file output/pdc_hazards_bushfire_high_risk.geojson

# Cap features for large layers (browsers can struggle above ~50K features)
python scripts/visualize_layer.py --layer flood_evidence --max-features 20000
python scripts/visualize_layer.py --layer land_management_agreements --max-features 10000

# Save to a named file instead of the default output/map.html
python scripts/visualize_layer.py --layer zones --output output/zones_map.html
```

The generated HTML includes layer toggle controls, hover tooltips, click popups with the full property table, and a basemap switcher (OpenStreetMap / CartoDB Light).

---

### Service discovery

Scans an ArcGIS REST catalog and writes a Markdown report of every accessible service and layer with feature counts.

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
| location.sa.gov.au/server6 | ArcGIS REST | Planning zones, flood overlays |
| lsa4.geohub.sa.gov.au | ArcGIS REST | LocationSA MapViewer backend — cadastre, building heights, 20+ layers |
| data.sa.gov.au / dptiapps.com.au | ZIP downloads | Heritage, fire ban, land use, PDC overlays (CC BY 4.0) |
| plan.sa.gov.au | ArcGIS REST | Requires SLIP auth — CurrentOverlays live service |

### Auth paths for locked services

- **SLIP credentials** (for `ePlanning/CurrentOverlays` on server6): Register at [location.sa.gov.au](https://location.sa.gov.au/) → Data → Request access
- **plan.sa.gov.au ArcGIS REST**: Contact `DIT.DataRequestsORG@sa.gov.au` or register at the SAPPA portal
- **Cadastre**: Now freely available via `lsa4.geohub.sa.gov.au` (see `cadastre` layer). Land Services SA commercial access is no longer required.

---

## Output Files

All GeoJSON files are written to `output/` (git-ignored due to size). Coordinate system is **WGS 84 (EPSG:4326)** for ArcGIS layers and **GDA2020** for ZIP downloads.

| File | Layer | Features | Description |
|------|-------|----------|-------------|
| `zones.geojson` | zones | ~5,391 | PDC zone boundaries |
| `lgas.geojson` | lgas | — | LGA boundaries |
| `suburbs.geojson` | suburbs | — | Suburb/locality boundaries |
| `flood.geojson` | flood | ~29,721 | Main PDC flood hazard overlay |
| `flood_general.geojson` | flood_general | — | General flood sub-overlay |
| `flood_evidence.geojson` | flood_evidence | ~119,126 | Evidence-required flood sub-overlay |
| `building_heights.geojson` | building_heights | 703 | Max building height (m) and storeys per zone |
| `bushfire.geojson` | bushfire | 353 | Bushfire protection areas (legacy dev plan) |
| `character_preservation_districts.geojson` | character_preservation_districts | 34 | McLaren Vale, Barossa, etc. |
| `energy_efficiency_zones.geojson` | energy_efficiency_zones | 11 | NCC climate zones |
| `energy_efficiency_concession.geojson` | energy_efficiency_concession | 96 | Modified NCC energy areas |
| `corrosion_environments.geojson` | corrosion_environments | 2 | Coastal corrosion risk zones |
| `electricity_regulations.geojson` | electricity_regulations | 132 | Electricity supply district boundaries |
| `open_space_proclamation.geojson` | open_space_proclamation | 75 | Proclaimed open space |
| `metro_adelaide_boundary.geojson` | metro_adelaide_boundary | 1 | Metropolitan Adelaide boundary |
| `sa_government_regions.geojson` | sa_government_regions | 12 | State administrative regions |
| `counties.geojson` | counties | 49 | Historical county boundaries |
| `earthquake_hazard.geojson` | earthquake_hazard | 47 | NCC seismic risk zones |
| `environment_food_production.geojson` | environment_food_production | 8 | Primary production protection areas |
| `future_urban_growth.geojson` | future_urban_growth | 167 | Future urban development areas |
| `urban_boundary_2045.geojson` | urban_boundary_2045 | 111 | Greater Adelaide urban growth boundary |
| `planning_regions.geojson` | planning_regions | 7 | SA planning regions 2020 |
| `state_heritage_areas.geojson` | state_heritage_areas | 20 | State heritage area polygons |
| `residential_broadhectare.geojson` | residential_broadhectare | 22,507 | Greenfield land supply 2024 |
| `industrial_land.geojson` | industrial_land | 15,514 | Designated industrial land 2018 |
| `land_management_agreements.geojson` | land_management_agreements | 37,124 | Conservation LMA parcels |
| `residential_code.geojson` | residential_code | 1,524 | Legacy dev plan residential areas |
| `development_plan_zones.geojson` | development_plan_zones | 4,563 | Legacy dev plan zone categories |
| `heritage.geojson` | heritage (zip) | — | State and Local Heritage Register places |
| `fire_ban_districts.geojson` | fire_ban_districts (zip) | 15 | CFS fire ban districts |
| `land_use.geojson` | land_use (zip) | — | SA Land Use Generalised 2025 |
| `pdc_overlays.geojson` | pdc_overlays (zip) | 380,855 | All 74 PDC overlays combined (1.75 GB) |
| `pdc_*.geojson` | — | — | Individual overlays split by split_pdc_overlays.py |
| `cadastre.geojson` | cadastre *(opt-in)* | 1,139,259 | Parcel lot boundaries with plan/title data |
| `valuation_cadastre.geojson` | valuation_cadastre *(opt-in)* | 1,049,355 | Valuation-linked parcel boundaries |

---

## Logs

Logs are written to `logs/etl_YYYYMMDD_HHmmss.log` (rotating, 50 MB per file, 10 files retained). DEBUG level is logged to file; INFO and above is printed to stderr.
