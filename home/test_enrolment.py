import hmac
import json
import re
import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .checkout import CheckoutError
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

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
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
        self.assertRedirects(signup, reverse("family_verify_email"))
        registered = get_user_model().objects.get(username="another.parent@example.com")
        self.assertFalse(registered.is_active)
        code = re.search(r"\b[0-9]{6}\b", mail.outbox[-1].body)[0]
        verification = self.client.post(reverse("family_verify_email"), {"code": code})
        self.assertRedirects(verification, self.class_url)
        registered.refresh_from_db()
        self.assertTrue(registered.is_active)
        self.client.post(reverse("family_logout"))
        sign_in = self.client.post(reverse("family_login"), {
            "username": "Another.Parent@example.com", "password": "family-test-password-9472",
        }, follow=True)
        self.assertContains(sign_in, "Another student")
        self.assertEqual(Student.objects.filter(parent__email="another.parent@example.com").count(), 1)

    def test_continuing_to_payment_lists_the_submitted_enrolment_immediately(self):
        self.client.force_login(self.parent)
        account = reverse("family_account")
        self.assertEqual(self.client.get(self.class_url).status_code, 200)
        self.assertEqual(self.client.post(self.class_url, {"student": self.student.pk}).status_code, 200)
        self.assertFalse(Enrolment.objects.exists())
        self.assertContains(self.client.get(account), "No enrolled classes yet.")

        enrolment = self.select_workshop()
        self.select_workshop()
        page = self.client.get(account)
        card, = page.context["student_cards"]
        self.assertEqual(card["enrolled"], [enrolment])
        self.assertEqual(card["pending"], [enrolment])
        self.assertContains(page, "Enrolled classes", count=1)
        self.assertNotContains(page, ">Payment</span>")
        self.assertContains(page, "Awaiting payment", count=1)
        courses_url = reverse("courses")
        self.assertContains(page, f'href="{courses_url}#january-home-class-6"', count=1)
        self.assertContains(self.client.get(courses_url), 'id="january-home-class-6"', count=1)
        payment_url = reverse("enrolment_payment", args=[enrolment.pk])
        self.assertContains(page, f'href="{payment_url}"', count=1)

        self.assertEqual(
            self.client.post(self.class_url, {"student": self.student.pk, "session": "jan-15"}).status_code, 302
        )
        page = self.client.get(account)
        self.assertContains(page, "Manage payment", count=2)
        for booking in self.student.enrolments.all():
            self.assertContains(page, booking.schedule, count=1)
            booking_url = reverse("enrolment_payment", args=[booking.pk])
            self.assertContains(page, f'href="{booking_url}"', count=1)

        enrolment.status = Enrolment.Status.PAID
        enrolment.save(update_fields=["status"])
        page = self.client.get(account)
        self.assertContains(page, "1 payment due")
        self.assertContains(page, "Manage payment", count=1)
        self.assertContains(page, "View enrolment", count=1)

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

    @override_settings(
        BANK_TRANSFER_ACCOUNT_NAME="Fixture Education",
        BANK_TRANSFER_BSB="000-000",
        BANK_TRANSFER_ACCOUNT_NUMBER="00000001",
        STRIPE_SECRET_KEY="sk_test_fixture",
        STRIPE_WEBHOOK_SECRET="whsec_fixture",
        STRIPE_CHECKOUT_ORIGIN="https://example.com",
    )
    def test_default_bank_details_are_visible_and_only_staff_can_confirm_transfer(self):
        self.client.force_login(self.parent)
        enrolment = self.select_workshop()
        url = reverse("enrolment_payment", args=[enrolment.pk])
        page = self.client.get(url)
        enrolment.refresh_from_db()
        reference = enrolment.bank_transfer_reference
        self.assertContains(page, "Recommended")
        self.assertContains(page, "Card payment")
        self.assertContains(page, "00000001")
        self.assertContains(page, reference)
        self.assertContains(page, "$240")
        self.assertNotContains(page, "Current method")
        self.assertRegex(reference, r"^[1-9][0-9]{4}$")
        self.assertEqual(enrolment.status, Enrolment.Status.PENDING)
        self.assertIsNone(enrolment.paid_at)
        self.assertContains(self.client.get(url), reference)

        inspect_url = reverse("enrolments:inspect", args=[enrolment.pk])
        viewer = get_user_model().objects.create_user(username="enrolment-reviewer")
        viewer.user_permissions.add(*Permission.objects.filter(
            codename__in=["access_admin", "view_enrolment"],
            content_type__app_label__in=["wagtailadmin", "home"],
        ))
        self.client.force_login(viewer)
        self.assertNotContains(self.client.get(inspect_url), "Mark as paid")
        # Wagtail redirects permission denials to its dashboard.
        self.assertRedirects(self.client.post(inspect_url, {"received": "yes"}), reverse("wagtailadmin_home"))
        enrolment.refresh_from_db()
        self.assertEqual(enrolment.status, Enrolment.Status.PENDING)
        self.assertIsNone(enrolment.paid_at)

        operator = get_user_model().objects.create_user(username="transfer-operator")
        operator.user_permissions.add(*Permission.objects.filter(
            codename__in=["access_admin", "change_enrolment"],
            content_type__app_label__in=["wagtailadmin", "home"],
        ))
        self.client.force_login(operator)
        self.assertContains(self.client.get(inspect_url), "Mark as paid")
        self.assertContains(self.client.get(inspect_url), reference)
        self.assertRedirects(self.client.post(inspect_url), inspect_url)
        enrolment.refresh_from_db()
        self.assertEqual(enrolment.status, Enrolment.Status.PENDING)
        self.assertRedirects(self.client.post(inspect_url, {"received": "yes"}), inspect_url)
        enrolment.refresh_from_db()
        self.assertEqual(enrolment.status, Enrolment.Status.PAID)
        self.assertIsNotNone(enrolment.paid_at)
        confirmed_at = enrolment.paid_at
        self.assertRedirects(self.client.post(inspect_url, {"received": "yes"}), inspect_url)
        enrolment.refresh_from_db()
        self.assertEqual(enrolment.paid_at, confirmed_at)

        self.client.force_login(self.parent)
        self.assertContains(self.client.get(url), "Payment received")
        page = self.client.get(reverse("family_account"))
        card, = page.context["student_cards"]
        self.assertEqual(card["enrolled"], [enrolment])
        self.assertEqual(card["pending"], [])
        self.assertContains(page, 'class="enrol-record-row enrol-record-row-paid"')
        self.assertContains(page, ">Paid</span>")
        self.assertContains(page, "View enrolment")
        self.assertNotContains(page, "Manage payment")
        self.assertNotContains(page, 'class="enrol-record-amount"')

    @override_settings(
        BANK_TRANSFER_ACCOUNT_NAME="Fixture Education",
        BANK_TRANSFER_BSB="000000",
        BANK_TRANSFER_ACCOUNT_NUMBER="00000001",
        STRIPE_SECRET_KEY="",
        STRIPE_WEBHOOK_SECRET="",
        STRIPE_CHECKOUT_ORIGIN="",
    )
    def test_bank_reference_retries_a_collision_and_keeps_previous_references(self):
        self.client.force_login(self.parent)
        existing = self.select_workshop()
        existing_url = reverse("enrolment_payment", args=[existing.pk])
        with patch("home.enrolment_views.secrets.randbelow", return_value=42):
            self.assertRedirects(self.client.post(existing_url, {"method": "bank"}), existing_url)
        existing.refresh_from_db()
        self.assertEqual(existing.bank_transfer_reference, "10042")

        payment = self.client.post(self.class_url, {"student": self.student.pk, "session": "jan-15"})
        with patch("home.enrolment_views.secrets.randbelow", side_effect=[42, 38271]) as generate:
            self.assertRedirects(self.client.post(payment.url, {"method": "bank"}), payment.url)
        self.assertEqual(generate.call_count, 2)
        new = self.student.enrolments.get(session_key="jan-15")
        self.assertEqual(new.bank_transfer_reference, "48271")
        self.assertEqual(new.status, Enrolment.Status.BANK_PENDING)

        legacy_reference = "LX1234567890ABCDEF"
        existing.previous_bank_transfer_reference = legacy_reference
        existing.save(update_fields=["previous_bank_transfer_reference"])
        self.assertRedirects(self.client.post(existing_url, {"method": "bank"}), existing_url)
        existing.refresh_from_db()
        self.assertEqual(existing.bank_transfer_reference, "10042")
        self.assertEqual(existing.previous_bank_transfer_reference, legacy_reference)
        page = self.client.get(existing_url)
        self.assertContains(page, "10042")
        self.assertNotContains(page, legacy_reference)

        operator = get_user_model().objects.create_user(username="bank-reference-reviewer")
        operator.user_permissions.add(*Permission.objects.filter(
            codename__in=["access_admin", "view_enrolment", "change_enrolment"],
            content_type__app_label__in=["wagtailadmin", "home"],
        ))
        self.client.force_login(operator)
        self.assertContains(self.client.get(reverse("enrolments:inspect", args=[existing.pk])), legacy_reference)
        self.assertContains(self.client.get(reverse("enrolments:index"), {"q": legacy_reference}), existing.program_title)

    @override_settings(
        DEBUG=False,
        BANK_TRANSFER_ACCOUNT_NAME="Fixture Education",
        BANK_TRANSFER_BSB="000000",
        BANK_TRANSFER_ACCOUNT_NUMBER="00000001",
        STRIPE_SECRET_KEY="rk_live_fixture",
        STRIPE_WEBHOOK_SECRET="whsec_fixture",
        STRIPE_CHECKOUT_ORIGIN="https://example.com",
    )
    def test_reconciling_a_bank_transfer_requires_closing_any_open_stripe_session(self):
        self.client.force_login(self.parent)
        enrolment = self.select_workshop()
        enrolment.stripe_mode = "live"
        enrolment.stripe_session_id = "cs_live_fixture"
        enrolment.save(update_fields=["stripe_mode", "stripe_session_id"])
        url = reverse("enrolment_payment", args=[enrolment.pk])
        session = {
            "id": enrolment.stripe_session_id, "client_reference_id": str(enrolment.pk),
            "currency": "aud", "amount_total": enrolment.amount_cents, "livemode": True,
            "mode": "payment", "status": "open", "payment_status": "unpaid",
        }
        self.assertContains(self.client.get(url), "Payment reference")
        enrolment.refresh_from_db()
        self.assertIsNotNone(enrolment.bank_transfer_reference)
        operator = get_user_model().objects.create_user(username="bank-reconciliation")
        operator.user_permissions.add(*Permission.objects.filter(
            codename__in=["access_admin", "change_enrolment"],
            content_type__app_label__in=["wagtailadmin", "home"],
        ))
        self.client.force_login(operator)
        inspect_url = reverse("enrolments:inspect", args=[enrolment.pk])

        with patch("home.checkout.retrieve_session", return_value=session), patch(
            "home.checkout.expire_session", side_effect=CheckoutError
        ):
            self.assertRedirects(self.client.post(inspect_url, {"received": "yes"}), inspect_url)
        enrolment.refresh_from_db()
        self.assertEqual(enrolment.status, Enrolment.Status.PENDING)
        self.assertIsNone(enrolment.paid_at)

        with patch("home.checkout.retrieve_session", return_value=session), patch(
            "home.checkout.expire_session", return_value={**session, "status": "expired"}
        ) as expire:
            self.assertRedirects(self.client.post(inspect_url, {"received": "yes"}), inspect_url)
            expire.assert_called_once_with(enrolment.stripe_session_id)
        enrolment.refresh_from_db()
        self.assertEqual(enrolment.status, Enrolment.Status.PAID)

    @override_settings(
        BANK_TRANSFER_ACCOUNT_NAME="Fixture Education",
        BANK_TRANSFER_BSB="000-000",
        BANK_TRANSFER_ACCOUNT_NUMBER="00000001",
        STRIPE_SECRET_KEY="sk_test_fixture",
        STRIPE_WEBHOOK_SECRET="whsec_fixture",
        STRIPE_CHECKOUT_ORIGIN="https://example.com",
    )
    def test_parent_can_open_payment_options_and_switch_to_card(self):
        self.client.force_login(self.parent)
        enrolment = self.select_workshop()
        url = reverse("enrolment_payment", args=[enrolment.pk])
        self.assertRedirects(self.client.post(url, {"method": "bank"}), url)
        enrolment.refresh_from_db()
        reference = enrolment.bank_transfer_reference

        # A bank enrolment can still hold a closed Stripe session from a previous choice.
        enrolment.stripe_session_id = "cs_test_closed_fixture"
        enrolment.stripe_mode = "test"
        enrolment.save(update_fields=["stripe_session_id", "stripe_mode"])
        account = self.client.get(reverse("family_account"))
        self.assertContains(account, "Manage payment")
        self.assertContains(account, "Awaiting bank transfer", count=1)
        self.assertNotContains(account, "Change payment method")
        self.assertNotContains(account, reference)
        self.assertNotContains(account, "00000001")
        options = self.client.get(url)
        self.assertContains(options, "Payment options")
        self.assertContains(options, "Bank transfer details")
        self.assertContains(options, "Recommended")
        self.assertContains(options, "Continue to card payment")
        self.assertContains(options, reference)
        self.assertNotContains(options, "Current method")
        enrolment.refresh_from_db()
        self.assertTrue(enrolment.awaiting_bank_transfer)
        self.assertEqual(enrolment.checkout_revision, 1)

        with patch("home.enrolment_views.create_session", side_effect=CheckoutError("Unavailable")) as launch:
            self.assertRedirects(self.client.post(url), url)
            launch.assert_not_called()
            unavailable = self.client.post(url, {"method": "card"})
            self.assertContains(unavailable, "Continue to card payment", status_code=503)
            self.assertTrue(unavailable.context["card_selected"])
            launch.assert_called_once()
        enrolment.refresh_from_db()
        self.assertEqual(enrolment.status, Enrolment.Status.BANK_PENDING)
        self.assertEqual(enrolment.bank_transfer_reference, reference)
        self.assertEqual(enrolment.stripe_session_id, "cs_test_closed_fixture")
        self.assertEqual(enrolment.checkout_revision, 1)

        session = {
            "id": "cs_test_new_fixture",
            "object": "checkout.session",
            "client_reference_id": str(enrolment.pk),
            "mode": "payment",
            "currency": "aud",
            "amount_total": enrolment.amount_cents,
            "livemode": False,
            "status": "open",
            "url": "https://checkout.stripe.com/c/pay/cs_test_new_fixture",
        }
        with patch("home.enrolment_views.create_session", return_value=session), patch(
            "home.enrolment_views.retrieve_session"
        ) as retrieve:
            self.assertRedirects(
                self.client.post(url, {"method": "card"}), session["url"], fetch_redirect_response=False,
            )
        retrieve.assert_not_called()
        enrolment.refresh_from_db()
        self.assertEqual(enrolment.status, Enrolment.Status.PENDING)
        self.assertEqual(enrolment.stripe_session_id, session["id"])
        self.assertEqual(enrolment.checkout_revision, 2)
        self.assertEqual(enrolment.bank_transfer_reference, reference)
        completed = {**session, "status": "complete", "payment_status": "paid"}
        with patch("home.enrolment_views.retrieve_session", return_value=completed):
            self.assertRedirects(self.client.get(url + "?session_id=" + session["id"]), url)
        enrolment.refresh_from_db()
        self.assertEqual(enrolment.status, Enrolment.Status.TESTED)
        self.assertEqual(enrolment.bank_transfer_reference, reference)

    @override_settings(
        STRIPE_SECRET_KEY="sk_test_fixture",
        STRIPE_PUBLISHABLE_KEY="pk_test_fixture",
        STRIPE_WEBHOOK_SECRET="whsec_fixture",
        STRIPE_CHECKOUT_ORIGIN="https://example.com",
    )
    def test_embedded_card_form_replaces_and_reuses_the_checkout_session(self):
        self.client.force_login(self.parent)
        enrolment = self.select_workshop()
        url = reverse("enrolment_payment", args=[enrolment.pk])
        enrolment.stripe_session_id = "cs_test_old_fixture"
        enrolment.stripe_mode = "test"
        enrolment.save(update_fields=["stripe_session_id", "stripe_mode"])
        self.assertContains(self.client.get(url), 'data-embedded-key="pk_test_fixture"')
        old_session = {
            "id": enrolment.stripe_session_id, "ui_mode": "hosted", "client_reference_id": str(enrolment.pk),
            "mode": "payment", "currency": "aud", "amount_total": enrolment.amount_cents, "livemode": False,
            "status": "open",
        }
        embedded_session = {
            **old_session, "id": "cs_test_embedded_fixture", "ui_mode": "embedded_page",
            "client_secret": "test_checkout_client_secret",
        }
        with patch("home.enrolment_views.retrieve_session", return_value=old_session), patch(
            "home.enrolment_views.expire_session", return_value={**old_session, "status": "expired"},
        ) as expire, patch("home.checkout.stripe_request", return_value=embedded_session) as api:
            response = self.client.post(url, {"method": "embedded_card", "amount_cents": "1"})
            self.assertEqual(response.json(), {"clientSecret": embedded_session["client_secret"]})
            self.assertIn("no-store", response["Cache-Control"])
            expire.assert_called_once_with(old_session["id"])
            parameters = api.call_args.args[1]
            self.assertEqual(parameters["line_items[0][price_data][unit_amount]"], enrolment.amount_cents)
            self.assertEqual(parameters["ui_mode"], "embedded_page")
            self.assertEqual(parameters["return_url"], "https://example.com" + url + "?session_id={CHECKOUT_SESSION_ID}")
            self.assertNotIn("success_url", parameters)
            self.assertNotIn("cancel_url", parameters)
        enrolment.refresh_from_db()
        self.assertEqual(enrolment.stripe_session_id, embedded_session["id"])
        self.assertEqual(enrolment.checkout_revision, 2)
        self.assertIsNone(enrolment.paid_at)

        with patch("home.enrolment_views.retrieve_session", return_value=embedded_session), patch(
            "home.enrolment_views.create_session",
        ) as create:
            self.assertEqual(
                self.client.post(url, {"method": "embedded_card"}).json(),
                {"clientSecret": embedded_session["client_secret"]},
            )
            create.assert_not_called()

        outsider = get_user_model().objects.create_user(username="embedded-outsider@example.com")
        self.client.force_login(outsider)
        self.assertEqual(self.client.post(url, {"method": "embedded_card"}).status_code, 404)

    @override_settings(
        DEBUG=False,
        BANK_TRANSFER_ACCOUNT_NAME="",
        BANK_TRANSFER_BSB="",
        BANK_TRANSFER_ACCOUNT_NUMBER="",
        STRIPE_SECRET_KEY="",
    )
    def test_unconfigured_bank_transfer_cannot_be_selected(self):
        self.client.force_login(self.parent)
        enrolment = self.select_workshop()
        url = reverse("enrolment_payment", args=[enrolment.pk])
        self.assertNotContains(self.client.get(url), "Choose bank transfer")
        self.assertEqual(self.client.post(url, {"method": "bank"}).status_code, 503)
        enrolment.refresh_from_db()
        self.assertEqual(enrolment.status, Enrolment.Status.PENDING)
        self.assertIsNone(enrolment.bank_transfer_reference)
