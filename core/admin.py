from django.contrib import admin
from .models import Driver, TransportRoute, RouteSegment, IncidentReport


class RouteSegmentInline(admin.TabularInline):
    model = RouteSegment
    extra = 0
    ordering = ["order"]


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone_number", "vehicle_type", "transport_type", "main_route", "created_at")
    search_fields = ("full_name", "phone_number", "main_route")
    list_filter = ("vehicle_type", "transport_type")


@admin.register(TransportRoute)
class TransportRouteAdmin(admin.ModelAdmin):
    list_display = ("name", "origin", "destination", "distance_km", "risk_score", "status")
    search_fields = ("name", "origin", "destination")
    list_filter = ("status",)
    inlines = [RouteSegmentInline]


@admin.register(RouteSegment)
class RouteSegmentAdmin(admin.ModelAdmin):
    list_display = ("route", "from_location", "to_location", "order", "risk_score", "status")
    list_filter = ("status", "route")
    search_fields = ("from_location", "to_location")


@admin.register(IncidentReport)
class IncidentReportAdmin(admin.ModelAdmin):
    list_display = (
        "incident_type",
        "location_name",
        "route",
        "segment",
        "severity",
        "ai_risk_score",
        "verified_count",
        "created_at",
    )
    search_fields = ("location_name", "reporter_name", "description")
    list_filter = ("incident_type", "severity", "route")
