import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from server.drift import BacktrackResult, DriftDataUnavailable
from server.api import detect_satellite_image, detect_satellite_image_candidates


def _request(content_type, body):
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/detect/image",
        "headers": [(b"content-type", content_type.encode("ascii"))],
    }
    return Request(scope, receive)


class SatelliteImageApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_binary_geotiff_upload_is_forwarded_to_detector(self):
        request = _request("image/tiff", b"geotiff-data")
        expected = {"status": "ok", "input": {"source": "sentinel1_geotiff"}}

        with patch("server.api.run_detection_on_geotiff", return_value=expected) as detector:
            response = await detect_satellite_image(
                request,
                backscatter_min_db=-30.0,
                backscatter_max_db=0.0,
                threshold=0.5,
            )

        self.assertEqual(expected, response)
        detector.assert_called_once_with(
            b"geotiff-data",
            backscatter_min_db=-30.0,
            backscatter_max_db=0.0,
            threshold=0.5,
        )

    async def test_detection_response_records_selected_catalog_scene(self):
        request = _request("image/tiff", b"geotiff-data")
        expected = {"status": "ok", "input": {"source": "sentinel1_geotiff"}}
        acquisition_time = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)

        with patch("server.api.run_detection_on_geotiff", return_value=expected):
            response = await detect_satellite_image(
                request,
                scene_id="S1A_TEST_SCENE",
                acquisition_time=acquisition_time,
            )

        self.assertEqual("S1A_TEST_SCENE", response["input"]["scene_id"])
        self.assertEqual(
            "Alaska Satellite Facility (ASF) DAAC",
            response["input"]["catalog_source"],
        )
        self.assertEqual(
            "2025-01-02T03:04:00+00:00",
            response["input"]["acquisition_time"],
        )

    async def test_non_tiff_upload_is_rejected(self):
        request = _request("application/json", b"{}")

        with self.assertRaises(HTTPException) as raised:
            await detect_satellite_image(request)

        self.assertEqual(415, raised.exception.status_code)

    async def test_detection_endpoint_searches_candidates_for_each_cluster(self):
        request = _request("image/tiff", b"geotiff-data")
        detection = {
            "status": "ok",
            "clusters": [
                {"cluster_id": 3, "centroid": [2.3, 101.9]},
            ],
        }
        candidates = {
            "candidate_count": 1,
            "candidates": [{"mmsi": "123456789", "score": 95.0}],
            "search": {"time_window_minutes": 30, "search_radius_km": 50.0},
        }
        source_time = datetime(2025, 1, 1, 0, tzinfo=timezone.utc)
        backtrack = BacktrackResult(
            source_lat=2.2,
            source_lon=101.8,
            source_time=source_time,
            displacement_km=12.5,
            path_length_km=12.5,
            path=[{"time": source_time.isoformat(), "lat": 2.2, "lon": 101.8}],
        )
        with (
            patch("server.api.run_detection_on_geotiff", return_value=detection),
            patch("server.api.sar_ais_candidates", return_value=candidates) as search,
            patch("server.api.fetch_environmental_drift", return_value=[object()]),
            patch("server.api.backtrack_slick", return_value=backtrack),
        ):
            response = await detect_satellite_image_candidates(
                request,
                sar_time="2025-01-01T12:00:00Z",
                time_window_minutes=30,
                search_radius_km=50.0,
                candidate_limit=200,
                drift_hours=12,
                drift_uncertainty_km=5.0,
                windage_coefficient=0.03,
            )

        self.assertEqual(detection, {key: value for key, value in response.items() if key != "ais_attribution"})
        search.assert_called_once()
        request_payload = search.call_args.args[0]
        self.assertEqual(3, response["ais_attribution"]["clusters"][0]["cluster_id"])
        self.assertEqual("corrected", response["ais_attribution"]["clusters"][0]["drift"]["status"])
        self.assertEqual("2025-01-01T00:00:00+00:00", request_payload.sar_time)
        self.assertEqual(2.2, request_payload.sar_lat)
        self.assertEqual(101.8, request_payload.sar_lon)
        self.assertTrue(response["ais_attribution"]["drift_corrected"])
        self.assertEqual(
            "not_validated_for_operational_use",
            response["ais_attribution"]["validation_status"],
        )
        self.assertIn(
            "must not be used operationally",
            response["ais_attribution"]["warning"],
        )
        self.assertIn("not proof of", response["ais_attribution"]["warning"])

    async def test_environmental_data_failure_is_explicit_and_uses_observed_slick(self):
        request = _request("image/tiff", b"geotiff-data")
        detection = {
            "status": "ok",
            "clusters": [{"cluster_id": 4, "centroid": [2.3, 101.9]}],
        }
        candidates = {
            "candidate_count": 0,
            "candidates": [],
            "search": {"time_window_minutes": 30, "search_radius_km": 50.0},
        }
        with (
            patch("server.api.run_detection_on_geotiff", return_value=detection),
            patch("server.api.sar_ais_candidates", return_value=candidates) as search,
            patch(
                "server.api.fetch_environmental_drift",
                side_effect=DriftDataUnavailable("No complete samples."),
            ),
        ):
            response = await detect_satellite_image_candidates(
                request,
                sar_time="2025-01-01T12:00:00Z",
                time_window_minutes=30,
                search_radius_km=50.0,
                candidate_limit=200,
                drift_hours=12,
                drift_uncertainty_km=5.0,
                windage_coefficient=0.03,
            )

        search_payload = search.call_args.args[0]
        self.assertEqual("2025-01-01T12:00:00Z", search_payload.sar_time)
        self.assertEqual(2.3, search_payload.sar_lat)
        self.assertEqual(101.9, search_payload.sar_lon)
        group = response["ais_attribution"]["clusters"][0]
        self.assertEqual("unavailable", group["drift"]["status"])
        self.assertEqual("No complete samples.", group["drift"]["reason"])
        self.assertFalse(response["ais_attribution"]["drift_corrected"])

    async def test_integrated_endpoint_requires_timezone_aware_timestamp(self):
        request = _request("image/tiff", b"geotiff-data")

        with self.assertRaises(HTTPException) as raised:
            await detect_satellite_image_candidates(
                request,
                sar_time="2025-01-01T12:00:00",
                drift_hours=12,
                drift_uncertainty_km=5.0,
                windage_coefficient=0.03,
            )

        self.assertEqual(400, raised.exception.status_code)

    async def test_integrated_endpoint_rejects_unsupported_drift_duration(self):
        request = _request("image/tiff", b"not-read")

        with self.assertRaises(HTTPException) as raised:
            await detect_satellite_image_candidates(
                request,
                sar_time="2025-01-01T12:00:00Z",
                drift_hours=7,
            )

        self.assertEqual(422, raised.exception.status_code)


if __name__ == "__main__":
    unittest.main()
