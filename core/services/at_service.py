"""
Africa's Talking — complete service layer for RouteWise TZ.

Services integrated:
  SMS      — individual alerts + bulk route broadcasts
  WhatsApp — rich driver alerts
  USSD     — *384*5959# menu (no internet needed, any phone)
  Voice    — outbound calls for Critical incidents
  Airtime  — reward community reporters
  Application — account balance / health check

All public methods return (success: bool, payload: dict) and NEVER raise.
"""

import logging
import textwrap
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# ── AT status codes for our own tracking ─────────────────────────
SUCCESS = "success"
SIMULATED = "simulated"
FAILED = "failed"

# ── Route shortnames for USSD menus (max 20 chars) ───────────────
USSD_ROUTE_LABELS = {
    "Dar es Salaam → Morogoro":       "DSM-Morogoro",
    "Dar es Salaam → Dodoma":         "DSM-Dodoma",
    "Dar es Salaam → Arusha":         "DSM-Arusha",
    "Dar es Salaam → Mwanza":         "DSM-Mwanza",
    "Dar es Salaam → Mbeya":          "DSM-Mbeya",
    "Dar es Salaam → Tanga":          "DSM-Tanga",
    "Morogoro → Dodoma":              "Morogoro-Dodoma",
    "Dodoma → Mwanza":                "Dodoma-Mwanza",
    "Arusha → Namanga Border":        "Arusha-Namanga",
    "Mbeya → Tunduma Border":         "Mbeya-Tunduma",
    "Dar es Salaam → Lindi":          "DSM-Lindi",
    "Dodoma → Tabora":                "Dodoma-Tabora",
    "Morogoro → Iringa":              "Morogoro-Iringa",
}

STATUS_EMOJI = {
    "Safe":      "✓ CLEAR",
    "Caution":   "! CAUTION",
    "High Risk": "!! HIGH RISK",
    "Avoid":     "X AVOID",
}

INCIDENT_MENU = {
    "1": "Accident",
    "2": "Flood",
    "3": "Bad Road",
    "4": "Traffic Jam",
    "5": "Road Block",
    "6": "Police Checkpoint",
    "7": "Fuel Shortage",
    "8": "Theft Hotspot",
    "9": "Vehicle Breakdown",
}

VEHICLE_MENU = {
    "1": "Truck",
    "2": "Bus",
    "3": "Van",
    "4": "Boda",
    "5": "Bajaji",
}


# ═══════════════════════════════════════════════════════════════════
# Singleton service class
# ═══════════════════════════════════════════════════════════════════

class ATService:
    _instance = None
    _initialized = False
    _sms = None
    _voice = None
    _airtime = None
    _whatsapp = None
    _application = None
    _live = False  # True when credentials are valid and connected

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ── Init ──────────────────────────────────────────────────────
    def _ensure_init(self) -> bool:
        if self._initialized:
            return self._live

        username = (getattr(settings, "AT_USERNAME", "") or "").strip()
        api_key  = (getattr(settings, "AT_API_KEY",  "") or "").strip()

        if not username or not api_key:
            logger.info("[AT] Credentials not configured — simulation mode.")
            self._initialized = True
            return False

        try:
            import africastalking
            africastalking.initialize(username, api_key)
            self._sms         = africastalking.SMS
            self._voice       = africastalking.Voice
            self._airtime     = africastalking.Airtime
            self._application = africastalking.Application
            # WhatsApp raises warning in sandbox — catch it
            try:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    self._whatsapp = africastalking.Whatsapp
            except Exception:
                self._whatsapp = None

            self._live = True
            self._initialized = True
            logger.info("[AT] Initialized. Username=%s sandbox=%s", username, username == "sandbox")
            return True
        except Exception as exc:
            logger.warning("[AT] Init failed: %s", exc)
            self._initialized = True
            return False

    @property
    def is_live(self) -> bool:
        self._ensure_init()
        return self._live

    @property
    def mode(self) -> str:
        return "live" if self.is_live else "sandbox/simulated"

    # ── SMS ───────────────────────────────────────────────────────
    def send_sms(self, phone: str, message: str, sender_id: str | None = None) -> dict:
        """
        Send a single SMS. Returns {status, phone, response}.
        Falls back to console log if AT not configured.
        """
        phone   = (phone   or "").strip()
        message = (message or "").strip()
        if not phone or not message:
            return {"status": FAILED, "error": "Missing phone or message"}

        if self._ensure_init() and self._sms:
            try:
                resp = self._sms.send(message, [phone], sender_id=sender_id)
                logger.info("[AT SMS] Sent to %s: %s", phone, resp)
                return {"status": SUCCESS, "phone": phone, "response": resp}
            except Exception as exc:
                logger.warning("[AT SMS] Send failed (%s): %s", phone, exc)

        # Simulated fallback
        _log_simulated("SMS", phone, message)
        return {"status": SIMULATED, "phone": phone, "message": message}

    def broadcast_sms(self, phones: list[str], message: str, sender_id: str | None = None) -> dict:
        """
        Send bulk SMS to multiple recipients in one AT call.
        """
        phones  = [p.strip() for p in phones if p and p.strip()]
        message = (message or "").strip()
        if not phones or not message:
            return {"status": FAILED, "error": "No recipients or empty message"}

        if self._ensure_init() and self._sms:
            try:
                resp = self._sms.send(message, phones, sender_id=sender_id)
                logger.info("[AT SMS Broadcast] %d recipients: %s", len(phones), resp)
                return {"status": SUCCESS, "count": len(phones), "response": resp}
            except Exception as exc:
                logger.warning("[AT SMS Broadcast] Failed: %s", exc)

        for p in phones:
            _log_simulated("SMS", p, message)
        return {"status": SIMULATED, "count": len(phones)}

    # ── WhatsApp ──────────────────────────────────────────────────
    def send_whatsapp(self, phone: str, message: str, wa_number: str | None = None) -> dict:
        """Send WhatsApp message. wa_number = your AT registered WA business number."""
        phone   = (phone   or "").strip()
        message = (message or "").strip()
        wa_num  = (wa_number or getattr(settings, "AT_WHATSAPP_NUMBER", "") or "").strip()

        if not phone or not message:
            return {"status": FAILED, "error": "Missing phone or message"}

        if self._ensure_init() and self._whatsapp and wa_num:
            try:
                body = {"type": "text", "text": {"body": message}}
                resp = self._whatsapp.send(body=body, wa_number=wa_num, phone_number=phone)
                logger.info("[AT WhatsApp] Sent to %s: %s", phone, resp)
                return {"status": SUCCESS, "phone": phone, "response": resp}
            except Exception as exc:
                logger.warning("[AT WhatsApp] Failed (%s): %s", phone, exc)

        _log_simulated("WhatsApp", phone, message)
        return {"status": SIMULATED, "phone": phone, "message": message}

    # ── Voice ─────────────────────────────────────────────────────
    def make_call(self, from_number: str, to_number: str) -> dict:
        """Initiate an outbound voice call."""
        from_number = (from_number or "").strip()
        to_number   = (to_number   or "").strip()

        if not from_number or not to_number:
            return {"status": FAILED, "error": "Missing from/to number"}

        if self._ensure_init() and self._voice:
            try:
                resp = self._voice.call(callFrom=from_number, callTo=[to_number])
                logger.info("[AT Voice] Called %s from %s: %s", to_number, from_number, resp)
                return {"status": SUCCESS, "to": to_number, "response": resp}
            except Exception as exc:
                logger.warning("[AT Voice] Call failed (%s): %s", to_number, exc)

        logger.info("[AT Voice simulated] %s → %s", from_number, to_number)
        return {"status": SIMULATED, "from": from_number, "to": to_number}

    # ── Airtime ───────────────────────────────────────────────────
    def send_airtime(self, phone: str, amount: float, currency: str = "TZS") -> dict:
        """Send airtime reward to a phone number."""
        phone = (phone or "").strip()
        if not phone or amount <= 0:
            return {"status": FAILED, "error": "Invalid phone or amount"}

        if self._ensure_init() and self._airtime:
            try:
                recipients = [{"phone_number": phone, "amount": str(amount), "currency_code": currency}]
                resp = self._airtime.send(recipients=recipients, max_num_retry=2)
                logger.info("[AT Airtime] %s %s → %s: %s", currency, amount, phone, resp)
                return {"status": SUCCESS, "phone": phone, "amount": amount, "response": resp}
            except Exception as exc:
                logger.warning("[AT Airtime] Failed (%s): %s", phone, exc)

        logger.info("[AT Airtime simulated] %s %s → %s", currency, amount, phone)
        return {"status": SIMULATED, "phone": phone, "amount": amount, "currency": currency}

    # ── Application (balance) ─────────────────────────────────────
    def get_balance(self) -> dict:
        """Fetch AT account balance."""
        if self._ensure_init() and self._application:
            try:
                resp = self._application.fetch_application_data()
                logger.info("[AT Balance] %s", resp)
                return {"status": SUCCESS, "data": resp}
            except Exception as exc:
                logger.warning("[AT Balance] Failed: %s", exc)
        return {"status": SIMULATED, "data": {"UserData": {"balance": "Sandbox mode"}}}

    # ── Broadcast to route subscribers ────────────────────────────
    def broadcast_route_alert(self, route, message: str, severity: str = "Medium") -> dict:
        """
        Send SMS/WhatsApp to every active ATSubscription + registered
        Driver whose main_route matches. Returns summary dict.
        """
        from ..models import ATSubscription, Driver

        phones_sms = set()
        phones_wa  = set()

        # Subscriptions
        for sub in ATSubscription.objects.filter(route=route, is_active=True):
            if sub.channel == "WhatsApp":
                phones_wa.add(sub.phone_number)
            else:
                phones_sms.add(sub.phone_number)

        # Registered drivers on this route
        route_key = route.name.lower()
        for driver in Driver.objects.filter(main_route__icontains=route.origin):
            if driver.phone_number:
                phones_sms.add(driver.phone_number)

        # Send
        sms_result = {"status": SIMULATED, "count": 0}
        if phones_sms:
            sms_result = self.broadcast_sms(list(phones_sms), message)

        wa_result = {"status": SIMULATED, "count": 0}
        for p in phones_wa:
            self.send_whatsapp(p, message)
        if phones_wa:
            wa_result = {"status": SIMULATED, "count": len(phones_wa)}

        # For Critical: make voice calls to all drivers on route
        if severity == "Critical":
            call_from = (getattr(settings, "AT_VOICE_NUMBER", "") or "").strip()
            if call_from:
                for phone in list(phones_sms)[:10]:  # cap at 10 calls
                    self.make_call(call_from, phone)

        return {
            "sms_recipients":       len(phones_sms),
            "whatsapp_recipients":  len(phones_wa),
            "sms_result":           sms_result,
            "wa_result":            wa_result,
        }

    # ── USSD Session Handler ──────────────────────────────────────
    def handle_ussd(
        self,
        session_id: str,
        service_code: str,
        phone_number: str,
        text: str,
        network_code: str = "",
    ) -> str:
        """
        Main USSD state machine.  AT sends accumulated input as 'text':
          ""        → root menu
          "1"       → user chose option 1 at root
          "1*2"     → option 1 at root then 2 at level-2 menu
          "1*2*foo" → typed free text 'foo' at level-3
        Always returns "CON <menu>" or "END <message>".
        """
        from ..models import (
            TransportRoute, IncidentReport, Driver, ATSubscription, USSDSession
        )
        from ..segment_utils import find_closest_segment
        from .incident_processing import finalize_incident_report

        # Log session
        try:
            sess, _ = USSDSession.objects.get_or_create(
                session_id=session_id,
                defaults={"phone_number": phone_number, "service_code": service_code,
                          "network_code": network_code},
            )
            sess.final_text = text
            sess.save(update_fields=["final_text", "updated_at"])
        except Exception:
            pass

        parts  = text.split("*") if text else []
        lvl    = lambda n, d="": parts[n] if len(parts) > n else d  # noqa: E731
        l0, l1, l2, l3, l4 = lvl(0), lvl(1), lvl(2), lvl(3), lvl(4)

        routes = list(TransportRoute.objects.order_by("-risk_score")[:9])

        # ── Root menu ──────────────────────────────────────────────
        if text == "":
            return (
                "CON Welcome to RouteWise TZ\n"
                "Tanzania Road Intelligence\n\n"
                "1. Check Route Status\n"
                "2. Report Road Incident\n"
                "3. Register as Driver\n"
                "4. Subscribe to Route Alerts\n"
                "5. Unsubscribe from Alerts\n"
                "0. Exit"
            )

        # ── Option 1: Check Route Status ──────────────────────────
        if l0 == "1":
            if l1 == "":
                menu = "CON Select Route:\n"
                for i, r in enumerate(routes, 1):
                    short = USSD_ROUTE_LABELS.get(r.name, r.name[:18])
                    menu += f"{i}. {short}\n"
                menu += "0. Back"
                return menu

            try:
                idx = int(l1) - 1
                if 0 <= idx < len(routes):
                    r = routes[idx]
                    st = STATUS_EMOJI.get(r.status, r.status)
                    latest = r.incidents.order_by("-created_at").first()
                    msg  = f"END {r.origin} to {r.destination}\n"
                    msg += f"Status: {st}\n"
                    msg += f"Risk Score: {r.risk_score}/100\n"
                    if latest:
                        msg += f"Latest: {latest.incident_type}\n"
                        msg += f"Near: {latest.location_name}\n"
                        msg += f"Severity: {latest.severity}\n"
                    msg += "\nDrive safe! - RouteWise TZ"
                    _log_ussd(phone_number, f"checked route: {r.name}")
                    return msg
            except (ValueError, IndexError):
                pass
            return "END Invalid selection. Try again."

        # ── Option 2: Report Incident ──────────────────────────────
        if l0 == "2":
            if l1 == "":
                return (
                    "CON Select Incident Type:\n"
                    "1. Accident\n2. Flood\n3. Bad Road\n"
                    "4. Traffic Jam\n5. Road Block\n"
                    "6. Police Checkpoint\n7. Fuel Shortage\n"
                    "8. Theft Hotspot\n9. Vehicle Breakdown\n"
                    "0. Back"
                )
            if l1 not in INCIDENT_MENU:
                return "END Invalid type. Please try again."

            if l2 == "":
                itype = INCIDENT_MENU[l1]
                return f"CON Reporting: {itype}\n\nEnter location name\n(town or landmark):"

            if l3 == "":
                return (
                    f"CON Location: {l2}\n\n"
                    "Enter route hint\n"
                    "(e.g. Morogoro or DSM-Dodoma\nor type 0 for nearest route):"
                )

            # ── Create the incident ────────────────────────────────
            itype    = INCIDENT_MENU[l1]
            location = l2
            hint     = l3

            route = _find_route_by_hint_ussd(hint) or (routes[0] if routes else None)
            if not route:
                return "END Could not match a route. Report via web."

            segment = find_closest_segment(route, location)
            try:
                report = IncidentReport.objects.create(
                    route=route,
                    segment=segment,
                    reporter_name=f"USSD:{phone_number}",
                    reporter_phone=phone_number,
                    incident_type=itype,
                    location_name=location,
                    description=f"Reported via USSD by {phone_number} (RouteWise TZ)",
                    severity="Medium",
                )
                finalize_incident_report(report, notify_phone=phone_number)
                _log_ussd(phone_number, f"reported {itype} @ {location}")
                return (
                    f"END Incident Reported!\n"
                    f"Type: {itype}\n"
                    f"Location: {location}\n"
                    f"Route: {route.origin} to {route.destination}\n\n"
                    f"Drivers on this route will be alerted.\n"
                    f"Thank you! - RouteWise TZ"
                )
            except Exception as exc:
                logger.error("[USSD] Incident create failed: %s", exc)
                return "END Error saving report. Please try again."

        # ── Option 3: Register as Driver ──────────────────────────
        if l0 == "3":
            if l1 == "":
                return "CON Driver Registration\n\nStep 1 of 3\nEnter your full name:"

            if l2 == "":
                return (
                    "CON Step 2 of 3: Vehicle Type\n\n"
                    "1. Truck\n2. Bus\n3. Van\n4. Boda\n5. Bajaji"
                )

            if l2 not in VEHICLE_MENU:
                return "END Invalid vehicle type. Try again."

            if l3 == "":
                menu = "CON Step 3 of 3: Select Main Route\n"
                for i, r in enumerate(routes[:6], 1):
                    short = USSD_ROUTE_LABELS.get(r.name, r.name[:18])
                    menu += f"{i}. {short}\n"
                menu += "0. Other"
                return menu

            route_name = "Other"
            try:
                ridx = int(l3) - 1
                if 0 <= ridx < len(routes):
                    route_name = routes[ridx].name
            except ValueError:
                pass

            driver, created = Driver.objects.get_or_create(
                phone_number=phone_number,
                defaults={
                    "full_name":      l1,
                    "vehicle_type":   VEHICLE_MENU.get(l2, "Van"),
                    "transport_type": "General Transport",
                    "main_route":     route_name,
                },
            )
            if created:
                _log_ussd(phone_number, f"registered driver: {l1}")
                return (
                    f"END Registration Complete!\n"
                    f"Name: {l1}\n"
                    f"Vehicle: {VEHICLE_MENU.get(l2)}\n"
                    f"Route: {route_name[:30]}\n\n"
                    f"You'll receive road alerts.\n"
                    f"- RouteWise TZ"
                )
            else:
                return (
                    f"END Already registered!\n"
                    f"Welcome back, {driver.full_name}.\n"
                    f"- RouteWise TZ"
                )

        # ── Option 4: Subscribe to Alerts ─────────────────────────
        if l0 == "4":
            if l1 == "":
                menu = "CON Subscribe to SMS Alerts:\n"
                for i, r in enumerate(routes, 1):
                    short = USSD_ROUTE_LABELS.get(r.name, r.name[:18])
                    st = "!" if r.status in ("High Risk", "Avoid") else ""
                    menu += f"{i}. {short}{st}\n"
                menu += "0. Back"
                return menu

            try:
                idx = int(l1) - 1
                if 0 <= idx < len(routes):
                    r = routes[idx]
                    sub, created = ATSubscription.objects.get_or_create(
                        phone_number=phone_number,
                        route=r,
                        defaults={"channel": "SMS", "is_active": True},
                    )
                    if not created and not sub.is_active:
                        sub.is_active = True
                        sub.save(update_fields=["is_active"])
                        created = True

                    _log_ussd(phone_number, f"subscribed to {r.name}")
                    if created:
                        return (
                            f"END Subscribed!\n"
                            f"Route: {r.origin} to {r.destination}\n\n"
                            f"You'll get SMS alerts when\n"
                            f"incidents are reported.\n"
                            f"Reply STOP to unsubscribe.\n"
                            f"- RouteWise TZ"
                        )
                    return f"END Already subscribed to\n{r.name[:40]}"
            except (ValueError, IndexError):
                pass
            return "END Invalid selection."

        # ── Option 5: Unsubscribe ──────────────────────────────────
        if l0 == "5":
            subs = list(ATSubscription.objects.filter(phone_number=phone_number, is_active=True))
            if l1 == "":
                if not subs:
                    return "END You have no active\nsubscriptions.\n- RouteWise TZ"
                menu = "CON Your Subscriptions:\n"
                for i, s in enumerate(subs, 1):
                    short = USSD_ROUTE_LABELS.get(s.route.name, s.route.name[:16])
                    menu += f"{i}. {short}\n"
                menu += "0. Cancel"
                return menu

            try:
                idx = int(l1) - 1
                if 0 <= idx < len(subs):
                    s = subs[idx]
                    s.is_active = False
                    s.save(update_fields=["is_active"])
                    return f"END Unsubscribed from\n{s.route.name[:40]}\n- RouteWise TZ"
            except (ValueError, IndexError):
                pass
            return "END Invalid selection."

        # ── Option 0: Exit ─────────────────────────────────────────
        if l0 == "0":
            return "END Thank you for using RouteWise TZ!\nDrive safe. 🇹🇿"

        return "END Invalid option. Dial again."

    # ── Incoming SMS handler ──────────────────────────────────────
    def handle_incoming_sms(
        self,
        from_number: str,
        text: str,
        to_number: str = "",
        message_id: str = "",
    ) -> dict:
        """
        Process an SMS report from a driver.
        Format: TYPE#Location#RouteHint
        Returns dict with {status, report, alert}.
        """
        from .messaging import parse_incoming_message, build_outgoing_alert
        from .incident_processing import finalize_incident_report
        from ..segment_utils import find_closest_segment
        from ..models import TransportRoute, IncidentReport

        logger.info("[AT SMS-IN] from=%s text=%s", from_number, text)

        # Handle STOP keyword
        if text.strip().upper() in ("STOP", "UNSUBSCRIBE", "CANCEL"):
            from ..models import ATSubscription
            count = ATSubscription.objects.filter(
                phone_number=from_number, is_active=True
            ).update(is_active=False)
            reply = f"You have been unsubscribed from all RouteWise TZ alerts. ({count} routes)"
            self.send_sms(from_number, reply)
            return {"status": "unsubscribed", "count": count}

        # Handle STATUS keyword
        if text.strip().upper().startswith("STATUS"):
            parts = text.strip().upper().split()
            hint = " ".join(parts[1:]) if len(parts) > 1 else ""
            route = _find_route_by_hint_ussd(hint)
            if route:
                reply = (
                    f"RouteWise TZ: {route.origin}→{route.destination}\n"
                    f"Status: {route.status} | Risk: {route.risk_score}/100"
                )
                latest = route.incidents.order_by("-created_at").first()
                if latest:
                    reply += f"\nLatest: {latest.incident_type} @ {latest.location_name}"
            else:
                routes_str = ", ".join(
                    r.destination for r in TransportRoute.objects.order_by("name")[:5]
                )
                reply = f"RouteWise TZ: Text STATUS <city> e.g. STATUS Morogoro. Routes: {routes_str}"
            self.send_sms(from_number, reply)
            return {"status": "status_sent"}

        # Handle HELP keyword
        if text.strip().upper() in ("HELP", "INFO", "?"):
            reply = (
                "RouteWise TZ Help:\n"
                "Report: TYPE#Location#Route\n"
                "e.g. ACCIDENT#Chalinze#Morogoro\n"
                "Types: ACCIDENT,FLOOD,BADROAD,\n"
                "TRAFFIC,ROADBLOCK,FUEL,THEFT\n"
                "Check: STATUS Morogoro\n"
                "Stop: STOP"
            )
            self.send_sms(from_number, reply)
            return {"status": "help_sent"}

        # Parse incident report
        parsed = parse_incoming_message(text)
        if not parsed:
            reply = (
                "RouteWise TZ: Format not recognised.\n"
                "Use: TYPE#Location#Route\n"
                "e.g. FLOOD#Kilosa#Morogoro\n"
                "Text HELP for more info."
            )
            self.send_sms(from_number, reply)
            return {"status": "parse_failed", "text": text}

        route = _find_route_by_hint_ussd(parsed["route_hint"])
        if not route:
            route = TransportRoute.objects.order_by("name").first()

        segment = find_closest_segment(route, parsed["location_name"]) if route else None
        severity = "High" if parsed["incident_type"] in ("Accident", "Flood", "Theft Hotspot") else "Medium"

        report = IncidentReport.objects.create(
            route=route,
            segment=segment,
            reporter_name=f"SMS:{from_number}",
            reporter_phone=from_number,
            incident_type=parsed["incident_type"],
            location_name=parsed["location_name"],
            description=f"Reported via SMS: {text}",
            severity=severity,
        )
        ai, alert = finalize_incident_report(report, notify_phone=from_number)

        # Confirmation back to reporter
        confirm = (
            f"RouteWise TZ: Received!\n"
            f"{parsed['incident_type']} @ {parsed['location_name']}\n"
            f"Risk: {ai.get('risk_score', 0)}/100\n"
            f"Drivers alerted. Thank you!"
        )
        self.send_sms(from_number, confirm)

        return {"status": SUCCESS, "report_id": report.pk, "alert": alert, "ai": ai}

    # ── Voice callback XML ────────────────────────────────────────
    def build_voice_response(self, incident_type: str, location: str,
                              route_name: str, delay: int) -> str:
        """Return AT Voice Actions XML for a critical incident alert call."""
        msg = (
            f"Hello. This is an urgent alert from RouteWise Tanzania. "
            f"A {incident_type} has been reported near {location} "
            f"on the {route_name} route. "
            f"Expected delay is approximately {delay} minutes. "
            f"Please drive with caution and check the RouteWise app for updates. "
            f"Stay safe. Goodbye."
        )
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            f'<Say voice="en-US-Wavenet-F" playBeep="false">{msg}</Say>'
            "<Hangup/>"
            "</Response>"
        )


# ── Module-level singleton ────────────────────────────────────────
at = ATService()


# ── Helpers ───────────────────────────────────────────────────────
def _log_simulated(channel: str, phone: str, message: str) -> None:
    truncated = message[:120] + "…" if len(message) > 120 else message
    print(f"[RouteWise {channel} → {phone}] {truncated}")
    logger.info("[AT %s simulated → %s] %s", channel, phone, truncated)


def _log_ussd(phone: str, action: str) -> None:
    logger.info("[AT USSD] %s – %s", phone, action)


def _find_route_by_hint_ussd(hint: str):
    """Fuzzy route matching used inside USSD/SMS handlers."""
    from ..models import TransportRoute
    hint = (hint or "").lower().strip()
    if not hint or hint == "0":
        return None
    for r in TransportRoute.objects.all():
        if r.origin.lower() in hint and r.destination.lower() in hint:
            return r
        combined = f"{r.origin} {r.destination} {r.name}".lower()
        words = [w for w in hint.split() if len(w) > 3]
        if words and all(w in combined for w in words):
            return r
    for r in TransportRoute.objects.all():
        combined = f"{r.origin} {r.destination}".lower()
        if any(w in combined for w in hint.split() if len(w) > 3):
            return r
    return None


# ── Convenience functions (used by views + incident_processing) ───
def send_incident_broadcast(route, message: str, severity: str = "Medium") -> dict:
    """Broadcast an incident alert to all route subscribers and drivers."""
    return at.broadcast_route_alert(route, message, severity)


def reward_reporter(report) -> bool:
    """Send airtime reward when a report is sufficiently verified."""
    from ..models import AirtimeReward
    phone = (report.reporter_phone or "").strip()
    if not phone or phone.startswith("+2557000"):  # skip system numbers
        return False

    # Only reward once per report
    if AirtimeReward.objects.filter(incident=report).exists():
        return False

    amount = 500  # TZS 500 ≈ 2 minutes of calls
    result = at.send_airtime(phone, amount, "TZS")
    AirtimeReward.objects.create(
        phone_number=phone,
        amount=amount,
        currency_code="TZS",
        reason=f"Community incident report: {report.incident_type} @ {report.location_name}",
        incident=report,
        status=SUCCESS if result["status"] == SUCCESS else SIMULATED,
        at_response=str(result.get("response", result.get("status", ""))),
    )
    logger.info("[AT Airtime Reward] TZS %s → %s for report %s", amount, phone, report.pk)
    return True
