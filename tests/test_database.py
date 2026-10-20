import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from server import database


class _FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.query = ""
        self.params = None
        self.executemany_calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.params = params

    def executemany(self, query, params_seq):
        self.executemany_calls.append((query, list(params_seq)))

    def fetchall(self):
        return self.rows


class _FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def cursor(self):
        return self.fake_cursor


class QueryVesselsTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "imo": 9482154,
            "name": "MT Ocean Vanguard",
            "mmsi": 636019842,
            "call_sign": "ELVA8",
            "flag": "Liberia",
            "flag_code": "lr",
            "type": "VLCC Crude Tanker",
            "length": "333m",
            "beam": "60m",
            "dwt": "305,000",
            "lat": 2.285,
            "lon": 102.120,
            "heading": 132,
            "speed": 13.8,
            "draft": "19.2m",
            "last_ping": "3 min ago",
            "signal_health": "Dark",
            "is_dark": 1,
            "dark_duration": "3h 48m",
            "risk_score": 95,
            "risk_level": "CRITICAL",
            "track_history_json": "[[2.65, 101.45]]",
        }
        self.cursor = _FakeCursor([self.row])
        self.connection = _FakeConnection(self.cursor)
        self.connection_patch = patch(
            "server.database.get_connection",
            return_value=self.connection,
        )
        self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)

    def test_search_and_high_risk_filter_are_parameterized_in_sql(self):
        result = database.query_vessels(
            "high-risk",
            "' OR 1=1 --",
        )

        self.assertIn("STRPOS(LOWER(name), LOWER(%s)) > 0", self.cursor.query)
        self.assertIn("risk_score >= %s", self.cursor.query)
        self.assertEqual(["' OR 1=1 --"] * 4 + [75], self.cursor.params)
        self.assertEqual([9482154], [vessel["imo"] for vessel in result])

    def test_tanker_filter_executes_as_a_database_predicate(self):
        database.query_vessels("tankers")

        self.assertIn("LOWER(type) LIKE %s OR LOWER(type) LIKE %s", self.cursor.query)
        self.assertEqual(["%tanker%", "%carrier%"], self.cursor.params)

    def test_dark_filter_executes_as_a_database_predicate(self):
        database.query_vessels("dark")

        self.assertIn("is_dark = 1", self.cursor.query)
        self.assertEqual([], self.cursor.params)


class QueryAisVesselsTests(unittest.TestCase):
    def test_current_vessels_and_track_are_scoped_to_viewport(self):
        observed_at = datetime(2026, 10, 18, 12, 34, tzinfo=timezone.utc)
        cursor = _FakeCursor([{
            "mmsi": 123456789,
            "imo": 9876543,
            "name": "TEST VESSEL",
            "call_sign": "TEST",
            "vessel_type": "Tanker",
            "destination": "PORT",
            "latitude": 2.5,
            "longitude": 101.8,
            "speed_knots": 12.4,
            "course_degrees": 135.2,
            "heading_degrees": 136,
            "last_seen": observed_at,
            "track_history": [[2.4, 101.7], [2.5, 101.8]],
        }])
        connection = _FakeConnection(cursor)
        connection_patch = patch(
            "server.database.get_connection",
            return_value=connection,
        )
        connection_patch.start()
        self.addCleanup(connection_patch.stop)

        result, data_source = database.query_ais_vessels(
            min_lat=2.0,
            min_lon=101.0,
            max_lat=3.0,
            max_lon=102.0,
            limit=120,
            track_hours=24,
        )

        self.assertIn("vessel.latitude BETWEEN %s AND %s", cursor.query)
        self.assertIn("jsonb_agg", cursor.query)
        self.assertEqual((24, 2.0, 3.0, 101.0, 102.0, 120), cursor.params)
        self.assertEqual([[2.4, 101.7], [2.5, 101.8]], result[0]["trackHistory"])
        self.assertEqual("live", data_source)

    def test_seed_fallback_is_labeled_demo(self):
        with patch.object(database, "_should_attempt_database", return_value=False):
            result, data_source = database.query_ais_vessels(
                min_lat=1.0,
                min_lon=100.0,
                max_lat=3.0,
                max_lon=103.0,
            )

        self.assertTrue(result)
        self.assertEqual("demo", data_source)


class UpsertAisMessagesTests(unittest.TestCase):
    def test_upsert_deduplicates_and_orders_rows_consistently(self):
        first = datetime(2026, 10, 18, 12, 30, tzinfo=timezone.utc)
        later = datetime(2026, 10, 18, 12, 31, tzinfo=timezone.utc)
        messages = [
            {
                "mmsi": 200,
                "observed_at": first,
                "sampled_at": first,
                "latitude": 2.0,
                "longitude": 102.0,
            },
            {
                "mmsi": 100,
                "observed_at": first,
                "sampled_at": first,
                "latitude": 1.0,
                "longitude": 101.0,
            },
            {
                "mmsi": 100,
                "observed_at": later,
                "sampled_at": first,
                "latitude": 1.5,
                "longitude": 101.5,
            },
            {
                "mmsi": 100,
                "observed_at": later,
                "sampled_at": later,
                "latitude": 1.6,
                "longitude": 101.6,
            },
        ]
        cursor = _FakeCursor([])
        connection = _FakeConnection(cursor)

        with (
            patch.object(database, "_should_attempt_database", return_value=True),
            patch("server.database.get_connection", return_value=connection),
        ):
            result = database.upsert_ais_messages(messages)

        self.assertTrue(result)
        vessel_rows = cursor.executemany_calls[0][1]
        position_rows = cursor.executemany_calls[1][1]
        self.assertEqual([100, 200], [row["mmsi"] for row in vessel_rows])
        self.assertEqual(later, vessel_rows[0]["observed_at"])
        self.assertEqual(
            [(100, first), (100, later), (200, first)],
            [(row["mmsi"], row["sampled_at"]) for row in position_rows],
        )
        self.assertEqual(1.5, position_rows[0]["latitude"])

    def test_database_failure_is_reported_instead_of_succeeding_in_memory(self):
        message = {
            "mmsi": 123456789,
            "latitude": 2.5,
            "longitude": 101.8,
            "sampled_at": datetime(2026, 10, 18, 12, 34, tzinfo=timezone.utc),
        }

        with (
            patch.object(database, "_should_attempt_database", return_value=True),
            patch(
                "server.database.get_connection",
                side_effect=database.psycopg.OperationalError("database unavailable"),
            ),
            patch.object(database, "_in_memory_ais_vessels", {}) as vessels,
        ):
            result = database.upsert_ais_messages([message])

        self.assertFalse(result)
        self.assertEqual({}, vessels)


class SupabaseConnectionTests(unittest.TestCase):
    def tearDown(self):
        database.close_connection_pool()

    def test_remote_postgres_connections_require_tls_by_default(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                "require",
                database._connection_sslmode(
                    "postgresql://postgres@example.supabase.co:5432/postgres"
                ),
            )

    def test_explicit_uri_ssl_mode_is_preserved(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                "verify-full",
                database._connection_sslmode(
                    "postgresql://postgres@example.supabase.co:5432/postgres?sslmode=verify-full"
                ),
            )

    def test_ssl_mode_can_be_overridden_for_local_development(self):
        with patch.dict("os.environ", {"DB_SSLMODE": "disable"}, clear=True):
            self.assertEqual(
                "disable",
                database._connection_sslmode(
                    "postgresql://localhost:5432/spillguard"
                ),
            )

    @patch("server.database.ConnectionPool")
    def test_pool_uses_small_connection_limit_and_disables_prepared_statements(self, pool_factory):
        with patch.dict(
            "os.environ",
            {"DATABASE_URL": "postgresql://postgres@example.supabase.co/postgres"},
            clear=True,
        ):
            pool = MagicMock()
            pool.connection.return_value.__enter__.return_value = object()
            pool_factory.return_value = pool

            with database.get_connection():
                pass

        pool_factory.assert_called_once()
        options = pool_factory.call_args.kwargs
        self.assertEqual(1, options["min_size"])
        self.assertEqual(5, options["max_size"])
        self.assertIsNone(options["kwargs"]["prepare_threshold"])
        self.assertEqual("require", options["kwargs"]["sslmode"])
        pool.connection.assert_called_once_with(timeout=5)

    def test_database_fallback_retries_after_backoff(self):
        with patch.object(database, "_db_available", False), patch.object(
            database, "_db_retry_after", 100.0
        ), patch("server.database.time.monotonic", return_value=99.0):
            self.assertFalse(database._should_attempt_database())

        with patch.object(database, "_db_available", False), patch.object(
            database, "_db_retry_after", 100.0
        ), patch("server.database.time.monotonic", return_value=100.0):
            self.assertTrue(database._should_attempt_database())


class QueryAisPositionsForAttributionTests(unittest.TestCase):
    def test_queries_time_window_radius_and_limit(self):
        observed_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        cursor = _FakeCursor([{"mmsi": 123456789, "observed_at": observed_at}])
        connection = _FakeConnection(cursor)

        with patch("server.database.get_connection") as get_connection:
            get_connection.return_value.__enter__.return_value = connection
            rows = database.query_ais_positions_for_attribution(
                sar_time=observed_at,
                sar_lat=2.3,
                sar_lon=101.9,
                time_window_minutes=45,
                search_radius_km=25.0,
                limit=10,
            )

        self.assertEqual([{"mmsi": 123456789, "observed_at": observed_at}], rows)
        self.assertIn("ais_pos.observed_at BETWEEN", cursor.query)
        self.assertIn("distance_km <=", cursor.query)
        self.assertIn("ROW_NUMBER() OVER", cursor.query)
        self.assertIn("PARTITION BY ais_pos.mmsi", cursor.query)
        self.assertNotIn("position.", cursor.query)
        self.assertEqual((observed_at, 2.3, 101.9, 45, 25.0, 10), cursor.params)


if __name__ == "__main__":
    unittest.main()
