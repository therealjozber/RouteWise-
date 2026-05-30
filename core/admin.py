from django.contrib import admin
from .models import (
    AirtimeReward, ATSubscription, Driver,
    IncidentReport, RouteSegment, TransportRoute, USSDSession,
)


class RouteSegmentInline(admin.TabularInline):
    model = RouteSegment
    extra = 0
    ordering = ["order"]


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display  = ("full_name", "phone_number", "vehicle_type", "transport_type", "main_route", "created_at")
    search_fields = ("full_name", "phone_number", "main_route")
    list_filter   = ("vehicle_type", "transport_type")


@admin.register(TransportRoute)
class TransportRouteAdmin(admin.ModelAdmin):
    list_display  = ("name", "origin", "destination", "distance_km", "risk_score", "status")
    search_fields = ("name", "origin", "destination")
    list_filter   = ("status",)
    inlines       = [RouteSegmentInline]


@admin.register(RouteSegment)
class RouteSegmentAdmin(admin.ModelAdmin):
    list_display  = ("route", "from_location", "to_location", "order", "risk_score", "status")
    list_filter   = ("status", "route")
    search_fields = ("from_location", "to_location")


@admin.register(IncidentReport)
class IncidentReportAdmin(admin.ModelAdmin):
    list_display  = (
        "incident_type", "location_name", "route", "segment",
        "severity", "ai_risk_score", "verified_count", "created_at",
    )
    search_fields = ("location_name", "reporter_name", "description")
    list_filter   = ("incident_type", "severity", "route")
    readonly_fields = ("ai_risk_score", "ai_estimated_delay_minutes", "ai_recommendation")


@admin.register(ATSubscription)
class ATSubscriptionAdmin(admin.ModelAdmin):
    list_display  = ("phone_number", "route", "channel", "is_active", "created_at")
    list_filter   = ("channel", "is_active", "route")
    search_fields = ("phone_number",)
    actions       = ["deactivate_subscriptions", "activate_subscriptions"]

    @admin.action(description="Deactivate selected subscriptions")
    def deactivate_subscriptions(self, request, queryset):
        queryset.update(is_active=False)

    @admin.action(description="Activate selected subscriptions")
    def activate_subscriptions(self, request, queryset):
        queryset.update(is_active=True)


@admin.register(AirtimeReward)
class AirtimeRewardAdmin(admin.ModelAdmin):
    list_display  = ("phone_number", "amount", "currency_code", "status", "reason", "created_at")
    list_filter   = ("status", "currency_code")
    search_fields = ("phone_number", "reason")
    readonly_fields = ("at_response",)


@admin.register(USSDSession)
class USSDSessionAdmin(admin.ModelAdmin):
    list_display  = ("session_id", "phone_number", "service_code", "action_taken", "created_at")
    search_fields = ("phone_number", "session_id")
    readonly_fields = ("session_id", "phone_number", "service_code",
                       "network_code", "final_text", "action_taken")
