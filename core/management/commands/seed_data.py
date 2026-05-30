from django.core.management.base import BaseCommand
from core.models import Driver, TransportRoute, RouteSegment, IncidentReport
from core.segment_utils import find_closest_segment
from core.services.risk_engine import apply_risk_to_route


ROUTES = [
    ("Dar es Salaam → Morogoro", "Dar es Salaam", "Morogoro", 192, "3–4 hours"),
    ("Dar es Salaam → Dodoma", "Dar es Salaam", "Dodoma", 451, "7–8 hours"),
    ("Dar es Salaam → Arusha", "Dar es Salaam", "Arusha", 636, "10–11 hours"),
    ("Dar es Salaam → Mwanza", "Dar es Salaam", "Mwanza", 1145, "14–16 hours"),
    ("Dar es Salaam → Mbeya", "Dar es Salaam", "Mbeya", 822, "12–14 hours"),
    ("Dar es Salaam → Tanga", "Dar es Salaam", "Tanga", 354, "5–6 hours"),
    ("Morogoro → Dodoma", "Morogoro", "Dodoma", 262, "4–5 hours"),
    ("Dodoma → Mwanza", "Dodoma", "Mwanza", 705, "9–10 hours"),
]

# (from, to, distance_km, estimated_time) per segment in order
ROUTE_SEGMENTS = {
    "Dar es Salaam → Morogoro": [
        ("Dar es Salaam", "Chalinze", 40, "45 min"),
        ("Chalinze", "Morogoro", 152, "2.5 hrs"),
    ],
    "Dar es Salaam → Dodoma": [
        ("Dar es Salaam", "Chalinze", 40, "45 min"),
        ("Chalinze", "Morogoro", 110, "1.5 hrs"),
        ("Morogoro", "Gairo", 80, "1 hr"),
        ("Gairo", "Dodoma", 221, "3 hrs"),
    ],
    "Dar es Salaam → Arusha": [
        ("Dar es Salaam", "Chalinze", 40, "45 min"),
        ("Chalinze", "Segera", 90, "1.5 hrs"),
        ("Segera", "Same", 120, "2 hrs"),
        ("Same", "Moshi", 80, "1.5 hrs"),
        ("Moshi", "Arusha", 86, "1.5 hrs"),
    ],
    "Dar es Salaam → Mwanza": [
        ("Dar es Salaam", "Chalinze", 40, "45 min"),
        ("Chalinze", "Morogoro", 110, "1.5 hrs"),
        ("Morogoro", "Dodoma", 180, "3 hrs"),
        ("Dodoma", "Singida", 190, "3 hrs"),
        ("Singida", "Nzega", 160, "2.5 hrs"),
        ("Nzega", "Mwanza", 265, "4 hrs"),
    ],
    "Dar es Salaam → Mbeya": [
        ("Dar es Salaam", "Morogoro", 192, "3 hrs"),
        ("Morogoro", "Mikumi", 107, "1.5 hrs"),
        ("Mikumi", "Iringa", 198, "3 hrs"),
        ("Iringa", "Makambako", 85, "1.5 hrs"),
        ("Makambako", "Mbeya", 240, "4 hrs"),
    ],
    "Dar es Salaam → Tanga": [
        ("Dar es Salaam", "Bagamoyo", 65, "1 hr"),
        ("Bagamoyo", "Msata", 45, "45 min"),
        ("Msata", "Tanga", 244, "3.5 hrs"),
    ],
    "Morogoro → Dodoma": [
        ("Morogoro", "Kilosa", 80, "1.5 hrs"),
        ("Kilosa", "Gairo", 70, "1 hr"),
        ("Gairo", "Dodoma", 112, "2 hrs"),
    ],
    "Dodoma → Mwanza": [
        ("Dodoma", "Singida", 190, "3 hrs"),
        ("Singida", "Nzega", 160, "2.5 hrs"),
        ("Nzega", "Mwanza", 355, "5 hrs"),
    ],
}

DRIVERS = [
    ("James Mwakasege", "+255712345001", "Truck", "Freight", "Dar es Salaam → Morogoro"),
    ("Amina Hassan", "+255713456002", "Bus", "Passenger", "Dar es Salaam → Dodoma"),
    ("Peter Kimaro", "+255714567003", "Van", "Courier", "Dar es Salaam → Arusha"),
    ("Fatuma Saidi", "+255715678004", "Boda", "Courier", "Dar es Salaam → Tanga"),
    ("Robert Ngonyani", "+255716789005", "Truck", "Agriculture", "Morogoro → Dodoma"),
    ("Grace Mushi", "+255717890006", "Bus", "Passenger", "Dar es Salaam → Mwanza"),
]

INCIDENTS = [
    ("Dar es Salaam → Morogoro", "Accident", "Chalinze", "High", "Multi-vehicle collision near weighbridge"),
    ("Dar es Salaam → Morogoro", "Traffic Jam", "Chalinze", "Medium", "Heavy trucks queueing"),
    ("Dar es Salaam → Dodoma", "Accident", "Chalinze", "High", "Jack-knifed truck blocking lane"),
    ("Dar es Salaam → Dodoma", "Bad Road", "Gairo", "Medium", "Potholes after rains"),
    ("Morogoro → Dodoma", "Flood", "Kilosa", "Critical", "Road partially submerged"),
    ("Dar es Salaam → Arusha", "Police Checkpoint", "Moshi", "Low", "Routine inspection"),
    ("Dar es Salaam → Mwanza", "Fuel Shortage", "Singida", "High", "Limited diesel at stations"),
    ("Dar es Salaam → Mbeya", "Bad Road", "Makambako", "Medium", "Gravel section rough"),
    ("Dodoma → Mwanza", "Theft Hotspot", "Nzega", "High", "Cargo theft reports"),
    ("Dar es Salaam → Tanga", "Road Block", "Msata", "Low", "Temporary maintenance"),
    ("Dar es Salaam → Morogoro", "Vehicle Breakdown", "Morogoro", "Low", "Broken down lorry"),
]


class Command(BaseCommand):
    help = "Seed routes with segments, drivers, and incident reports"

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Delete existing data first")

    def handle(self, *args, **options):
        if options["clear"]:
            TransportRoute.objects.all().delete()
            Driver.objects.all().delete()
            self.stdout.write("Cleared existing data.")

        route_map = {}
        for name, origin, dest, dist, est in ROUTES:
            route, _ = TransportRoute.objects.get_or_create(
                name=name,
                defaults={
                    "origin": origin,
                    "destination": dest,
                    "distance_km": dist,
                    "estimated_time": est,
                    "risk_score": 0,
                    "status": "Safe",
                    "description": f"Multi-segment corridor: {origin} to {dest} via key towns.",
                },
            )
            route_map[name] = route

            RouteSegment.objects.filter(route=route).delete()
            seg_defs = ROUTE_SEGMENTS.get(name, [])
            for i, (f, t, d_km, est_seg) in enumerate(seg_defs, start=1):
                RouteSegment.objects.create(
                    route=route,
                    from_location=f,
                    to_location=t,
                    order=i,
                    distance_km=d_km,
                    estimated_time=est_seg,
                    notes=f"Section {i}: {f} to {t}",
                )

        for full_name, phone, vehicle, transport, main_route in DRIVERS:
            Driver.objects.get_or_create(
                phone_number=phone,
                defaults={
                    "full_name": full_name,
                    "vehicle_type": vehicle,
                    "transport_type": transport,
                    "main_route": main_route,
                },
            )

        for route_name, itype, loc, sev, desc in INCIDENTS:
            route = route_map.get(route_name)
            if not route:
                continue
            segment = find_closest_segment(route, loc)
            IncidentReport.objects.get_or_create(
                route=route,
                location_name=loc,
                incident_type=itype,
                defaults={
                    "segment": segment,
                    "reporter_name": "Community Reporter",
                    "reporter_phone": "+255700000000",
                    "description": desc,
                    "severity": sev,
                    "verified_count": 2 if sev in ("High", "Critical") else 0,
                },
            )

        for route in TransportRoute.objects.all():
            apply_risk_to_route(route)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {TransportRoute.objects.count()} routes, "
                f"{RouteSegment.objects.count()} segments, "
                f"{Driver.objects.count()} drivers, "
                f"{IncidentReport.objects.count()} incidents."
            )
        )
