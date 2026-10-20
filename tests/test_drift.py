import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from server.drift import (
    DriftDataUnavailable,
    DriftSample,
    backtrack_slick,
    fetch_environmental_drift,
)


class DriftBacktrackingTests(unittest.TestCase):
    def setUp(self):
        self.sar_time = datetime(2025, 1, 1, 12, tzinfo=timezone.utc)

    def _samples(self, hours, current_speed=1.0, current_direction=0.0,
                 wind_speed=0.0, wind_direction=0.0):
        return [
            DriftSample(
                time_utc=self.sar_time - timedelta(hours=hour + 1),
                current_speed_mps=current_speed,
                current_direction_degrees=current_direction,
                wind_speed_mps=wind_speed,
                wind_direction_from_degrees=wind_direction,
            )
            for hour in range(hours)
        ]

    def test_constant_north_current_backtracks_south_and_sets_release_time(self):
        result = backtrack_slick(
            latitude=0.0,
            longitude=0.0,
            sar_time=self.sar_time,
            drift_hours=6,
            samples=self._samples(6),
        )

        self.assertAlmostEqual(-0.1945, result.source_lat, places=3)
        self.assertAlmostEqual(0.0, result.source_lon, places=5)
        self.assertEqual(self.sar_time - timedelta(hours=6), result.source_time)
        self.assertAlmostEqual(21.6, result.displacement_km, places=3)
        self.assertEqual(7, len(result.path))

    def test_wind_from_west_is_added_as_downwind_east_drift(self):
        result = backtrack_slick(
            latitude=0.0,
            longitude=0.0,
            sar_time=self.sar_time,
            drift_hours=6,
            samples=self._samples(
                6,
                current_speed=0.0,
                wind_speed=10.0,
                wind_direction=270.0,
            ),
            windage_coefficient=0.1,
        )

        self.assertLess(result.source_lon, 0.0)
        self.assertAlmostEqual(21.6, result.displacement_km, places=3)

    def test_missing_environmental_hour_fails_without_zero_fill(self):
        samples = self._samples(6)[:-1]

        with self.assertRaisesRegex(DriftDataUnavailable, "sample missing"):
            backtrack_slick(
                latitude=0.0,
                longitude=0.0,
                sar_time=self.sar_time,
                drift_hours=6,
                samples=samples,
            )

    def test_rejects_naive_timestamp_and_invalid_hours(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            backtrack_slick(
                latitude=0,
                longitude=0,
                sar_time=datetime(2025, 1, 1, 12),
                drift_hours=6,
                samples=[],
            )
        with self.assertRaisesRegex(ValueError, "one of 6"):
            backtrack_slick(
                latitude=0,
                longitude=0,
                sar_time=self.sar_time,
                drift_hours=7,
                samples=[],
            )


class OpenMeteoSampleTests(unittest.TestCase):
    def test_converts_current_speed_and_joins_hourly_wind_by_utc(self):
        start_time = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=2)
        times = [
            (start_time + timedelta(hours=hour)).strftime("%Y-%m-%dT%H:%M")
            for hour in range(72)
        ]
        marine = {
            "hourly_units": {"ocean_current_velocity": "km/h"},
            "hourly": {
                "time": times,
                "ocean_current_velocity": [3.6] * len(times),
                "ocean_current_direction": [90.0] * len(times),
            },
        }
        weather = {
            "hourly_units": {"wind_speed_10m": "m/s"},
            "hourly": {
                "time": times,
                "wind_speed_10m": [5.0] * len(times),
                "wind_direction_10m": [270.0] * len(times),
            },
        }
        with patch(
            "server.drift._hourly_payload",
            side_effect=[marine, weather],
        ) as get_payload:
            samples = fetch_environmental_drift(
                2.3,
                101.9,
                datetime.now(timezone.utc) - timedelta(hours=1),
                6,
            )

        self.assertEqual(2, get_payload.call_count)
        self.assertEqual(1.0, samples[0].current_speed_mps)
        self.assertEqual(5.0, samples[0].wind_speed_mps)
        self.assertEqual(270.0, samples[0].wind_direction_from_degrees)

    def test_missing_hourly_variables_are_reported(self):
        with (
            patch(
                "server.drift._hourly_payload",
                side_effect=[
                    {"hourly": {}},
                    {"hourly": {}},
                ],
            ),
            self.assertRaisesRegex(DriftDataUnavailable, "missing required"),
        ):
            fetch_environmental_drift(
                2.3,
                101.9,
                datetime.now(timezone.utc) - timedelta(hours=1),
                6,
            )


if __name__ == "__main__":
    unittest.main()
