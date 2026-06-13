"""
Scan location.sa.gov.au/server6 public ArcGIS REST catalog.

Writes a Markdown report to output/service_discovery.md listing every
accessible service, its layers, and the feature count of each layer.

Usage:
    python scripts/discover_services.py
    python scripts/discover_services.py --host https://location.sa.gov.au/server6
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import requests

BASE_HOST = "https://location.sa.gov.au/server6"
OUTPUT_PATH = Path("output/service_discovery.md")
REQUEST_TIMEOUT = 30
PAGE_DELAY = 0.3  # seconds between requests


def get_json(session: requests.Session, url: str, params: dict | None = None) -> dict | None:
    try:
        resp = session.get(url, params=params or {}, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None


def get_feature_count(session: requests.Session, layer_url: str) -> int | None:
    data = get_json(session, f"{layer_url}/query", {
        "where": "1=1",
        "returnCountOnly": "true",
        "f": "json",
    })
    if data and "count" in data:
        return int(data["count"])
    return None


def discover(host: str) -> list[dict]:
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    print(f"Fetching service catalog from {host}/rest/services …")
    catalog = get_json(session, f"{host}/rest/services", {"f": "json"})
    if not catalog:
        raise SystemExit(f"ERROR: Could not reach {host}/rest/services")

    results: list[dict] = []

    # Top-level services (no folder)
    folders = [""] + [f["name"] for f in catalog.get("folders", [])]
    # Top-level services that are NOT in subfolders
    top_services = catalog.get("services", [])

    # Build list of (folder, service_name, service_type) to probe
    service_refs: list[tuple[str, str, str]] = []
    for svc in top_services:
        service_refs.append(("", svc["name"], svc["type"]))

    for folder in folders:
        if not folder:
            continue
        time.sleep(PAGE_DELAY)
        folder_data = get_json(session, f"{host}/rest/services/{folder}", {"f": "json"})
        if not folder_data:
            print(f"  [skip] {folder} — no response")
            continue
        for svc in folder_data.get("services", []):
            service_refs.append((folder, svc["name"], svc["type"]))

    print(f"Found {len(service_refs)} services. Probing each for layers …\n")

    for folder, svc_name, svc_type in service_refs:
        if svc_type not in ("MapServer", "FeatureServer"):
            continue

        svc_path = f"{svc_name}/{svc_type}" if not folder else f"{svc_name}/{svc_type}"
        svc_url = f"{host}/rest/services/{svc_path}"
        time.sleep(PAGE_DELAY)
        info = get_json(session, svc_url, {"f": "json"})
        if not info:
            print(f"  [403/skip] {svc_path}")
            continue

        layers = info.get("layers", []) + info.get("tables", [])
        if not layers:
            continue

        print(f"  {svc_path} — {len(layers)} layer(s)")
        service_entry = {
            "folder": folder,
            "name": svc_name,
            "type": svc_type,
            "url": svc_url,
            "description": info.get("description", ""),
            "layers": [],
        }

        for layer in layers:
            layer_id = layer.get("id", "?")
            layer_name = layer.get("name", "?")
            layer_url = f"{svc_url}/{layer_id}"
            time.sleep(PAGE_DELAY)
            count = get_feature_count(session, layer_url)
            count_str = f"{count:,}" if count is not None else "—"
            print(f"      layer {layer_id}: {layer_name} ({count_str} features)")
            service_entry["layers"].append({
                "id": layer_id,
                "name": layer_name,
                "url": layer_url,
                "count": count,
            })

        results.append(service_entry)

    return results


def write_report(results: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        "# SA server6 Public Service Discovery Report\n",
        f"_Host: `https://location.sa.gov.au/server6`_\n\n",
        "Layers with a feature count are publicly accessible without auth. "
        "Layers showing `—` returned an error (likely auth-required).\n\n",
    ]

    for svc in results:
        lines.append(f"## {svc['name']} / {svc['type']}\n\n")
        lines.append(f"URL: `{svc['url']}`\n\n")
        if svc["description"]:
            lines.append(f"{svc['description']}\n\n")
        lines.append("| ID | Layer Name | Features | Layer URL |\n")
        lines.append("|----|-----------|----------|-----------|\n")
        for layer in svc["layers"]:
            count_str = f"{layer['count']:,}" if layer["count"] is not None else "—"
            lines.append(
                f"| {layer['id']} | {layer['name']} | {count_str} | `{layer['url']}` |\n"
            )
        lines.append("\n")

    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"\nReport written to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=BASE_HOST, help="ArcGIS REST root (default: %(default)s)")
    parser.add_argument("--output", default=str(OUTPUT_PATH), help="Output Markdown path (default: %(default)s)")
    args = parser.parse_args()

    results = discover(args.host)
    write_report(results, Path(args.output))
    accessible = sum(
        1 for svc in results for layer in svc["layers"] if layer["count"] is not None
    )
    total = sum(len(svc["layers"]) for svc in results)
    print(f"Summary: {accessible}/{total} layers publicly accessible across {len(results)} services.")


if __name__ == "__main__":
    main()
