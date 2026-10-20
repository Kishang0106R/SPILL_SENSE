import unittest
import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

from server.aisstream import _flush_batch, normalize_ais_message, run_aisstream


class NormalizeAisMessageTests(unittest.TestCase):
    def test_position_report_is_normalized_and_sampled_by_utc_minute(self):
        result = normalize_ais_message({
            "MessageType": "PositionReport",
            "MetaData": {
                "MMSI": 123456789,
                "ShipName": "TEST VESSEL",
                "time_utc": "2026-10-18T12:34:56.789Z",
            },
            "Message": {
                "PositionReport": {
                    "UserID": 123456789,
                    "Latitude": 2.5,
                    "Longitude": 101.8,
                    "Sog": 12.4,
                    "Cog": 135.2,
                    "TrueHeading": 136,
                },
            },
        })

        self.assertEqual(123456789, result["mmsi"])
        self.assertEqual("TEST VESSEL", result["name"])
        self.assertEqual(2.5, result["latitude"])
        self.assertEqual(101.8, result["longitude"])
        self.assertEqual(12.4, result["speed_knots"])
        self.assertEqual(
            datetime(2026, 10, 18, 12, 34, tzinfo=timezone.utc),
            result["sampled_at"],
        )

    def test_provider_utc_timestamp_with_nanoseconds_is_parsed(self):
        result = normalize_ais_message({
            "MessageType": "PositionReport",
            "MetaData": {
                "MMSI": 123456789,
                "time_utc": "2026-10-19 08:53:43.974885083 +0000 UTC",
            },
            "Message": {
                "PositionReport": {
                    "UserID": 123456789,
                    "Latitude": 2.5,
                    "Longitude": 101.8,
                },
            },
        })

        self.assertEqual(
            datetime(2026, 10, 19, 8, 53, 43, 974885, tzinfo=timezone.utc),
            result["observed_at"],
        )
        self.assertEqual(
            datetime(2026, 10, 19, 8, 53, tzinfo=timezone.utc),
            result["sampled_at"],
        )

    def test_invalid_mmsi_is_rejected(self):
        result = normalize_ais_message({
            "MessageType": "PositionReport",
            "MetaData": {"MMSI": "not-an-mmsi"},
            "Message": {"PositionReport": {}},
        })

        self.assertIsNone(result)

    def test_missing_mmsi_is_rejected(self):
        result = normalize_ais_message({
            "MessageType": "PositionReport",
            "MetaData": {},
            "Message": {"PositionReport": {}},
        })

        self.assertIsNone(result)

    def test_out_of_range_coordinates_do_not_create_a_track_point(self):
        result = normalize_ais_message({
            "MessageType": "PositionReport",
            "MetaData": {"MMSI": 123456789, "time_utc": "2026-10-18T12:34:56Z"},
            "Message": {
                "PositionReport": {
                    "UserID": 123456789,
                    "Latitude": 91,
                    "Longitude": 181,
                },
            },
        })

        self.assertIsNone(result["latitude"])
        self.assertIsNone(result["longitude"])


class AisPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_batch_persistence_keeps_messages_for_retry(self):
        batch = [{"mmsi": 123456789}]

        with patch("server.aisstream.upsert_ais_messages", return_value=False):
            with self.assertRaisesRegex(ConnectionError, "retaining it for retry"):
                await _flush_batch(batch)

        self.assertEqual([{"mmsi": 123456789}], batch)

    async def test_successful_batch_persistence_clears_messages(self):
        batch = [{"mmsi": 123456789}]

        with patch("server.aisstream.upsert_ais_messages", return_value=True):
            await _flush_batch(batch)

        self.assertEqual([], batch)

    async def test_receiver_reconnects_after_websocket_disconnect(self):
        class FakeWebSocket:
            def __init__(self):
                self.sent = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return False

            async def send(self, message):
                self.sent.append(message)

            async def recv(self):
                raise ConnectionError("simulated WebSocket disconnect")

        connections = []
        connection_options = []

        def connect(*args, **kwargs):
            websocket = FakeWebSocket()
            connections.append(websocket)
            connection_options.append(kwargs)
            return websocket

        sleep_calls = 0

        delays = []

        async def immediate_sleep(delay):
            nonlocal sleep_calls
            sleep_calls += 1
            delays.append(delay)
            if sleep_calls == 2:
                raise asyncio.CancelledError

        async def wait_for_cancellation():
            await asyncio.Future()

        with (
            patch("server.aisstream.websockets.connect", side_effect=connect),
            patch("server.aisstream._prune_old_positions", wait_for_cancellation),
            patch("server.aisstream.asyncio.sleep", side_effect=immediate_sleep),
            patch("server.aisstream.random.uniform", side_effect=lambda _low, high: high),
            patch("server.aisstream.logger.exception"),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await run_aisstream("test-key")

        self.assertEqual(2, len(connections))
        self.assertEqual([1.0, 2.0], delays)
        self.assertEqual(30, connection_options[0]["open_timeout"])
        self.assertEqual(60, connection_options[0]["ping_timeout"])
        self.assertTrue(connections[0].sent)


if __name__ == "__main__":
    unittest.main()
