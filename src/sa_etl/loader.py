from __future__ import annotations

import json
from pathlib import Path
from typing import Generator

from loguru import logger


class GeoJSONLoader:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write_layer(
        self,
        filename: str,
        features: Generator[dict, None, None],
    ) -> int:
        """Stream features into a GeoJSON FeatureCollection file. Returns feature count."""
        path = self.output_dir / filename
        count = 0

        with open(path, "w", encoding="utf-8") as f:
            f.write('{"type":"FeatureCollection","features":[\n')
            first = True
            for feature in features:
                if not first:
                    f.write(",\n")
                f.write(json.dumps(feature, separators=(",", ":")))
                first = False
                count += 1
            f.write("\n]}\n")

        size_mb = path.stat().st_size / 1_048_576
        if count == 0:
            logger.warning(f"Wrote 0 features → {path} — layer may be empty or the query returned no results")
        else:
            logger.info(f"Wrote {count:,} features → {path} ({size_mb:.1f} MB)")
        return count
