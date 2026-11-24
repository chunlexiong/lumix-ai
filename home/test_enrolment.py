import hmac
import json
import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Enrolment, Student


class EnrolmentTests(TestCase):
    def setUp(self):
        self.parent = get_user_model().objects.create_user(
            username="parent@example.com", email="parent@example.com", password="a-family-test-secret"
        )
        self.student = Student.objects.create(parent=self.parent, name="Example student")
        self.class_url = reverse("enrolment_select", args=["january-home", 6])

    def select_workshop(self):
        response = self.client.post(self.class_url, {"student": self.student.pk, "session": "jan-22"})
        enrolment = Enrolment.objects.get(student=self.student)
        self.assertRedirects(response, reverse("enrolment_payment", args=[enrolment.pk]), fetch_redirect_response=False)
        return enrolment

    def test_registration_keeps_the_selected_class_and_sign_in_reuses_student(self):
        self.assertRedirects(
            self.client.get(self.class_url),
            f"{reverse('family_register')}?next={self.class_url}",
            fetch_redirect_response=False,
        )
        signup = self.client.post(reverse("family_register"), {
            "first_name": "Another parent",
            "username": "Another.Parent@example.com",
            "student_name": "Another student",
            "password1": "family-test-password-9472",
            "password2": "family-test-password-9472",
            "next": self.class_url,
        })
        self.assertRedirects(signup, self.class_url)
        self.client.post(reverse("family_logout"))
        sign_in = self.client.post(reverse("family_login"), {
            "username": "Another.Parent@example.com", "password": "family-test-password-9472",
        }, follow=True)
        self.assertContains(sign_in, "Another student")
        self.assertEqual(Student.objects.filter(parent__email="another.parent@example.com").count(), 1)

    @override_settings(DEBUG=True, STRIPE_SECRET_KEY="", STRIPE_WEBHOOK_SECRET="", STRIPE_CHECKOUT_ORIGIN="")
    def test_preview_preserves_catalogue_price_and_never_marks_paid(self):
        self.client.force_login(self.parent)
        enrolment = self.select_workshop()
        self.select_workshop()
        self.assertEqual(Enrolment.objects.count(), 1)
        self.assertEqual(enrolment.amount_cents, 24000)
        self.assertIn("22–24 Jan", enrolment.schedule)
        url = reverse("enrolment_payment", args=[enrolment.pk])
        preview = self.client.post(url, {"amount_cents": "1"}, follow=True)
        self.assertContains(preview, "No money was charged")
        enrolment.refresh_from_db()
        self.assertEqual(enrolment.status, Enrolment.Status.PREVIEW)
        self.assertEqual(enrolment.amount_cents, 24000)
        self.assertIsNone(enrolment.paid_at)

    def test_family_cannot_select_another_familys_student_or_open_their_payment(self):
        self.client.force_login(self.parent)
        enrolment = self.select_workshop()
        outsider = get_user_model().objects.create_user(username="other@example.com")
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(reverse("enrolment_payment", args=[enrolment.pk])).status_code, 404)
        response = self.client.post(self.class_url, {"student": self.student.pk, "session": "jan-15"})
        self.assertIn("student", response.context["form"].errors)
        self.assertEqual(Enrolment.objects.count(), 1)

    @override_settings(
        STRIPE_SECRET_KEY="sk_test_fixture",
        STRIPE_WEBHOOK_SECRET="whsec_fixture",
        STRIPE_CHECKOUT_ORIGIN="https://example.com",
    )
    def test_stripe_session_is_reused_and_confirmation_checks_the_amount(self):
        self.client.force_login(self.parent)
        enrolment = self.select_workshop()
        url = reverse("enrolment_payment", args=[enrolment.pk])
        session = {
            "id": "cs_test_fixture",
            "object": "checkout.session",
            "client_reference_id": str(enrolment.pk),
            "mode": "payment",
            "currency": "aud",
            "amount_total": enrolment.amount_cents,
            "livemode": False,
            "url": "https://checkout.stripe.com/c/pay/cs_test_fixture",
            "status": "open",
            "payment_status": "unpaid",
        }
        with patch("home.enrolment_views.create_session", return_value=session) as launch, patch(
            "home.enrolment_views.retrieve_session", return_value=session
        ) as retrieve:
            self.assertRedirects(self.client.post(url), session["url"], fetch_redirect_response=False)
            self.assertRedirects(self.client.post(url), session["url"], fetch_redirect_response=False)
            launch.assert_called_once()
            retrieve.assert_called_once_with(session["id"])

        paid = {**session, "status": "complete", "payment_status": "paid"}
        webhook = reverse("stripe_webhook")

        def send_event(data):
            body = json.dumps({"type": "checkout.session.completed", "data": {"object": data}}).encode()
            timestamp = int(time.time())
            digest = hmac.digest(b"whsec_fixture", f"{timestamp}.".encode() + body, "sha256").hex()
            return self.client.post(
                webhook, body, content_type="application/json",
                HTTP_STRIPE_SIGNATURE=f"t={timestamp},v1={digest}",
            )

        self.assertEqual(self.client.post(webhook, "{}", content_type="application/json").status_code, 400)
        self.assertEqual(send_event({**paid, "amount_total": 1}).status_code, 200)
        enrolment.refresh_from_db()
        self.assertEqual(enrolment.status, Enrolment.Status.PENDING)
        self.assertEqual(send_event(paid).status_code, 200)
        self.assertEqual(send_event(paid).status_code, 200)
        enrolment.refresh_from_db()
        self.assertEqual(enrolment.status, Enrolment.Status.TESTED)
        self.assertContains(self.client.get(url), "Test payment complete.")
