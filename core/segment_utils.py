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
    """Incidents tied to this segment or matching its locations."""
    from .models import IncidentReport

    qs = IncidentReport.objects.filter(route=segment.route)
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
    """Waypoints along segments, polyline path, and incident markers."""
    segments = route.segments.order_by("order")
    waypoints = []
    seen = set()

    if segments.exists():
        seg_list = list(segments)
        for i, seg in enumerate(seg_list):
            for j, loc in enumerate((seg.from_location, seg.to_location)):
                key = loc.strip().lower()
                if key not in seen:
                    seen.add(key)
                    c = get_coords(loc)
                    if c:
                        st = None
                        if loc == seg.to_location:
                            st = seg.status
                        waypoints.append(
                            {
                                "name": loc,
                                "lat": c[0],
                                "lng": c[1],
                                "status": st,
                            }
                        )
    else:
        for loc in (route.origin, route.destination):
            c = get_coords(loc)
            if c:
                waypoints.append({"name": loc, "lat": c[0], "lng": c[1], "status": None})

    incident_markers = []
    for r in route.incidents.all()[:30]:
        coords = get_coords(r.location_name)
        if coords:
            incident_markers.append(
                {
                    "lat": coords[0],
                    "lng": coords[1],
                    "type": r.incident_type,
                    "location": r.location_name,
                    "severity": r.severity,
                    "segment": r.segment.label if r.segment else None,
                }
            )

    path = [[w["lat"], w["lng"]] for w in waypoints]
    return {
        "waypoints": waypoints,
        "path": path,
        "incidents": incident_markers,
    }
