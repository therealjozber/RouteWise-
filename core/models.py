from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg
from django.utils import timezone


class Driver(models.Model):
    VEHICLE_TYPES = [
        ("Truck", "Truck"),
        ("Bus", "Bus"),
        ("Van", "Van"),
        ("Boda", "Boda"),
        ("Bajaji", "Bajaji"),
        ("Courier Bike", "Courier Bike"),
    ]
    TRANSPORT_TYPES = [
        ("Freight", "Freight"),
        ("Passenger", "Passenger"),
        ("Courier", "Courier"),
        ("Agriculture", "Agriculture"),
        ("General Transport", "General Transport"),
    ]

    # ── Auth link ───────────────────────────────────────────────
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="driver_profile",
    )

    # ── Profile ─────────────────────────────────────────────────
    full_name     = models.CharField(max_length=200)
    phone_number  = models.CharField(max_length=20)
    vehicle_type  = models.CharField(max_length=50, choices=VEHICLE_TYPES)
    transport_type = models.CharField(max_length=50, choices=TRANSPORT_TYPES)
    main_route    = models.CharField(max_length=200, help_text="Primary route e.g. Dar es Salaam → Morogoro")
    bio           = models.TextField(blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    # ── Trust / reputation ──────────────────────────────────────
    trust_score   = models.FloatField(default=5.0)   # starts at max (5.0)
    ratings_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name} ({self.vehicle_type})"

    @property
    def is_trusted(self):
        """Trusted drivers can approve anonymous incident reports."""
        return self.trust_score >= 3.5

    @property
    def trust_level(self):
        if self.trust_score >= 4.5:
            return "Elite"
        if self.trust_score >= 3.5:
            return "Trusted"
        if self.trust_score >= 2.5:
            return "Caution"
        return "Low"

    @property
    def trust_color(self):
        return {
            "Elite": "safe",
            "Trusted": "caution",
            "Caution": "high-risk",
            "Low": "avoid",
        }.get(self.trust_level, "caution")

    @property
    def star_display(self):
        full  = int(self.trust_score)
        half  = 1 if (self.trust_score - full) >= 0.5 else 0
        empty = 5 - full - half
        return "★" * full + "½" * half + "☆" * empty

    def recalculate_trust(self):
        """Recompute trust_score from all received ratings."""
        agg = self.received_ratings.aggregate(avg=Avg("score"))
        avg = agg["avg"]
        self.ratings_count = self.received_ratings.count()
        self.trust_score = round(avg, 2) if avg is not None else 5.0
        self.save(update_fields=["trust_score", "ratings_count"])

    @property
    def reported_count(self):
        return self.reported_incidents.filter(approved=True).count()

    @property
    def pending_count(self):
        return self.reported_incidents.filter(needs_approval=True).count()

    @property
    def approved_count(self):
        return self.approved_incidents.count()


class TransportRoute(models.Model):
    STATUS_CHOICES = [
        ("Safe", "Safe"),
        ("Caution", "Caution"),
        ("High Risk", "High Risk"),
        ("Avoid", "Avoid"),
    ]

    name          = models.CharField(max_length=200)
    origin        = models.CharField(max_length=100)
    destination   = models.CharField(max_length=100)
    distance_km   = models.PositiveIntegerField(default=0)
    estimated_time = models.CharField(max_length=100, default="—")
    risk_score    = models.PositiveIntegerField(default=0)
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Safe")
    description   = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def display_name(self):
        return f"{self.origin} → {self.destination}"

    @property
    def via_display(self):
        segments = self.segments.order_by("order")
        if not segments.exists():
            return self.display_name
        points = [segments.first().from_location]
        for seg in segments:
            points.append(seg.to_location)
        return " → ".join(points)


class RouteSegment(models.Model):
    STATUS_CHOICES = TransportRoute.STATUS_CHOICES

    route         = models.ForeignKey(TransportRoute, on_delete=models.CASCADE, related_name="segments")
    from_location = models.CharField(max_length=100)
    to_location   = models.CharField(max_length=100)
    order         = models.PositiveIntegerField(default=0)
    distance_km   = models.PositiveIntegerField(default=0)
    estimated_time = models.CharField(max_length=50, default="—")
    risk_score    = models.PositiveIntegerField(default=0)
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Safe")
    notes         = models.TextField(blank=True)

    class Meta:
        ordering = ["route", "order"]
        unique_together = [["route", "order"]]

    def __str__(self):
        return f"{self.from_location} → {self.to_location} (seg {self.order})"

    @property
    def label(self):
        return f"{self.from_location} → {self.to_location}"


class IncidentReport(models.Model):
    INCIDENT_TYPES = [
        ("Accident", "Accident"),
        ("Flood", "Flood"),
        ("Bad Road", "Bad Road"),
        ("Traffic Jam", "Traffic Jam"),
        ("Road Block", "Road Block"),
        ("Police Checkpoint", "Police Checkpoint"),
        ("Fuel Shortage", "Fuel Shortage"),
        ("Theft Hotspot", "Theft Hotspot"),
        ("Vehicle Breakdown", "Vehicle Breakdown"),
    ]
    SEVERITY_CHOICES = [
        ("Low", "Low"),
        ("Medium", "Medium"),
        ("High", "High"),
        ("Critical", "Critical"),
    ]

    route    = models.ForeignKey(TransportRoute, on_delete=models.CASCADE, related_name="incidents")
    segment  = models.ForeignKey(RouteSegment, on_delete=models.SET_NULL, null=True, blank=True, related_name="incidents")

    # ── Reporter ─────────────────────────────────────────────────
    reporter_name   = models.CharField(max_length=200)
    reporter_phone  = models.CharField(max_length=20, blank=True)
    reporter_driver = models.ForeignKey(
        "Driver",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="reported_incidents",
        help_text="Linked driver account (if reporter was logged in)",
    )

    # ── Incident details ─────────────────────────────────────────
    incident_type = models.CharField(max_length=50, choices=INCIDENT_TYPES)
    location_name = models.CharField(max_length=200)
    description   = models.TextField(blank=True)
    severity      = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default="Medium")
    verified_count = models.PositiveIntegerField(default=0)

    # ── Approval workflow ────────────────────────────────────────
    approved         = models.BooleanField(default=True)   # True = published, False = hidden
    needs_approval   = models.BooleanField(default=False)  # True = pending trusted-driver review
    approved_by      = models.ForeignKey(
        "Driver",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="approved_incidents",
    )
    rejection_reason = models.CharField(max_length=300, blank=True)

    # ── AI analysis ──────────────────────────────────────────────
    ai_risk_score             = models.PositiveIntegerField(default=0)
    ai_estimated_delay_minutes = models.PositiveIntegerField(default=0)
    ai_recommendation         = models.TextField(blank=True)
    created_at                = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        tag = "" if self.approved else " [PENDING]"
        return f"{self.incident_type} @ {self.location_name}{tag}"

    @property
    def source_label(self):
        if self.reporter_driver:
            return f"Driver: {self.reporter_driver.full_name}"
        return "Anonymous"


class DriverRating(models.Model):
    """A driver rates another driver 1–5 stars based on report quality."""
    rater   = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name="given_ratings")
    rated   = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name="received_ratings")
    score   = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="1 (poor) to 5 (excellent)",
    )
    comment    = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [["rater", "rated"]]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.rater} → {self.rated}: {self.score}★"


# ── Africa's Talking models ───────────────────────────────────────

class ATSubscription(models.Model):
    CHANNEL_CHOICES = [("SMS", "SMS"), ("WhatsApp", "WhatsApp")]

    phone_number = models.CharField(max_length=20)
    route        = models.ForeignKey(TransportRoute, on_delete=models.CASCADE, related_name="subscribers")
    channel      = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default="SMS")
    is_active    = models.BooleanField(default=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["phone_number", "route"]]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.phone_number} → {self.route.name} ({self.channel})"


class AirtimeReward(models.Model):
    STATUS_CHOICES = [("pending", "Pending"), ("sent", "Sent"), ("failed", "Failed")]

    phone_number  = models.CharField(max_length=20)
    amount        = models.DecimalField(max_digits=8, decimal_places=2, default=500)
    currency_code = models.CharField(max_length=5, default="TZS")
    reason        = models.CharField(max_length=200)
    incident      = models.ForeignKey(IncidentReport, on_delete=models.SET_NULL, null=True, blank=True, related_name="airtime_rewards")
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    at_response   = models.TextField(blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.currency_code} {self.amount} → {self.phone_number} ({self.status})"


class USSDSession(models.Model):
    session_id   = models.CharField(max_length=100, unique=True)
    phone_number = models.CharField(max_length=20)
    service_code = models.CharField(max_length=20, blank=True)
    network_code = models.CharField(max_length=20, blank=True)
    final_text   = models.TextField(blank=True)
    action_taken = models.CharField(max_length=100, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"USSD {self.session_id[:16]} – {self.phone_number}"
