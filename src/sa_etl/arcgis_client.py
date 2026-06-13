from __future__ import annotations

import json as _json
import time
from typing import Generator, Optional

import requests
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

class _RetryableError(Exception):
    """Wraps transient server errors so tenacity can retry them."""


_RETRYABLE_REQUESTS = (
    requests.Timeout,
    requests.ConnectionError,
    requests.exceptions.ChunkedEncodingError,
    _RetryableError,
)


class ArcGISClient:
    def __init__(
        self,
        timeout: int = 60,
        max_retries: int = 5,
        token: Optional[str] = None,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        if token:
            self.session.params = {"token": token}  # type: ignore[assignment]

    def _get_json(self, url: str, params: dict) -> dict:
        @retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=2, min=4, max=120),
            retry=retry_if_exception_type(_RETRYABLE_REQUESTS),
            reraise=True,
        )
        def _request() -> dict:
            resp = self.session.get(url, params=params, timeout=self.timeout)

            # Retry on 5xx server errors (transient); let 4xx propagate (permanent)
            if resp.status_code >= 500:
                raise _RetryableError(
                    f"HTTP {resp.status_code} from {url} — {resp.text[:200]!r}"
                )
            resp.raise_for_status()

            text = resp.text.strip()
            if not text:
                raise _RetryableError(f"Empty response body from {url}")

            try:
                return resp.json()
            except _json.JSONDecodeError as exc:
                raise _RetryableError(
                    f"Malformed JSON from {url} ({exc}); body={text[:200]!r}"
                ) from exc

        return _request()

    def get_service_info(self, service_url: str) -> dict:
        return self._get_json(service_url, {"f": "json"})

    def get_feature_count(self, service_url: str, where: str = "1=1") -> int:
        data = self._get_json(
            f"{service_url}/query",
            {"where": where, "returnCountOnly": "true", "f": "json"},
        )
        return int(data.get("count", 0))

    def fetch_features_paginated(
        self,
        service_url: str,
        where: str = "1=1",
        out_fields: str = "*",
        page_size: int = 1000,
        page_delay: float = 0.5,
        geometry_precision: Optional[int] = None,
    ) -> Generator[list[dict], None, None]:
        """Yield pages of GeoJSON features. Auto-selects pagination strategy."""
        info = self.get_service_info(service_url)
        max_record_count = info.get("maxRecordCount", page_size)
        effective_page = min(page_size, max_record_count)

        supports_pagination = (
            info.get("advancedQueryCapabilities", {})
            .get("supportsPagination", True)
        )

        if supports_pagination:
            logger.debug(f"Using offset-based pagination (page={effective_page})")
            yield from self._fetch_by_offset(service_url, where, out_fields, effective_page, page_delay, geometry_precision)
        else:
            logger.info("Service does not support offset pagination — using OID-based strategy")
            yield from self._fetch_by_oids(service_url, where, out_fields, effective_page, page_delay, geometry_precision)

    # ── Pagination strategies ────────────────────────────────────────────────

    def _fetch_by_offset(
        self,
        service_url: str,
        where: str,
        out_fields: str,
        page_size: int,
        page_delay: float = 0.5,
        geometry_precision: Optional[int] = None,
    ) -> Generator[list[dict], None, None]:
        offset = 0
        while True:
            params: dict = {
                "where": where,
                "outFields": out_fields,
                "outSR": "4326",
                "returnGeometry": "true",
                "f": "geojson",
                "resultOffset": offset,
                "resultRecordCount": page_size,
            }
            if geometry_precision is not None:
                params["geometryPrecision"] = geometry_precision
            data = self._get_json(f"{service_url}/query", params)
            features: list[dict] = data.get("features", [])
            if not features:
                break

            yield features

            exceeded = data.get("exceededTransferLimit", False)
            if not exceeded:
                break
            offset += len(features)
            if page_delay > 0:
                time.sleep(page_delay)

    def _fetch_by_oids(
        self,
        service_url: str,
        where: str,
        out_fields: str,
        page_size: int,
        page_delay: float = 0.5,
        geometry_precision: Optional[int] = None,
    ) -> Generator[list[dict], None, None]:
        oid_data = self._get_json(
            f"{service_url}/query",
            {"where": where, "returnIdsOnly": "true", "f": "json"},
        )
        oids: list[int] = oid_data.get("objectIds") or []
        logger.info(f"OID strategy: retrieved {len(oids):,} object IDs")

        for i in range(0, len(oids), page_size):
            batch = oids[i : i + page_size]
            params: dict = {
                "objectIds": ",".join(str(o) for o in batch),
                "outFields": out_fields,
                "outSR": "4326",
                "returnGeometry": "true",
                "f": "geojson",
            }
            if geometry_precision is not None:
                params["geometryPrecision"] = geometry_precision
            data = self._get_json(f"{service_url}/query", params)
            features: list[dict] = data.get("features", [])
            if features:
                yield features
            if page_delay > 0:
                time.sleep(page_delay)
