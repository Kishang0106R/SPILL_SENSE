import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import HTTPException, Response
from pydantic import ValidationError

from server.api import ais_vessels, sar_ais_candidates
from server.models import SarAisCandidateRequest


class SarAisCandidateApiTests(unittest.TestCase):
    def setUp(self):
        self.payload = SarAisCandidateRequest(
            sar_time="2025-01-01T12:00:00Z",
            sar_lat=2.3,
            sar_lon=101.9,
        )
        self.position = {
            "mmsi": 123456789,
            "vessel_name": "Test Vessel",
            "vessel_type": "Cargo",
            "latitude": 2.3,
            "longitude": 101.9,
            "speed_knots": 10.0,
            "course_degrees": 90.0,
            "observed_at": datetime(2025, 1, 1, 12, tzinfo=timezone.utc),
            "distance_km": 0.0,
        }

    @patch("server.api.query_ais_positions_for_attribution")
    def test_returns_candidates_from_stored_ais_positions(self, query):
        query.return_value = [self.position]

        response = sar_ais_candidates(self.payload)

        query.assert_called_once()
        self.assertEqual(1, response["candidate_count"])
        candidate = response["candidates"][0]
        self.assertEqual("123456789", candidate["mmsi"])
        self.assertEqual("higher", candidate["review_priority"])
        self.assertNotIn("matched", candidate)
        self.assertEqual(
            "heuristic_match_score_not_probability", response["score_type"]
        )
        self.assertFalse(response["drift_corrected"])
        self.assertIn("do not establish spill causation", response["warning"])

    @patch("server.api.query_ais_positions_for_attribution", return_value=[])
    def test_empty_query_returns_no_candidates(self, query):
        response = sar_ais_candidates(self.payload)

        self.assertEqual([], response["candidates"])
        self.assertEqual(0, response["candidate_count"])
        self.assertTrue(response["warning"])

    @patch("server.api.query_ais_positions_for_attribution", return_value=[])
    def test_requires_timezone_aware_acquisition_time(self, query):
        payload = self.payload.model_copy(update={"sar_time": "2025-01-01T12:00:00"})

        with self.assertRaises(HTTPException) as raised:
            sar_ais_candidates(payload)

        self.assertEqual(400, raised.exception.status_code)
        query.assert_not_called()

    @patch("server.api.query_ais_positions_for_attribution")
    def test_database_failure_returns_service_unavailable(self, query):
        import psycopg

        query.side_effect = psycopg.OperationalError("database unavailable")

        with self.assertRaises(HTTPException) as raised:
            sar_ais_candidates(self.payload)

        self.assertEqual(503, raised.exception.status_code)

    def test_rejects_coordinates_outside_geographic_bounds(self):
        with self.assertRaises(ValidationError):
            SarAisCandidateRequest(
                sar_time="2025-01-01T12:00:00Z",
                sar_lat=91,
                sar_lon=101.9,
            )


class AisVesselsApiTests(unittest.TestCase):
    @patch("server.api.query_ais_vessels", return_value=([], "demo"))
    def test_returns_source_header_with_existing_list_response(self, query):
        response = Response()

        result = ais_vessels(
            response=response,
            min_lat=-10,
            min_lon=-20,
            max_lat=10,
            max_lon=20,
            limit=100,
            track_hours=3,
        )

        self.assertEqual([], result)
        self.assertEqual("demo", response.headers["X-AIS-Data-Source"])
        query.assert_called_once_with(-10, -20, 10, 20, 100, 3)


if __name__ == "__main__":
    unittest.main()
