"""Sentinel-1 scene discovery through the Alaska Satellite Facility catalog."""

import json
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ASF_SEARCH_URL = "https://api.daac.asf.alaska.edu/services/search/param"
ASF_SEARCH_PAGE_URL = "https://search.asf.alaska.edu/"


class SatelliteCatalogUnavailable(RuntimeError):
    """Raised when the external Sentinel-1 catalog cannot be queried."""


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Search dates must include a timezone.")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_product(feature: Dict[str, Any]) -> Dict[str, Any]:
    properties = feature.get("properties") or {}
    granule = (
        properties.get("sceneName")
        or properties.get("granuleName")
        or properties.get("fileName")
        or feature.get("id")
        or "Unknown Sentinel-1 scene"
    )
    product_url = properties.get("url") or properties.get("downloadUrl")
    catalog_query = urlencode({"granule": granule})

    return {
        "id": str(granule),
        "platform": properties.get("platform") or properties.get("platformName") or "Sentinel-1",
        "acquisition_start": properties.get("startTime") or properties.get("start_time"),
        "acquisition_end": properties.get("stopTime") or properties.get("stop_time"),
        "processing_level": properties.get("processingLevel") or properties.get("processing_level"),
        "beam_mode": properties.get("beamModeType") or properties.get("beamMode") or properties.get("beam_mode"),
        "polarization": properties.get("polarization"),
        "flight_direction": properties.get("flightDirection") or properties.get("flight_direction"),
        "download_url": product_url,
        "catalog_url": f"{ASF_SEARCH_PAGE_URL}#/?{catalog_query}",
        "geometry": feature.get("geometry"),
    }


def search_sentinel1(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    start_date: datetime,
    end_date: datetime,
    limit: int = 25,
) -> Dict[str, Any]:
    if min_lat > max_lat or min_lon > max_lon:
        raise ValueError("Minimum map bounds must not exceed maximum bounds.")
    start_utc = _iso_utc(start_date)
    end_utc = _iso_utc(end_date)
    if start_date.astimezone(timezone.utc) > end_date.astimezone(timezone.utc):
        raise ValueError("Start date must not be later than end date.")
    if not 1 <= limit <= 50:
        raise ValueError("Result limit must be between 1 and 50.")

    wkt = (
        f"POLYGON(({min_lon} {min_lat},{max_lon} {min_lat},"
        f"{max_lon} {max_lat},{min_lon} {max_lat},{min_lon} {min_lat}))"
    )
    query = urlencode({
        "platform": "Sentinel-1",
        "intersectsWith": wkt,
        "start": start_utc,
        "end": end_utc,
        "output": "json",
        "maxResults": limit,
    })
    request = Request(
        f"{ASF_SEARCH_URL}?{query}",
        headers={"Accept": "application/json", "User-Agent": "SpillSense/1.0"},
    )

    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise SatelliteCatalogUnavailable(
            "The ASF Sentinel-1 catalog could not be reached. Try again later."
        ) from exc

    if isinstance(payload, dict):
        features = payload.get("features")
    else:
        features = payload
    if not isinstance(features, list):
        raise SatelliteCatalogUnavailable(
            "The ASF catalog returned an unexpected response."
        )

    products = [
        _normalize_product(feature)
        for feature in features
        if isinstance(feature, dict)
    ]
    products.sort(
        key=lambda product: product["acquisition_start"] or "",
        reverse=True,
    )
    return {
        "source": "Alaska Satellite Facility (ASF) DAAC",
        "catalog_url": ASF_SEARCH_PAGE_URL,
        "search": {
            "min_lat": min_lat,
            "min_lon": min_lon,
            "max_lat": max_lat,
            "max_lon": max_lon,
            "start": start_utc,
            "end": end_utc,
            "returned": len(products),
        },
        "products": products,
        "preparation": (
            "ASF catalog results are scene metadata, not imagery pixels. Product "
            "downloads may require Earthdata authentication. The detector accepts "
            "a calibrated, single-band projected GeoTIFF in metres via /api/detect/image."
        ),
    }
