"""
Spill Sense — Quick Spill Alert evaluation engine.

A slick reading raises an alert when ANY of three triggers fires:

  * oil confidence >= 75%
  * spill area     >= 2 km²
  * a sensitive receptor (beach, port, coral reef, mangrove, fishing zone,
    island, marine protected area) lies within 20 km

Severity is then tiered by the predicted time-to-impact:

  * Critical : impact within 12 hours
  * High     : impact within 12-24 hours, or a high-confidence slick near coast
  * Medium   : possible impact within 24-48 hours
  * Low      : offshore, low-confidence spill

Kept in its own module so the thresholds and response language are auditable in
one place, and so server/api.py stays a thin routing layer.
"""

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import HTTPException

try:  # package import when run as `uvicorn server.api:app`
    from server.models import QuickAlertEvaluateRequest
except ImportError:  # pragma: no cover - direct script execution
    from models import QuickAlertEvaluateRequest
# --- Shared geo/time helpers --------------------------------------------------
# Duplicated here rather than imported from server.api on purpose: api.py
# imports this module, so reaching back into it would be a circular import.
def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points, in kilometres."""
    radius_km = 6371.0
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c

def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into an aware UTC datetime."""
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid ISO datetime: {value}") from exc


# --- Trigger thresholds -------------------------------------------------------
ALERT_CONFIDENCE_TRIGGER = 75.0    # oil confidence %
ALERT_AREA_TRIGGER_KM2 = 2.0       # spill area km²
ALERT_PROXIMITY_TRIGGER_KM = 20.0  # distance to a sensitive receptor

# Fallback advection speed, used only to turn a distance into an ETA when the
# caller supplied no predicted_impact_hours. Deliberately conservative.
DEFAULT_ADVECTION_KMPH = 1.2

# Ordered worst-first; `max_hours=None` is the catch-all Low tier.
ALERT_TIERS: List[Dict[str, Any]] = [
    {"level": "Critical", "max_hours": 12, "rank": 4, "color": "#FF4438"},
    {"level": "High", "max_hours": 24, "rank": 3, "color": "#FF8A3D"},
    {"level": "Medium", "max_hours": 48, "rank": 2, "color": "#FFB020"},
    {"level": "Low", "max_hours": None, "rank": 1, "color": "#2BD97C"},
]

SENSITIVE_AREA_TYPES = {
    "beach": "Beach",
    "port": "Port",
    "coral_reef": "Coral Reef",
    "mangrove": "Mangrove",
    "fishing_zone": "Fishing Zone",
    "island": "Island",
    "marine_protected_area": "Marine Protected Area",
}

# Recommended action depends on severity AND on whether a receptor is actually in
# the path — a Critical ETA with nothing nearby is a different response from one
# about to land on a mangrove belt.
ALERT_NEXT_ACTIONS = {
    "Critical": {
        True: "Immediate escalation: notify the coastal/port authority and mobilise containment to the receptor at risk. Dispatch a verification flight or vessel survey within 12 hours.",
        False: "Immediate escalation: task an urgent verification pass and alert the regional response centre. Prepare offshore containment assets pending field confirmation.",
    },
    "High": {
        True: "Raise a priority tasking: verify the slick on the next SAR pass and warn the receptor operator. Begin pre-positioning booms and skimmers.",
        False: "Verify on the next SAR pass and notify the regional response centre. Track drift toward the nearest receptor.",
    },
    "Medium": {
        True: "Monitor and re-evaluate every 12 hours. Request a dedicated SAR revisit and confirm vessel traffic near the reported position.",
        False: "Log for routine follow-up and re-check on the next scheduled SAR pass. No immediate mobilisation recommended.",
    },
    "Low": {
        True: "Continue routine monitoring; a low-confidence detection near a receptor still warrants a scheduled re-look.",
        False: "Log as an offshore low-confidence detection and continue routine monitoring. Do not task assets without stronger corroboration.",
    },
}

ALERT_DISCLAIMER = "Investigation support only — requires authorised field verification."


def _alert_tier_for_hours(impact_hours: Optional[float]) -> Dict[str, Any]:
    """Map a predicted time-to-impact onto a severity tier (Critical -> Low)."""
    if impact_hours is None:
        return ALERT_TIERS[-1]
    for tier in ALERT_TIERS:
        if tier["max_hours"] is not None and impact_hours <= tier["max_hours"]:
            return tier
    return ALERT_TIERS[-1]


def evaluate_quick_alert(payload: QuickAlertEvaluateRequest) -> Dict[str, Any]:
    """Evaluate one SAR slick reading and return a Quick Spill Alert.

    Returns severity "None" when no trigger fires, so the caller can tell
    "no alert" apart from "Low-severity alert".
    """
    if payload.oil_confidence < 0 or payload.oil_confidence > 100:
        raise HTTPException(status_code=400, detail="oil_confidence must be between 0 and 100")
    if payload.area_km2 < 0:
        raise HTTPException(status_code=400, detail="area_km2 cannot be negative")

    detected_at = parse_iso_datetime(payload.detected_at_utc) or datetime.now(timezone.utc)

    # --- Rank sensitive receptors by distance --------------------------------
    ranked_receptors: List[Dict[str, Any]] = []
    for area in payload.sensitive_areas:
        distance_km = haversine_distance_km(payload.spill_lat, payload.spill_lon, area.lat, area.lon)
        ranked_receptors.append({
            "name": area.name,
            "type": area.type,
            "type_label": SENSITIVE_AREA_TYPES.get(area.type, area.type.replace("_", " ").title()),
            "lat": area.lat,
            "lon": area.lon,
            "distance_km": round(distance_km, 2),
        })
    ranked_receptors.sort(key=lambda item: item["distance_km"])
    nearest_receptor = ranked_receptors[0] if ranked_receptors else None

    # --- Resolve the governing distance --------------------------------------
    # An impact counts only if a receptor sits inside the 20 km ring, or the
    # caller supplied an explicit coastline distance that is closer still.
    coast_km = payload.distance_to_coast_km
    if nearest_receptor is not None and (coast_km is None or nearest_receptor["distance_km"] < coast_km):
        coast_km = nearest_receptor["distance_km"]
    distance_to_receptor = coast_km
    receptor_in_path = distance_to_receptor is not None and distance_to_receptor <= ALERT_PROXIMITY_TRIGGER_KM

    # --- Trigger 1: confidence | Trigger 2: area | Trigger 3: proximity ------
    confidence_hit = payload.oil_confidence >= ALERT_CONFIDENCE_TRIGGER
    area_hit = payload.area_km2 >= ALERT_AREA_TRIGGER_KM2
    proximity_hit = receptor_in_path

    if not (confidence_hit or area_hit or proximity_hit):
        return {
            "alert": False,
            "severity": "None",
            "severity_color": None,
            "severity_rank": 0,
            "triggered_by": [],
            "detected_at_utc": detected_at.isoformat().replace("+00:00", "Z"),
            "spill": {"lat": payload.spill_lat, "lon": payload.spill_lon},
            "area_km2": round(payload.area_km2, 2),
            "oil_confidence": round(payload.oil_confidence, 1),
            "nearest_sensitive_area": nearest_receptor,
            "distance_to_sensitive_area_km": round(distance_to_receptor, 2) if distance_to_receptor is not None else None,
            "predicted_impact_hours": None,
            "receptors_ranked": ranked_receptors,
            "recommended_next_action": "No threshold breached. Continue routine monitoring on the next scheduled SAR pass.",
            "disclaimer": ALERT_DISCLAIMER,
        }

    triggered_by = []
    if confidence_hit:
        triggered_by.append(f"Oil confidence {payload.oil_confidence:.1f}% \u2265 {ALERT_CONFIDENCE_TRIGGER:.0f}%")
    if area_hit:
        triggered_by.append(f"Spill area {payload.area_km2:.1f} km\u00b2 \u2265 {ALERT_AREA_TRIGGER_KM2:.0f} km\u00b2")
    if proximity_hit and nearest_receptor is not None:
        triggered_by.append(f"Within {ALERT_PROXIMITY_TRIGGER_KM:.0f} km of {nearest_receptor['name']}")

    # --- Predicted time to impact --------------------------------------------
    impact_hours = payload.predicted_impact_hours
    if impact_hours is None and receptor_in_path and distance_to_receptor:
        impact_hours = distance_to_receptor / DEFAULT_ADVECTION_KMPH
    tier = _alert_tier_for_hours(impact_hours)

    # A high-confidence slick already inside the coastal ring, with no ETA
    # supplied, is treated as High rather than falling through to Low.
    if impact_hours is None and receptor_in_path and confidence_hit:
        high_tier = next(item for item in ALERT_TIERS if item["level"] == "High")
        if tier["rank"] < high_tier["rank"]:
            tier = high_tier

    return {
        "alert": True,
        "severity": tier["level"],
        "severity_color": tier["color"],
        "severity_rank": tier["rank"],
        "triggered_by": triggered_by,
        "detected_at_utc": detected_at.isoformat().replace("+00:00", "Z"),
        "spill": {"lat": payload.spill_lat, "lon": payload.spill_lon},
        "area_km2": round(payload.area_km2, 2),
        "oil_confidence": round(payload.oil_confidence, 1),
        "is_offshore": payload.is_offshore,
        "nearest_sensitive_area": nearest_receptor,
        "distance_to_sensitive_area_km": round(distance_to_receptor, 2) if distance_to_receptor is not None else None,
        "predicted_impact_hours": round(impact_hours, 2) if impact_hours is not None else None,
        "receptors_ranked": ranked_receptors,
        "recommended_next_action": ALERT_NEXT_ACTIONS[tier["level"]][receptor_in_path],
        "disclaimer": ALERT_DISCLAIMER,
    }
