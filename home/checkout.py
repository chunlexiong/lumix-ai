"""Create and verify Stripe-hosted Checkout Sessions."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from .models import Enrolment
from .payment_email import send_payment_confirmation_email


class CheckoutError(Exception):
    pass


def checkout_mode():
    key = settings.STRIPE_SECRET_KEY
    try:
        origin = urlsplit(settings.STRIPE_CHECKOUT_ORIGIN)
    except ValueError:
        return ""
    origin_valid = origin.netloc and not (origin.path.rstrip("/") or origin.query or origin.fragment)
    if not (origin_valid and settings.STRIPE_WEBHOOK_SECRET):
        return ""
    if key.startswith(("sk_live_", "rk_live_")) and origin.scheme == "https" and not settings.DEBUG:
        return "live"
    if key.startswith("sk_test_") and origin.scheme in {"http", "https"}:
        return "test"
    return ""


def stripe_request(path, data=None, idempotency_key=None, *, api_version=None):
    headers = {"Authorization": f"Bearer {settings.STRIPE_SECRET_KEY}"}
    if api_version:
        headers["Stripe-Version"] = api_version
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    payload = urlencode(data).encode() if data is not None else None
    request = Request(f"https://api.stripe.com/v1/checkout/sessions{path}", data=payload, headers=headers)
    try:
        with urlopen(request, timeout=8) as response:
            result = json.load(response)
    except (OSError, ValueError) as exc:
        raise CheckoutError("Stripe Checkout is unavailable.") from exc
    if not isinstance(result, dict) or result.get("object") != "checkout.session":
        raise CheckoutError("Stripe returned an unexpected response.")
    return result


def create_session(enrolment, *, embedded=False):
    origin = settings.STRIPE_CHECKOUT_ORIGIN.rstrip("/")
    payment = origin + reverse("enrolment_payment", args=[enrolment.pk])
    data = {
        "mode": "payment",
        "allowed_payment_method_types[0]": "card",
        "adaptive_pricing[enabled]": "false",
        "client_reference_id": str(enrolment.pk),
        "customer_email": enrolment.student.parent.email,
    }
    success_url = payment + "?session_id={CHECKOUT_SESSION_ID}"
    if embedded:
        data.update(ui_mode="embedded_page", return_url=success_url, redirect_on_completion="always")
    else:
        data.update(success_url=success_url, cancel_url=payment + "?cancelled=1")
    data.update({
        "line_items[0][quantity]": 1,
        "line_items[0][price_data][currency]": "aud",
        "line_items[0][price_data][unit_amount]": enrolment.amount_cents,
        "line_items[0][price_data][product_data][name]": f"{enrolment.program_title} · {enrolment.class_title}",
        "line_items[0][price_data][product_data][description]": enrolment.schedule,
    })
    request_fingerprint = hashlib.sha256(urlencode(data).encode()).hexdigest()
    idempotency_key = (
        f"enrolment-{enrolment.pk}-{enrolment.stripe_mode}-"
        f"{enrolment.checkout_revision}-{request_fingerprint}"
    )
    return stripe_request("", data, idempotency_key, api_version="2026-09-30.endive" if embedded else None)


def session_path(session_id):
    if not session_id.startswith(("cs_test_", "cs_live_")) or not session_id.replace("_", "").isalnum():
        raise CheckoutError("Invalid Checkout Session.")
    return f"/{session_id}"


def retrieve_session(session_id):
    return stripe_request(session_path(session_id))


def expire_session(session_id):
    return stripe_request(f"{session_path(session_id)}/expire", data={})


def session_matches(enrolment, session):
    return (
        session.get("client_reference_id") == str(enrolment.pk)
        and session.get("currency") == "aud"
        and session.get("amount_total") == enrolment.amount_cents
        and session.get("livemode") is (enrolment.stripe_mode == "live")
        and session.get("mode") == "payment"
    )


def confirm_session(enrolment, session):
    if enrolment.awaiting_bank_transfer or not session_matches(enrolment, session):
        return False
    if session.get("id") != enrolment.stripe_session_id:
        return False
    if session.get("payment_status") != "paid" or session.get("status") != "complete":
        return False
    if (
        enrolment.status == Enrolment.Status.PAID
        and enrolment.payment_method == Enrolment.PaymentMethod.BANK_TRANSFER
    ):
        return False
    status = Enrolment.Status.PAID if enrolment.stripe_mode == "live" else Enrolment.Status.TESTED
    update_fields = []
    if enrolment.status not in {status, Enrolment.Status.PAID}:
        enrolment.status = status
        enrolment.paid_at = timezone.now()
        update_fields.extend(["status", "paid_at"])
    if enrolment.payment_method != Enrolment.PaymentMethod.CARD:
        enrolment.payment_method = Enrolment.PaymentMethod.CARD
        update_fields.append("payment_method")
    if update_fields:
        enrolment.save(update_fields=update_fields)
    if enrolment.status in {Enrolment.Status.PAID, Enrolment.Status.TESTED}:
        send_payment_confirmation_email(enrolment)
    return True


def prepare_bank_transfer(enrolment, mode):
    session_id = enrolment.stripe_session_id
    if session_id and (enrolment.stripe_mode == mode or enrolment.stripe_mode == "live"):
        if enrolment.stripe_mode != mode:
            raise CheckoutError("The existing live card payment could not be checked.")
        session = retrieve_session(session_id)
        if not session_matches(enrolment, session) or session.get("id") != session_id:
            raise CheckoutError("The saved Checkout Session does not match.")
        if session.get("livemode") and confirm_session(enrolment, session):
            return False
        if session.get("status") == "open":
            session = expire_session(session_id)
        if session.get("status") != "expired" and not (
            mode == "test" and session.get("status") == "complete"
        ):
            raise CheckoutError("The existing card payment could not be closed.")
        if not session_matches(enrolment, session) or session.get("id") != session_id:
            raise CheckoutError("The closed Checkout Session does not match.")

    return True


def signed_event(body, signature):
    parts = [part.strip().partition("=") for part in signature.split(",")]
    try:
        timestamp = int(next(value for key, _, value in parts if key == "t"))
    except (StopIteration, ValueError):
        return None
    if abs(time.time() - timestamp) > 300:
        return None
    signed = str(timestamp).encode() + b"." + body
    digest = hmac.digest(settings.STRIPE_WEBHOOK_SECRET.encode(), signed, "sha256").hex()
    signatures = [value for key, _, value in parts if key == "v1"]
    if not any(hmac.compare_digest(digest, value) for value in signatures if value.isascii()):
        return None
    try:
        event = json.loads(body)
    except ValueError:
        return None
    return event if isinstance(event, dict) else None
