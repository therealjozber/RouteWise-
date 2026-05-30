"""Route segment matching and map helpers."""

from .locations import get_coords, location_matches
from .models import RouteSegment


def find_closest_segment(route, location_name: str):
    """
    Find the segment most likely affected by an incident at location_name.
    Matches against segment from/to locations and order.
    """
    if not location_name or not route:
        return None

    segments = list(route.segments.order_by("order"))
    if not segments:
        return None

    loc = location_name.strip().lower()
    best = None
    best_score = 0

    for seg in segments:
        score = 0
        for place in (seg.from_location, seg.to_location):
            p = place.strip().lower()
            if loc == p:
                score = 100
            elif loc in p or p in loc:
                score = max(score, 80)
            elif any(word in p for word in loc.split() if len(word) > 3):
                score = max(score, 50)
        if score > best_score:
            best_score = score
            best = seg

    if best_score >= 50:
        return best

    coords = get_coords(location_name)
    if not coords:
        return segments[0]

    nearest = None
    min_dist = float("inf")
    for seg in segments:
        for place in (seg.from_location, seg.to_location):
            c = get_coords(place)
            if c:
                dist = (coords[0] - c[0]) ** 2 + (coords[1] - c[1]) ** 2
                if dist < min_dist:
                    min_dist = dist
                    nearest = seg
    return nearest or segments[0]


def reports_for_segment(segment):
    """Approved incidents tied to this segment or matching its locations."""
    from .models import IncidentReport

    qs = IncidentReport.objects.filter(route=segment.route, approved=True)
    tied = qs.filter(segment=segment)
    loose = qs.filter(segment__isnull=True)
    matched = []
    for r in loose:
        if location_matches(r.location_name, segment.from_location) or location_matches(
            r.location_name, segment.to_location
        ):
            matched.append(r.pk)
    return qs.filter(pk__in=list(tied.values_list("pk", flat=True)) + matched).distinct()


def build_route_map_data(route):
    """Waypoints, colored segment polylines, and incident markers for a single route."""
    segments = list(route.segments.order_by("order"))
    waypoints = []
    colored_segments = []
    seen = set()

    if segments:
        for seg in segments:
            from_loc = seg.from_location
            to_loc = seg.to_location
            from_key = from_loc.strip().lower()
            to_key = to_loc.strip().lower()

            from_coords = get_coords(from_loc)
            to_coords = get_coords(to_loc)

            if from_coords and from_key not in seen:
                seen.add(from_key)
                waypoints.append({
                    "name": from_loc,
                    "lat": from_coords[0],
                    "lng": from_coords[1],
                    "status": None,
                })

            if to_coords and to_key not in seen:
                seen.add(to_key)
                waypoints.append({
                    "name": to_loc,
                    "lat": to_coords[0],
                    "lng": to_coords[1],
                    "status": seg.status,
                })

            # Colored segment polyline
            if from_coords and to_coords:
                colored_segments.append({
                    "from": from_loc,
                    "to": to_loc,
                    "coords": [
                        [from_coords[0], from_coords[1]],
                        [to_coords[0], to_coords[1]],
                    ],
                    "status": seg.status,
                    "risk_score": seg.risk_score,
                    "distance_km": seg.distance_km,
                    "estimated_time": seg.estimated_time,
                })
    else:
        for loc in (route.origin, route.destination):
            c = get_coords(loc)
            if c:
                waypoints.append({"name": loc, "lat": c[0], "lng": c[1], "status": None})

    incident_markers = []
    for r in route.incidents.filter(approved=True)[:30]:
        coords = get_coords(r.location_name)
        if not coords and r.segment:
            coords = get_coords(r.segment.from_location)
        if coords:
            incident_markers.append({
                "lat": coords[0],
                "lng": coords[1],
                "type": r.incident_type,
                "location": r.location_name,
                "severity": r.severity,
                "segment": r.segment.label if r.segment else None,
                "description": (r.description or "")[:120],
            })

    path = [[w["lat"], w["lng"]] for w in waypoints]
    return {
        "waypoints": waypoints,
        "path": path,
        "segments": colored_segments,
        "incidents": incident_markers,
    }


def build_all_routes_map_data():
    """Build combined map data for all routes — used on dashboard and live map."""
    from .models import TransportRoute

    routes_data = []
    all_routes = TransportRoute.objects.prefetch_related("segments", "incidents").all()

    for route in all_routes:
        segs = list(route.segments.order_by("order"))
        colored_segments = []
        for seg in segs:
            fc = get_coords(seg.from_location)
            tc = get_coords(seg.to_location)
            if fc and tc:
                colored_segments.append({
                    "from": seg.from_location,
                    "to": seg.to_location,
                    "coords": [[fc[0], fc[1]], [tc[0], tc[1]]],
                    "status": seg.status,
                    "risk_score": seg.risk_score,
                })

        incidents = []
        for r in route.incidents.filter(approved=True)[:15]:
            coords = get_coords(r.location_name)
            if not coords and r.segment:
                coords = get_coords(r.segment.from_location)
            if coords:
                incidents.append({
                    "lat": coords[0],
                    "lng": coords[1],
                    "type": r.incident_type,
                    "severity": r.severity,
                    "location": r.location_name,
                    "route": route.name,
                    "route_id": route.pk,
                })

        if colored_segments:
            routes_data.append({
                "id": route.pk,
                "name": route.name,
                "status": route.status,
                "risk_score": route.risk_score,
                "segments": colored_segments,
                "incidents": incidents,
            })

    return {"routes": routes_data}
