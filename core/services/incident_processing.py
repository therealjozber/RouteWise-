"""Orchestrate AI analysis, risk recalculation, and AT alerts for incidents."""

import logging

from .ai_engine import analyze_incident_with_ai
from .messaging import build_outgoing_alert, send_sms_alert, send_whatsapp_alert, broadcast_route_sms
from .at_service import reward_reporter
from ..segment_utils import find_closest_segment
from .risk_engine import apply_risk_to_route, attach_incident_to_segment

logger = logging.getLogger(__name__)


def build_report_text(report) -> str:
    segment_note = f"Segment: {report.segment.label}\n" if report.segment_id else ""
    return (
        f"Incident type: {report.incident_type}\n"
        f"Location: {report.location_name}\n"
        f"Route: {report.route.name}\n"
        f"{segment_note}"
        f"Severity (reporter): {report.severity}\n"
        f"Description: {report.description or 'No extra details'}"
    )


def apply_ai_to_report(report) -> dict:
    """Run Gemini/rule analysis and persist AI fields on the report."""
    text = build_report_text(report)
    ai = analyze_incident_with_ai(
        text,
        route_name=report.route.name,
        location_name=report.location_name,
    )
    report.ai_risk_score             = ai["risk_score"]
    report.ai_estimated_delay_minutes = ai["estimated_delay_minutes"]
    report.ai_recommendation          = ai["recommendation"]
    report.save(update_fields=[
        "ai_risk_score",
        "ai_estimated_delay_minutes",
        "ai_recommendation",
    ])
    return ai


def finalize_incident_report(report, notify_phone: str | None = None, channel: str = "SMS"):
    """
    Full pipeline:
      1. Match segment
      2. Run AI analysis
      3. Recalculate route risk
      4. Build SMS/WA alert text
      5. Send confirmation to reporter
      6. Broadcast to all route subscribers + drivers
      7. Reward reporter with airtime if incident is verified

    Returns (ai_result dict, outgoing_alert str).
    """
    # 1. Segment matching
    if not report.segment_id and report.location_name:
        segment = find_closest_segment(report.route, report.location_name)
        if segment:
            report.segment = segment
            report.save(update_fields=["segment"])

    # 2. AI analysis
    ai = apply_ai_to_report(report)

    # 3. Risk recalculation
    attach_incident_to_segment(report, save_segment=False)
    apply_risk_to_route(report.route)

    # 4. Build alert text
    alert = build_outgoing_alert(
        incident_type=report.incident_type,
        location=report.location_name,
        route_name=report.route.name,
        risk_score=ai["risk_score"],
        delay_minutes=ai["estimated_delay_minutes"],
        recommendation=ai["recommendation"],
        segment_label=report.segment.label if report.segment_id else None,
    )

    # 5. Send confirmation to the reporter
    phone = (notify_phone or report.reporter_phone or "").strip()
    if phone:
        if channel == "WhatsApp":
            send_whatsapp_alert(phone, alert)
        else:
            send_sms_alert(phone, alert)

    # 6. Broadcast to route subscribers + drivers (skip if reporter IS a driver)
    try:
        broadcast_route_sms(report.route, alert, severity=report.severity)
    except Exception as exc:
        logger.warning("[AT Broadcast] Failed for route %s: %s", report.route.name, exc)

    # 7. Airtime reward for community reporters (not system/USSD/SMS bots)
    reporter = (report.reporter_name or "").lower()
    is_system = any(k in reporter for k in ("ussd:", "sms:", "community reporter", "system"))
    if not is_system and report.severity in ("High", "Critical"):
        try:
            reward_reporter(report)
        except Exception as exc:
            logger.warning("[AT Airtime] Reward failed: %s", exc)

    return ai, alert
