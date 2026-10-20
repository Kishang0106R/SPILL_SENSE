"""
Spill Sense Database Layer - PostgreSQL Persistence & In-Memory Fallback
Handles tables for spills, vessels, investigations, analyst notes, and analytics.
When PostgreSQL is offline or unreachable, seamlessly provides in-memory demo data.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from threading import Lock
from contextlib import contextmanager
from pathlib import Path
from typing import List, Dict, Any, Generator, Optional
from urllib.parse import parse_qs, urlsplit

import psycopg
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool, PoolTimeout
from psycopg.rows import DictRow, dict_row

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger(__name__)

# Track whether PostgreSQL is currently accessible
_db_available: Optional[bool] = None
_db_retry_after = 0.0
_connection_pool: Optional[ConnectionPool[psycopg.Connection[DictRow]]] = None
_connection_pool_url: Optional[str] = None
_connection_pool_lock = Lock()


def _connection_sslmode(database_url: str) -> Optional[str]:
    configured_sslmode = os.getenv("DB_SSLMODE")
    if configured_sslmode:
        return configured_sslmode

    uri_sslmode = parse_qs(urlsplit(database_url).query).get("sslmode")
    if uri_sslmode:
        return uri_sslmode[0]

    host = urlsplit(database_url).hostname
    if host and host not in {"localhost", "127.0.0.1", "::1"}:
        return "require"
    return "prefer"


@contextmanager
def get_connection() -> Generator[psycopg.Connection[DictRow], None, None]:
    global _db_available
    global _connection_pool, _connection_pool_url
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/spillguard",
    )
    with _connection_pool_lock:
        if _connection_pool is None or _connection_pool_url != database_url:
            if _connection_pool is not None:
                _connection_pool.close()
            _connection_pool = ConnectionPool(
                conninfo=database_url,
                min_size=1,
                max_size=5,
                timeout=5,
                kwargs={
                    "connect_timeout": 5,
                    "row_factory": dict_row,
                    "prepare_threshold": None,
                    "sslmode": _connection_sslmode(database_url),
                },
                open=True,
            )
            _connection_pool_url = database_url
    try:
        with _connection_pool.connection(timeout=5) as conn:
            _db_available = True
            yield conn
    except psycopg.OperationalError as exc:
        _mark_db_unavailable(exc)
        raise


def close_connection_pool() -> None:
    global _connection_pool, _connection_pool_url
    with _connection_pool_lock:
        if _connection_pool is not None:
            _connection_pool.close()
            _connection_pool = None
            _connection_pool_url = None


def check_database_connection() -> Dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT current_database() AS database_name,
                       current_user AS database_role,
                       current_setting('server_version') AS server_version
            """)
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("PostgreSQL did not return connection metadata.")
    return {
        "connected": True,
        "database": row["database_name"],
        "role": row["database_role"],
        "serverVersion": row["server_version"],
    }


def _is_mocked() -> bool:
    """Return True if get_connection is mocked (e.g. during unit tests)."""
    return (
        hasattr(get_connection, "mock_calls")
        or hasattr(get_connection, "_mock_return_value")
        or hasattr(get_connection, "return_value")
    )


def _mark_db_unavailable(exc: Optional[Exception] = None) -> None:
    global _db_available, _db_retry_after
    _db_available = False
    _db_retry_after = time.monotonic() + 30
    if exc:
        logger.warning(
            "PostgreSQL unavailable (%s); database-backed operations may use in-memory demo data.",
            exc,
        )


def _should_attempt_database() -> bool:
    return _db_available is not False or time.monotonic() >= _db_retry_after


# ===========================================================================
# SEED & IN-MEMORY DATASETS
# ===========================================================================
SEED_SPILLS = [
    {
        "id": "SG-8842",
        "title": "Malacca Strait TSS Central Infiltration",
        "severity": "critical",
        "status": "UNATTRIBUTED DISCHARGE",
        "lat": 2.3812,
        "lon": 101.9124,
        "area_km2": 45.2,
        "volume_bbls": 18400,
        "confidence": 96.8,
        "sensor": "Sentinel-1A (C-Band IW VV+VH)",
        "detected_at": "2026-09-16 04:12:44 UTC",
        "wind": "14 kt NW (310°)",
        "current": "1.8 kt SE (135°)",
        "surface_temp": "29.4°C",
        "slick_type": "Heavy Crude Oil Emulsion",
        "thumbnail": "assets/images/sar_slick_detail.jpg",
        "primary_suspect": {
            "name": "MT Ocean Vanguard",
            "imo": 9482154,
            "confidence": 94.8,
            "matchType": "High Forensic Correlation"
        },
        "polygon": [
            [2.420, 101.860], [2.435, 101.905], [2.410, 101.960],
            [2.370, 101.980], [2.340, 101.930], [2.355, 101.875]
        ]
    },
    {
        "id": "SG-8839",
        "title": "Cape Rachado Outer Slick",
        "severity": "medium",
        "status": "UNDER INVESTIGATION",
        "lat": 2.5210,
        "lon": 101.7100,
        "area_km2": 12.8,
        "volume_bbls": 3600,
        "confidence": 88.4,
        "sensor": "ICEYE-X12 (X-Band StripMap)",
        "detected_at": "2026-09-16 01:45:10 UTC",
        "wind": "11 kt WNW (295°)",
        "current": "1.4 kt SE (140°)",
        "surface_temp": "29.6°C",
        "slick_type": "Bilge Wash / Fuel Oil Residue",
        "thumbnail": "assets/images/sar_slick_detail.jpg",
        "primary_suspect": {
            "name": "Nordic Titan",
            "imo": 9310842,
            "confidence": 41.2,
            "matchType": "Secondary Candidate"
        },
        "polygon": [
            [2.535, 101.690], [2.540, 101.730], [2.510, 101.745],
            [2.495, 101.715], [2.515, 101.685]
        ]
    },
    {
        "id": "SG-8831",
        "title": "Port Dickson South Discharge",
        "severity": "medium",
        "status": "FLAGGED PRELIMINARY",
        "lat": 2.2240,
        "lon": 102.0450,
        "area_km2": 5.4,
        "volume_bbls": 980,
        "confidence": 82.1,
        "sensor": "RADARSAT Constellation Mission-2",
        "detected_at": "2026-09-15 22:30:18 UTC",
        "wind": "9 kt N (350°)",
        "current": "1.6 kt SE (130°)",
        "surface_temp": "29.2°C",
        "slick_type": "Oily Water Separator Discharge",
        "thumbnail": "assets/images/sar_slick_detail.jpg",
        "primary_suspect": {
            "name": "Stellar Voyager",
            "imo": 9604122,
            "confidence": 18.5,
            "matchType": "Uncorrelated"
        },
        "polygon": [
            [2.235, 102.030], [2.240, 102.060], [2.215, 102.065], [2.210, 102.035]
        ]
    }
]

SEED_VESSELS = [
    {
        "imo": 9482154, "name": "MT Ocean Vanguard", "mmsi": 636019842, "call_sign": "ELVA8",
        "flag": "Liberia", "flag_code": "lr", "type": "VLCC Crude Tanker",
        "length": "333m", "beam": "60m", "dwt": "305,000",
        "lat": 2.285, "lon": 102.120, "heading": 132, "speed": 13.8, "draft": "19.2m",
        "last_ping": "3 min ago", "signal_health": "Dark", "is_dark": 1,
        "dark_duration": "3h 48m Blackout at Spill Origin", "risk_score": 95, "risk_level": "CRITICAL",
        "track_history": [
            [2.650, 101.450], [2.540, 101.680], [2.440, 101.880], [2.350, 102.010], [2.285, 102.120]
        ]
    },
    {
        "imo": 9310842, "name": "Nordic Titan", "mmsi": 538006214, "call_sign": "V7KT4",
        "flag": "Marshall Islands", "flag_code": "mh", "type": "Capesize Bulk Carrier",
        "length": "292m", "beam": "45m", "dwt": "180,000",
        "lat": 2.480, "lon": 101.820, "heading": 130, "speed": 11.4, "draft": "16.8m",
        "last_ping": "45 sec ago", "signal_health": "Good", "is_dark": 0,
        "dark_duration": "None (Continuous)", "risk_score": 42, "risk_level": "MEDIUM",
        "track_history": [
            [2.720, 101.350], [2.600, 101.600], [2.480, 101.820]
        ]
    },
    {
        "imo": 9604122, "name": "Stellar Voyager", "mmsi": 354891000, "call_sign": "3FGL9",
        "flag": "Panama", "flag_code": "pa", "type": "Ultra-Large Container (20k TEU)",
        "length": "399m", "beam": "59m", "dwt": "198,000",
        "lat": 2.180, "lon": 102.250, "heading": 128, "speed": 18.2, "draft": "14.5m",
        "last_ping": "1 min ago", "signal_health": "Good", "is_dark": 0,
        "dark_duration": "None (Continuous)", "risk_score": 18, "risk_level": "SAFE",
        "track_history": [
            [2.450, 101.800], [2.320, 102.020], [2.180, 102.250]
        ]
    },
    {
        "imo": 9284177, "name": "Seaborne Horizon", "mmsi": 636014522, "call_sign": "D5HG2",
        "flag": "Liberia", "flag_code": "lr", "type": "Chemical / Products Tanker",
        "length": "183m", "beam": "32m", "dwt": "50,000",
        "lat": 2.580, "lon": 101.620, "heading": 310, "speed": 12.0, "draft": "10.2m",
        "last_ping": "5 min ago", "signal_health": "Degraded", "is_dark": 1,
        "dark_duration": "1h 14m Intermittent Gap", "risk_score": 78, "risk_level": "HIGH",
        "track_history": [
            [2.420, 101.900], [2.500, 101.760], [2.580, 101.620]
        ]
    },
    {
        "imo": 9839923, "name": "CMA CGM Pegasus", "mmsi": 228389000, "call_sign": "FNKJ",
        "flag": "France", "flag_code": "fr", "type": "Container Ship",
        "length": "366m", "beam": "51m", "dwt": "155,000",
        "lat": 2.390, "lon": 102.040, "heading": 134, "speed": 16.5, "draft": "13.8m",
        "last_ping": "20 sec ago", "signal_health": "Good", "is_dark": 0,
        "dark_duration": "None", "risk_score": 12, "risk_level": "SAFE",
        "track_history": [
            [2.610, 101.650], [2.500, 101.840], [2.390, 102.040]
        ]
    },
    {
        "imo": 9145892, "name": "Apex Trader", "mmsi": 312548000, "call_sign": "V3TR8",
        "flag": "Belize", "flag_code": "bz", "type": "Aframax Crude Carrier",
        "length": "244m", "beam": "42m", "dwt": "105,000",
        "lat": 2.620, "lon": 101.550, "heading": 135, "speed": 9.8, "draft": "15.1m",
        "last_ping": "2h ago", "signal_health": "Dark", "is_dark": 1,
        "dark_duration": "5h 22m Blackout", "risk_score": 88, "risk_level": "CRITICAL",
        "track_history": [
            [2.780, 101.240], [2.620, 101.550]
        ]
    },
    {
        "imo": 9741203, "name": "Pacific Sentinel", "mmsi": 563044100, "call_sign": "9V648",
        "flag": "Singapore", "flag_code": "sg", "type": "LPG Tanker",
        "length": "226m", "beam": "37m", "dwt": "55,000",
        "lat": 2.310, "lon": 101.990, "heading": 312, "speed": 14.1, "draft": "11.4m",
        "last_ping": "1 min ago", "signal_health": "Good", "is_dark": 0,
        "dark_duration": "None", "risk_score": 14, "risk_level": "SAFE",
        "track_history": [
            [2.150, 102.260], [2.310, 101.990]
        ]
    }
]

SEED_INVESTIGATION = {
    "satellite_info": {
        "name": "Sentinel-1A SAR",
        "passTime": "2026-09-16 04:12:44 UTC",
        "orbit": "Ascending Path 148, Frame 582",
        "mode": "Interferometric Wide (IW)",
        "polarization": "VV + VH Dual-Pol",
        "spatialResolution": "10m x 10m"
    },
    "metocean_info": {
        "windSpeed": "14.2 knots",
        "windDir": "310° (NW)",
        "surfaceCurrent": "1.8 knots @ 135° (SE)",
        "driftVelocity": "2.1 knots @ 138°",
        "sst": "29.4 °C",
        "waveHeight": "0.8m significant",
        "coralReefProximity": "8.4 nautical miles (Pulau Besar MPA)"
    },
    "forensics_info": {
        "polarimetricRatio": "VV/VH ratio drops by -7.4 dB within anomaly zone (characteristic of crude oil dampening capillary-gravity waves)",
        "meanThickness": "1.42 mm (emulsified core exceeds 3.8 mm)",
        "slickTotalArea": "45.2 km²",
        "slickVolumeEst": "18,400 bbls (2,925 m³)",
        "sha256DossierHash": "e4b983c27189fa3198de7e5a01bc6f4439c09d57a2c4187f1b70298e10fa31ce"
    },
    "drift_sim": {
        "timeSteps": [
            {"time": "T-0h (Now / SAR Scan)", "label": "SAR Acquisition", "coords": [2.381, 101.912]},
            {"time": "T-3h (01:12 UTC)", "label": "Lagrangian Step -3h", "coords": [2.410, 101.885]},
            {"time": "T-6h (22:12 UTC)", "label": "Lagrangian Step -6h", "coords": [2.438, 101.860]},
            {"time": "T-9h (19:12 UTC)", "label": "Slick Origin Confluence", "coords": [2.465, 101.835]}
        ],
        "originEstimate": {
            "coords": [2.445, 101.855],
            "timestamp": "2026-09-15 23:45 UTC ± 35 min",
            "accuracyRadius": "0.4 nautical miles"
        }
    },
    "candidates": [
        {
            "rank": 1,
            "name": "MT Ocean Vanguard",
            "imo": 9482154,
            "flag": "Liberia 🇱🇷",
            "type": "VLCC Crude Tanker",
            "confidence": 94.8,
            "matchLevel": "PRIMARY SUSPECT",
            "evidence": [
                {"type": "red", "text": "AIS transponder disabled for 3h 48m precisely across slick origin zone"},
                {"type": "red", "text": "Vessel draft dropped by 1.6m mid-transit (-2,400 tonnes displacement)"},
                {"type": "red", "text": "Speed anomaly: decelerated from 14.4 kt to 6.4 kt during transponder blackout"},
                {"type": "amber", "text": "Lagrangian reverse-drift origin trajectory aligns with ship course (r = 0.984)"},
                {"type": "amber", "text": "SAR backscatter detects distinctive dark trailing stern wake plume on swath"}
            ]
        },
        {
            "rank": 2,
            "name": "Nordic Titan",
            "imo": 9310842,
            "flag": "Marshall Islands 🇲🇭",
            "type": "Bulk Carrier",
            "confidence": 41.2,
            "matchLevel": "LOW PROBABILITY",
            "evidence": [
                {"type": "neutral", "text": "Passed 4.8 nm downwind of estimated origin coordinates"},
                {"type": "neutral", "text": "Maintained continuous uninterrupted AIS broadcast"},
                {"type": "neutral", "text": "Engine RPM and draft telemetry show nominal steady cruising"}
            ]
        },
        {
            "rank": 3,
            "name": "Stellar Voyager",
            "imo": 9604122,
            "flag": "Panama 🇵🇦",
            "type": "Container Carrier",
            "confidence": 18.5,
            "matchLevel": "EXCLUDED",
            "evidence": [
                {"type": "neutral", "text": "Transited TSS corridor 8.5 hours after calculated discharge timestamp"},
                {"type": "neutral", "text": "Speed maintained steady at 18.2 kt throughout sector"}
            ]
        }
    ]
}

SEED_ANALYTICS = {
    "kpis": {
        "totalDetections90d": 1248,
        "volumeDischargedBbls": "342,800 bbls",
        "attributionSuccessRate": "92.4%",
        "penaltiesLeviedUSD": "$48.2M"
    },
    "monthly_trend": [
        {"month": "Apr", "catastrophic": 2, "significant": 8, "minor": 24},
        {"month": "May", "catastrophic": 3, "significant": 11, "minor": 28},
        {"month": "Jun", "catastrophic": 1, "significant": 7, "minor": 19},
        {"month": "Jul", "catastrophic": 4, "significant": 14, "minor": 32},
        {"month": "Aug", "catastrophic": 2, "significant": 9, "minor": 22},
        {"month": "Sep (MTD)", "catastrophic": 5, "significant": 16, "minor": 38}
    ],
    "regional_dist": [
        {"region": "Strait of Malacca", "percent": 42, "color": "#FF4438"},
        {"region": "Persian Gulf", "percent": 28, "color": "#FFB020"},
        {"region": "South China Sea", "percent": 14, "color": "#00D4FF"},
        {"region": "North Sea", "percent": 10, "color": "#2BD97C"},
        {"region": "Gulf of Mexico", "percent": 6, "color": "#90A4BE"}
    ],
    "top_fleets": [
        {"name": "Liberia (FOC)", "count": 48, "pct": 85, "color": "red-fill"},
        {"name": "Panama (FOC)", "count": 39, "pct": 70, "color": "red-fill"},
        {"name": "Gabon (Dark Tanker Fleet)", "count": 31, "pct": 56, "color": "amber-fill"},
        {"name": "Marshall Islands", "count": 18, "pct": 32, "color": "cyan-fill"},
        {"name": "Cook Islands", "count": 14, "pct": 25, "color": "cyan-fill"}
    ]
}

# Mutable in-memory state for fallback mode
_in_memory_vessel_notes = [
    {
        "id": 1,
        "imo": 9482154,
        "note": "Automated Alert: Transponder silent for 3h 48m in TSS Sector 4. High correlation with Sentinel-1A SAR slick #SG-8842.",
        "author": "SYSTEM_AUTO_FORENSIC",
        "createdAt": "2026-09-16 04:12:44 UTC"
    }
]
_in_memory_feedback: List[Dict[str, Any]] = []
_in_memory_ais_vessels: Dict[int, Dict[str, Any]] = {}
_in_memory_ais_positions: Dict[int, List[Dict[str, Any]]] = {}


def init_db():
    global _db_available
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS spills (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        status TEXT NOT NULL,
                        lat REAL NOT NULL,
                        lon REAL NOT NULL,
                        area_km2 REAL NOT NULL,
                        volume_bbls INTEGER NOT NULL,
                        confidence REAL NOT NULL,
                        sensor TEXT NOT NULL,
                        detected_at TEXT NOT NULL,
                        wind TEXT NOT NULL,
                        current TEXT NOT NULL,
                        surface_temp TEXT NOT NULL,
                        slick_type TEXT NOT NULL,
                        thumbnail TEXT NOT NULL,
                        primary_suspect_json TEXT NOT NULL,
                        polygon_json TEXT NOT NULL
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS vessels (
                        imo INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        mmsi INTEGER NOT NULL,
                        call_sign TEXT NOT NULL,
                        flag TEXT NOT NULL,
                        flag_code TEXT NOT NULL,
                        type TEXT NOT NULL,
                        length TEXT NOT NULL,
                        beam TEXT NOT NULL,
                        dwt TEXT NOT NULL,
                        lat REAL NOT NULL,
                        lon REAL NOT NULL,
                        heading INTEGER NOT NULL,
                        speed REAL NOT NULL,
                        draft TEXT NOT NULL,
                        last_ping TEXT NOT NULL,
                        signal_health TEXT NOT NULL,
                        is_dark INTEGER NOT NULL,
                        dark_duration TEXT NOT NULL,
                        risk_score INTEGER NOT NULL,
                        risk_level TEXT NOT NULL,
                        track_history_json TEXT NOT NULL
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS investigations (
                        incident_id TEXT PRIMARY KEY,
                        case_code TEXT NOT NULL,
                        classification TEXT NOT NULL,
                        location_desc TEXT NOT NULL,
                        lat_long TEXT NOT NULL,
                        satellite_json TEXT NOT NULL,
                        metocean_json TEXT NOT NULL,
                        forensics_json TEXT NOT NULL,
                        drift_sim_json TEXT NOT NULL,
                        candidates_json TEXT NOT NULL
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS vessel_notes (
                        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                        imo INTEGER NOT NULL REFERENCES vessels(imo),
                        note_text TEXT NOT NULL,
                        author TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS analytics (
                        id INTEGER PRIMARY KEY,
                        kpis_json TEXT NOT NULL,
                        monthly_trend_json TEXT NOT NULL,
                        regional_dist_json TEXT NOT NULL,
                        top_fleets_json TEXT NOT NULL
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS feedback (
                        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                        name TEXT,
                        email TEXT,
                        feedback_type TEXT NOT NULL,
                        rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
                        message TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ais_vessels (
                        mmsi BIGINT PRIMARY KEY CHECK (mmsi BETWEEN 1 AND 999999999),
                        imo INTEGER,
                        name TEXT,
                        call_sign TEXT,
                        vessel_type TEXT,
                        destination TEXT,
                        latitude DOUBLE PRECISION,
                        longitude DOUBLE PRECISION,
                        speed_knots DOUBLE PRECISION,
                        course_degrees DOUBLE PRECISION,
                        heading_degrees INTEGER,
                        last_seen TIMESTAMPTZ
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ais_positions (
                        mmsi BIGINT NOT NULL REFERENCES ais_vessels(mmsi) ON DELETE CASCADE,
                        observed_at TIMESTAMPTZ NOT NULL,
                        sampled_at TIMESTAMPTZ NOT NULL,
                        latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
                        longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
                        speed_knots DOUBLE PRECISION,
                        course_degrees DOUBLE PRECISION,
                        heading_degrees INTEGER,
                        PRIMARY KEY (mmsi, sampled_at)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_spills_severity
                    ON spills (severity)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_vessels_high_risk
                    ON vessels (risk_score DESC)
                    WHERE risk_score >= 75
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_vessel_notes_imo_created_at
                    ON vessel_notes (imo, created_at DESC)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ais_vessels_position
                    ON ais_vessels (latitude, longitude)
                    WHERE latitude IS NOT NULL AND longitude IS NOT NULL
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ais_vessels_last_seen
                    ON ais_vessels (last_seen DESC)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ais_positions_sampled_at
                    ON ais_positions (sampled_at)
                """)
                for table_name in (
                    "spills",
                    "vessels",
                    "investigations",
                    "vessel_notes",
                    "analytics",
                    "feedback",
                    "ais_vessels",
                    "ais_positions",
                ):
                    cursor.execute(
                        f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY"
                    )

                cursor.execute("LOCK TABLE spills IN SHARE ROW EXCLUSIVE MODE")
                cursor.execute("SELECT COUNT(*) AS spill_count FROM spills")
                spill_count = cursor.fetchone()
                if spill_count is None:
                    raise RuntimeError("Failed to retrieve the spill count during database initialization.")
                if spill_count["spill_count"] == 0:
                    seed_initial_data(cursor)
                _db_available = True
    except Exception as exc:
        _mark_db_unavailable(exc)
        raise


def seed_initial_data(cursor):
    for s in SEED_SPILLS:
        cursor.execute("""
            INSERT INTO spills (
                id, title, severity, status, lat, lon, area_km2, volume_bbls,
                confidence, sensor, detected_at, wind, current, surface_temp,
                slick_type, thumbnail, primary_suspect_json, polygon_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            s["id"], s["title"], s["severity"], s["status"], s["lat"], s["lon"],
            s["area_km2"], s["volume_bbls"], s["confidence"], s["sensor"],
            s["detected_at"], s["wind"], s["current"], s["surface_temp"],
            s["slick_type"], s["thumbnail"],
            json.dumps(s["primary_suspect"]), json.dumps(s["polygon"])
        ))

    for v in SEED_VESSELS:
        cursor.execute("""
            INSERT INTO vessels (
                imo, name, mmsi, call_sign, flag, flag_code, type, length,
                beam, dwt, lat, lon, heading, speed, draft, last_ping,
                signal_health, is_dark, dark_duration, risk_score, risk_level,
                track_history_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            v["imo"], v["name"], v["mmsi"], v["call_sign"], v["flag"], v["flag_code"],
            v["type"], v["length"], v["beam"], v["dwt"], v["lat"], v["lon"],
            v["heading"], v["speed"], v["draft"], v["last_ping"], v["signal_health"],
            v["is_dark"], v["dark_duration"], v["risk_score"], v["risk_level"],
            json.dumps(v["track_history"])
        ))

    cursor.execute("""
        INSERT INTO vessel_notes (imo, note_text, author) VALUES (%s, %s, %s)
    """, (9482154, "Automated Alert: Transponder silent for 3h 48m in TSS Sector 4. High correlation with Sentinel-1A SAR slick #SG-8842.", "SYSTEM_AUTO_FORENSIC"))

    cursor.execute("""
        INSERT INTO investigations VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        "SG-8842",
        "CASE-2026-SG8842-MLC",
        "MARPOL Annex I Hydrocarbon Discharge",
        "Strait of Malacca TSS Sector 4 (Offshore Melaka)",
        '02°22\'52"N, 101°54\'45"E',
        json.dumps(SEED_INVESTIGATION["satellite_info"]),
        json.dumps(SEED_INVESTIGATION["metocean_info"]),
        json.dumps(SEED_INVESTIGATION["forensics_info"]),
        json.dumps(SEED_INVESTIGATION["drift_sim"]),
        json.dumps(SEED_INVESTIGATION["candidates"])
    ))

    cursor.execute("""
        INSERT INTO analytics (
            id, kpis_json, monthly_trend_json, regional_dist_json, top_fleets_json
        ) VALUES (1, %s, %s, %s, %s)
    """, (
        json.dumps(SEED_ANALYTICS["kpis"]),
        json.dumps(SEED_ANALYTICS["monthly_trend"]),
        json.dumps(SEED_ANALYTICS["regional_dist"]),
        json.dumps(SEED_ANALYTICS["top_fleets"])
    ))


# ===========================================================================
# IN-MEMORY QUERY IMPLEMENTATIONS
# ===========================================================================
def _in_memory_query_spills(severity: Optional[str] = None) -> List[Dict[str, Any]]:
    result = []
    for s in SEED_SPILLS:
        if severity and s["severity"].lower() != severity.lower():
            continue
        result.append({
            "id": s["id"],
            "title": s["title"],
            "severity": s["severity"],
            "status": s["status"],
            "coords": [s["lat"], s["lon"]],
            "areaKm2": s["area_km2"],
            "volumeBbls": s["volume_bbls"],
            "confidence": s["confidence"],
            "sensor": s["sensor"],
            "detectedAt": s["detected_at"],
            "wind": s["wind"],
            "current": s["current"],
            "surfaceTemp": s["surface_temp"],
            "slickType": s["slick_type"],
            "thumbnail": s["thumbnail"],
            "primarySuspect": s["primary_suspect"],
            "slickPolygon": s["polygon"]
        })
    return result


def _in_memory_query_vessels(filter_type: Optional[str] = None, search: Optional[str] = None) -> List[Dict[str, Any]]:
    result = []
    for v in SEED_VESSELS:
        if search:
            q = search.lower()
            match = (
                q in v["name"].lower()
                or q in str(v["imo"])
                or q in v["flag"].lower()
                or q in v["type"].lower()
            )
            if not match:
                continue
        if filter_type == "dark":
            if not v["is_dark"]:
                continue
        elif filter_type == "tankers":
            t = v["type"].lower()
            if "tanker" not in t and "carrier" not in t:
                continue
        elif filter_type == "high-risk":
            if v["risk_score"] < 75:
                continue

        result.append({
            "imo": v["imo"],
            "name": v["name"],
            "mmsi": v["mmsi"],
            "callSign": v["call_sign"],
            "flag": v["flag"],
            "flagCode": v["flag_code"],
            "type": v["type"],
            "length": v["length"],
            "beam": v["beam"],
            "dwt": v["dwt"],
            "coords": [v["lat"], v["lon"]],
            "heading": v["heading"],
            "speed": v["speed"],
            "draft": v["draft"],
            "lastAisPing": v["last_ping"],
            "signalHealth": v["signal_health"],
            "isDarkVessel": bool(v["is_dark"]),
            "darkDuration": v["dark_duration"],
            "riskScore": v["risk_score"],
            "riskLevel": v["risk_level"],
            "trackHistory": v["track_history"]
        })
    return result


# ===========================================================================
# PUBLIC QUERY INTERFACE (POSTGRES WITH AUTOMATIC IN-MEMORY FALLBACK)
# ===========================================================================
def query_spills(severity: Optional[str] = None) -> List[Dict[str, Any]]:
    if _is_mocked() or _should_attempt_database():
        try:
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    if severity:
                        cursor.execute("""
                            SELECT id, title, severity, status, lat, lon, area_km2,
                                   volume_bbls, confidence, sensor, detected_at, wind,
                                   current, surface_temp, slick_type, thumbnail,
                                   primary_suspect_json, polygon_json
                            FROM spills
                            WHERE severity = %s
                        """, (severity,))
                    else:
                        cursor.execute("""
                            SELECT id, title, severity, status, lat, lon, area_km2,
                                   volume_bbls, confidence, sensor, detected_at, wind,
                                   current, surface_temp, slick_type, thumbnail,
                                   primary_suspect_json, polygon_json
                            FROM spills
                        """)
                    rows = cursor.fetchall()

            result = []
            for r in rows:
                primary = r["primary_suspect_json"]
                poly = r["polygon_json"]
                result.append({
                    "id": r["id"],
                    "title": r["title"],
                    "severity": r["severity"],
                    "status": r["status"],
                    "coords": [r["lat"], r["lon"]],
                    "areaKm2": r["area_km2"],
                    "volumeBbls": r["volume_bbls"],
                    "confidence": r["confidence"],
                    "sensor": r["sensor"],
                    "detectedAt": r["detected_at"],
                    "wind": r["wind"],
                    "current": r["current"],
                    "surfaceTemp": r["surface_temp"],
                    "slickType": r["slick_type"],
                    "thumbnail": r["thumbnail"],
                    "primarySuspect": json.loads(primary) if isinstance(primary, str) else primary,
                    "slickPolygon": json.loads(poly) if isinstance(poly, str) else poly
                })
            return result
        except (psycopg.OperationalError, psycopg.Error, OSError) as exc:
            _mark_db_unavailable(exc)

    return _in_memory_query_spills(severity)


def query_spill_by_id(spill_id: str) -> Optional[Dict[str, Any]]:
    if _is_mocked() or _should_attempt_database():
        try:
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT id, title, severity, status, lat, lon, area_km2,
                               volume_bbls, confidence, sensor, detected_at, wind,
                               current, surface_temp, slick_type, thumbnail,
                               primary_suspect_json, polygon_json
                        FROM spills
                        WHERE id = %s
                    """, (spill_id,))
                    r = cursor.fetchone()
            if r is not None:
                primary = r["primary_suspect_json"]
                poly = r["polygon_json"]
                return {
                    "id": r["id"],
                    "title": r["title"],
                    "severity": r["severity"],
                    "status": r["status"],
                    "coords": [r["lat"], r["lon"]],
                    "areaKm2": r["area_km2"],
                    "volumeBbls": r["volume_bbls"],
                    "confidence": r["confidence"],
                    "sensor": r["sensor"],
                    "detectedAt": r["detected_at"],
                    "wind": r["wind"],
                    "current": r["current"],
                    "surfaceTemp": r["surface_temp"],
                    "slickType": r["slick_type"],
                    "thumbnail": r["thumbnail"],
                    "primarySuspect": json.loads(primary) if isinstance(primary, str) else primary,
                    "slickPolygon": json.loads(poly) if isinstance(poly, str) else poly
                }
            return None
        except (psycopg.OperationalError, psycopg.Error, OSError) as exc:
            _mark_db_unavailable(exc)

    spills = _in_memory_query_spills()
    for s in spills:
        if s["id"] == spill_id:
            return s
    return None


def query_vessels(filter_type: Optional[str] = None, search: Optional[str] = None) -> List[Dict[str, Any]]:
    if _is_mocked() or _should_attempt_database():
        try:
            conditions = []
            params: List[Any] = []
            if search:
                conditions.append("""
                    (
                        STRPOS(LOWER(name), LOWER(%s)) > 0
                        OR STRPOS(imo::text, %s) > 0
                        OR STRPOS(LOWER(flag), LOWER(%s)) > 0
                        OR STRPOS(LOWER(type), LOWER(%s)) > 0
                    )
                """)
                params.extend([search] * 4)
            if filter_type == "dark":
                conditions.append("is_dark = 1")
            elif filter_type == "tankers":
                conditions.append("(LOWER(type) LIKE %s OR LOWER(type) LIKE %s)")
                params.extend(["%tanker%", "%carrier%"])
            elif filter_type == "high-risk":
                conditions.append("risk_score >= %s")
                params.append(75)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            query = f"""
                SELECT imo, name, mmsi, call_sign, flag, flag_code, type, length,
                       beam, dwt, lat, lon, heading, speed, draft, last_ping,
                       signal_health, is_dark, dark_duration, risk_score, risk_level,
                       track_history_json
                FROM vessels
                {where_clause}
                ORDER BY imo
            """
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    rows = cursor.fetchall()

            result = []
            for r in rows:
                th = r["track_history_json"]
                v = {
                    "imo": r["imo"],
                    "name": r["name"],
                    "mmsi": r["mmsi"],
                    "callSign": r["call_sign"],
                    "flag": r["flag"],
                    "flagCode": r["flag_code"],
                    "type": r["type"],
                    "length": r["length"],
                    "beam": r["beam"],
                    "dwt": r["dwt"],
                    "coords": [r["lat"], r["lon"]],
                    "heading": r["heading"],
                    "speed": r["speed"],
                    "draft": r["draft"],
                    "lastAisPing": r["last_ping"],
                    "signalHealth": r["signal_health"],
                    "isDarkVessel": bool(r["is_dark"]),
                    "darkDuration": r["dark_duration"],
                    "riskScore": r["risk_score"],
                    "riskLevel": r["risk_level"],
                    "trackHistory": json.loads(th) if isinstance(th, str) else th
                }
                result.append(v)
            return result
        except (psycopg.OperationalError, psycopg.Error, OSError) as exc:
            _mark_db_unavailable(exc)

    return _in_memory_query_vessels(filter_type, search)


def save_feedback(name: Optional[str], email: Optional[str], feedback_type: str, rating: int, message: str) -> Dict[str, Any]:
    if _is_mocked() or _should_attempt_database():
        try:
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO feedback (name, email, feedback_type, rating, message)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id, name, email, feedback_type, rating, message, created_at
                        """,
                        (name, email, feedback_type, rating, message),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise RuntimeError("The feedback insert did not return a row.")
            return {
                "id": row["id"],
                "name": row["name"],
                "email": row["email"],
                "feedback_type": row["feedback_type"],
                "rating": row["rating"],
                "message": row["message"],
                "created_at": row["created_at"].isoformat() if row["created_at"] is not None else None,
            }
        except (psycopg.OperationalError, psycopg.Error, OSError) as exc:
            _mark_db_unavailable(exc)

    fb = {
        "id": len(_in_memory_feedback) + 1,
        "name": name,
        "email": email,
        "feedback_type": feedback_type,
        "rating": rating,
        "message": message,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _in_memory_feedback.append(fb)
    return fb


def add_vessel_note(imo: int, note_text: str, author: str = "Operator") -> Dict[str, Any]:
    if _is_mocked() or _should_attempt_database():
        try:
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO vessel_notes (imo, note_text, author)
                        VALUES (%s, %s, %s)
                        RETURNING id
                    """, (imo, note_text, author))
                    row = cursor.fetchone()
                    if row is None:
                        raise RuntimeError("The vessel note insert did not return a row.")
                    note_id = row["id"]
            return {"id": note_id, "imo": imo, "note": note_text, "author": author}
        except (psycopg.OperationalError, psycopg.Error, OSError) as exc:
            _mark_db_unavailable(exc)

    note = {
        "id": len(_in_memory_vessel_notes) + 1,
        "imo": imo,
        "note": note_text,
        "author": author,
        "createdAt": datetime.now(timezone.utc).isoformat()
    }
    _in_memory_vessel_notes.insert(0, note)
    return note


def get_vessel_notes(imo: int) -> List[Dict[str, Any]]:
    if _is_mocked() or _should_attempt_database():
        try:
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT id, imo, note_text, author, created_at
                        FROM vessel_notes
                        WHERE imo = %s
                        ORDER BY created_at DESC, id DESC
                    """, (imo,))
                    rows = cursor.fetchall()
            return [{"id": r["id"], "imo": r["imo"], "note": r["note_text"], "author": r["author"], "createdAt": r["created_at"]} for r in rows]
        except (psycopg.OperationalError, psycopg.Error, OSError) as exc:
            _mark_db_unavailable(exc)

    return [n for n in _in_memory_vessel_notes if n["imo"] == imo]


def query_investigation(incident_id: str) -> Optional[Dict[str, Any]]:
    if _is_mocked() or _should_attempt_database():
        try:
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT incident_id, case_code, classification, location_desc,
                               lat_long, satellite_json, metocean_json, forensics_json,
                               drift_sim_json, candidates_json
                        FROM investigations
                        WHERE incident_id = %s
                    """, (incident_id,))
                    r = cursor.fetchone()
            if r is not None:
                return {
                    "incidentId": r["incident_id"],
                    "caseCode": r["case_code"],
                    "classification": r["classification"],
                    "locationDesc": r["location_desc"],
                    "latLong": r["lat_long"],
                    "satellite": json.loads(r["satellite_json"]) if isinstance(r["satellite_json"], str) else r["satellite_json"],
                    "metocean": json.loads(r["metocean_json"]) if isinstance(r["metocean_json"], str) else r["metocean_json"],
                    "forensics": json.loads(r["forensics_json"]) if isinstance(r["forensics_json"], str) else r["forensics_json"],
                    "driftSimulation": json.loads(r["drift_sim_json"]) if isinstance(r["drift_sim_json"], str) else r["drift_sim_json"],
                    "candidates": json.loads(r["candidates_json"]) if isinstance(r["candidates_json"], str) else r["candidates_json"]
                }
            return None
        except (psycopg.OperationalError, psycopg.Error, OSError) as exc:
            _mark_db_unavailable(exc)

    return {
        "incidentId": "SG-8842",
        "caseCode": "CASE-2026-SG8842-MLC",
        "classification": "MARPOL Annex I Hydrocarbon Discharge",
        "locationDesc": "Strait of Malacca TSS Sector 4 (Offshore Melaka)",
        "latLong": '02°22\'52"N, 101°54\'45"E',
        "satellite": SEED_INVESTIGATION["satellite_info"],
        "metocean": SEED_INVESTIGATION["metocean_info"],
        "forensics": SEED_INVESTIGATION["forensics_info"],
        "driftSimulation": SEED_INVESTIGATION["drift_sim"],
        "candidates": SEED_INVESTIGATION["candidates"]
    }


def query_analytics() -> Dict[str, Any]:
    if _is_mocked() or _should_attempt_database():
        try:
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT kpis_json, monthly_trend_json, regional_dist_json,
                               top_fleets_json
                        FROM analytics
                        WHERE id = %s
                    """, (1,))
                    r = cursor.fetchone()
            if r is not None:
                return {
                    "kpis": json.loads(r["kpis_json"]) if isinstance(r["kpis_json"], str) else r["kpis_json"],
                    "monthlyTrend": json.loads(r["monthly_trend_json"]) if isinstance(r["monthly_trend_json"], str) else r["monthly_trend_json"],
                    "regionalDistribution": json.loads(r["regional_dist_json"]) if isinstance(r["regional_dist_json"], str) else r["regional_dist_json"],
                    "topFlaggedFleets": json.loads(r["top_fleets_json"]) if isinstance(r["top_fleets_json"], str) else r["top_fleets_json"]
                }
            return {}
        except (psycopg.OperationalError, psycopg.Error, OSError) as exc:
            _mark_db_unavailable(exc)

    return {
        "kpis": SEED_ANALYTICS["kpis"],
        "monthlyTrend": SEED_ANALYTICS["monthly_trend"],
        "regionalDistribution": SEED_ANALYTICS["regional_dist"],
        "topFlaggedFleets": SEED_ANALYTICS["top_fleets"]
    }


def upsert_ais_messages(messages: List[Dict[str, Any]]) -> bool:
    if not messages:
        return True
    if not (_is_mocked() or _should_attempt_database()):
        return False

    latest_by_mmsi: Dict[int, Dict[str, Any]] = {}
    latest_positions: Dict[tuple[int, datetime], Dict[str, Any]] = {}
    for message in messages:
        mmsi = message["mmsi"]
        current = latest_by_mmsi.get(mmsi)
        if current is None or message["observed_at"] >= current["observed_at"]:
            latest_by_mmsi[mmsi] = message

        if message["latitude"] is not None and message["longitude"] is not None:
            position_key = (mmsi, message["sampled_at"])
            current_position = latest_positions.get(position_key)
            if (
                current_position is None
                or message["observed_at"] >= current_position["observed_at"]
            ):
                latest_positions[position_key] = message

    ordered_vessels = sorted(latest_by_mmsi.values(), key=lambda message: message["mmsi"])
    ordered_positions = sorted(latest_positions.values(), key=lambda message: (
        message["mmsi"],
        message["sampled_at"],
    ))
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.executemany("""
                        INSERT INTO ais_vessels (
                            mmsi, imo, name, call_sign, vessel_type, destination,
                            latitude, longitude, speed_knots, course_degrees,
                            heading_degrees, last_seen
                        )
                        VALUES (
                            %(mmsi)s, %(imo)s, %(name)s, %(call_sign)s, %(vessel_type)s,
                            %(destination)s, %(latitude)s, %(longitude)s,
                            %(speed_knots)s, %(course_degrees)s, %(heading_degrees)s,
                            CASE
                                WHEN %(latitude)s::DOUBLE PRECISION IS NOT NULL
                                THEN %(observed_at)s::TIMESTAMPTZ
                                ELSE NULL
                            END
                        )
                        ON CONFLICT (mmsi) DO UPDATE SET
                            imo = COALESCE(EXCLUDED.imo, ais_vessels.imo),
                            name = COALESCE(NULLIF(EXCLUDED.name, ''), ais_vessels.name),
                            call_sign = COALESCE(NULLIF(EXCLUDED.call_sign, ''), ais_vessels.call_sign),
                            vessel_type = COALESCE(EXCLUDED.vessel_type, ais_vessels.vessel_type),
                            destination = COALESCE(NULLIF(EXCLUDED.destination, ''), ais_vessels.destination),
                            latitude = CASE
                                WHEN EXCLUDED.last_seen IS NOT NULL
                                 AND (ais_vessels.last_seen IS NULL OR EXCLUDED.last_seen >= ais_vessels.last_seen)
                                THEN COALESCE(EXCLUDED.latitude, ais_vessels.latitude)
                                ELSE ais_vessels.latitude
                            END,
                            longitude = CASE
                                WHEN EXCLUDED.last_seen IS NOT NULL
                                 AND (ais_vessels.last_seen IS NULL OR EXCLUDED.last_seen >= ais_vessels.last_seen)
                                THEN COALESCE(EXCLUDED.longitude, ais_vessels.longitude)
                                ELSE ais_vessels.longitude
                            END,
                            speed_knots = CASE
                                WHEN EXCLUDED.last_seen IS NOT NULL
                                 AND (ais_vessels.last_seen IS NULL OR EXCLUDED.last_seen >= ais_vessels.last_seen)
                                THEN COALESCE(EXCLUDED.speed_knots, ais_vessels.speed_knots)
                                ELSE ais_vessels.speed_knots
                            END,
                            course_degrees = CASE
                                WHEN EXCLUDED.last_seen IS NOT NULL
                                 AND (ais_vessels.last_seen IS NULL OR EXCLUDED.last_seen >= ais_vessels.last_seen)
                                THEN COALESCE(EXCLUDED.course_degrees, ais_vessels.course_degrees)
                                ELSE ais_vessels.course_degrees
                            END,
                            heading_degrees = CASE
                                WHEN EXCLUDED.last_seen IS NOT NULL
                                 AND (ais_vessels.last_seen IS NULL OR EXCLUDED.last_seen >= ais_vessels.last_seen)
                                THEN COALESCE(EXCLUDED.heading_degrees, ais_vessels.heading_degrees)
                                ELSE ais_vessels.heading_degrees
                            END,
                            last_seen = CASE
                                WHEN EXCLUDED.last_seen IS NULL THEN ais_vessels.last_seen
                                ELSE GREATEST(ais_vessels.last_seen, EXCLUDED.last_seen)
                            END
                """, ordered_vessels)
                cursor.executemany("""
                        INSERT INTO ais_positions (
                            mmsi, observed_at, sampled_at, latitude, longitude,
                            speed_knots, course_degrees, heading_degrees
                        )
                        VALUES (
                            %(mmsi)s, %(observed_at)s, %(sampled_at)s, %(latitude)s,
                            %(longitude)s, %(speed_knots)s, %(course_degrees)s,
                            %(heading_degrees)s
                        )
                        ON CONFLICT (mmsi, sampled_at) DO UPDATE SET
                            observed_at = EXCLUDED.observed_at,
                            latitude = EXCLUDED.latitude,
                            longitude = EXCLUDED.longitude,
                            speed_knots = EXCLUDED.speed_knots,
                            course_degrees = EXCLUDED.course_degrees,
                            heading_degrees = EXCLUDED.heading_degrees
                        WHERE ais_positions.observed_at < EXCLUDED.observed_at
                """, ordered_positions)
        return True
    except (psycopg.OperationalError, psycopg.Error, OSError) as exc:
        _mark_db_unavailable(exc)
        return False


def query_ais_vessels(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    limit: int = 500,
    track_hours: int = 6,
) -> tuple[List[Dict[str, Any]], str]:
    if _is_mocked() or _should_attempt_database():
        try:
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT
                            vessel.mmsi,
                            vessel.imo,
                            vessel.name,
                            vessel.call_sign,
                            vessel.vessel_type,
                            vessel.destination,
                            vessel.latitude,
                            vessel.longitude,
                            vessel.speed_knots,
                            vessel.course_degrees,
                            vessel.heading_degrees,
                            vessel.last_seen,
                            COALESCE(track.points, '[]'::jsonb) AS track_history
                        FROM ais_vessels AS vessel
                        LEFT JOIN LATERAL (
                            SELECT jsonb_agg(
                                jsonb_build_array(sample.latitude, sample.longitude)
                                ORDER BY sample.track_bucket
                            ) AS points
                            FROM (
                                SELECT DISTINCT ON (
                                    date_bin(
                                        INTERVAL '5 minutes',
                                        position.sampled_at,
                                        TIMESTAMPTZ '2000-01-01 00:00:00+00'
                                    )
                                )
                                    position.latitude,
                                    position.longitude,
                                    date_bin(
                                        INTERVAL '5 minutes',
                                        position.sampled_at,
                                        TIMESTAMPTZ '2000-01-01 00:00:00+00'
                                    ) AS track_bucket,
                                    position.sampled_at
                                FROM ais_positions AS position
                                WHERE position.mmsi = vessel.mmsi
                                  AND position.sampled_at >= NOW() - (%s * INTERVAL '1 hour')
                                ORDER BY track_bucket, position.sampled_at DESC
                            ) AS sample
                        ) AS track ON TRUE
                        WHERE vessel.latitude BETWEEN %s AND %s
                          AND vessel.longitude BETWEEN %s AND %s
                          AND vessel.last_seen >= NOW() - INTERVAL '30 minutes'
                        ORDER BY vessel.last_seen DESC NULLS LAST
                        LIMIT %s
                    """, (track_hours, min_lat, max_lat, min_lon, max_lon, limit))
                    rows = cursor.fetchall()

            return [
                {
                    "mmsi": row["mmsi"],
                    "imo": row["imo"],
                    "name": row["name"] or f"Vessel {row['mmsi']}",
                    "callSign": row["call_sign"],
                    "type": row["vessel_type"],
                    "destination": row["destination"],
                    "lat": row["latitude"],
                    "lon": row["longitude"],
                    "speed": row["speed_knots"],
                    "course": row["course_degrees"],
                    "heading": row["heading_degrees"],
                    "lastSeen": row["last_seen"].isoformat() if hasattr(row.get("last_seen"), "isoformat") and row["last_seen"] else (row.get("last_seen") or None),
                    "trackHistory": row["track_history"],
                }
                for row in rows
            ], "live"
        except (psycopg.OperationalError, psycopg.Error, OSError) as exc:
            _mark_db_unavailable(exc)

    # In-memory fallback
    results = []
    for v in SEED_VESSELS:
        lat = v["lat"]
        lon = v["lon"]
        if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
            results.append({
                "mmsi": v["mmsi"],
                "imo": v["imo"],
                "name": v["name"],
                "callSign": v["call_sign"],
                "type": v["type"],
                "destination": "SINGAPORE",
                "lat": v["lat"],
                "lon": v["lon"],
                "speed": v["speed"],
                "course": float(v["heading"]),
                "heading": v["heading"],
                "lastSeen": datetime.now(timezone.utc).isoformat(),
                "trackHistory": v["track_history"],
            })
    return results[:limit], "demo"


def query_ais_positions_for_attribution(
    sar_time: datetime,
    sar_lat: float,
    sar_lon: float,
    time_window_minutes: int = 30,
    search_radius_km: float = 50.0,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Fetch the closest-in-time AIS observation per vessel near a SAR target."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                WITH parameters AS (
                    SELECT
                        %s::TIMESTAMPTZ AS sar_time,
                        %s::DOUBLE PRECISION AS sar_lat,
                        %s::DOUBLE PRECISION AS sar_lon,
                        %s::INTEGER AS time_window_minutes,
                        %s::DOUBLE PRECISION AS search_radius_km
                ),
                measured_positions AS (
                    SELECT
                        ais_pos.mmsi,
                        vessel.name AS vessel_name,
                        vessel.vessel_type,
                        ais_pos.latitude,
                        ais_pos.longitude,
                        ais_pos.speed_knots,
                        ais_pos.course_degrees,
                        ais_pos.observed_at,
                        2 * 6371.0088 * ASIN(SQRT(LEAST(
                            1.0,
                            POWER(SIN(RADIANS(ais_pos.latitude - parameters.sar_lat) / 2), 2)
                            + COS(RADIANS(parameters.sar_lat))
                            * COS(RADIANS(ais_pos.latitude))
                            * POWER(SIN(RADIANS(ais_pos.longitude - parameters.sar_lon) / 2), 2)
                        ))) AS distance_km,
                        ROW_NUMBER() OVER (
                            PARTITION BY ais_pos.mmsi
                            ORDER BY
                                ABS(EXTRACT(EPOCH FROM (ais_pos.observed_at - parameters.sar_time))),
                                ais_pos.observed_at DESC
                        ) AS time_rank
                    FROM ais_positions AS ais_pos
                    JOIN ais_vessels AS vessel ON vessel.mmsi = ais_pos.mmsi
                    CROSS JOIN parameters
                    WHERE ais_pos.observed_at BETWEEN
                        parameters.sar_time - parameters.time_window_minutes * INTERVAL '1 minute'
                        AND parameters.sar_time + parameters.time_window_minutes * INTERVAL '1 minute'
                )
                SELECT
                    mmsi,
                    vessel_name,
                    vessel_type,
                    latitude,
                    longitude,
                    speed_knots,
                    course_degrees,
                    observed_at,
                    distance_km
                FROM measured_positions
                WHERE time_rank = 1
                  AND distance_km <= (SELECT search_radius_km FROM parameters)
                ORDER BY distance_km ASC, observed_at DESC
                LIMIT %s
            """, (
                sar_time,
                sar_lat,
                sar_lon,
                time_window_minutes,
                search_radius_km,
                limit,
            ))
            return cursor.fetchall()


def prune_ais_positions(retention_days: int) -> int:
    if _is_mocked() or _should_attempt_database():
        try:
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        DELETE FROM ais_positions
                        WHERE sampled_at < NOW() - (%s * INTERVAL '1 day')
                    """, (retention_days,))
                    deleted_rows = cursor.rowcount
                    cursor.execute("""
                        DELETE FROM ais_vessels
                        WHERE last_seen IS NULL
                           OR last_seen < NOW() - (%s * INTERVAL '1 day')
                    """, (retention_days,))
                    return deleted_rows + cursor.rowcount
        except (psycopg.OperationalError, psycopg.Error, OSError) as exc:
            _mark_db_unavailable(exc)
    return 0
