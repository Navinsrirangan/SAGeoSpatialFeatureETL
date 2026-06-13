from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LayerConfig(BaseModel):
    name: str
    description: str
    source: str = "arcgis"          # "arcgis" | "zip_download"
    service_url: str = "CONFIGURE_ME"
    download_url: Optional[str] = None
    output_file: str
    where: str = "1=1"
    out_fields: str = "*"
    page_size: int = 1000
    page_delay: float = 0.5   # seconds to sleep between paginated requests
    geometry_precision: Optional[int] = None  # decimal places; None = server default
    enabled: bool = True

    @model_validator(mode="after")
    def url_must_be_configured_if_enabled(self) -> "LayerConfig":
        if not self.enabled:
            return self
        if self.source == "arcgis" and self.service_url == "CONFIGURE_ME":
            raise ValueError(
                f"Layer '{self.name}' is enabled but service_url is still 'CONFIGURE_ME' -- "
                "update config/layers.yaml with the actual ArcGIS REST Feature Service URL"
            )
        if self.source == "zip_download" and not self.download_url:
            raise ValueError(
                f"Layer '{self.name}' has source=zip_download but download_url is not set"
            )
        return self


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SA_ETL_")

    output_dir: Path = Path("output")
    log_dir: Path = Path("logs")
    request_timeout: int = 120
    max_retries: int = 5
    token: Optional[str] = None


def load_layers(config_path: Path = Path("config/layers.yaml")) -> list[LayerConfig]:
    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return [LayerConfig(**layer) for layer in data["layers"]]
