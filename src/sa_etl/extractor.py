from __future__ import annotations

from typing import Generator

from loguru import logger
from tqdm import tqdm

from .arcgis_client import ArcGISClient
from .config import LayerConfig


class LayerExtractor:
    def __init__(self, client: ArcGISClient) -> None:
        self.client = client

    def extract(self, layer: LayerConfig) -> Generator[dict, None, None]:
        """Yield individual GeoJSON features from the layer, with a progress bar."""
        logger.info(f"[{layer.name}] Starting extraction — {layer.description}")

        total: int | None = None
        try:
            total = self.client.get_feature_count(layer.service_url, layer.where)
            logger.info(f"[{layer.name}] {total:,} features to fetch")
        except Exception as exc:
            logger.warning(f"[{layer.name}] Could not retrieve feature count: {exc}")

        with tqdm(total=total, desc=layer.name, unit="feat", dynamic_ncols=True) as pbar:
            for page in self.client.fetch_features_paginated(
                service_url=layer.service_url,
                where=layer.where,
                out_fields=layer.out_fields,
                page_size=layer.page_size,
                page_delay=layer.page_delay,
                geometry_precision=layer.geometry_precision,
            ):
                for feature in page:
                    yield feature
                    pbar.update(1)

        logger.info(f"[{layer.name}] Extraction complete")
