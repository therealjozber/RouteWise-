"""Segment-aware route risk scoring and recommendations."""

from datetime import timedelta
from django.utils import timezone

from core.segment_utils import reports_for_segment

SEVERITY_POINTS = {
    "Low": 5,
    "Medium": 15,
    "High": 25,
    "Critical": 35,
}

INCIDENT_WEIGHT = {
    "Accident": 1.5,
    "Flood": 1.4,
    "Theft Hotspot": 1.4,
    "Road Block": 1.3,
    "Bad Road": 1.2,
    "Traffic Jam": 1.1,
    "Police Checkpoint": 1.0,
    "Fuel Shortage": 1.0,
    "Vehicle Breakdown": 1.0,
}

FRESH_HOURS = 24
STALE_FACTOR = 0.5


def _freshness_factor(created_at):
    if not created_at:
        return 1.0
    age = timezone.now() - created_at
    if age <= timedelta(hours=FRESH_HOURS):
        return 1.0
    if age <= timedelta(hours=48):
        return STALE_FACTOR
    return STALE_FACTOR * 0.5


def score_report(report) -> float:
    base = SEVERITY_POINTS.get(report.severity, 10)
    weight = INCIDENT_WEIGHT.get(report.incident_type, 1.0)
    verified_bonus = min(report.verified_count * 2, 10)
    fresh = _freshness_factor(report.created_at)
    return (base * weight + verified_bonus) * fresh


def risk_score_to_status(score: float) -> str:
    score = max(0, min(100, int(round(score))))
    if score <= 30:
        return "Safe"
    if score <= 60:
        return "Caution"
    if score <= 80:
        return "High Risk"
    return "Avoid"


def estimate_delay_minutes(score: float, report_count: int) -> int:
    base = int(score * 0.8)
    extra = min(report_count * 5, 30)
    return max(0, min(180, base + extra))


def _score_reports(reports):
    if not reports:
        return 0, "Safe", 0, []
    total = sum(score_report(r) for r in reports)
    raw = min(100, total)
    status = risk_score_to_status(raw)
    delay = estimate_delay_minutes(raw, len(reports))
    top = sorted(reports, key=score_report, reverse=True)[:3]
    return int(round(raw)), status, delay, top


def calculate_segment_risk(segment):
    reports = list(reports_for_segment(segment)[:50])
    score, status, delay, top = _score_reports(reports)
    return {
        "risk_score": score,
        "status": status,
        "estimated_delay_minutes": delay,
        "top_reports": top,
        "report_count": len(reports),
    }


def apply_risk_to_segment(segment, save=True):
    result = calculate_segment_risk(segment)
    segment.risk_score = result["risk_score"]
    segment.status = result["status"]
    if save:
        segment.save(update_fields=["risk_score", "status"])
    return result


def _aggregate_route_from_segments(segments_data):
    """Full route risk from segment scores."""
    if not segments_data:
        return 0, "Safe", 0

    scores = [s["risk_score"] for s in segments_data]
    statuses = [s["status"] for s in segments_data]
    delays = [s["estimated_delay_minutes"] for s in segments_data]

    base = max(scores) if scores else 0
    risky_count = sum(1 for st in statuses if st not in ("Safe",))
    if risky_count >= 2:
        base = min(100, base + 8 * (risky_count - 1))
    if risky_count >= 4:
        base = min(100, base + 10)

    status = risk_score_to_status(base)
    delay = max(delays) if delays else 0
    return int(round(base)), status, delay


def build_segment_recommendation(route, segments_data, route_score, route_status, route_delay):
    """Section-level intelligence — do not cancel whole journey for one bad segment."""
    route_name = route.via_display if route.segments.exists() else route.display_name

    risky = [s for s in segments_data if s["status"] not in ("Safe",)]
    critical = [s for s in segments_data if s["status"] == "Avoid" or any(
        r.severity == "Critical" for r in s.get("top_reports", [])
    )]

    if not risky:
        return (
            f"{route_name} is clear across all sections. "
            f"Minimal delays expected. Good conditions for departure."
        )

    risky_sorted = sorted(risky, key=lambda x: x["risk_score"], reverse=True)
    worst = risky_sorted[0]
    seg_label = worst["label"]
    loc = worst["top_reports"][0].location_name if worst.get("top_reports") else worst["to_location"]
    detail = (
        f"{worst['top_reports'][0].incident_type.lower()} reports near {loc}"
        if worst.get("top_reports")
        else "community reports"
    )

    delay_lo = worst["estimated_delay_minutes"]
    delay_hi = delay_lo + 25

    if len(risky) == 1 and route_score <= 60:
        return (
            f"{route.origin} → {route.destination} is mostly usable, but the "
            f"{seg_label} segment has {worst['status'].upper()} due to {detail}. "
            f"Expected delay: {delay_lo}–{delay_hi} minutes. "
            f"Recommendation: continue only if necessary, reduce speed, and monitor updates."
        )

    if len(risky) == 1:
        return (
            f"Route mostly clear, but caution near {worst['to_location']}. "
            f"The {seg_label} section is {worst['status']} ({detail}). "
            f"Expect {delay_lo}–{delay_hi} min delay in that section only."
        )

    if critical:
        blocked = critical[0]["label"]
        return (
            f"{route_name}: critical incident blocks {blocked}. "
            f"Recommendation: reroute around {critical[0]['to_location']} if possible, "
            f"or delay departure until segment reopens. "
            f"Other sections may still be passable."
        )

    if len(risky) >= 3 or route_status in ("High Risk", "Avoid"):
        names = ", ".join(s["to_location"] for s in risky_sorted[:3])
        return (
            f"Multiple risky sections on {route.origin} → {route.destination} "
            f"({names}). Overall status: {route_status}. "
            f"Expected total delay: {route_delay}–{route_delay + 40} minutes. "
            f"Recommendation: delay departure or seek alternative corridor."
        )

    names = " and ".join(s["label"] for s in risky_sorted[:2])
    return (
        f"{route.origin} → {route.destination} has localized issues on {names}. "
        f"Overall route {route_status.lower()}; plan extra {route_delay} minutes. "
        f"Drive with caution through flagged sections; remainder of route is manageable."
    )


def calculate_route_risk(route):
    segments = list(route.segments.order_by("order"))
    segments_data = []

    if segments:
        for seg in segments:
            seg_result = calculate_segment_risk(seg)
            segments_data.append(
                {
                    "segment": seg,
                    "segment_id": seg.pk,
                    "label": seg.label,
                    "from_location": seg.from_location,
                    "to_location": seg.to_location,
                    "order": seg.order,
                    "distance_km": seg.distance_km,
                    "risk_score": seg_result["risk_score"],
                    "status": seg_result["status"],
                    "estimated_delay_minutes": seg_result["estimated_delay_minutes"],
                    "top_reports": seg_result["top_reports"],
                    "report_count": seg_result["report_count"],
                }
            )
        route_score, route_status, route_delay = _aggregate_route_from_segments(segments_data)
    else:
        reports = list(route.incidents.filter(approved=True).order_by("-created_at")[:50])
        route_score, route_status, route_delay, top = _score_reports(reports)
        segments_data = []

    recommendation = build_segment_recommendation(
        route, segments_data, route_score, route_status, route_delay
    )

    dangerous = [s for s in segments_data if s["status"] in ("High Risk", "Avoid", "Caution")]
    dangerous.sort(key=lambda x: x["risk_score"], reverse=True)

    return {
        "risk_score": route_score,
        "status": route_status,
        "estimated_delay_minutes": route_delay,
        "recommendation": recommendation,
        "segments": segments_data,
        "dangerous_segments": dangerous,
        "worst_segment": dangerous[0] if dangerous else None,
    }


def apply_risk_to_route(route, save=True):
    """Recalculate all segments, then aggregate route risk."""
    for seg in route.segments.order_by("order"):
        apply_risk_to_segment(seg, save=save)

    result = calculate_route_risk(route)
    route.risk_score = result["risk_score"]
    route.status = result["status"]
    if save:
        route.save(update_fields=["risk_score", "status"])
    return result


def attach_incident_to_segment(report, save_segment=True):
    """Auto-match segment from location if not set; recalculate all risks."""
    from core.segment_utils import find_closest_segment

    if report.route_id and report.location_name and not report.segment_id:
        segment = find_closest_segment(report.route, report.location_name)
        if segment:
            report.segment = segment
            if save_segment:
                report.save(update_fields=["segment"])
    apply_risk_to_route(report.route)
    return report
