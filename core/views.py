import json
import logging

from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Prefetch, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from .forms import (
    DriverLoginForm, DriverRatingForm, DriverSignupForm,
    IncidentReportForm, SimulateMessageForm,
)
from .models import (
    AirtimeReward, ATSubscription, Driver, DriverRating,
    IncidentReport, RouteSegment, TransportRoute, USSDSession,
)
from .segment_utils import build_all_routes_map_data, build_route_map_data, find_closest_segment
from .services.at_service import at, send_incident_broadcast
from .services.incident_processing import finalize_incident_report
from .services.messaging import parse_incoming_message
from .services.risk_engine import calculate_route_risk

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────

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


def _get_driver(request):
    """Return the Driver linked to the logged-in user, or None."""
    if request.user.is_authenticated:
        return getattr(request.user, "driver_profile", None)
    return None


# ── Core pages ────────────────────────────────────────────────────

def home(request):
    featured_routes = TransportRoute.objects.prefetch_related("segments").order_by("-risk_score")[:6]
    stats = {
        "routes":    TransportRoute.objects.count(),
        "drivers":   Driver.objects.count(),
        "incidents": IncidentReport.objects.filter(approved=True).count(),
        "high_risk": TransportRoute.objects.filter(status__in=["High Risk", "Avoid"]).count(),
    }
    all_map_data = build_all_routes_map_data()
    return render(request, "home.html", {
        "featured_routes": featured_routes,
        "stats":           stats,
        "all_map_json":    all_map_data,
    })


def dashboard(request):
    driver = _get_driver(request)
    pending_count = IncidentReport.objects.filter(needs_approval=True).count()

    drivers_count   = Driver.objects.count()
    routes_count    = TransportRoute.objects.count()
    incidents_count = IncidentReport.objects.filter(approved=True).count()

    high_risk = TransportRoute.objects.filter(
        status__in=["High Risk", "Avoid"]
    ).order_by("-risk_score")[:6]
    safest = TransportRoute.objects.filter(status="Safe").order_by("risk_score")[:5]

    dangerous_segments = (
        RouteSegment.objects.filter(status__in=["High Risk", "Avoid", "Caution"])
        .select_related("route").order_by("-risk_score")[:10]
    )
    latest_reports = (
        IncidentReport.objects
        .filter(approved=True)
        .select_related("route", "segment", "reporter_driver")
        .order_by("-created_at")[:10]
    )
    pending_reports = []
    if driver and driver.is_trusted:
        pending_reports = (
            IncidentReport.objects
            .filter(needs_approval=True)
            .select_related("route", "segment")
            .order_by("-created_at")[:10]
        )

    location_counts = (
        IncidentReport.objects.filter(approved=True)
        .values("location_name").annotate(c=Count("id")).order_by("-c")[:8]
    )
    most_reported = [{"location": x["location_name"], "count": x["c"]} for x in location_counts]
    all_map_data  = build_all_routes_map_data()

    return render(request, "dashboard.html", {
        "drivers_count":    drivers_count,
        "routes_count":     routes_count,
        "incidents_count":  incidents_count,
        "pending_count":    pending_count,
        "high_risk_routes": high_risk,
        "safest_routes":    safest,
        "dangerous_segments": dangerous_segments,
        "latest_reports":   latest_reports,
        "pending_reports":  pending_reports,
        "most_reported":    most_reported,
        "all_map_json":     all_map_data,
        "current_driver":   driver,
    })


def live_map(request):
    all_map_data   = build_all_routes_map_data()
    routes         = TransportRoute.objects.order_by("-risk_score")
    recent_incidents = (
        IncidentReport.objects.filter(approved=True)
        .select_related("route", "segment").order_by("-created_at")[:15]
    )
    return render(request, "live_map.html", {
        "all_map_json":    all_map_data,
        "routes":          routes,
        "recent_incidents": recent_incidents,
        "routes_count":    routes.count(),
        "incidents_count": IncidentReport.objects.filter(approved=True).count(),
    })


def routes_list(request):
    routes = TransportRoute.objects.prefetch_related("segments").order_by("-risk_score")
    return render(request, "routes.html", {"routes": routes})


def route_detail(request, pk):
    route = get_object_or_404(
        TransportRoute.objects.prefetch_related(
            Prefetch("segments", queryset=RouteSegment.objects.order_by("order")),
            Prefetch("incidents", queryset=IncidentReport.objects.filter(approved=True).select_related("segment", "reporter_driver")),
        ),
        pk=pk,
    )
    risk    = calculate_route_risk(route)
    reports = route.incidents.filter(approved=True).order_by("-created_at")[:20]
    map_data = build_route_map_data(route)

    waypoint_ladder = []
    segments = list(route.segments.order_by("order"))
    if segments:
        waypoint_ladder.append({"name": segments[0].from_location, "segment": None, "status": None})
        for seg in segments:
            seg_risk = next((s for s in risk["segments"] if s["segment_id"] == seg.pk), None)
            waypoint_ladder.append({
                "name":       seg.to_location,
                "segment":    seg,
                "risk":       seg_risk,
                "status":     seg.status,
                "risk_score": seg.risk_score,
            })
    return render(request, "route_detail.html", {
        "route":           route,
        "risk":            risk,
        "reports":         reports,
        "map_data_json":   map_data,
        "waypoint_ladder": waypoint_ladder,
    })


# ── Incident reporting ────────────────────────────────────────────

@require_http_methods(["GET", "POST"])
def report_incident(request):
    driver         = _get_driver(request)
    submitted      = False
    ai_result      = None
    outgoing_alert = None
    submitted_report = None

    if request.method == "POST":
        form = IncidentReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)

            if driver:
                # Logged-in driver → auto-approved, pre-fill info
                report.reporter_driver  = driver
                report.reporter_name    = driver.full_name
                report.reporter_phone   = driver.phone_number
                report.approved         = True
                report.needs_approval   = False
            else:
                # Anonymous → needs approval from a trusted driver
                report.approved       = False
                report.needs_approval = True

            report.save()

            if report.approved:
                ai_result, outgoing_alert = finalize_incident_report(report)
                msg = f"Incident reported on {report.route.name}. AI analysis complete."
            else:
                msg = (
                    "Your report has been submitted and is pending approval "
                    "from a trusted driver. Thank you for keeping roads safe!"
                )

            submitted        = True
            submitted_report = report
            messages.success(request, msg)
            form = IncidentReportForm()
    else:
        initial  = {}
        route_id = request.GET.get("route")
        if route_id:
            initial["route"] = route_id
        if driver:
            initial["reporter_name"]  = driver.full_name
            initial["reporter_phone"] = driver.phone_number
        form = IncidentReportForm(initial=initial)

    recent = (
        IncidentReport.objects.filter(approved=True)
        .select_related("route", "segment").order_by("-created_at")[:8]
    )
    return render(request, "report_incident.html", {
        "form":             form,
        "recent_reports":   recent,
        "submitted":        submitted,
        "ai_result":        ai_result,
        "outgoing_alert":   outgoing_alert,
        "submitted_report": submitted_report,
        "current_driver":   driver,
    })


# ── Approval workflow ─────────────────────────────────────────────

@login_required
@require_POST
def approve_incident(request, pk):
    driver = _get_driver(request)
    if not driver or not driver.is_trusted:
        messages.error(request, "Only trusted drivers (rating ≥ 3.5★) can approve reports.")
        return redirect("dashboard")

    report = get_object_or_404(IncidentReport, pk=pk, needs_approval=True)
    report.approved       = True
    report.needs_approval = False
    report.approved_by    = driver
    report.save(update_fields=["approved", "needs_approval", "approved_by"])

    # Now run the full AI + broadcast pipeline
    finalize_incident_report(report)
    messages.success(request, f"Report approved and published: {report.incident_type} @ {report.location_name}")
    return redirect("dashboard")


@login_required
@require_POST
def reject_incident(request, pk):
    driver = _get_driver(request)
    if not driver or not driver.is_trusted:
        messages.error(request, "Only trusted drivers can reject reports.")
        return redirect("dashboard")

    report = get_object_or_404(IncidentReport, pk=pk, needs_approval=True)
    reason = request.POST.get("reason", "Not accurate or insufficient detail").strip()
    report.approved          = False
    report.needs_approval    = False
    report.rejection_reason  = reason
    report.save(update_fields=["approved", "needs_approval", "rejection_reason"])

    messages.info(request, f"Report rejected: {report.incident_type} @ {report.location_name}")
    return redirect("dashboard")


# ── Driver auth ───────────────────────────────────────────────────

def driver_signup(request):
    if request.user.is_authenticated:
        return redirect("driver_profile")

    if request.method == "POST":
        form = DriverSignupForm(request.POST)
        if form.is_valid():
            driver = form.save()
            login(request, driver.user)
            messages.success(
                request,
                f"Welcome to RouteWise TZ, {driver.full_name}! "
                f"You start with a 5★ trust score. Drive safe and keep it up!"
            )
            return redirect("driver_profile")
    else:
        form = DriverSignupForm()

    return render(request, "driver_signup.html", {"form": form})


def driver_login_view(request):
    if request.user.is_authenticated:
        return redirect("driver_profile")

    if request.method == "POST":
        form = DriverLoginForm(request.POST, request=request)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            driver = getattr(user, "driver_profile", None)
            name = driver.full_name if driver else user.username
            messages.success(request, f"Welcome back, {name}!")
            nxt = request.GET.get("next") or "driver_profile"
            return redirect(nxt)
    else:
        form = DriverLoginForm(request=request)

    return render(request, "driver_login.html", {"form": form})


def driver_logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out. Drive safe!")
    return redirect("home")


# ── Driver profile & directory ────────────────────────────────────

@login_required
def driver_profile(request):
    driver = _get_driver(request)
    if not driver:
        messages.error(request, "No driver profile linked to your account.")
        return redirect("home")

    my_reports   = driver.reported_incidents.select_related("route").order_by("-created_at")[:15]
    my_ratings   = driver.received_ratings.select_related("rater").order_by("-created_at")[:10]
    pending_mine = driver.reported_incidents.filter(needs_approval=True).count()

    pending_to_review = []
    if driver.is_trusted:
        pending_to_review = (
            IncidentReport.objects.filter(needs_approval=True)
            .select_related("route", "segment").order_by("-created_at")[:8]
        )

    return render(request, "driver_profile.html", {
        "driver":            driver,
        "my_reports":        my_reports,
        "my_ratings":        my_ratings,
        "pending_mine":      pending_mine,
        "pending_to_review": pending_to_review,
    })


def driver_directory(request):
    # Include phone-only drivers registered via USSD (user__isnull=True), not just web accounts.
    drivers = (
        Driver.objects
        .annotate(report_count=Count("reported_incidents", filter=Q(reported_incidents__approved=True)))
        .order_by("-trust_score", "-created_at")
    )
    return render(request, "driver_directory.html", {
        "drivers":       drivers,
        "current_driver": _get_driver(request),
    })


def driver_public_profile(request, pk):
    viewed_driver  = get_object_or_404(Driver, pk=pk)
    current_driver = _get_driver(request)
    existing_rating = None
    if current_driver and current_driver != viewed_driver:
        existing_rating = DriverRating.objects.filter(
            rater=current_driver, rated=viewed_driver
        ).first()

    reports = (
        viewed_driver.reported_incidents
        .filter(approved=True)
        .select_related("route")
        .order_by("-created_at")[:10]
    )
    ratings = viewed_driver.received_ratings.select_related("rater").order_by("-created_at")[:8]
    rating_form = DriverRatingForm(instance=existing_rating)

    return render(request, "driver_public_profile.html", {
        "viewed_driver":   viewed_driver,
        "current_driver":  current_driver,
        "existing_rating": existing_rating,
        "reports":         reports,
        "ratings":         ratings,
        "rating_form":     rating_form,
    })


@login_required
@require_POST
def rate_driver(request, pk):
    rated_driver   = get_object_or_404(Driver, pk=pk)
    current_driver = _get_driver(request)

    if not current_driver:
        messages.error(request, "Create a driver profile to rate others.")
        return redirect("driver_public_profile", pk=pk)
    if current_driver == rated_driver:
        messages.error(request, "You cannot rate yourself.")
        return redirect("driver_public_profile", pk=pk)

    score   = int(request.POST.get("score", 3))
    comment = request.POST.get("comment", "").strip()

    if not 1 <= score <= 5:
        messages.error(request, "Score must be between 1 and 5.")
        return redirect("driver_public_profile", pk=pk)

    DriverRating.objects.update_or_create(
        rater=current_driver,
        rated=rated_driver,
        defaults={"score": score, "comment": comment},
    )
    rated_driver.recalculate_trust()

    messages.success(
        request,
        f"You rated {rated_driver.full_name} {score}★. "
        f"New trust score: {rated_driver.trust_score:.1f}/5.0"
    )
    return redirect("driver_public_profile", pk=pk)


# ── Legacy driver registration (redirects to signup) ─────────────

def register_driver(request):
    return redirect("driver_signup")


# ── Simulate message (SMS demo) ───────────────────────────────────

@require_http_methods(["GET", "POST"])
def simulate_message(request):
    outgoing_alert   = None
    ai_result        = None
    submitted_report = None

    if request.method == "POST":
        form = SimulateMessageForm(request.POST)
        if form.is_valid():
            phone   = form.cleaned_data["phone_number"]
            channel = form.cleaned_data["channel"]
            text    = form.cleaned_data["message_text"]
            parsed  = parse_incoming_message(text)
            if not parsed:
                messages.error(request, "Could not parse message. Use: TYPE#Location#Route")
            else:
                route = _find_route_by_hint(parsed["route_hint"])
                if not route:
                    messages.error(request, "No matching route found.")
                else:
                    segment  = find_closest_segment(route, parsed["location_name"])
                    severity = (
                        "High" if parsed["incident_type"] in ("Accident", "Flood", "Theft Hotspot")
                        else "Medium"
                    )
                    report = IncidentReport.objects.create(
                        route=route, segment=segment,
                        reporter_name="SMS Reporter", reporter_phone=phone,
                        incident_type=parsed["incident_type"],
                        location_name=parsed["location_name"],
                        description=f"Reported via {channel}: {text}",
                        severity=severity,
                        approved=True, needs_approval=False,
                    )
                    ai_result, outgoing_alert = finalize_incident_report(
                        report, notify_phone=phone, channel=channel
                    )
                    submitted_report = report
                    seg_label = report.segment.label if report.segment_id else "auto"
                    messages.success(request, f"Message parsed. Segment: {seg_label}. AI + alert sent.")
    else:
        form = SimulateMessageForm()

    return render(request, "simulate_message.html", {
        "form":             form,
        "outgoing_alert":   outgoing_alert,
        "ai_result":        ai_result,
        "submitted_report": submitted_report,
    })


# ══════════════════════════════════════════════════════════════════
# AFRICA'S TALKING WEBHOOKS
# ══════════════════════════════════════════════════════════════════

@csrf_exempt
@require_POST
def at_ussd_webhook(request):
    session_id   = request.POST.get("sessionId", "")
    service_code = request.POST.get("serviceCode", "")
    phone_number = request.POST.get("phoneNumber", "")
    text         = request.POST.get("text", "")
    network_code = request.POST.get("networkCode", "")
    logger.info("[USSD] session=%s phone=%s text=%r", session_id, phone_number, text)
    try:
        response_text = at.handle_ussd(
            session_id=session_id, service_code=service_code,
            phone_number=phone_number, text=text, network_code=network_code,
        )
    except Exception as exc:
        logger.error("[USSD] Handler error: %s", exc)
        response_text = "END Sorry, a system error occurred. Please try again."
    return HttpResponse(response_text, content_type="text/plain")


@csrf_exempt
@require_POST
def at_sms_webhook(request):
    from_number = request.POST.get("from", "")
    to_number   = request.POST.get("to", "")
    text        = request.POST.get("text", "")
    message_id  = request.POST.get("id", "")
    logger.info("[SMS-IN] from=%s to=%s text=%r", from_number, to_number, text)
    try:
        result = at.handle_incoming_sms(
            from_number=from_number, text=text,
            to_number=to_number, message_id=message_id,
        )
        return JsonResponse({"status": "ok", "result": result.get("status", "processed")})
    except Exception as exc:
        logger.error("[SMS-IN] Error: %s", exc)
        return JsonResponse({"status": "error", "detail": str(exc)}, status=500)


@csrf_exempt
def at_voice_webhook(request):
    session_id = request.POST.get("sessionId", "")
    caller     = request.POST.get("callerNumber", request.POST.get("from", ""))
    logger.info("[VOICE] session=%s caller=%s", session_id, caller)
    recent = IncidentReport.objects.filter(
        severity__in=("High", "Critical"), approved=True
    ).order_by("-created_at").first()
    if recent:
        xml = at.build_voice_response(
            incident_type=recent.incident_type,
            location=recent.location_name,
            route_name=recent.route.name,
            delay=recent.ai_estimated_delay_minutes or 30,
        )
    else:
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?><Response>'
            "<Say>Welcome to RouteWise Tanzania. All routes are currently clear. Drive safely.</Say>"
            "<Hangup/></Response>"
        )
    return HttpResponse(xml, content_type="application/xml")


@csrf_exempt
@require_POST
def at_delivery_report(request):
    logger.info("[AT Delivery] id=%s status=%s phone=%s",
                request.POST.get("id"), request.POST.get("status"),
                request.POST.get("phoneNumber"))
    return HttpResponse("OK")


# ══════════════════════════════════════════════════════════════════
# AT SERVICES DASHBOARD
# ══════════════════════════════════════════════════════════════════

def at_services(request):
    from django.conf import settings as dj_settings
    balance    = at.get_balance()
    routes     = TransportRoute.objects.order_by("-risk_score")
    subs_count = ATSubscription.objects.filter(is_active=True).count()
    rewards    = AirtimeReward.objects.order_by("-created_at")[:10]
    sessions   = USSDSession.objects.order_by("-created_at")[:10]
    recent_inc = IncidentReport.objects.filter(approved=True).select_related("route").order_by("-created_at")[:5]
    return render(request, "at_services.html", {
        "balance":     balance,
        "at_mode":     at.mode,
        "at_live":     at.is_live,
        "routes":      routes,
        "subs_count":  subs_count,
        "rewards":     rewards,
        "sessions":    sessions,
        "recent_inc":  recent_inc,
        "at_username": getattr(dj_settings, "AT_USERNAME", ""),
    })


@require_POST
def at_test_sms(request):
    phone   = request.POST.get("phone", "").strip()
    message = request.POST.get("message", "RouteWise TZ test. Hello from Tanzania!").strip()
    if not phone:
        messages.error(request, "Phone number is required.")
        return redirect("at_services")
    result = at.send_sms(phone, message)
    if result["status"] == "success":
        messages.success(request, f"SMS sent to {phone} via Africa's Talking.")
    elif result["status"] == "simulated":
        messages.info(request, f"Simulated SMS logged → {phone}. Check server console.")
    else:
        messages.error(request, f"SMS failed: {result.get('error', 'unknown')}")
    return redirect("at_services")


@require_POST
def at_test_airtime(request):
    phone    = request.POST.get("phone", "").strip()
    amount   = float(request.POST.get("amount", 100))
    currency = request.POST.get("currency", "TZS")
    if not phone:
        messages.error(request, "Phone number is required.")
        return redirect("at_services")
    result = at.send_airtime(phone, amount, currency)
    if result["status"] == "success":
        messages.success(request, f"Airtime {currency} {amount} sent to {phone}.")
    elif result["status"] == "simulated":
        messages.info(request, f"Airtime simulated → {phone} {currency} {amount}.")
    else:
        messages.error(request, f"Airtime failed: {result.get('error', 'unknown')}")
    return redirect("at_services")


@require_POST
def at_broadcast_route(request):
    route_id   = request.POST.get("route_id")
    custom_msg = request.POST.get("message", "").strip()
    route      = get_object_or_404(TransportRoute, pk=route_id)
    if not custom_msg:
        custom_msg = (
            f"RouteWise TZ: {route.name} is {route.status}. "
            f"Risk: {route.risk_score}/100. Stay alert."
        )
    result    = send_incident_broadcast(route, custom_msg)
    sms_count = result.get("sms_recipients", 0)
    wa_count  = result.get("whatsapp_recipients", 0)
    messages.success(
        request,
        f"Broadcast sent: {sms_count} SMS + {wa_count} WhatsApp on {route.name}."
    )
    return redirect("at_services")
