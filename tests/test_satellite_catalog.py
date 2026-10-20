import json
import unittest
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from server.satellite_catalog import (
    SatelliteCatalogUnavailable,
    search_sentinel1,
)


class SentinelCatalogTests(unittest.TestCase):
    def test_search_normalizes_acquisition_metadata_and_catalog_source(self):
        payload = [
            {
                "id": "S1A_TEST_SCENE",
                "geometry": {"type": "Polygon", "coordinates": []},
                "properties": {
                    "sceneName": "S1A_TEST_SCENE",
                    "platform": "Sentinel-1A",
                    "startTime": "2025-01-02T03:04:05Z",
                    "stopTime": "2025-01-02T03:04:35Z",
                    "processingLevel": "GRD_HD",
                    "beamModeType": "IW",
                    "polarization": "VV+VH",
                    "url": "https://example.invalid/scene.zip",
                },
            }
        ]
        response = BytesIO(json.dumps(payload).encode("utf-8"))

        with patch("server.satellite_catalog.urlopen", return_value=response) as open_url:
            result = search_sentinel1(
                1.0,
                100.0,
                4.0,
                103.0,
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 3, tzinfo=timezone.utc),
            )

        product = result["products"][0]
        self.assertEqual("Alaska Satellite Facility (ASF) DAAC", result["source"])
        self.assertEqual("S1A_TEST_SCENE", product["id"])
        self.assertEqual("2025-01-02T03:04:05Z", product["acquisition_start"])
        self.assertEqual("GRD_HD", product["processing_level"])
        self.assertEqual("VV+VH", product["polarization"])
        self.assertEqual("https://example.invalid/scene.zip", product["download_url"])
        self.assertEqual({"type": "Polygon", "coordinates": []}, product["geometry"])

        query = parse_qs(urlparse(open_url.call_args.args[0].full_url).query)
        self.assertEqual(["Sentinel-1"], query["platform"])
        self.assertEqual(
            ["POLYGON((100.0 1.0,103.0 1.0,103.0 4.0,100.0 4.0,100.0 1.0))"],
            query["intersectsWith"],
        )
        self.assertEqual(["25"], query["maxResults"])

    def test_empty_catalog_results_are_returned_as_empty(self):
        with patch(
            "server.satellite_catalog.urlopen",
            return_value=BytesIO(b"[]"),
        ):
            result = search_sentinel1(
                1, 100, 4, 103,
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 3, tzinfo=timezone.utc),
            )

        self.assertEqual([], result["products"])
        self.assertEqual(0, result["search"]["returned"])

    def test_invalid_bounds_and_naive_dates_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "bounds"):
            search_sentinel1(
                4, 100, 1, 103,
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 3, tzinfo=timezone.utc),
            )
        with self.assertRaisesRegex(ValueError, "timezone"):
            search_sentinel1(
                1, 100, 4, 103,
                datetime(2025, 1, 1),
                datetime(2025, 1, 3, tzinfo=timezone.utc),
            )

    def test_catalog_network_errors_are_explicit(self):
        with patch(
            "server.satellite_catalog.urlopen",
            side_effect=TimeoutError("timed out"),
        ):
            with self.assertRaises(SatelliteCatalogUnavailable):
                search_sentinel1(
                    1, 100, 4, 103,
                    datetime(2025, 1, 1, tzinfo=timezone.utc),
                    datetime(2025, 1, 3, tzinfo=timezone.utc),
                )


if __name__ == "__main__":
    unittest.main()
