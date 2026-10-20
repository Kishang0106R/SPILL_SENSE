"""AISStream WebSocket ingestion and message normalization."""

import asyncio
import json
import logging
import math
import os
import random
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import websockets

try:
    from server.database import prune_ais_positions, upsert_ais_messages
except ImportError:  # pragma: no cover - direct script execution
    from database import prune_ais_positions, upsert_ais_messages

logger = logging.getLogger(__name__)
STREAM_URL = "wss://stream.aisstream.io/v0/stream"
WORLDWIDE_BOUNDS = [[[-90, -180], [90, 180]]]
MAX_BATCH_SIZE = 500
FLUSH_INTERVAL_SECONDS = 1
STABLE_CONNECTION_SECONDS = 60
OPEN_TIMEOUT_SECONDS = 30
PING_TIMEOUT_SECONDS = 60

_status: Dict[str, Any] = {
    "enabled": False,
    "connected": False,
    "lastMessageAt": None,
    "lastError": None,
}


def aisstream_status() -> Dict[str, Any]:
    return dict(_status)


def _number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _timestamp(value: Any) -> datetime:
    if isinstance(value, str):
        timestamp = value.strip()
        go_utc_timestamp = re.fullmatch(
            r"(.+?)(?:\.(\d+))?\s+([+-]\d{4})\s+UTC",
            timestamp,
        )
        if go_utc_timestamp:
            date_time, fractional, offset = go_utc_timestamp.groups()
            normalized_fraction = (
                f".{fractional[:6].ljust(6, '0')}" if fractional else ""
            )
            timestamp = (
                f"{date_time}{normalized_fraction}"
                f"{offset[:3]}:{offset[3:]}"
            )
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            logger.warning("AISStream emitted an invalid UTC timestamp: %r", value)
    return datetime.now(timezone.utc)


def normalize_ais_message(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    message_type = message.get("MessageType")
    metadata = message.get("MetaData") or {}
    payload = (message.get("Message") or {}).get(message_type) or {}
    if not isinstance(payload, dict):
        return None

    mmsi_value = payload.get("UserID") or metadata.get("MMSI")
    if mmsi_value is None:
        return None
    try:
        mmsi = int(mmsi_value)
    except (TypeError, ValueError):
        return None
    if not 1 <= mmsi <= 999999999:
        return None

    latitude = _number(payload.get("Latitude", metadata.get("latitude")))
    longitude = _number(payload.get("Longitude", metadata.get("longitude")))
    if latitude is not None and not -90 <= latitude <= 90:
        latitude = None
    if longitude is not None and not -180 <= longitude <= 180:
        longitude = None
    if latitude is None or longitude is None:
        latitude = longitude = None

    observed_at = _timestamp(metadata.get("time_utc"))
    heading = _number(payload.get("TrueHeading"))
    if heading is not None and not 0 <= heading <= 359:
        heading = None
    course = _number(payload.get("Cog"))
    if course is not None and not 0 <= course <= 360:
        course = None
    speed = _number(payload.get("Sog"))
    if speed is not None and not 0 <= speed <= 102.3:
        speed = None

    imo = payload.get("ImoNumber")
    try:
        imo = int(imo) if imo else None
    except (TypeError, ValueError):
        imo = None

    name = payload.get("Name") or metadata.get("ShipName")
    call_sign = payload.get("CallSign")
    destination = payload.get("Destination")
    vessel_type = payload.get("Type")
    return {
        "mmsi": mmsi,
        "imo": imo if imo and imo > 0 else None,
        "name": str(name).strip() or None if name else None,
        "call_sign": str(call_sign).strip() or None if call_sign else None,
        "vessel_type": str(vessel_type) if vessel_type is not None else None,
        "destination": str(destination).strip() or None if destination else None,
        "latitude": latitude,
        "longitude": longitude,
        "speed_knots": speed,
        "course_degrees": course,
        "heading_degrees": int(heading) if heading is not None else None,
        "observed_at": observed_at,
        "sampled_at": observed_at.replace(second=0, microsecond=0),
    }


async def _flush_batch(batch: list[Dict[str, Any]]) -> None:
    if batch:
        persisted = await asyncio.to_thread(upsert_ais_messages, batch)
        if not persisted:
            raise ConnectionError(
                f"Database did not persist AIS batch ({len(batch)} messages); retaining it for retry."
            )
        batch.clear()


async def _consume_stream(
    websocket: Any,
    batch: Optional[list[Dict[str, Any]]] = None,
) -> None:
    if batch is None:
        batch = []
    last_flush = asyncio.get_running_loop().time()
    try:
        while True:
            try:
                raw_message = await asyncio.wait_for(
                    websocket.recv(),
                    timeout=FLUSH_INTERVAL_SECONDS,
                )
            except asyncio.TimeoutError:
                raw_message = None

            if raw_message is not None:
                try:
                    decoded = json.loads(raw_message)
                except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
                    logger.warning("Discarding malformed AISStream message.")
                    decoded = None
                if isinstance(decoded, dict):
                    normalized = normalize_ais_message(decoded)
                    if normalized is not None:
                        batch.append(normalized)
                        _status["lastMessageAt"] = datetime.now(timezone.utc).isoformat()

            elapsed = asyncio.get_running_loop().time() - last_flush
            if batch and (len(batch) >= MAX_BATCH_SIZE or elapsed >= FLUSH_INTERVAL_SECONDS):
                await _flush_batch(batch)
                last_flush = asyncio.get_running_loop().time()
    finally:
        await _flush_batch(batch)


async def _prune_old_positions() -> None:
    while True:
        try:
            retention_days = int(os.getenv("AIS_TRACK_RETENTION_DAYS", "30"))
            if retention_days < 1:
                raise ValueError("AIS_TRACK_RETENTION_DAYS must be at least 1.")
            deleted = await asyncio.to_thread(prune_ais_positions, retention_days)
            logger.info("Pruned %s expired AIS records older than %s days.", deleted, retention_days)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("AIS track retention cleanup failed.")
        await asyncio.sleep(6 * 60 * 60)


async def run_aisstream(api_key: str) -> None:
    _status.update(enabled=True, connected=False, lastError=None)
    backoff_seconds = 1.0
    pending_batch: list[Dict[str, Any]] = []
    prune_task = asyncio.create_task(_prune_old_positions())
    try:
        while True:
            connected_at = None
            try:
                if pending_batch:
                    await _flush_batch(pending_batch)
                async with websockets.connect(
                    STREAM_URL,
                    open_timeout=OPEN_TIMEOUT_SECONDS,
                    compression="deflate",
                    ping_interval=20,
                    ping_timeout=PING_TIMEOUT_SECONDS,
                    close_timeout=10,
                    max_queue=MAX_BATCH_SIZE,
                ) as websocket:
                    subscription = {
                        "APIKey": api_key,
                        "BoundingBoxes": WORLDWIDE_BOUNDS,
                        "FilterMessageTypes": [
                            "PositionReport",
                            "StandardClassBPositionReport",
                            "ExtendedClassBPositionReport",
                            "LongRangeAisBroadcastMessage",
                            "ShipStaticData",
                        ],
                    }
                    await websocket.send(json.dumps(subscription))
                    _status.update(connected=True, lastError=None)
                    logger.info("Connected to the AISStream worldwide feed.")
                    connected_at = asyncio.get_running_loop().time()
                    await _consume_stream(websocket, pending_batch)
                    raise ConnectionError("AISStream closed the connection.")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _status.update(connected=False, lastError=str(exc))
                logger.exception("AISStream connection or database batch failed.")
                connection_duration = (
                    asyncio.get_running_loop().time() - connected_at
                    if connected_at is not None
                    else None
                )
                if (
                    connection_duration is not None
                    and connection_duration >= STABLE_CONNECTION_SECONDS
                ):
                    backoff_seconds = 1.0
                delay = random.uniform(backoff_seconds / 2, backoff_seconds)
                await asyncio.sleep(delay)
                backoff_seconds = min(backoff_seconds * 2, 60.0)
    finally:
        _status["connected"] = False
        prune_task.cancel()
        try:
            await prune_task
        except asyncio.CancelledError:
            pass
