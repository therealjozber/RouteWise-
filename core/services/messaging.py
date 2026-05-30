"""
RouteWise TZ — messaging helpers.
All actual delivery goes through at_service.ATService.
This module keeps the public API stable for callers.
"""

import logging
from .at_service import at, _find_route_by_hint_ussd

logger = logging.getLogger(__name__)


# ── Outbound helpers ──────────────────────────────────────────────

def send_sms_alert(phone_number: str, message: str) -> bool:
    result = at.send_sms(phone_number, message)
    return result["status"] in ("success", "simulated")


def send_whatsapp_alert(phone_number: str, message: str) -> bool:
    result = at.send_whatsapp(phone_number, message)
    return result["status"] in ("success", "simulated")


def broadcast_route_sms(route, message: str, severity: str = "Medium") -> dict:
    """Send to all drivers + subscribers on a route."""
    return at.broadcast_route_alert(route, message, severity)


def build_outgoing_alert(
    incident_type: str,
    location: str,
    route_name: str,
    risk_score: int,
    delay_minutes: int,
    recommendation: str,
    segment_label: str | None = None,
) -> str:
    seg = f" Section: {segment_label}." if segment_label else ""
    rec = (recommendation or "").strip()
    # Keep under 160 chars for a single SMS page
    short_rec = rec[:80] + "…" if len(rec) > 80 else rec
    return (
        f"RouteWise TZ: {incident_type} near {location} on {route_name}."
        f"{seg} Risk:{risk_score}/100 Delay:{delay_minutes}min. {short_rec}"
    )


# ── Inbound parsing ───────────────────────────────────────────────

def parse_incoming_message(text: str) -> dict | None:
    """
    Parse: TYPE#Location#RouteHint
    Example: ACCIDENT#Chalinze#Dar es Salaam to Morogoro
    Returns None if unparseable.
    """
    text = (text or "").strip()
    if not text or "#" not in text:
        return None

    parts = text.split("#")
    if len(parts) < 2:
        return None

    type_key   = parts[0].strip().upper().replace(" ", "")
    location   = parts[1].strip() if len(parts) > 1 else ""
    route_hint = "#".join(parts[2:]).strip() if len(parts) > 2 else ""

    type_map = {
        "ACCIDENT":   "Accident",
        "FLOOD":      "Flood",
        "BADROAD":    "Bad Road",
        "BAD":        "Bad Road",
        "TRAFFIC":    "Traffic Jam",
        "TRAFFICJAM": "Traffic Jam",
        "ROADBLOCK":  "Road Block",
        "BLOCK":      "Road Block",
        "POLICE":     "Police Checkpoint",
        "CHECKPOINT": "Police Checkpoint",
        "FUEL":       "Fuel Shortage",
        "THEFT":      "Theft Hotspot",
        "BREAKDOWN":  "Vehicle Breakdown",
    }

    incident_type = type_map.get(type_key)
    if not incident_type:
        for key, val in type_map.items():
            if key in type_key or type_key in key:
                incident_type = val
                break
    if not incident_type:
        incident_type = "Bad Road"

    if not location:
        return None

    return {
        "incident_type": incident_type,
        "location_name": location,
        "route_hint":    route_hint,
    }
