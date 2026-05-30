from django.contrib import admin
from .models import (
    AirtimeReward, ATSubscription, Driver, DriverRating,
    IncidentReport, RouteSegment, TransportRoute, USSDSession,
)


class RouteSegmentInline(admin.TabularInline):
    model   = RouteSegment
    extra   = 0
    ordering = ["order"]


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display  = ("full_name", "phone_number", "vehicle_type", "trust_score", "trust_level", "ratings_count", "has_account", "created_at")
    search_fields = ("full_name", "phone_number", "main_route")
    list_filter   = ("vehicle_type", "transport_type")
    readonly_fields = ("trust_score", "ratings_count")

    @admin.display(boolean=True, description="Has account")
    def has_account(self, obj):
        return obj.user_id is not None


@admin.register(DriverRating)
class DriverRatingAdmin(admin.ModelAdmin):
    list_display  = ("rater", "rated", "score", "comment", "created_at")
    list_filter   = ("score",)
    search_fields = ("rater__full_name", "rated__full_name")


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
        "incident_type", "location_name", "route", "severity",
        "approved", "needs_approval", "reporter_driver", "ai_risk_score", "created_at",
    )
    search_fields = ("location_name", "reporter_name", "description")
    list_filter   = ("incident_type", "severity", "approved", "needs_approval", "route")
    readonly_fields = ("ai_risk_score", "ai_estimated_delay_minutes", "ai_recommendation")
    actions = ["approve_selected", "reject_selected"]

    @admin.action(description="Approve selected reports")
    def approve_selected(self, request, queryset):
        queryset.update(approved=True, needs_approval=False)

    @admin.action(description="Reject selected reports")
    def reject_selected(self, request, queryset):
        queryset.update(approved=False, needs_approval=False, rejection_reason="Rejected by admin")


@admin.register(ATSubscription)
class ATSubscriptionAdmin(admin.ModelAdmin):
    list_display  = ("phone_number", "route", "channel", "is_active", "created_at")
    list_filter   = ("channel", "is_active", "route")
    search_fields = ("phone_number",)


@admin.register(AirtimeReward)
class AirtimeRewardAdmin(admin.ModelAdmin):
    list_display  = ("phone_number", "amount", "currency_code", "status", "reason", "created_at")
    list_filter   = ("status", "currency_code")
    search_fields = ("phone_number", "reason")


@admin.register(USSDSession)
class USSDSessionAdmin(admin.ModelAdmin):
    list_display  = ("session_id", "phone_number", "service_code", "action_taken", "created_at")
    search_fields = ("phone_number", "session_id")
    readonly_fields = ("session_id", "phone_number", "service_code", "network_code", "final_text", "action_taken")
