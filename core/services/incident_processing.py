"""Orchestrate AI analysis, risk recalc, and alerts for incident reports."""

from .ai_engine import analyze_incident_with_ai
from .messaging import build_outgoing_alert, send_sms_alert, send_whatsapp_alert
from ..segment_utils import find_closest_segment
from .risk_engine import apply_risk_to_route, attach_incident_to_segment


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
    report.ai_risk_score = ai["risk_score"]
    report.ai_estimated_delay_minutes = ai["estimated_delay_minutes"]
    report.ai_recommendation = ai["recommendation"]
    report.save(
        update_fields=[
            "ai_risk_score",
            "ai_estimated_delay_minutes",
            "ai_recommendation",
        ]
    )
    return ai


def finalize_incident_report(report, notify_phone: str | None = None, channel: str = "SMS"):
    """
    Match segment, apply AI, recalculate risks, build and send alert.
    Returns (ai_result dict, outgoing_alert str).
    """
    if not report.segment_id and report.location_name:
        segment = find_closest_segment(report.route, report.location_name)
        if segment:
            report.segment = segment
            report.save(update_fields=["segment"])

    ai = apply_ai_to_report(report)
    attach_incident_to_segment(report, save_segment=False)
    apply_risk_to_route(report.route)

    risk_score = ai["risk_score"]
    delay = ai["estimated_delay_minutes"]
    alert = build_outgoing_alert(
        incident_type=report.incident_type,
        location=report.location_name,
        route_name=report.route.name,
        risk_score=risk_score,
        delay_minutes=delay,
        recommendation=ai["recommendation"],
        segment_label=report.segment.label if report.segment_id else None,
    )

    phone = (notify_phone or report.reporter_phone or "").strip()
    if phone:
        if channel == "WhatsApp":
            send_whatsapp_alert(phone, alert)
        else:
            send_sms_alert(phone, alert)

    return ai, alert
