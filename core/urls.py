from django.urls import path
from . import views

urlpatterns = [
    # ── Core pages ──────────────────────────────────────────────
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("map/", views.live_map, name="live_map"),
    path("routes/", views.routes_list, name="routes_list"),
    path("routes/<int:pk>/", views.route_detail, name="route_detail"),
    path("report/", views.report_incident, name="report_incident"),
    path("register-driver/", views.register_driver, name="register_driver"),
    path("simulate-message/", views.simulate_message, name="simulate_message"),

    # ── Africa's Talking services dashboard ─────────────────────
    path("at/", views.at_services, name="at_services"),
    path("at/test/sms/", views.at_test_sms, name="at_test_sms"),
    path("at/test/airtime/", views.at_test_airtime, name="at_test_airtime"),
    path("at/broadcast/", views.at_broadcast_route, name="at_broadcast_route"),

    # ── Africa's Talking webhooks (register these in AT dashboard) ──
    path("at/ussd/", views.at_ussd_webhook, name="at_ussd_webhook"),
    path("at/sms/incoming/", views.at_sms_webhook, name="at_sms_webhook"),
    path("at/voice/", views.at_voice_webhook, name="at_voice_webhook"),
    path("at/sms/delivery/", views.at_delivery_report, name="at_delivery_report"),
]
