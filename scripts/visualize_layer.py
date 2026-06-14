"""
Visualize one or more output GeoJSON layers on an interactive South Australia map.

Generates a self-contained HTML file using Folium (Leaflet.js).
Open the output file in any browser — no server required.

Usage:
    python scripts/visualize_layer.py --layer zones
    python scripts/visualize_layer.py --layer zones --layer lgas
    python scripts/visualize_layer.py --file output/pdc_hazards_bushfire_high_risk.geojson
    python scripts/visualize_layer.py --layer zones --color-by value
    python scripts/visualize_layer.py --layer flood --color-by name --output output/flood_map.html
    python scripts/visualize_layer.py --list

Requires:  pip install folium
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

_LAYER_COLOURS = [
    "#e63946",  # red
    "#457b9d",  # steel blue
    "#2a9d8f",  # teal
    "#e9c46a",  # gold
    "#f4a261",  # orange
    "#a8dadc",  # light blue
    "#6a4c93",  # purple
    "#52b788",  # green
    "#f72585",  # pink
    "#b5838d",  # mauve
]

_PROP_PALETTE = [
    "#e63946", "#457b9d", "#2a9d8f", "#e9c46a", "#f4a261",
    "#a8dadc", "#6a4c93", "#52b788", "#f72585", "#b5838d",
    "#264653", "#e76f51", "#06d6a0", "#118ab2", "#ffd166",
]


def _prop_colour_map(features: list[dict], prop: str) -> dict[str, str]:
    values = sorted({str((f.get("properties") or {}).get(prop, "")) for f in features})
    return {v: _PROP_PALETTE[i % len(_PROP_PALETTE)] for i, v in enumerate(values)}


# ---------------------------------------------------------------------------
# Layer loading
# ---------------------------------------------------------------------------

def _load_geojson(path: Path) -> dict:
    print(f"  Loading {path} ({path.stat().st_size / 1_048_576:.1f} MB)...")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _resolve_files(layer_names: list[str], file_paths: list[str], output_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for name in layer_names:
        p = output_dir / f"{name}.geojson"
        if not p.exists():
            sys.exit(f"ERROR: {p} not found. Run: python run.py --layer {name}")
        paths.append(p)
    for fp in file_paths:
        p = Path(fp)
        if not p.exists():
            sys.exit(f"ERROR: {fp} not found.")
        paths.append(p)
    return paths


# ---------------------------------------------------------------------------
# Popup builder
# ---------------------------------------------------------------------------

def _make_popup(props: dict | None, max_rows: int = 20) -> str:
    if not props:
        return "<em>no properties</em>"
    rows = []
    for k, v in list(props.items())[:max_rows]:
        if v is None:
            continue
        rows.append(f"<tr><td style='color:#888;padding:2px 6px 2px 0'>{k}</td>"
                    f"<td style='padding:2px 0'>{v}</td></tr>")
    if not rows:
        return "<em>no properties</em>"
    return f"<table style='font-size:12px;font-family:monospace'>{''.join(rows)}</table>"


# ---------------------------------------------------------------------------
# Map builder
# ---------------------------------------------------------------------------

def build_map(
    files: list[Path],
    color_by: str | None,
    max_features: int,
) -> "folium.Map":
    try:
        import folium
    except ImportError:
        sys.exit("folium is not installed. Run:  pip install folium")

    # SA centre
    m = folium.Map(location=[-30.0, 135.7], zoom_start=6, tiles=None)

    folium.TileLayer(
        tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        attr="© OpenStreetMap contributors",
        name="OpenStreetMap",
        max_zoom=19,
    ).add_to(m)

    folium.TileLayer(
        tiles="CartoDB positron",
        name="CartoDB Light",
        max_zoom=19,
    ).add_to(m)

    for idx, fpath in enumerate(files):
        data = _load_geojson(fpath)
        features = data.get("features", [])
        total = len(features)

        if total > max_features:
            print(f"  WARNING: {fpath.name} has {total:,} features — showing first {max_features:,}. "
                  f"Use --max-features to increase (may slow browser).")
            features = features[:max_features]
            data = {"type": "FeatureCollection", "features": features}

        print(f"  Rendering {len(features):,} features from {fpath.name}")

        default_colour = _LAYER_COLOURS[idx % len(_LAYER_COLOURS)]

        if color_by:
            colour_map = _prop_colour_map(features, color_by)

            def _style(feature, _cm=colour_map, _cb=color_by, _dc=default_colour):
                val = str((feature.get("properties") or {}).get(_cb, ""))
                c = _cm.get(val, _dc)
                return {"fillColor": c, "color": c, "weight": 1, "fillOpacity": 0.55}
        else:
            def _style(feature, _dc=default_colour):
                return {"fillColor": _dc, "color": _dc, "weight": 1, "fillOpacity": 0.45}

        layer_name = fpath.stem

        fg = folium.FeatureGroup(name=layer_name, show=True)

        folium.GeoJson(
            data,
            name=layer_name,
            style_function=_style,
            tooltip=folium.GeoJsonTooltip(
                fields=_tooltip_fields(features),
                aliases=_tooltip_fields(features),
                sticky=True,
                max_width=400,
            ),
            popup=folium.GeoJsonPopup(
                fields=_popup_fields(features),
                aliases=_popup_fields(features),
                max_width=500,
            ),
        ).add_to(fg)

        fg.add_to(m)

        # Legend for colour-by layers
        if color_by:
            _add_legend(m, layer_name, color_by, colour_map)

    folium.LayerControl(collapsed=False).add_to(m)
    return m


def _tooltip_fields(features: list[dict], max_fields: int = 4) -> list[str]:
    if not features:
        return []
    props = features[0].get("properties") or {}
    # prefer name/description/value/code fields first
    priority = ["name", "description", "value", "code", "lga_name", "suburb_name",
                "zonecode", "status", "HERITAGENR", "DETAILS", "HERITAGECLASS1"]
    found = [f for f in priority if f in props]
    rest = [k for k in props if k not in found]
    return (found + rest)[:max_fields]


def _popup_fields(features: list[dict], max_fields: int = 12) -> list[str]:
    if not features:
        return []
    props = features[0].get("properties") or {}
    return list(props.keys())[:max_fields]


def _add_legend(m, layer_name: str, prop: str, colour_map: dict[str, str]) -> None:
    try:
        import branca
    except ImportError:
        return  # optional

    items = "".join(
        f"<li><span style='background:{c};width:12px;height:12px;"
        f"display:inline-block;border-radius:2px;margin-right:6px'></span>{v[:40]}</li>"
        for v, c in list(colour_map.items())[:20]
    )
    more = f"<li>… and {len(colour_map)-20} more</li>" if len(colour_map) > 20 else ""
    html = (
        f"<div style='position:fixed;bottom:30px;right:10px;z-index:1000;"
        f"background:white;padding:10px 14px;border-radius:6px;"
        f"box-shadow:0 2px 8px rgba(0,0,0,.25);font-family:sans-serif;font-size:12px'>"
        f"<b>{layer_name}</b> — {prop}<br>"
        f"<ul style='list-style:none;padding:0;margin:6px 0 0'>{items}{more}</ul></div>"
    )
    m.get_root().html.add_child(branca.element.Element(html))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _list_available(output_dir: Path) -> None:
    files = sorted(output_dir.glob("*.geojson"))
    if not files:
        print(f"No .geojson files found in {output_dir}/")
        return
    print(f"\nAvailable layers in {output_dir}/:\n")
    for f in files:
        size_mb = f.stat().st_size / 1_048_576
        try:
            with open(f, encoding="utf-8") as fh:
                count = fh.read().count('"type":"Feature"') + fh.read().count('"type": "Feature"')
        except Exception:
            count = 0
        print(f"  --layer {f.stem:<30}  {size_mb:6.1f} MB  (use --file {f} for full path)")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--layer", "-l",
        action="append", default=[],
        metavar="NAME",
        help="Layer name to visualize (matches output/<NAME>.geojson). Repeat for multiple layers.",
    )
    parser.add_argument(
        "--file", "-f",
        action="append", default=[],
        metavar="PATH",
        help="Path to any .geojson file (use for split PDC overlays or custom files).",
    )
    parser.add_argument(
        "--color-by",
        metavar="PROPERTY",
        help="Feature property name to use for colour-coding (e.g. 'value', 'name', 'status').",
    )
    parser.add_argument(
        "--output", "-o",
        default="output/map.html",
        help="Output HTML file path (default: output/map.html)",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory containing GeoJSON output files (default: output)",
    )
    parser.add_argument(
        "--max-features",
        type=int,
        default=50_000,
        help="Max features per layer to render (default: 50000). Large values slow the browser.",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Don't auto-open the HTML file in a browser after generating.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available GeoJSON files in the output directory and exit.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)

    if args.list:
        _list_available(output_dir)
        return

    if not args.layer and not args.file:
        parser.error("Specify at least one --layer NAME or --file PATH. Use --list to see available layers.")

    files = _resolve_files(args.layer, args.file, output_dir)

    print(f"\nBuilding map for {len(files)} layer(s)...")
    m = build_map(files, color_by=args.color_by, max_features=args.max_features)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out_path))
    size_kb = out_path.stat().st_size / 1024
    print(f"\nMap saved -> {out_path}  ({size_kb:.0f} KB)")

    if not args.no_open:
        url = out_path.resolve().as_uri()
        print(f"Opening in browser: {url}")
        webbrowser.open(url)


if __name__ == "__main__":
    main()
