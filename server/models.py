"""
Pydantic Data Models for Spill Sense FastAPI Server
"""

from typing import Any, Dict, List, Optional, Literal

from pydantic import BaseModel, Field


class PrimarySuspectModel(BaseModel):
    name: str
    imo: int
    confidence: float
    matchType: str


class SpillCreateModel(BaseModel):
    id: str
    title: str
    severity: str
    status: str
    coords: List[float]
    areaKm2: float
    
    volumeBbls: int
    confidence: float
    sensor: str
    wind: str
    current: str
    surfaceTemp: str
    slickType: str
    primarySuspect: PrimarySuspectModel
    slickPolygon: List[List[float]]


class VesselNoteCreate(BaseModel):
    note: str
    author: Optional[str] = "Command Analyst"


class FeedbackCreate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    feedback_type: str
    rating: int = Field(..., ge=1, le=5)
    message: str


class VesselFlagUpdate(BaseModel):
    isDarkVessel: bool
    riskLevel: str
    riskScore: int


class LoginRequest(BaseModel):
    email: str
    password: str
    role: Optional[str] = "commander"


class DossierGenerateRequest(BaseModel):
    incidentId: str
    accusedImo: int
    classificationLevel: Optional[str] = "LEVEL 3 FORENSIC EVIDENCE"


class AISPointModel(BaseModel):
    mmsi: str
    vessel_name: str
    lat: float
    lon: float
    timestamp: str
    speed_knots: Optional[float] = None
    heading: Optional[float] = None
    vessel_type: Optional[str] = None
    length_m: Optional[float] = None


class SARVesselModel(BaseModel):
    id: str
    lat: float
    lon: float
    heading: Optional[float] = None
    length_m: Optional[float] = None


class MatchVesselsRequest(BaseModel):
    sar_time: str
    sar_vessels: List[SARVesselModel]
    ais_points: List[AISPointModel]


class SarAisCorrelateRequest(BaseModel):
    sar_time: str
    sar_lat: float
    sar_lon: float
    sar_heading: Optional[float] = None
    sar_length_m: Optional[float] = None
    ais_records: List[AISPointModel]


class RankSuspectVesselModel(BaseModel):
    vessel_name: Optional[str] = None
    name: Optional[str] = None
    vessel_type: Optional[str] = None
    type: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed_knots: Optional[float] = None
    speed: Optional[float] = None
    timestamp: Optional[str] = None
    last_seen: Optional[str] = None
    ais_gap_minutes: Optional[float] = None
    ais_gap: Optional[float] = None
    is_dark_vessel: Optional[bool] = None
    dark_vessel: Optional[bool] = None


class RankSuspectsRequest(BaseModel):
    origin_lat: float
    origin_lon: float
    release_start: str
    release_end: str
    vessels: List[RankSuspectVesselModel]


class DriftRequest(BaseModel):
    spill_lat: float
    spill_lon: float
    sar_time: Optional[str] = None
    current_speed_mps: float
    current_direction_degrees: float
    wind_speed_mps: float = 0.0
    wind_direction_degrees: Optional[float] = None
    hours: Literal[6, 12, 24, 48] = 12
    uncertainty_km: float = 5.0
# =============================================================================
# QUICK SPILL ALERT
# =============================================================================
class QuickAlertSensitiveAreaModel(BaseModel):
    """A sensitive receptor the analyst wants alerts checked against.

    The frontend passes the built-in catalogue, so a new receptor type only
    needs adding here (and to SENSITIVE_AREA_TYPES in alerts.py) to work.
    """
    name: str
    type: Literal[
        "beach",
        "port",
        "coral_reef",
        "mangrove",
        "fishing_zone",
        "island",
        "marine_protected_area",
    ]
    lat: float
    lon: float
class QuickAlertEvaluateRequest(BaseModel):
    """Evaluate one SAR-observed slick reading for immediate alerting."""
    spill_lat: float
    spill_lon: float
    oil_confidence: float
    area_km2: float
    detected_at_utc: Optional[str] = None
    # Forecast time for the slick to reach the nearest sensitive area. Omit when
    # unknown and the backend estimates it from a simple default advection speed.
    predicted_impact_hours: Optional[float] = None
    # Distance from the slick to a shoreline / sensitive receptor, when the
    # analyst already knows it.
    distance_to_coast_km: Optional[float] = None
    # Treated as a boolean flag: true suppresses automatic proximity re-tiering,
    # false/omitted lets a near-coast high-confidence slick escalate to High.
    is_offshore: bool = False
    sensitive_areas: List[QuickAlertSensitiveAreaModel] = []
