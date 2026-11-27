import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .models import Enrolment


logger = logging.getLogger(__name__)


def send_payment_confirmation_email(enrolment):
    """Send one confirmation email for a paid enrolment, if not already sent."""
    with transaction.atomic():
        current = Enrolment.objects.select_for_update().select_related(
            "student__parent"
        ).get(pk=enrolment.pk)
        is_test_payment = current.status == Enrolment.Status.TESTED
        if current.status not in {Enrolment.Status.PAID, Enrolment.Status.TESTED}:
            return False
        if is_test_payment and current.stripe_mode != "test":
            return False

        sent_field = (
            "test_payment_confirmation_sent_at"
            if is_test_payment
            else "payment_confirmation_sent_at"
        )
        if getattr(current, sent_field):
            return True

        parent_email = current.parent_email
        if not parent_email:
            logger.error("Cannot send payment confirmation for enrolment %s: parent email is missing.", current.pk)
            return False

        payment_method = {
            Enrolment.PaymentMethod.BANK_TRANSFER: "bank transfer",
            Enrolment.PaymentMethod.CARD: "card",
        }.get(current.payment_method, "not recorded")
        subject_prefix = "[TEST] " if is_test_payment else ""
        subject = f"{subject_prefix}Payment confirmation for {current.student.name}'s LUMIX AI enrolment"
        payment_message = (
            "This was a Stripe test transaction. No money was charged and this does not reserve a place."
            if is_test_payment
            else "We have received your payment for this LUMIX AI enrolment."
        )
        completion_message = (
            "This test email confirms that the app's payment email delivery is working."
            if is_test_payment
            else "Your enrolment is confirmed. Please keep this email for your records."
        )
        body = "\n".join([
            f"Hello {current.student.parent.first_name or 'there'},",
            "",
            payment_message,
            "",
            f"Student: {current.student.name}",
            f"Course: {current.program_title}",
            f"Class: {current.class_title}",
            f"Schedule: {current.schedule}",
            f"Sessions: {current.session_count}",
            f"Amount: AUD {current.total}",
            f"Payment method: {payment_method}",
            *([f"Bank transfer reference: {current.bank_transfer_reference}"]
              if current.payment_method == Enrolment.PaymentMethod.BANK_TRANSFER
              and current.bank_transfer_reference else []),
            "",
            completion_message,
            "",
            "LUMIX AI",
        ])

        try:
            delivered = send_mail(
                subject,
                body,
                settings.DEFAULT_FROM_EMAIL,
                [parent_email],
                fail_silently=False,
            )
        except Exception:
            logger.exception("Could not send payment confirmation for enrolment %s.", current.pk)
            return False

        if delivered != 1:
            logger.error("Payment confirmation for enrolment %s was not accepted by the email backend.", current.pk)
            return False

        sent_at = timezone.now()
        setattr(current, sent_field, sent_at)
        current.save(update_fields=[sent_field])
        setattr(enrolment, sent_field, sent_at)
        return True
