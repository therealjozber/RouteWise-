from django import forms
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.core.validators import MinValueValidator, MaxValueValidator

from .models import Driver, DriverRating, IncidentReport, RouteSegment, TransportRoute

_FC = "form-control"
_FS = "form-select"


# ── Driver signup (creates User + Driver) ─────────────────────────
class DriverSignupForm(forms.Form):
    username = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={"class": _FC, "placeholder": "e.g. jmwakasege"}),
        help_text="Letters, digits and @/./+/-/_ only.",
    )
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"class": _FC, "placeholder": "Minimum 8 characters"}),
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"class": _FC, "placeholder": "Repeat password"}),
    )
    full_name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={"class": _FC, "placeholder": "John Mwangi"}),
    )
    phone_number = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={"class": _FC, "placeholder": "+255712345678"}),
    )
    vehicle_type = forms.ChoiceField(
        choices=Driver.VEHICLE_TYPES,
        widget=forms.Select(attrs={"class": _FS}),
    )
    transport_type = forms.ChoiceField(
        choices=Driver.TRANSPORT_TYPES,
        widget=forms.Select(attrs={"class": _FS}),
    )
    main_route = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={"class": _FC, "placeholder": "Dar es Salaam → Morogoro"}),
        help_text="Your primary driving corridor.",
    )
    bio = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": _FC, "rows": 2, "placeholder": "Brief intro (optional)"}),
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def clean_phone_number(self):
        phone = self.cleaned_data["phone_number"].strip()
        if Driver.objects.filter(phone_number=phone).exists():
            raise forms.ValidationError("A driver with this phone number already exists.")
        return phone

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1", "")
        p2 = cleaned.get("password2", "")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")
        if p1 and len(p1) < 8:
            self.add_error("password1", "Password must be at least 8 characters.")
        return cleaned

    def save(self):
        d = self.cleaned_data
        user = User.objects.create_user(
            username=d["username"],
            password=d["password1"],
            first_name=d["full_name"].split()[0],
            last_name=" ".join(d["full_name"].split()[1:]),
        )
        driver = Driver.objects.create(
            user=user,
            full_name=d["full_name"],
            phone_number=d["phone_number"],
            vehicle_type=d["vehicle_type"],
            transport_type=d["transport_type"],
            main_route=d["main_route"],
            bio=d.get("bio", ""),
            trust_score=5.0,   # start at maximum
            ratings_count=0,
        )
        return driver


# ── Driver login ──────────────────────────────────────────────────
class DriverLoginForm(forms.Form):
    username = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={"class": _FC, "placeholder": "Username", "autofocus": True}),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": _FC, "placeholder": "Password"}),
    )

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        self._user  = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned  = super().clean()
        username = cleaned.get("username", "").strip()
        password = cleaned.get("password", "")
        if username and password:
            self._user = authenticate(self.request, username=username, password=password)
            if self._user is None:
                raise forms.ValidationError("Incorrect username or password. Please try again.")
            if not self._user.is_active:
                raise forms.ValidationError("This account has been disabled.")
        return cleaned

    def get_user(self):
        return self._user


# ── Driver rating ─────────────────────────────────────────────────
class DriverRatingForm(forms.ModelForm):
    score = forms.IntegerField(
        widget=forms.HiddenInput(),
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )

    class Meta:
        model   = DriverRating
        fields  = ["score", "comment"]
        widgets = {
            "comment": forms.Textarea(attrs={
                "class": _FC, "rows": 2,
                "placeholder": "Optional: describe your experience with this driver's reports...",
            }),
        }


# ── Incident report form (existing, unchanged API) ─────────────────
class IncidentReportForm(forms.ModelForm):
    class Meta:
        model  = IncidentReport
        fields = [
            "route", "segment", "reporter_name", "reporter_phone",
            "incident_type", "location_name", "description", "severity",
        ]
        widgets = {
            "route":         forms.Select(attrs={"class": _FS, "id": "id_route"}),
            "segment":       forms.Select(attrs={"class": _FS, "id": "id_segment"}),
            "reporter_name": forms.TextInput(attrs={"class": _FC}),
            "reporter_phone": forms.TextInput(attrs={"class": _FC, "placeholder": "+255..."}),
            "incident_type": forms.Select(attrs={"class": _FS}),
            "location_name": forms.TextInput(attrs={"class": _FC, "placeholder": "e.g. Chalinze"}),
            "description":   forms.Textarea(attrs={"class": _FC, "rows": 3}),
            "severity":      forms.Select(attrs={"class": _FS}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["segment"].required    = False
        self.fields["segment"].empty_label = "Auto-detect from location"
        route_id = self.data.get("route") or self.initial.get("route")
        if route_id:
            self.fields["segment"].queryset = RouteSegment.objects.filter(
                route_id=route_id
            ).order_by("order")
        else:
            self.fields["segment"].queryset = RouteSegment.objects.none()


# ── Simulate SMS form (unchanged) ─────────────────────────────────
class SimulateMessageForm(forms.Form):
    CHANNEL_CHOICES = [("SMS", "SMS"), ("WhatsApp", "WhatsApp")]

    phone_number = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={"class": _FC, "placeholder": "+255712345678"}),
    )
    channel = forms.ChoiceField(
        choices=CHANNEL_CHOICES,
        widget=forms.Select(attrs={"class": _FS}),
    )
    message_text = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": _FC, "rows": 4,
            "placeholder": "ACCIDENT#Chalinze#Dar es Salaam to Dodoma",
        }),
        help_text="Format: TYPE#Location#Route — segment auto-detected from location",
    )
