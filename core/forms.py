from django import forms
from .models import Driver, IncidentReport, RouteSegment, TransportRoute


class DriverRegistrationForm(forms.ModelForm):
    class Meta:
        model = Driver
        fields = [
            "full_name",
            "phone_number",
            "vehicle_type",
            "transport_type",
            "main_route",
        ]
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "John Mwangi"}),
            "phone_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "+255712345678"}),
            "vehicle_type": forms.Select(attrs={"class": "form-select"}),
            "transport_type": forms.Select(attrs={"class": "form-select"}),
            "main_route": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Dar es Salaam → Morogoro"}
            ),
        }


class IncidentReportForm(forms.ModelForm):
    class Meta:
        model = IncidentReport
        fields = [
            "route",
            "segment",
            "reporter_name",
            "reporter_phone",
            "incident_type",
            "location_name",
            "description",
            "severity",
        ]
        widgets = {
            "route": forms.Select(attrs={"class": "form-select", "id": "id_route"}),
            "segment": forms.Select(attrs={"class": "form-select", "id": "id_segment"}),
            "reporter_name": forms.TextInput(attrs={"class": "form-control"}),
            "reporter_phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "+255..."}),
            "incident_type": forms.Select(attrs={"class": "form-select"}),
            "location_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. Chalinze (auto-matches segment)"}
            ),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "severity": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["segment"].required = False
        self.fields["segment"].empty_label = "Auto-detect from location"
        route_id = None
        if self.data.get("route"):
            route_id = self.data.get("route")
        elif self.initial.get("route"):
            route_id = self.initial.get("route")
        if route_id:
            self.fields["segment"].queryset = RouteSegment.objects.filter(
                route_id=route_id
            ).order_by("order")
        else:
            self.fields["segment"].queryset = RouteSegment.objects.none()


class SimulateMessageForm(forms.Form):
    CHANNEL_CHOICES = [("SMS", "SMS"), ("WhatsApp", "WhatsApp")]

    phone_number = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "+255712345678"}),
    )
    channel = forms.ChoiceField(
        choices=CHANNEL_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    message_text = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "ACCIDENT#Chalinze#Dar es Salaam to Dodoma",
            }
        ),
        help_text="Format: TYPE#Location#Route — segment auto-detected from location",
    )
