from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ContactFormTests(SimpleTestCase):
    def setUp(self):
        self.url = reverse("contact")
        self.enquiry = {
            "name": "Example parent",
            "email": "parent@example.com",
            "program": "january-home",
            "age": "9–11",
            "message": "Do you have places for the January workshop?",
        }

    def test_class_link_prefills_program_and_age(self):
        response = self.client.get(self.url, {"program": "january-home", "age": "9–11"})
        self.assertContains(response, 'value="january-home" selected')
        self.assertContains(response, 'value="9–11" selected')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')

    def test_missing_and_invalid_email_do_not_send(self):
        for email in ("", "missing-at-sign"):
            with self.subTest(email=email):
                response = self.client.post(self.url, {**self.enquiry, "email": email})
                self.assertEqual(response.status_code, 400)
                self.assertIn("email", response.context["form"].errors)
        self.assertEqual(len(mail.outbox), 0)

    def test_mismatched_class_age_does_not_send(self):
        response = self.client.post(self.url, {**self.enquiry, "age": "9–12"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("age", response.context["form"].errors)
        self.assertEqual(len(mail.outbox), 0)

    def test_submission_sends_to_the_displayed_inbox(self):
        response = self.client.post(self.url, self.enquiry)
        self.assertRedirects(response, f"{self.url}#enquiry", fetch_redirect_response=False)
        [email] = mail.outbox
        self.assertEqual(email.to, [settings.CONTACT_EMAIL])
        self.assertEqual(email.reply_to, [self.enquiry["email"]])
        self.assertEqual(email.from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertIn(self.enquiry["message"], email.body)

        receipt = self.client.get(self.url)
        self.assertContains(receipt, "Your enquiry has been sent.")
        self.assertContains(receipt, f"mailto:{settings.CONTACT_EMAIL}")
        self.assertNotContains(self.client.get(self.url), "Your enquiry has been sent.")
        self.assertEqual(len(mail.outbox), 1)

    def test_delivery_failure_keeps_the_enquiry_text(self):
        with patch("home.views.EmailMessage.send", side_effect=OSError):
            response = self.client.post(self.url, self.enquiry)
        self.assertContains(response, "We couldn’t send your enquiry.", status_code=503)
        self.assertContains(response, self.enquiry["message"], status_code=503)
        self.assertNotContains(response, "Your enquiry has been sent.", status_code=503)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_console_backend_does_not_report_delivery(self):
        with patch("home.views.EmailMessage.send") as send:
            response = self.client.post(self.url, self.enquiry)
        send.assert_not_called()
        self.assertContains(response, "We couldn’t send your enquiry.", status_code=503)

    def test_submission_requires_a_csrf_token(self):
        response = Client(enforce_csrf_checks=True).post(self.url, self.enquiry)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(mail.outbox), 0)
