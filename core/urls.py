from django.urls import path
from . import views

urlpatterns = [
    # ── Core ────────────────────────────────────────────────────
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("map/", views.live_map, name="live_map"),
    path("routes/", views.routes_list, name="routes_list"),
    path("routes/<int:pk>/", views.route_detail, name="route_detail"),
    path("report/", views.report_incident, name="report_incident"),
    path("register-driver/", views.register_driver, name="register_driver"),  # legacy redirect
    path("simulate-message/", views.simulate_message, name="simulate_message"),

    # ── Driver auth ──────────────────────────────────────────────
    path("driver/signup/",   views.driver_signup,       name="driver_signup"),
    path("driver/login/",    views.driver_login_view,    name="driver_login"),
    path("driver/logout/",   views.driver_logout_view,   name="driver_logout"),
    path("driver/profile/",  views.driver_profile,       name="driver_profile"),
    path("driver/directory/",views.driver_directory,     name="driver_directory"),
    path("driver/<int:pk>/", views.driver_public_profile,name="driver_public_profile"),
    path("driver/<int:pk>/rate/", views.rate_driver,     name="rate_driver"),

    # ── Incident approval ────────────────────────────────────────
    path("incident/<int:pk>/approve/", views.approve_incident, name="approve_incident"),
    path("incident/<int:pk>/reject/",  views.reject_incident,  name="reject_incident"),

    # ── AT services ──────────────────────────────────────────────
    path("at/",              views.at_services,       name="at_services"),
    path("at/test/sms/",     views.at_test_sms,       name="at_test_sms"),
    path("at/test/airtime/", views.at_test_airtime,   name="at_test_airtime"),
    path("at/broadcast/",    views.at_broadcast_route,name="at_broadcast_route"),

    # ── AT webhooks (register in AT dashboard) ───────────────────
    path("at/ussd/",          views.at_ussd_webhook,    name="at_ussd_webhook"),
    path("at/sms/incoming/",  views.at_sms_webhook,     name="at_sms_webhook"),
    path("at/voice/",         views.at_voice_webhook,   name="at_voice_webhook"),
    path("at/sms/delivery/",  views.at_delivery_report, name="at_delivery_report"),
]
