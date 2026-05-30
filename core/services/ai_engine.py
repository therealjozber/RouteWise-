"""Gemini AI incident analysis with safe local fallback."""

import json
import logging
import re
from django.conf import settings

logger = logging.getLogger(__name__)

VALID_SEVERITIES = {"Low", "Medium", "High", "Critical"}
VALID_INCIDENT_TYPES = {
    "Accident",
    "Flood",
    "Bad Road",
    "Traffic Jam",
    "Road Block",
    "Police Checkpoint",
    "Fuel Shortage",
    "Theft Hotspot",
    "Vehicle Breakdown",
}

SYSTEM_PROMPT = """You are RouteWise TZ AI, a transport intelligence assistant for Tanzanian drivers and logistics operators.

Analyze road incident reports and return ONLY valid JSON with no markdown fences or extra text.

Required fields:
- incident_type (one of: Accident, Flood, Bad Road, Traffic Jam, Road Block, Police Checkpoint, Fuel Shortage, Theft Hotspot, Vehicle Breakdown)
- severity (exactly one of: Low, Medium, High, Critical)
- risk_score (integer 0-100)
- estimated_delay_minutes (integer 0-180)
- recommendation (string, practical advice for drivers)

Rules:
- Risk score must be 0-100.
- Severity must be Low, Medium, High, or Critical.
- Recommendation must be practical and must NOT always cancel the whole route.
- If only one segment or town is affected, recommend caution or reroute around that section only.
- Consider Tanzanian long-distance corridors, weighbridges, seasonal floods, and truck traffic."""


def _normalize_result(data: dict) -> dict:
    """Ensure clean output dict with valid ranges."""
    severity = data.get("severity", "Medium")
    if severity not in VALID_SEVERITIES:
        severity = "Medium"

    incident_type = data.get("incident_type", "Bad Road")
    if incident_type not in VALID_INCIDENT_TYPES:
        incident_type = "Bad Road"

    try:
        risk_score = int(data.get("risk_score", 0))
    except (TypeError, ValueError):
        risk_score = 0
    risk_score = max(0, min(100, risk_score))

    try:
        delay = int(data.get("estimated_delay_minutes", 0))
    except (TypeError, ValueError):
        delay = 0
    delay = max(0, min(180, delay))

    recommendation = (data.get("recommendation") or "").strip()
    if not recommendation:
        recommendation = _fallback_recommendation(incident_type, severity, risk_score)

    return {
        "incident_type": incident_type,
        "severity": severity,
        "risk_score": risk_score,
        "estimated_delay_minutes": delay,
        "recommendation": recommendation,
    }


def _fallback_recommendation(incident_type: str, severity: str, risk_score: int) -> str:
    if risk_score <= 30:
        return (
            "Conditions appear manageable. Proceed with normal caution and "
            "monitor community updates."
        )
    if risk_score <= 60:
        return (
            f"Moderate impact from {incident_type.lower()} reported. "
            f"Reduce speed near the affected area; the wider route may still be usable."
        )
    if risk_score <= 80:
        return (
            f"Significant {incident_type.lower()} risk ({severity} severity). "
            f"Use caution through the affected section only; consider delaying if loaded."
        )
    return (
        f"Critical conditions ({incident_type}). Consider rerouting around the affected "
        f"section rather than cancelling the entire journey if alternate roads exist."
    )


def _rule_based_fallback(
    report_text: str,
    route_name: str | None = None,
    location_name: str | None = None,
) -> dict:
    """Local fallback when Gemini is unavailable."""
    text = (report_text or "").lower()
    route_name = route_name or "the route"
    location_name = location_name or "the reported area"

    incident_type = "Bad Road"
    if "accident" in text:
        incident_type = "Accident"
    elif "flood" in text:
        incident_type = "Flood"
    elif "traffic" in text or "jam" in text:
        incident_type = "Traffic Jam"
    elif "theft" in text:
        incident_type = "Theft Hotspot"
    elif "police" in text or "checkpoint" in text:
        incident_type = "Police Checkpoint"
    elif "fuel" in text:
        incident_type = "Fuel Shortage"
    elif "block" in text:
        incident_type = "Road Block"

    severity = "Medium"
    if "critical" in text:
        severity = "Critical"
    elif "high" in text:
        severity = "High"
    elif "low" in text:
        severity = "Low"

    weights = {"Low": 15, "Medium": 35, "High": 55, "Critical": 75}
    type_boost = {"Accident": 15, "Flood": 12, "Theft Hotspot": 10}
    risk_score = min(100, weights.get(severity, 35) + type_boost.get(incident_type, 0))
    delay = min(120, int(risk_score * 0.7))

    recommendation = (
        f"{route_name} is mostly usable, but exercise caution near {location_name} "
        f"due to {incident_type.lower()} reports. Expected delay in that section: "
        f"{delay}–{delay + 20} minutes. Continue only if necessary and monitor updates."
    )

    return _normalize_result(
        {
            "incident_type": incident_type,
            "severity": severity,
            "risk_score": risk_score,
            "estimated_delay_minutes": delay,
            "recommendation": recommendation,
        }
    )


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return None
    return None


def _call_gemini(report_text: str, route_name: str | None, location_name: str | None) -> dict | None:
    api_key = getattr(settings, "GEMINI_API_KEY", "") or ""
    model = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash") or "gemini-2.5-flash"

    if not api_key:
        logger.info("GEMINI_API_KEY not set; using rule-based fallback.")
        return None

    user_prompt = f"""Analyze this road incident report:

Route: {route_name or 'Unknown'}
Location: {location_name or 'Unknown'}

Report:
{report_text}

Return ONLY valid JSON with keys: incident_type, severity, risk_score, estimated_delay_minutes, recommendation."""

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=f"{SYSTEM_PROMPT}\n\n{user_prompt}",
        )
        raw = getattr(response, "text", None) or ""
        if not raw and hasattr(response, "candidates") and response.candidates:
            parts = response.candidates[0].content.parts
            raw = "".join(getattr(p, "text", "") for p in parts)
        parsed = _extract_json(raw)
        if parsed:
            return _normalize_result(parsed)
        logger.warning("Gemini returned non-JSON response; using fallback.")
    except Exception as exc:
        logger.warning("Gemini API error: %s", exc)
    return None


def analyze_incident_with_ai(
    report_text: str,
    route_name: str | None = None,
    location_name: str | None = None,
) -> dict:
    """
    Analyze incident text with Gemini; fall back to rules if unavailable.
    Returns dict with incident_type, severity, risk_score, estimated_delay_minutes, recommendation.
    """
    result = _call_gemini(report_text, route_name, location_name)
    if result:
        return result
    return _rule_based_fallback(report_text, route_name, location_name)
