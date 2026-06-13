"""
Split pdc_overlays.geojson into one GeoJSON file per overlay NAME.

The combined PDC overlays file contains 74 distinct overlay types in a single
FeatureCollection. This script splits it by the NAME field and writes each
overlay to output/<slug>.geojson.

Usage:
    python scripts/split_pdc_overlays.py
    python scripts/split_pdc_overlays.py --input output/pdc_overlays.geojson --list
    python scripts/split_pdc_overlays.py --only "Hazards (Bushfire - High Risk)" "State Heritage Place"
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def split_overlays(
    input_path: Path,
    output_dir: Path,
    only: list[str] | None = None,
) -> dict[str, int]:
    print(f"Reading {input_path} …")
    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    features = data.get("features", [])
    print(f"  {len(features):,} total features across all overlays")

    buckets: dict[str, list[dict]] = defaultdict(list)
    for feat in features:
        name = (feat.get("properties") or {}).get("name", "unknown")
        buckets[name].append(feat)

    if only:
        missing = [n for n in only if n not in buckets]
        if missing:
            print(f"WARNING: overlays not found: {missing}")
        buckets = {k: v for k, v in buckets.items() if k in only}

    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, int] = {}

    for name, feats in sorted(buckets.items()):
        slug = slugify(name)
        out_path = output_dir / f"pdc_{slug}.geojson"
        fc = {"type": "FeatureCollection", "features": feats}
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(fc, f, separators=(",", ":"))
        size_mb = out_path.stat().st_size / 1_048_576
        print(f"  {name!r:60s} -> {out_path.name} ({len(feats):,} features, {size_mb:.1f} MB)")
        written[name] = len(feats)

    print(f"\nWrote {len(written)} overlay file(s) to {output_dir}/")
    return written


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--input",
        default="output/pdc_overlays.geojson",
        help="Path to combined PDC overlays GeoJSON (default: %(default)s)",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory for split output files (default: %(default)s)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List overlay names and feature counts without writing files",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="NAME",
        help="Only extract these overlay names (exact match)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"ERROR: {input_path} not found. Run: python run.py --layer pdc_overlays")

    if args.list:
        print(f"Reading {input_path} …")
        with open(input_path, encoding="utf-8") as f:
            data = json.load(f)
        counts: dict[str, int] = defaultdict(int)
        for feat in data.get("features", []):
            name = (feat.get("properties") or {}).get("name", "unknown")
            counts[name] += 1
        print(f"\n{'Overlay Name':<60} {'Features':>10}")
        print("-" * 72)
        for name, count in sorted(counts.items()):
            print(f"{name:<60} {count:>10,}")
        print(f"\nTotal: {len(counts)} overlays, {sum(counts.values()):,} features")
        return

    split_overlays(Path(args.input), Path(args.output_dir), args.only)


if __name__ == "__main__":
    main()
