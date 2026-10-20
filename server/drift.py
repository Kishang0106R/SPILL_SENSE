"""Environmental drift samples and time-aware slick backtracking."""

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class DriftDataUnavailable(RuntimeError):
    """Raised when the environmental source cannot provide a complete track."""


@dataclass(frozen=True)
class DriftSample:
    time_utc: datetime
    current_speed_mps: float
    current_direction_degrees: float
    wind_speed_mps: float
    wind_direction_from_degrees: float


@dataclass(frozen=True)
class BacktrackResult:
    source_lat: float
    source_lon: float
    source_time: datetime
    displacement_km: float
    path_length_km: float
    path: List[Dict[str, Any]]


def _hourly_payload(url: str) -> Dict[str, Any]:
    request = Request(url, headers={"User-Agent": "SpillSense/1.0"})
    try:
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read())
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise DriftDataUnavailable("Environmental data service could not be reached.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("hourly"), dict):
        raise DriftDataUnavailable("Environmental data service returned an invalid hourly response.")
    return payload


def _utc_hour(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DriftDataUnavailable("Environmental data contains an invalid timestamp.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _as_finite_float(value: Any) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Environmental sample is not finite.")
    return result


def fetch_environmental_drift(
    latitude: float,
    longitude: float,
    sar_time: datetime,
    drift_hours: int,
) -> List[DriftSample]:
    """Fetch hourly Open-Meteo marine currents and 10 m winds near the slick."""
    if sar_time.tzinfo is None:
        raise DriftDataUnavailable("SAR acquisition time must include a timezone.")

    now = datetime.now(timezone.utc)
    sar_time_utc = sar_time.astimezone(timezone.utc)
    if sar_time_utc > now:
        raise DriftDataUnavailable("Environmental drift is unavailable for a future SAR time.")
    required_history_hours = max(
        0.0, (now - sar_time_utc).total_seconds() / 3600.0
    ) + drift_hours + 2
    past_days = max(1, math.ceil(required_history_hours / 24))
    if past_days > 92:
        raise DriftDataUnavailable(
            "Open-Meteo marine history does not cover this SAR time and backtrack window."
        )

    common = {
        "latitude": f"{latitude:.6f}",
        "longitude": f"{longitude:.6f}",
        "past_days": str(past_days),
        "forecast_days": "1",
        "timezone": "GMT",
    }
    marine_url = "https://marine-api.open-meteo.com/v1/marine?" + urlencode({
        **common,
        "hourly": "ocean_current_velocity,ocean_current_direction",
    })
    weather_url = "https://api.open-meteo.com/v1/forecast?" + urlencode({
        **common,
        "hourly": "wind_speed_10m,wind_direction_10m",
        "wind_speed_unit": "ms",
    })
    marine = _hourly_payload(marine_url)
    weather = _hourly_payload(weather_url)

    marine_hourly = marine["hourly"]
    weather_hourly = weather["hourly"]
    marine_times = marine_hourly.get("time")
    weather_times = weather_hourly.get("time")
    current_speeds = marine_hourly.get("ocean_current_velocity")
    current_directions = marine_hourly.get("ocean_current_direction")
    wind_speeds = weather_hourly.get("wind_speed_10m")
    wind_directions = weather_hourly.get("wind_direction_10m")
    arrays = (
        marine_times,
        current_speeds,
        current_directions,
        weather_times,
        wind_speeds,
        wind_directions,
    )
    if any(not isinstance(values, list) for values in arrays):
        raise DriftDataUnavailable("Environmental response is missing required hourly variables.")
    if not (len(marine_times) == len(current_speeds) == len(current_directions)):
        raise DriftDataUnavailable("Marine current arrays have inconsistent lengths.")
    if not (len(weather_times) == len(wind_speeds) == len(wind_directions)):
        raise DriftDataUnavailable("Wind arrays have inconsistent lengths.")

    current_unit = marine.get("hourly_units", {}).get("ocean_current_velocity")
    if current_unit == "km/h":
        current_scale = 1.0 / 3.6
    elif current_unit in {"m/s", "m s-1"}:
        current_scale = 1.0
    else:
        raise DriftDataUnavailable("Marine current speed has an unsupported unit.")
    wind_unit = weather.get("hourly_units", {}).get("wind_speed_10m")
    if wind_unit in {"m/s", "m s-1"}:
        wind_scale = 1.0
    elif wind_unit == "km/h":
        wind_scale = 1.0 / 3.6
    else:
        raise DriftDataUnavailable("Wind speed has an unsupported unit.")

    winds: Dict[datetime, tuple[float, float]] = {}
    for timestamp, speed, direction in zip(weather_times, wind_speeds, wind_directions):
        if speed is None or direction is None:
            continue
        try:
            wind_speed_mps = _as_finite_float(speed) * wind_scale
            wind_direction = _as_finite_float(direction)
        except (TypeError, ValueError):
            continue
        if wind_speed_mps < 0:
            continue
        winds[_utc_hour(timestamp)] = (wind_speed_mps, wind_direction % 360.0)

    samples: List[DriftSample] = []
    for timestamp, speed, direction in zip(
        marine_times, current_speeds, current_directions
    ):
        if speed is None or direction is None:
            continue
        try:
            current_speed_mps = _as_finite_float(speed) * current_scale
            current_direction = _as_finite_float(direction)
        except (TypeError, ValueError):
            continue
        if current_speed_mps < 0:
            continue
        time_utc = _utc_hour(timestamp)
        wind = winds.get(time_utc)
        if wind is None:
            continue
        samples.append(
            DriftSample(
                time_utc=time_utc,
                current_speed_mps=current_speed_mps,
                current_direction_degrees=current_direction % 360.0,
                wind_speed_mps=wind[0],
                wind_direction_from_degrees=wind[1],
            )
        )
    if not samples:
        raise DriftDataUnavailable(
            "No complete ocean-current and wind samples are available near the slick."
        )
    return samples


def _destination(
    latitude: float, longitude: float, east_m: float, north_m: float
) -> tuple[float, float]:
    distance_m = math.hypot(east_m, north_m)
    if distance_m == 0:
        return latitude, longitude
    bearing = math.atan2(east_m, north_m)
    angular_distance = distance_m / 6_371_008.8
    lat1 = math.radians(latitude)
    lon1 = math.radians(longitude)
    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_distance)
        + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), (math.degrees(lon2) + 540.0) % 360.0 - 180.0


def backtrack_slick(
    latitude: float,
    longitude: float,
    sar_time: datetime,
    drift_hours: int,
    samples: List[DriftSample],
    windage_coefficient: float = 0.03,
) -> BacktrackResult:
    """Integrate hourly current and wind vectors backward from the observed slick."""
    if sar_time.tzinfo is None:
        raise ValueError("SAR acquisition time must include a timezone.")
    if drift_hours not in {6, 12, 24, 48}:
        raise ValueError("drift_hours must be one of 6, 12, 24, or 48.")
    if not 0.0 <= windage_coefficient <= 0.1:
        raise ValueError("windage_coefficient must be between 0 and 0.1.")

    sample_by_hour = {sample.time_utc: sample for sample in samples}
    cursor = sar_time.astimezone(timezone.utc)
    source_lat = latitude
    source_lon = longitude
    path = [{
        "time": cursor.isoformat(),
        "lat": round(source_lat, 6),
        "lon": round(source_lon, 6),
    }]
    remaining_seconds = drift_hours * 3600.0
    displacement_m = 0.0

    while remaining_seconds > 0:
        step_seconds = min(3600.0, remaining_seconds)
        midpoint = cursor - timedelta(seconds=step_seconds / 2.0)
        sample_time = midpoint.replace(minute=0, second=0, microsecond=0)
        sample = sample_by_hour.get(sample_time)
        if sample is None:
            raise DriftDataUnavailable(
                f"Environmental sample missing for {sample_time.isoformat()}."
            )

        current_bearing = math.radians(sample.current_direction_degrees)
        wind_bearing = math.radians(
            (sample.wind_direction_from_degrees + 180.0) % 360.0
        )
        east_mps = (
            sample.current_speed_mps * math.sin(current_bearing)
            + sample.wind_speed_mps * windage_coefficient * math.sin(wind_bearing)
        )
        north_mps = (
            sample.current_speed_mps * math.cos(current_bearing)
            + sample.wind_speed_mps * windage_coefficient * math.cos(wind_bearing)
        )
        east_displacement = -east_mps * step_seconds
        north_displacement = -north_mps * step_seconds
        source_lat, source_lon = _destination(
            source_lat, source_lon, east_displacement, north_displacement
        )
        displacement_m += math.hypot(east_displacement, north_displacement)
        cursor -= timedelta(seconds=step_seconds)
        remaining_seconds -= step_seconds
        path.append({
            "time": cursor.isoformat(),
            "lat": round(source_lat, 6),
            "lon": round(source_lon, 6),
        })

    start = path[0]
    delta_lat = math.radians(source_lat - float(start["lat"]))
    delta_lon = math.radians(source_lon - float(start["lon"]))
    start_lat_rad = math.radians(float(start["lat"]))
    source_lat_rad = math.radians(source_lat)
    haversine = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(start_lat_rad)
        * math.cos(source_lat_rad)
        * math.sin(delta_lon / 2.0) ** 2
    )
    net_displacement_m = 2 * 6_371_008.8 * math.asin(
        math.sqrt(min(1.0, haversine))
    )

    return BacktrackResult(
        source_lat=source_lat,
        source_lon=source_lon,
        source_time=cursor,
        displacement_km=net_displacement_m / 1000.0,
        path_length_km=displacement_m / 1000.0,
        path=path,
    )
