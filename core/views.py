import json

from django.contrib import messages
from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import DriverRegistrationForm, IncidentReportForm, SimulateMessageForm
from .models import Driver, IncidentReport, RouteSegment, TransportRoute
from .segment_utils import build_all_routes_map_data, build_route_map_data, find_closest_segment
from .services.incident_processing import finalize_incident_report
from .services.messaging import parse_incoming_message
from .services.risk_engine import calculate_route_risk


def _find_route_by_hint(hint: str):
    hint = (hint or "").lower().replace(" to ", " ").replace("→", " ")
    routes = TransportRoute.objects.all()
    for route in routes:
        if route.origin.lower() in hint and route.destination.lower() in hint:
            return route
        combined = f"{route.origin} {route.destination} {route.name}".lower()
        if all(part in combined for part in hint.split() if len(part) > 3):
            return route
    for route in routes:
        if route.origin.lower() in hint or route.destination.lower() in hint:
            return route
    return routes.first()


def home(request):
    featured_routes = TransportRoute.objects.prefetch_related("segments").order_by("-risk_score")[:6]
    stats = {
        "routes": TransportRoute.objects.count(),
        "drivers": Driver.objects.count(),
        "incidents": IncidentReport.objects.count(),
        "high_risk": TransportRoute.objects.filter(status__in=["High Risk", "Avoid"]).count(),
    }
    all_map_data = build_all_routes_map_data()
    return render(request, "home.html", {
        "featured_routes": featured_routes,
        "stats": stats,
        "all_map_json": all_map_data,
    })


def dashboard(request):
    drivers_count = Driver.objects.count()
    routes_count = TransportRoute.objects.count()
    incidents_count = IncidentReport.objects.count()
    high_risk = TransportRoute.objects.filter(
        status__in=["High Risk", "Avoid"]
    ).order_by("-risk_score")[:6]
    safest = TransportRoute.objects.filter(status="Safe").order_by("risk_score")[:5]
    dangerous_segments = (
        RouteSegment.objects.filter(status__in=["High Risk", "Avoid", "Caution"])
        .select_related("route")
        .order_by("-risk_score")[:10]
    )
    latest_reports = IncidentReport.objects.select_related("route", "segment").order_by("-created_at")[:10]
    location_counts = (
        IncidentReport.objects.values("location_name")
        .annotate(c=Count("id"))
        .order_by("-c")[:8]
    )
    most_reported = [
        {"location": x["location_name"], "count": x["c"]}
        for x in location_counts
    ]
    all_map_data = build_all_routes_map_data()
    return render(
        request,
        "dashboard.html",
        {
            "drivers_count": drivers_count,
            "routes_count": routes_count,
            "incidents_count": incidents_count,
            "high_risk_routes": high_risk,
            "safest_routes": safest,
            "dangerous_segments": dangerous_segments,
            "latest_reports": latest_reports,
            "most_reported": most_reported,
            "all_map_json": all_map_data,
        },
    )


def live_map(request):
    all_map_data = build_all_routes_map_data()
    routes = TransportRoute.objects.order_by("-risk_score")
    recent_incidents = IncidentReport.objects.select_related("route", "segment").order_by("-created_at")[:15]
    return render(request, "live_map.html", {
        "all_map_json": all_map_data,
        "routes": routes,
        "recent_incidents": recent_incidents,
        "routes_count": routes.count(),
        "incidents_count": IncidentReport.objects.count(),
    })


def routes_list(request):
    routes = TransportRoute.objects.prefetch_related("segments").order_by("-risk_score")
    return render(request, "routes.html", {"routes": routes})


def route_detail(request, pk):
    route = get_object_or_404(
        TransportRoute.objects.prefetch_related(
            Prefetch("segments", queryset=RouteSegment.objects.order_by("order")),
            Prefetch("incidents", queryset=IncidentReport.objects.select_related("segment")),
        ),
        pk=pk,
    )
    risk = calculate_route_risk(route)
    reports = route.incidents.all().order_by("-created_at")[:20]
    map_data = build_route_map_data(route)
    waypoint_ladder = []
    segments = list(route.segments.order_by("order"))
    if segments:
        waypoint_ladder.append({"name": segments[0].from_location, "segment": None, "status": None})
        for seg in segments:
            seg_risk = next(
                (s for s in risk["segments"] if s["segment_id"] == seg.pk),
                None,
            )
            waypoint_ladder.append({
                "name": seg.to_location,
                "segment": seg,
                "risk": seg_risk,
                "status": seg.status,
                "risk_score": seg.risk_score,
            })
    return render(
        request,
        "route_detail.html",
        {
            "route": route,
            "risk": risk,
            "reports": reports,
            "map_data_json": map_data,
            "waypoint_ladder": waypoint_ladder,
        },
    )


@require_http_methods(["GET", "POST"])
def report_incident(request):
    submitted = False
    ai_result = None
    outgoing_alert = None
    submitted_report = None

    if request.method == "POST":
        form = IncidentReportForm(request.POST)
        if form.is_valid():
            report = form.save()
            ai_result, outgoing_alert = finalize_incident_report(report)
            submitted = True
            submitted_report = report
            seg_note = f" → section {report.segment.label}" if report.segment_id else ""
            messages.success(
                request,
                f"Incident reported on {report.route.name}{seg_note}. AI analysis complete.",
            )
            form = IncidentReportForm()
    else:
        initial = {}
        route_id = request.GET.get("route")
        if route_id:
            initial["route"] = route_id
        form = IncidentReportForm(initial=initial)

    recent = IncidentReport.objects.select_related("route", "segment").order_by("-created_at")[:8]
    return render(
        request,
        "report_incident.html",
        {
            "form": form,
            "recent_reports": recent,
            "submitted": submitted,
            "ai_result": ai_result,
            "outgoing_alert": outgoing_alert,
            "submitted_report": submitted_report,
        },
    )


@require_http_methods(["GET", "POST"])
def register_driver(request):
    if request.method == "POST":
        form = DriverRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Driver registered successfully. Karibu RouteWise TZ!")
            return redirect("register_driver")
    else:
        form = DriverRegistrationForm()
    drivers = Driver.objects.all().order_by("-created_at")[:20]
    return render(
        request,
        "register_driver.html",
        {"form": form, "drivers": drivers},
    )


@require_http_methods(["GET", "POST"])
def simulate_message(request):
    outgoing_alert = None
    ai_result = None
    submitted_report = None

    if request.method == "POST":
        form = SimulateMessageForm(request.POST)
        if form.is_valid():
            phone = form.cleaned_data["phone_number"]
            channel = form.cleaned_data["channel"]
            text = form.cleaned_data["message_text"]
            parsed = parse_incoming_message(text)
            if not parsed:
                messages.error(
                    request,
                    "Could not parse message. Use: TYPE#Location#Route",
                )
            else:
                route = _find_route_by_hint(parsed["route_hint"])
                if not route:
                    messages.error(request, "No matching route found.")
                else:
                    segment = find_closest_segment(route, parsed["location_name"])
                    severity = (
                        "High"
                        if parsed["incident_type"]
                        in ("Accident", "Flood", "Theft Hotspot")
                        else "Medium"
                    )
                    report = IncidentReport.objects.create(
                        route=route,
                        segment=segment,
                        reporter_name="SMS Reporter",
                        reporter_phone=phone,
                        incident_type=parsed["incident_type"],
                        location_name=parsed["location_name"],
                        description=f"Reported via {channel}: {text}",
                        severity=severity,
                    )
                    ai_result, outgoing_alert = finalize_incident_report(
                        report, notify_phone=phone, channel=channel
                    )
                    submitted_report = report
                    seg_label = report.segment.label if report.segment_id else "auto"
                    messages.success(
                        request,
                        f"Message parsed. Segment: {seg_label}. AI + alert sent.",
                    )
    else:
        form = SimulateMessageForm()

    return render(
        request,
        "simulate_message.html",
        {
            "form": form,
            "outgoing_alert": outgoing_alert,
            "ai_result": ai_result,
            "submitted_report": submitted_report,
        },
    )
