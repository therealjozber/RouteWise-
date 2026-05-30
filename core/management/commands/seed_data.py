from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from core.models import Driver, DriverRating, TransportRoute, RouteSegment, IncidentReport
from core.segment_utils import find_closest_segment
from core.services.risk_engine import apply_risk_to_route


# ── Driver accounts (username, password, full_name) ───────────────
# All non-admin passwords follow pattern: RouteWise + 2024!
DRIVER_ACCOUNTS = [
    ("jmwakasege",  "RouteWise2024!", "James Mwakasege"),
    ("ahassan",     "RouteWise2024!", "Amina Hassan"),
    ("pkimaro",     "RouteWise2024!", "Peter Kimaro"),
    ("fsaidi",      "RouteWise2024!", "Fatuma Saidi"),
    ("rngonyani",   "RouteWise2024!", "Robert Ngonyani"),
    ("gmushi",      "RouteWise2024!", "Grace Mushi"),
    ("sjuma",       "RouteWise2024!", "Salim Juma"),
    ("nkweka",      "RouteWise2024!", "Neema Kweka"),
    ("homari",      "RouteWise2024!", "Hassan Omari"),
    ("zmfinanga",   "RouteWise2024!", "Zawadi Mfinanga"),
    ("elyimo",      "RouteWise2024!", "Emmanuel Lyimo"),
    ("rmassawe",    "RouteWise2024!", "Rehema Massawe"),
]

# Peer ratings between drivers (rater_name, rated_name, score, comment)
DRIVER_RATINGS = [
    ("Amina Hassan",    "James Mwakasege", 5, "Very accurate accident reports near Chalinze"),
    ("Peter Kimaro",    "James Mwakasege", 4, "Reliable, always reports with exact location"),
    ("Grace Mushi",     "James Mwakasege", 5, "Best reporter on the Morogoro corridor"),
    ("James Mwakasege", "Amina Hassan",    4, "Good reports, sometimes delayed"),
    ("Robert Ngonyani", "Amina Hassan",    5, "Excellent flood reports near Kilosa"),
    ("James Mwakasege", "Peter Kimaro",    5, "Top driver, accurate Arusha route info"),
    ("Amina Hassan",    "Peter Kimaro",    4, "Helpful checkpoint reports"),
    ("Peter Kimaro",    "Fatuma Saidi",    3, "Reports are okay but need more detail"),
    ("Grace Mushi",     "Salim Juma",      5, "Excellent reports on southern corridor"),
    ("Salim Juma",      "Grace Mushi",     4, "Consistent and reliable"),
    ("Hassan Omari",    "Robert Ngonyani", 5, "Best agriculture route reporter"),
    ("Neema Kweka",     "Emmanuel Lyimo",  4, "Good border crossing updates"),
]


ROUTES = [
    ("Dar es Salaam → Morogoro", "Dar es Salaam", "Morogoro", 192, "3–4 hours"),
    ("Dar es Salaam → Dodoma", "Dar es Salaam", "Dodoma", 451, "7–8 hours"),
    ("Dar es Salaam → Arusha", "Dar es Salaam", "Arusha", 636, "10–11 hours"),
    ("Dar es Salaam → Mwanza", "Dar es Salaam", "Mwanza", 1145, "14–16 hours"),
    ("Dar es Salaam → Mbeya", "Dar es Salaam", "Mbeya", 822, "12–14 hours"),
    ("Dar es Salaam → Tanga", "Dar es Salaam", "Tanga", 354, "5–6 hours"),
    ("Morogoro → Dodoma", "Morogoro", "Dodoma", 262, "4–5 hours"),
    ("Dodoma → Mwanza", "Dodoma", "Mwanza", 705, "9–10 hours"),
    ("Arusha → Namanga Border", "Arusha", "Namanga", 107, "1.5–2 hours"),
    ("Mbeya → Tunduma Border", "Mbeya", "Tunduma", 100, "1.5–2 hours"),
    ("Dar es Salaam → Lindi", "Dar es Salaam", "Lindi", 580, "9–10 hours"),
    ("Dodoma → Tabora", "Dodoma", "Tabora", 340, "5–6 hours"),
    ("Morogoro → Iringa", "Morogoro", "Iringa", 305, "5–6 hours"),
]

ROUTE_SEGMENTS = {
    "Dar es Salaam → Morogoro": [
        ("Dar es Salaam", "Kibaha", 35, "35 min"),
        ("Kibaha", "Chalinze", 45, "50 min"),
        ("Chalinze", "Morogoro", 152, "2.5 hrs"),
    ],
    "Dar es Salaam → Dodoma": [
        ("Dar es Salaam", "Kibaha", 35, "35 min"),
        ("Kibaha", "Chalinze", 45, "50 min"),
        ("Chalinze", "Morogoro", 110, "1.5 hrs"),
        ("Morogoro", "Gairo", 80, "1 hr"),
        ("Gairo", "Dodoma", 221, "3 hrs"),
    ],
    "Dar es Salaam → Arusha": [
        ("Dar es Salaam", "Chalinze", 75, "1.5 hrs"),
        ("Chalinze", "Segera", 90, "1.5 hrs"),
        ("Segera", "Korogwe", 60, "1 hr"),
        ("Korogwe", "Same", 140, "2.5 hrs"),
        ("Same", "Moshi", 80, "1.5 hrs"),
        ("Moshi", "Arusha", 86, "1.5 hrs"),
    ],
    "Dar es Salaam → Mwanza": [
        ("Dar es Salaam", "Chalinze", 75, "1.5 hrs"),
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
        ("Msata", "Pangani", 80, "1.5 hrs"),
        ("Pangani", "Tanga", 54, "1 hr"),
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
    "Arusha → Namanga Border": [
        ("Arusha", "Namanga", 107, "1.5–2 hrs"),
    ],
    "Mbeya → Tunduma Border": [
        ("Mbeya", "Tunduma", 100, "1.5 hrs"),
    ],
    "Dar es Salaam → Lindi": [
        ("Dar es Salaam", "Kibaha", 35, "35 min"),
        ("Kibaha", "Kilosa", 200, "3 hrs"),
        ("Kilosa", "Masasi", 245, "4 hrs"),
        ("Masasi", "Lindi", 100, "2 hrs"),
    ],
    "Dodoma → Tabora": [
        ("Dodoma", "Singida", 190, "3 hrs"),
        ("Singida", "Tabora", 150, "2.5 hrs"),
    ],
    "Morogoro → Iringa": [
        ("Morogoro", "Mikumi", 107, "1.5 hrs"),
        ("Mikumi", "Iringa", 198, "3 hrs"),
    ],
}

DRIVERS = [
    ("James Mwakasege", "+255712345001", "Truck", "Freight", "Dar es Salaam → Morogoro"),
    ("Amina Hassan", "+255713456002", "Bus", "Passenger", "Dar es Salaam → Dodoma"),
    ("Peter Kimaro", "+255714567003", "Van", "Courier", "Dar es Salaam → Arusha"),
    ("Fatuma Saidi", "+255715678004", "Boda", "Courier", "Dar es Salaam → Tanga"),
    ("Robert Ngonyani", "+255716789005", "Truck", "Agriculture", "Morogoro → Dodoma"),
    ("Grace Mushi", "+255717890006", "Bus", "Passenger", "Dar es Salaam → Mwanza"),
    ("Salim Juma", "+255718901007", "Truck", "Freight", "Dar es Salaam → Mbeya"),
    ("Neema Kweka", "+255719012008", "Van", "Passenger", "Arusha → Namanga Border"),
    ("Hassan Omari", "+255720123009", "Truck", "Agriculture", "Dodoma → Mwanza"),
    ("Zawadi Mfinanga", "+255721234010", "Bus", "Passenger", "Dar es Salaam → Tanga"),
    ("Emmanuel Lyimo", "+255722345011", "Truck", "Freight", "Mbeya → Tunduma Border"),
    ("Rehema Massawe", "+255723456012", "Bajaji", "General Transport", "Dar es Salaam → Morogoro"),
]

INCIDENTS = [
    # Dar-Morogoro corridor
    ("Dar es Salaam → Morogoro", "Accident", "Chalinze", "High",
     "Multi-vehicle collision near weighbridge — two trucks jackknifed, lane blocked", 3),
    ("Dar es Salaam → Morogoro", "Traffic Jam", "Kibaha", "Medium",
     "Weighbridge queue backing up 3 km — all trucks being checked", 2),
    ("Dar es Salaam → Morogoro", "Police Checkpoint", "Morogoro", "Low",
     "Routine police inspection at town entry, minor delays expected", 0),
    ("Dar es Salaam → Morogoro", "Road Block", "Chalinze", "Medium",
     "TANROADS maintenance crew, one lane closed 08:00–17:00", 1),
    # Dar-Dodoma corridor
    ("Dar es Salaam → Dodoma", "Accident", "Chalinze", "High",
     "Jack-knifed fuel tanker blocking the fast lane — fuel spill hazard", 4),
    ("Dar es Salaam → Dodoma", "Bad Road", "Gairo", "High",
     "Large potholes after seasonal rains — road surface badly damaged", 3),
    ("Dar es Salaam → Dodoma", "Flood", "Gairo", "Critical",
     "Flash flooding at river crossing — road underwater, impassable for small vehicles", 5),
    # Morogoro-Dodoma
    ("Morogoro → Dodoma", "Flood", "Kilosa", "Critical",
     "Road partially submerged after heavy rains — alternative track dangerous", 5),
    ("Morogoro → Dodoma", "Bad Road", "Gairo", "Medium",
     "10 km section of degraded tarmac, deep potholes every few meters", 2),
    # Dar-Arusha corridor
    ("Dar es Salaam → Arusha", "Police Checkpoint", "Moshi", "Low",
     "Routine inspection at Moshi bypass, 10–15 min delay expected", 0),
    ("Dar es Salaam → Arusha", "Accident", "Korogwe", "High",
     "Bus vs truck head-on collision near Korogwe junction — road partially blocked", 4),
    ("Dar es Salaam → Arusha", "Road Block", "Same", "Medium",
     "Overturned cattle truck, animals on road — proceed with extreme caution", 2),
    # Dar-Mwanza
    ("Dar es Salaam → Mwanza", "Fuel Shortage", "Singida", "High",
     "Diesel unavailable at all three stations — stock expected tomorrow", 2),
    ("Dar es Salaam → Mwanza", "Theft Hotspot", "Nzega", "High",
     "Armed robbery of two cargo trucks in past 48 hours — travel in convoy advised", 4),
    ("Dar es Salaam → Mwanza", "Bad Road", "Nzega", "Medium",
     "Gravel section severely rutted after rains, 4x4 advisable", 2),
    # Dar-Mbeya
    ("Dar es Salaam → Mbeya", "Bad Road", "Makambako", "Medium",
     "Gravel section rough and uneven — reduce speed to 40 km/h", 1),
    ("Dar es Salaam → Mbeya", "Accident", "Iringa", "High",
     "Truck vs passenger van collision on steep descent — rescue teams on site", 3),
    ("Dar es Salaam → Mbeya", "Road Block", "Mikumi", "Low",
     "Wildlife crossing — elephant herd crossing road near Mikumi National Park", 0),
    # Dar-Tanga
    ("Dar es Salaam → Tanga", "Road Block", "Msata", "Low",
     "TANROADS temporary maintenance closure, 30 min delays", 0),
    ("Dar es Salaam → Tanga", "Bad Road", "Pangani", "Medium",
     "Coastal road erosion — narrow single lane for 5 km stretch", 1),
    # Dodoma-Mwanza
    ("Dodoma → Mwanza", "Theft Hotspot", "Nzega", "High",
     "Reports of cargo theft targeting trucks traveling alone at night", 3),
    ("Dodoma → Mwanza", "Fuel Shortage", "Singida", "Medium",
     "Petrol available but diesel very limited — fill up in Dodoma", 2),
    # Arusha-Namanga
    ("Arusha → Namanga Border", "Police Checkpoint", "Namanga", "Low",
     "Border crossing congestion — long queues for trucks, transit docs required", 1),
    # Mbeya-Tunduma
    ("Mbeya → Tunduma Border", "Road Block", "Tunduma", "Medium",
     "Border crossing backlog — 4–6 hour wait for freight trucks", 2),
    ("Mbeya → Tunduma Border", "Bad Road", "Tunduma", "Medium",
     "Construction work on approach road — dust and reduced visibility", 1),
    # Morogoro-Iringa
    ("Morogoro → Iringa", "Accident", "Mikumi", "High",
     "Overloaded truck rolled on bend near Mikumi — tow trucks dispatched", 3),
]


class Command(BaseCommand):
    help = "Seed routes with segments, drivers, and incident reports"

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Delete existing data first")

    def handle(self, *args, **options):
        if options["clear"]:
            TransportRoute.objects.all().delete()
            Driver.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()
            self.stdout.write("Cleared existing data.")

        # ── Superuser for admin ─────────────────────────────────
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@routewise.tz", "admin123")
            self.stdout.write("Created superuser: admin / admin123")

        # ── Routes ──────────────────────────────────────────────
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
                    "description": (
                        f"Key Tanzanian transport corridor: {origin} to {dest}. "
                        f"Community-monitored route with real-time risk updates."
                    ),
                },
            )
            route_map[name] = route
            RouteSegment.objects.filter(route=route).delete()
            for i, (f, t, d_km, est_seg) in enumerate(ROUTE_SEGMENTS.get(name, []), start=1):
                RouteSegment.objects.create(
                    route=route, from_location=f, to_location=t,
                    order=i, distance_km=d_km, estimated_time=est_seg,
                    notes=f"Section {i}: {f} to {t}.",
                )

        # ── Driver accounts (User + Driver) ─────────────────────
        # Build name→driver map for ratings later
        name_to_driver = {}
        for (username, password, full_name), (d_full, phone, vehicle, transport, main_route) in zip(
            DRIVER_ACCOUNTS, DRIVERS
        ):
            # Create or update User
            user, u_created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": full_name.split()[0],
                    "last_name": " ".join(full_name.split()[1:]),
                },
            )
            if u_created or not user.has_usable_password():
                user.set_password(password)
                user.save()

            # Create or update Driver, linked to User
            driver, d_created = Driver.objects.get_or_create(
                phone_number=phone,
                defaults={
                    "full_name":     full_name,
                    "vehicle_type":  vehicle,
                    "transport_type": transport,
                    "main_route":    main_route,
                    "trust_score":   5.0,
                    "ratings_count": 0,
                },
            )
            if driver.user is None:
                driver.user = user
                driver.save(update_fields=["user"])

            name_to_driver[full_name] = driver

        # ── Incidents (all approved — seed data is trusted) ──────
        for route_name, itype, loc, sev, desc, verified in INCIDENTS:
            route = route_map.get(route_name)
            if not route:
                continue
            segment = find_closest_segment(route, loc)
            IncidentReport.objects.get_or_create(
                route=route, location_name=loc, incident_type=itype,
                defaults={
                    "segment":        segment,
                    "reporter_name":  "Community Reporter",
                    "reporter_phone": "+255700000000",
                    "description":    desc,
                    "severity":       sev,
                    "verified_count": verified,
                    "approved":       True,
                    "needs_approval": False,
                },
            )

        # ── Risk recalculation ───────────────────────────────────
        for route in TransportRoute.objects.all():
            apply_risk_to_route(route)

        # ── Driver ratings ───────────────────────────────────────
        DriverRating.objects.all().delete()
        for rater_name, rated_name, score, comment in DRIVER_RATINGS:
            rater = name_to_driver.get(rater_name)
            rated = name_to_driver.get(rated_name)
            if rater and rated and rater != rated:
                DriverRating.objects.get_or_create(
                    rater=rater, rated=rated,
                    defaults={"score": score, "comment": comment},
                )

        # Recalculate trust scores from ratings
        for driver in Driver.objects.all():
            driver.recalculate_trust()

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {TransportRoute.objects.count()} routes, "
                f"{RouteSegment.objects.count()} segments, "
                f"{Driver.objects.count()} drivers, "
                f"{IncidentReport.objects.count()} incidents."
            )
        )
