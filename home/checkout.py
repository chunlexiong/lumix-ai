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
    if key.startswith("sk_live_") and origin.scheme == "https" and not settings.DEBUG:
        return "live"
    if key.startswith("sk_test_") and origin.scheme in {"http", "https"}:
        return "test"
    return ""


def stripe_request(path, data=None, idempotency_key=None):
    headers = {"Authorization": f"Bearer {settings.STRIPE_SECRET_KEY}"}
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


def create_session(enrolment):
    origin = settings.STRIPE_CHECKOUT_ORIGIN.rstrip("/")
    payment = origin + reverse("enrolment_payment", args=[enrolment.pk])
    data = {
        "mode": "payment",
        "allowed_payment_method_types[0]": "card",
        "adaptive_pricing[enabled]": "false",
        "client_reference_id": str(enrolment.pk),
        "customer_email": enrolment.student.parent.email,
        "success_url": payment + "?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": payment + "?cancelled=1",
        "line_items[0][quantity]": 1,
        "line_items[0][price_data][currency]": "aud",
        "line_items[0][price_data][unit_amount]": enrolment.amount_cents,
        "line_items[0][price_data][product_data][name]": f"{enrolment.program_title} · {enrolment.class_title}",
        "line_items[0][price_data][product_data][description]": enrolment.schedule,
    }
    request_fingerprint = hashlib.sha256(urlencode(data).encode()).hexdigest()
    idempotency_key = (
        f"enrolment-{enrolment.pk}-{enrolment.stripe_mode}-"
        f"{enrolment.checkout_revision}-{request_fingerprint}"
    )
    return stripe_request("", data, idempotency_key)


def retrieve_session(session_id):
    if not session_id.startswith(("cs_test_", "cs_live_")) or not session_id.replace("_", "").isalnum():
        raise CheckoutError("Invalid Checkout Session.")
    return stripe_request(f"/{session_id}")


def session_matches(enrolment, session):
    return (
        session.get("client_reference_id") == str(enrolment.pk)
        and session.get("currency") == "aud"
        and session.get("amount_total") == enrolment.amount_cents
        and session.get("livemode") is (enrolment.stripe_mode == "live")
        and session.get("mode") == "payment"
    )


def confirm_session(enrolment, session):
    if not session_matches(enrolment, session) or session.get("id") != enrolment.stripe_session_id:
        return False
    if session.get("payment_status") != "paid" or session.get("status") != "complete":
        return False
    status = Enrolment.Status.PAID if enrolment.stripe_mode == "live" else Enrolment.Status.TESTED
    if enrolment.status != status:
        enrolment.status = status
        enrolment.paid_at = timezone.now()
        enrolment.save(update_fields=["status", "paid_at"])
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
