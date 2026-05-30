from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import IncidentReport
from .services.risk_engine import attach_incident_to_segment


@receiver(post_save, sender=IncidentReport)
def recalculate_route_risk(sender, instance, **kwargs):
    attach_incident_to_segment(instance, save_segment=True)
