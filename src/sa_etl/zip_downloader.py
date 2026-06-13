from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path
from typing import Generator

import requests
from loguru import logger

from .config import LayerConfig

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


class ZipDownloader:
    def __init__(self, timeout: int = 300) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = _BROWSER_UA

    def download_features(self, layer: LayerConfig) -> Generator[dict, None, None]:
        url = layer.download_url
        logger.info(f"[{layer.name}] Starting ZIP download — {layer.description}")
        logger.info(f"[{layer.name}] URL: {url}")

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            with self.session.get(url, timeout=self.timeout, stream=True) as resp:
                resp.raise_for_status()
                content_length = int(resp.headers.get("Content-Length", 0))
                if content_length:
                    logger.info(f"[{layer.name}] ZIP size: {content_length / 1_048_576:.1f} MB")
                with open(tmp_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        f.write(chunk)

            logger.debug(f"[{layer.name}] Download complete, extracting features …")
            yield from self._extract_features(layer.name, tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def _extract_features(self, layer_name: str, zip_path: Path) -> Generator[dict, None, None]:
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            # Prefer GDA2020 datum; fall back to any GeoJSON in the archive
            geojson_entry = (
                next((n for n in names if n.endswith("_GDA2020.geojson")), None)
                or next((n for n in names if n.lower().endswith(".geojson")), None)
            )
            if not geojson_entry:
                raise ValueError(
                    f"[{layer_name}] No .geojson file found in ZIP. "
                    f"Archive contents: {names}"
                )

            logger.debug(f"[{layer_name}] Reading {geojson_entry}")
            with zf.open(geojson_entry) as f:
                data = json.load(f)

        features: list[dict] = data.get("features", [])
        logger.info(f"[{layer_name}] {len(features):,} features loaded from {geojson_entry}")
        yield from features
