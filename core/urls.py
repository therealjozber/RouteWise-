from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("routes/", views.routes_list, name="routes_list"),
    path("routes/<int:pk>/", views.route_detail, name="route_detail"),
    path("report/", views.report_incident, name="report_incident"),
    path("register-driver/", views.register_driver, name="register_driver"),
    path("simulate-message/", views.simulate_message, name="simulate_message"),
]
