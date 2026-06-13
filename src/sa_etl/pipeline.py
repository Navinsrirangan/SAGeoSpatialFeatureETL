from __future__ import annotations

import sys
from pathlib import Path

import click
from loguru import logger

from .arcgis_client import ArcGISClient
from .config import Settings, load_layers
from .extractor import LayerExtractor
from .loader import GeoJSONLoader
from .zip_downloader import ZipDownloader


def run_pipeline(
    layer_names: list[str] | None = None,
    config_path: str = "config/layers.yaml",
) -> dict[str, dict]:
    settings = Settings()
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(sys.stderr, level="INFO", colorize=True, format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message}")
    logger.add(
        settings.log_dir / "etl_{time:YYYYMMDD_HHmmss}.log",
        level="DEBUG",
        rotation="50 MB",
        retention=10,
    )

    all_layers = load_layers(Path(config_path))
    layers = [l for l in all_layers if l.enabled]

    if layer_names:
        layers = [l for l in layers if l.name in layer_names]
        if not layers:
            available = [l.name for l in all_layers]
            logger.error(f"No matching layers for {layer_names}. Available: {available}")
            return {}

    logger.info(f"Pipeline starting — {len(layers)} layer(s): {[l.name for l in layers]}")

    client = ArcGISClient(
        timeout=settings.request_timeout,
        max_retries=settings.max_retries,
        token=settings.token,
    )
    extractor = LayerExtractor(client)
    zip_dl = ZipDownloader(timeout=settings.request_timeout)
    loader = GeoJSONLoader(settings.output_dir)

    results: dict[str, dict] = {}
    for layer in layers:
        try:
            features = (
                zip_dl.download_features(layer)
                if layer.source == "zip_download"
                else extractor.extract(layer)
            )
            count = loader.write_layer(layer.output_file, features)
            results[layer.name] = {"status": "ok", "count": count, "file": layer.output_file}
        except Exception as exc:
            logger.error(f"[{layer.name}] FAILED: {exc}")
            results[layer.name] = {"status": "error", "error": str(exc)}

    # Summary
    logger.info("─" * 60)
    logger.info("Pipeline summary:")
    for name, result in results.items():
        if result["status"] == "ok":
            logger.info(f"  ✓ {name}: {result['count']:,} features → {result['file']}")
        else:
            logger.error(f"  ✗ {name}: {result['error']}")

    return results


@click.command()
@click.option(
    "--layer",
    "-l",
    multiple=True,
    metavar="NAME",
    help="Layer name(s) to run. Repeat for multiple. Default: all enabled layers.",
)
@click.option(
    "--config",
    "-c",
    default="config/layers.yaml",
    show_default=True,
    help="Path to layers YAML config.",
)
def cli(layer: tuple[str, ...], config: str) -> None:
    """Ingest SA geospatial planning data from ArcGIS REST APIs into local GeoJSON files."""
    run_pipeline(list(layer) if layer else None, config)
