from django.test import TestCase

from .models import ATSubscription, Driver, TransportRoute, USSDSession
from .services.at_service import at


class USSDPersistenceTests(TestCase):
    """Verify USSD flows persist to the database and record an action on the session."""

    SERVICE_CODE = "*384*5959#"
    PHONE = "+255700000001"

    def setUp(self):
        self.route = TransportRoute.objects.create(
            name="Dar es Salaam → Morogoro",
            origin="Dar es Salaam",
            destination="Morogoro",
            risk_score=40,
            status="Caution",
        )

    def _ussd(self, session_id, text):
        return at.handle_ussd(
            session_id=session_id,
            service_code=self.SERVICE_CODE,
            phone_number=self.PHONE,
            text=text,
            network_code="63902",
        )

    def test_registration_creates_phone_only_driver(self):
        session_id = "reg-session-1"
        # Walk the full registration state machine.
        self._ussd(session_id, "3")
        self._ussd(session_id, "3*Juma Hassan")
        self._ussd(session_id, "3*Juma Hassan*1")
        final = self._ussd(session_id, "3*Juma Hassan*1*1")

        self.assertTrue(final.startswith("END Registration Complete!"))

        driver = Driver.objects.get(phone_number=self.PHONE)
        self.assertEqual(driver.full_name, "Juma Hassan")
        self.assertEqual(driver.vehicle_type, "Truck")
        self.assertIsNone(driver.user_id)
        self.assertEqual(driver.main_route, self.route.name)

        session = USSDSession.objects.get(session_id=session_id)
        self.assertTrue(session.action_taken)
        self.assertIn("register", session.action_taken)

    def test_subscription_persists(self):
        session_id = "sub-session-1"
        self._ussd(session_id, "4")
        final = self._ussd(session_id, "4*1")

        self.assertTrue(final.startswith("END Subscribed!"))
        self.assertTrue(
            ATSubscription.objects.filter(
                phone_number=self.PHONE, route=self.route, is_active=True
            ).exists()
        )

        session = USSDSession.objects.get(session_id=session_id)
        self.assertIn("subscribe", session.action_taken)

    def test_unsubscribe_deactivates(self):
        ATSubscription.objects.create(
            phone_number=self.PHONE, route=self.route, channel="SMS", is_active=True
        )
        session_id = "unsub-session-1"
        self._ussd(session_id, "5")
        final = self._ussd(session_id, "5*1")

        self.assertTrue(final.startswith("END Unsubscribed from"))
        sub = ATSubscription.objects.get(phone_number=self.PHONE, route=self.route)
        self.assertFalse(sub.is_active)
