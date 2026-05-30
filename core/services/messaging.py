"""SMS/WhatsApp via Africa's Talking when configured; safe logging fallback."""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

_at_initialized = False
_at_sms = None


def _get_at_credentials():
    username = getattr(settings, "AT_USERNAME", "") or ""
    api_key = getattr(settings, "AT_API_KEY", "") or ""
    return username.strip(), api_key.strip()


def _init_africas_talking():
    global _at_initialized, _at_sms
    if _at_initialized:
        return _at_sms is not None

    username, api_key = _get_at_credentials()
    if not username or not api_key:
        logger.info("Africa's Talking credentials not configured.")
        _at_initialized = True
        return False

    try:
        import africastalking

        africastalking.initialize(username, api_key)
        _at_sms = africastalking.SMS
        _at_initialized = True
        logger.info("Africa's Talking SMS initialized for user: %s", username)
        return True
    except Exception as exc:
        logger.warning("Africa's Talking init failed: %s", exc)
        _at_initialized = True
        return False


def send_sms_alert(phone_number: str, message: str) -> bool:
    """Send SMS via Africa's Talking if credentials exist; otherwise log."""
    phone_number = (phone_number or "").strip()
    message = (message or "").strip()
    if not phone_number or not message:
        return False

    if _init_africas_talking() and _at_sms:
        try:
            response = _at_sms.send(message, [phone_number])
            logger.info("AT SMS sent to %s: %s", phone_number, response)
            return True
        except Exception as exc:
            logger.warning("AT SMS send failed: %s — logging instead.", exc)

    logger.info("[SMS (simulated) -> %s] %s", phone_number, message)
    print(f"[RouteWise SMS -> {phone_number}] {message}")
    return True


def send_whatsapp_alert(phone_number: str, message: str) -> bool:
    """
    WhatsApp: log/simulate until official AT WhatsApp endpoint is configured.
    Never crashes the app.
    """
    phone_number = (phone_number or "").strip()
    message = (message or "").strip()
    if not phone_number or not message:
        return False

    logger.info("[WhatsApp (simulated) -> %s] %s", phone_number, message)
    print(f"[RouteWise WhatsApp -> {phone_number}] {message}")
    return True


def parse_incoming_message(text: str) -> dict | None:
    """
    Parse: TYPE#Location#Route Name
    Example: ACCIDENT#Chalinze#Dar es Salaam to Morogoro
    """
    text = (text or "").strip()
    if not text:
        return None

    parts = text.split("#")
    if len(parts) < 3:
        return None

    type_key = parts[0].strip().upper().replace(" ", "")
    location = parts[1].strip()
    route_hint = "#".join(parts[2:]).strip()

    type_map = {
        "ACCIDENT": "Accident",
        "FLOOD": "Flood",
        "BADROAD": "Bad Road",
        "BAD ROAD": "Bad Road",
        "TRAFFIC": "Traffic Jam",
        "TRAFFICJAM": "Traffic Jam",
        "ROADBLOCK": "Road Block",
        "POLICE": "Police Checkpoint",
        "CHECKPOINT": "Police Checkpoint",
        "FUEL": "Fuel Shortage",
        "THEFT": "Theft Hotspot",
        "BREAKDOWN": "Vehicle Breakdown",
    }

    incident_type = type_map.get(type_key)
    if not incident_type:
        for key, val in type_map.items():
            if key in type_key or type_key in key:
                incident_type = val
                break
    if not incident_type:
        incident_type = "Bad Road"

    return {
        "incident_type": incident_type,
        "location_name": location,
        "route_hint": route_hint,
    }


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
    return (
        f"RouteWise TZ Alert: {incident_type} reported near {location} "
        f"on {route_name}.{seg} Risk: {risk_score}/100. "
        f"Delay: {delay_minutes} mins. {rec}"
    )
