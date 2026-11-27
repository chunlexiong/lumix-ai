import logging
import re
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from .catalogue import PROGRAMS
from .checkout import (
    CheckoutError, checkout_mode, confirm_session, create_session, expire_session, prepare_bank_transfer,
    retrieve_session, session_matches, signed_event,
)
from .enrolment_forms import (
    FamilyLoginForm, FamilyPasswordResetForm, FamilyRegistrationForm,
    PasswordResetRequestForm, SelectClassForm, StudentForm, VerificationCodeForm,
)
from .models import BankTransferReferenceCounter, EmailVerificationCode, Enrolment


logger = logging.getLogger(__name__)
User = get_user_model()

PENDING_SIGNUP_KEY = "pending_email_verification_user_id"
PENDING_SIGNUP_NEXT_KEY = "pending_email_verification_next"
PENDING_SIGNUP_NOTICE_KEY = "pending_email_verification_notice"
PENDING_RESET_EMAIL_KEY = "pending_password_reset_email"
PENDING_RESET_USER_KEY = "pending_password_reset_user_id"
CODE_COOLDOWN = timedelta(seconds=60)
CODE_HOURLY_LIMIT = 5

WORKSHOP_SESSIONS = {
    "jan-15": "15–17 Jan 2027",
    "jan-22": "22–24 Jan 2027",
}


def safe_next(request, fallback):
    target = request.POST.get("next") or request.GET.get("next", "")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return reverse(fallback)


class FamilySignIn(LoginView):
    template_name = "home/enrolment/sign_in.html"
    authentication_form = FamilyLoginForm
    next_page = reverse_lazy("family_account")


class FamilySignOut(LogoutView):
    next_page = reverse_lazy("family_register")


@never_cache
@require_http_methods(["GET", "POST"])
def family_register(request):
    destination = safe_next(request, "enrolment_classes")
    if request.user.is_authenticated:
        return redirect(destination)

    form = FamilyRegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["username"]
        existing = User.objects.filter(username__iexact=email).first()
        if existing and existing.is_active:
            form.add_error("username", "An account already uses this email. Sign in to continue.")
        elif existing and not existing.check_password(form.cleaned_data["password1"]):
            form.add_error("username", "An account with this email is awaiting verification. Use the password you chose when registering.")
        else:
            try:
                with transaction.atomic():
                    if existing:
                        parent = existing
                    else:
                        parent = form.save(commit=False)
                        parent.is_active = False
                        parent.save()
                        parent.students.create(name=form.cleaned_data["student_name"])
                    request.session[PENDING_SIGNUP_KEY] = parent.pk
                    request.session[PENDING_SIGNUP_NEXT_KEY] = destination
                    request.session.modified = True
            except IntegrityError:
                form.add_error("username", "An account already uses this email. Sign in to continue.")
            else:
                result = send_verification_code(parent, EmailVerificationCode.Purpose.SIGNUP)
                if result != "sent":
                    request.session[PENDING_SIGNUP_NOTICE_KEY] = code_delivery_message(result)
                return redirect("family_verify_email")

    return render(request, "home/enrolment/register.html", {
        "form": form, "next": destination,
        "sign_in_url": reverse("family_login") + "?" + urlencode({"next": destination}),
    })


def send_verification_code(user, purpose):
    now = timezone.now()
    recent_codes = EmailVerificationCode.objects.filter(
        user=user, purpose=purpose, created_at__gte=now - timedelta(hours=1)
    )
    if recent_codes.filter(created_at__gte=now - CODE_COOLDOWN).exists():
        return "cooldown"
    if recent_codes.count() >= CODE_HOURLY_LIMIT:
        return "rate_limited"

    EmailVerificationCode.objects.filter(
        user=user, purpose=purpose, consumed_at__isnull=True
    ).update(consumed_at=now)
    record, code = EmailVerificationCode.create_for_user(user, purpose=purpose)
    if not settings.EMAIL_HOST and "smtp" in settings.EMAIL_BACKEND:
        # A missing SMTP host is a configuration problem; leave the code available
        # for resend after correcting settings rather than exposing it in logs.
        logger.warning("Email code delivery skipped because EMAIL_HOST is not configured.")
        return "send_failed"
    try:
        send_mail(
            subject=(
                "Your LumiX AI password reset code"
                if purpose == EmailVerificationCode.Purpose.PASSWORD_RESET
                else "Your LumiX AI email verification code"
            ),
            message=(
                f"Your six-digit {'password reset' if purpose == EmailVerificationCode.Purpose.PASSWORD_RESET else 'email verification'} code is {code}.\n\n"
                "It expires in 15 minutes. If you did not request this email, you can ignore it."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Email code delivery failed for user id %s.", user.pk)
        return "send_failed"
    return "sent"


def code_delivery_message(result):
    if result == "cooldown":
        return "A code was sent recently. Please wait a minute before requesting another."
    if result == "rate_limited":
        return "You’ve requested several codes. Please try again in an hour."
    if result == "send_failed":
        return "We couldn’t send the email right now. Please try again shortly."
    return "A new code has been sent."


@never_cache
@require_http_methods(["GET", "POST"])
def family_verify_email(request):
    user_id = request.session.get(PENDING_SIGNUP_KEY)
    if not user_id:
        return redirect("family_register")
    user = User.objects.filter(pk=user_id, is_active=False).first()
    if not user:
        request.session.pop(PENDING_SIGNUP_KEY, None)
        return redirect("family_register")

    form = VerificationCodeForm(request.POST if request.method == "POST" else None)
    notice = request.session.pop(PENDING_SIGNUP_NOTICE_KEY, "")
    if request.method == "POST":
        action = request.POST.get("action", "verify")
        if action == "resend":
            notice = code_delivery_message(send_verification_code(user, EmailVerificationCode.Purpose.SIGNUP))
        elif form.is_valid():
            with transaction.atomic():
                locked_user = User.objects.select_for_update().filter(pk=user.pk, is_active=False).first()
                record = EmailVerificationCode.objects.select_for_update().filter(
                    user=user, purpose=EmailVerificationCode.Purpose.SIGNUP,
                    consumed_at__isnull=True,
                ).first()
                if locked_user and record and record.verify(form.cleaned_data["code"]):
                    locked_user.is_active = True
                    locked_user.save(update_fields=["is_active"])
                    destination = request.session.get(PENDING_SIGNUP_NEXT_KEY) or reverse("enrolment_classes")
                    request.session.pop(PENDING_SIGNUP_KEY, None)
                    request.session.pop(PENDING_SIGNUP_NEXT_KEY, None)
                    login(request, locked_user, backend="django.contrib.auth.backends.ModelBackend")
                    return redirect(destination)
            form.add_error("code", "That code is incorrect, expired, or has already been used. Request a new code and try again.")
    return render(request, "home/enrolment/verify_email.html", {"form": form, "email": user.email, "notice": notice})


@never_cache
@require_http_methods(["GET", "POST"])
def password_reset_request(request):
    form = PasswordResetRequestForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        request.session[PENDING_RESET_EMAIL_KEY] = email
        if user:
            request.session[PENDING_RESET_USER_KEY] = user.pk
            send_verification_code(user, EmailVerificationCode.Purpose.PASSWORD_RESET)
        else:
            request.session.pop(PENDING_RESET_USER_KEY, None)
        return redirect("family_password_reset_verify")
    return render(request, "home/enrolment/password_reset_request.html", {"form": form})


@never_cache
@require_http_methods(["GET", "POST"])
def password_reset_verify(request):
    email = request.session.get(PENDING_RESET_EMAIL_KEY)
    if not email:
        return redirect("family_password_reset_request")
    user_id = request.session.get(PENDING_RESET_USER_KEY)
    user = User.objects.filter(pk=user_id, is_active=True).first() if user_id else None
    form = FamilyPasswordResetForm(
        request.POST if request.method == "POST" and request.POST.get("action") != "resend" else None,
        user=user,
    )
    notice = "If an active family account uses this email, a code has been sent. Check your inbox and spam folder."
    if request.method == "POST" and request.POST.get("action") == "resend":
        if user:
            send_verification_code(user, EmailVerificationCode.Purpose.PASSWORD_RESET)
            notice = "If an active family account uses this email, a code can be sent. Check your inbox and spam folder."
    elif request.method == "POST" and form.is_valid():
        if user:
            with transaction.atomic():
                locked_user = User.objects.select_for_update().filter(pk=user.pk, is_active=True).first()
                record = EmailVerificationCode.objects.select_for_update().filter(
                    user=user, purpose=EmailVerificationCode.Purpose.PASSWORD_RESET,
                    consumed_at__isnull=True,
                ).first()
                if locked_user and record and record.verify(form.cleaned_data["code"]):
                    locked_user.set_password(form.cleaned_data["password1"])
                    locked_user.save(update_fields=["password"])
                    request.session.pop(PENDING_RESET_EMAIL_KEY, None)
                    request.session.pop(PENDING_RESET_USER_KEY, None)
                    login(request, locked_user, backend="django.contrib.auth.backends.ModelBackend")
                    return redirect("family_account")
        form.add_error("code", "That code is incorrect, expired, or has already been used. Request a new code and try again.")
    return render(request, "home/enrolment/password_reset_verify.html", {
        "form": form, "email": email, "notice": notice,
    })


@never_cache
@login_required(login_url="family_login")
def family_account(request):
    student_cards = []
    for student in request.user.students.prefetch_related("enrolments"):
        enrolled = list(student.enrolments.all())
        pending = [enrolment for enrolment in enrolled if enrolment.payment_pending]
        student_cards.append({
            "student": student,
            "enrolled": enrolled,
            "pending": pending,
        })
    return render(request, "home/enrolment/account.html", {
        "student_cards": student_cards,
    })


@never_cache
@login_required(login_url="family_login")
@require_http_methods(["GET", "POST"])
def family_add_student(request):
    destination = safe_next(request, "family_account")
    form = StudentForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        student = form.save(commit=False)
        student.parent = request.user
        student.save()
        return redirect(destination)
    return render(request, "home/enrolment/student.html", {"form": form, "next": destination})


@never_cache
@login_required(login_url="family_register")
def enrolment_classes(request):
    return render(request, "home/enrolment/classes.html", {"programs": PROGRAMS})


def available_sessions(program, card):
    if program["id"] == "january-home":
        return {key: f'{dates} · {card["time"]}' for key, dates in WORKSHOP_SESSIONS.items()}
    if program["id"] == "term-four" and " or " in card["time"]:
        first, second = card["time"].split(" or ", 1)
        return {"morning": f'{program["dates"]} · {first}', "afternoon": f'{program["dates"]} · {second}'}
    if program["id"] == "term-one":
        return {"term": f'{program["dates"]} · {program["schedule"]}'}
    return {"term": f'{program["dates"]} · {card["time"]}'}


@never_cache
@login_required(login_url="family_register")
@require_http_methods(["GET", "POST"])
def enrolment_select(request, program_slug, age_min):
    program = next((entry for entry in PROGRAMS if entry["id"] == program_slug), None)
    card = next((group for group in program["cards"] if group["min_age"] == age_min), None) if program else None
    if not card:
        raise Http404("Class not found")
    sessions = available_sessions(program, card)
    students = request.user.students.all()
    first_student = students.first()
    form = SelectClassForm(
        request.POST if request.method == "POST" else None,
        parent=request.user,
        sessions=[("", "Choose a session"), *sessions.items()] if len(sessions) > 1 else sessions.items(),
        initial={"student": first_student if students.count() == 1 else None, "session": next(iter(sessions)) if len(sessions) == 1 else ""},
    )
    if request.method == "POST" and form.is_valid():
        session = form.cleaned_data["session"]
        enrolment, _ = Enrolment.objects.get_or_create(
            student=form.cleaned_data["student"], program_slug=program_slug, age_group=card["age"], session_key=session,
            defaults={
                "program_title": program["title"],
                "class_title": card["name"],
                "schedule": sessions[session],
                "session_count": program["session_count"],
                "amount_cents": card["session_price"] * program["session_count"] * 100,
            },
        )
        return redirect("enrolment_payment", enrolment.pk)

    return render(request, "home/enrolment/select.html", {
        "program": program, "card": card, "form": form, "has_students": first_student is not None,
        "add_student_url": reverse("family_add_student") + "?" + urlencode({"next": request.path}),
    })


def bank_transfer_details():
    name = settings.BANK_TRANSFER_ACCOUNT_NAME
    bsb = settings.BANK_TRANSFER_BSB.replace("-", "").replace(" ", "")
    account = settings.BANK_TRANSFER_ACCOUNT_NUMBER
    if not name or not re.fullmatch(r"[0-9]{6}", bsb) or not re.fullmatch(r"[0-9]+", account):
        return None
    return {"name": name, "bsb": f"{bsb[:3]}-{bsb[3:]}", "account": account}


def embedded_checkout_key(mode):
    key = settings.STRIPE_PUBLISHABLE_KEY
    return key if mode and key.startswith(f"pk_{mode}_") else ""


def payment_page(request, enrolment, *, error="", cancelled=False, status=200, hosted_fallback=False):
    mode = checkout_mode()
    bank_details = bank_transfer_details()
    if bank_details and enrolment.status != Enrolment.Status.PAID and not enrolment.bank_transfer_reference:
        try:
            with transaction.atomic():
                enrolment = Enrolment.objects.select_for_update().get(pk=enrolment.pk)
                if enrolment.status != Enrolment.Status.PAID and not enrolment.bank_transfer_reference:
                    assign_bank_transfer_reference(enrolment)
        except CheckoutError:
            enrolment.refresh_from_db()
            logger.warning("Unable to reserve a bank transfer reference.")

    preview_complete = enrolment.status == Enrolment.Status.PREVIEW and not mode
    preview_available = settings.DEBUG and not mode and enrolment.stripe_mode != "live" and not preview_complete
    test_complete = enrolment.status == Enrolment.Status.TESTED and mode != "live"
    bank_available = bool(bank_details) or enrolment.awaiting_bank_transfer
    card_available = bool(mode and not test_complete) or (preview_available and not enrolment.awaiting_bank_transfer)
    return render(request, "home/enrolment/payment.html", {
        "enrolment": enrolment,
        "mode": mode,
        "bank_details": bank_details,
        "bank_available": bank_available,
        "card_available": card_available,
        "embedded_key": "" if hosted_fallback else embedded_checkout_key(mode),
        "card_selected": card_available and (not bank_available or request.POST.get("method") == "card"),
        "test_complete": test_complete,
        "preview_complete": preview_complete,
        "error": error,
        "cancelled": cancelled,
    }, status=status)


def assign_bank_transfer_reference(enrolment):
    while True:
        # Start above the old five- and six-digit references. The database
        # sequence gives each allocation a distinct increasing number.
        allocation = BankTransferReferenceCounter.objects.create()
        reference = str(1_000_000 + allocation.pk)
        if (
            Enrolment.objects.filter(bank_transfer_reference=reference).exists()
            or Enrolment.objects.filter(previous_bank_transfer_reference=reference).exists()
        ):
            continue

        try:
            with transaction.atomic():
                enrolment.bank_transfer_reference = reference
                enrolment.save(update_fields=["bank_transfer_reference"])
        except IntegrityError:
            if not (
                Enrolment.objects.filter(bank_transfer_reference=reference).exists()
                or Enrolment.objects.filter(previous_bank_transfer_reference=reference).exists()
            ):
                raise
        else:
            return


def start_bank_transfer(enrolment, mode):
    if not bank_transfer_details():
        raise CheckoutError("Bank transfer is unavailable.")

    if not prepare_bank_transfer(enrolment, mode):
        return

    if not enrolment.bank_transfer_reference:
        assign_bank_transfer_reference(enrolment)
    enrolment.status = Enrolment.Status.BANK_PENDING
    enrolment.paid_at = None
    enrolment.save(update_fields=["status", "paid_at"])


def start_checkout(enrolment, mode, *, embedded=False):
    if enrolment.awaiting_bank_transfer:
        # Bank transfer selection already closed the old Stripe session or verified it was a test.
        if enrolment.stripe_session_id:
            enrolment.checkout_revision += 1
        enrolment.stripe_session_id = None
        enrolment.stripe_mode = ""

    if enrolment.stripe_mode == "live" and mode != "live":
        raise CheckoutError("A live payment session already exists.")
    if enrolment.stripe_session_id and enrolment.stripe_mode == mode:
        session = retrieve_session(enrolment.stripe_session_id)
        if not session_matches(enrolment, session) or session.get("id") != enrolment.stripe_session_id:
            raise CheckoutError("The saved Checkout Session does not match.")
        if confirm_session(enrolment, session):
            return None
        if session.get("status") == "open":
            if session_is_embedded(session) == embedded:
                return checkout_access(session, embedded)
            session = expire_session(enrolment.stripe_session_id)
            if not session_matches(enrolment, session) or session.get("id") != enrolment.stripe_session_id:
                raise CheckoutError("The closed Checkout Session does not match.")
        if session.get("status") != "expired":
            raise CheckoutError("The payment is still being checked.")

    if enrolment.stripe_session_id:
        enrolment.checkout_revision += 1
    enrolment.stripe_mode = mode
    session = create_session(enrolment, embedded=embedded)
    if not session_matches(enrolment, session) or not session.get("id"):
        raise CheckoutError("The new Checkout Session does not match.")
    access = checkout_access(session, embedded)
    enrolment.stripe_session_id = session["id"]
    enrolment.status = Enrolment.Status.PENDING
    enrolment.paid_at = None
    enrolment.save(update_fields=["stripe_mode", "stripe_session_id", "checkout_revision", "status", "paid_at"])
    return access


def session_is_embedded(session):
    return session.get("ui_mode") in {"embedded", "embedded_page"}


def checkout_access(session, embedded):
    if session_is_embedded(session) != embedded:
        raise CheckoutError("Checkout returned the wrong display mode.")
    if embedded:
        secret = session.get("client_secret")
        if not isinstance(secret, str) or not secret:
            raise CheckoutError("Checkout did not return a client secret.")
        return secret

    url = session.get("url") or ""
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc != "checkout.stripe.com":
        raise CheckoutError("Checkout returned an invalid address.")
    return url


@never_cache
@login_required(login_url="family_login")
@require_http_methods(["GET", "POST"])
def enrolment_payment(request, enrolment_id):
    owned = Enrolment.objects.filter(student__parent=request.user)
    mode = checkout_mode()
    if request.method == "POST":
        method = request.POST.get("method")
        embedded = method == "embedded_card"
        if embedded and not embedded_checkout_key(mode):
            return JsonResponse({"error": "Card form unavailable."}, status=503)
        payment_url = reverse("enrolment_payment", args=[enrolment_id])
        try:
            with transaction.atomic():
                enrolment = get_object_or_404(owned.select_for_update(), pk=enrolment_id)
                if enrolment.status == Enrolment.Status.PAID:
                    return JsonResponse({"redirect": payment_url}) if embedded else redirect(payment_url)
                if method not in {None, "bank", "card", "embedded_card"}:
                    return redirect("enrolment_payment", enrolment.pk)
                if enrolment.awaiting_bank_transfer and not (mode and method in {"card", "embedded_card"}):
                    return redirect("enrolment_payment", enrolment.pk)
                if method == "bank":
                    start_bank_transfer(enrolment, mode)
                    return redirect("enrolment_payment", enrolment.pk)
                if enrolment.status == Enrolment.Status.TESTED and mode != "live":
                    return JsonResponse({"redirect": payment_url}) if embedded else redirect(payment_url)
                if mode:
                    access = start_checkout(enrolment, mode, embedded=embedded)
                    if embedded:
                        return JsonResponse({"clientSecret": access} if access else {"redirect": payment_url})
                    return redirect(access or payment_url)
                if method is None and settings.DEBUG and enrolment.stripe_mode != "live":
                    enrolment.status = Enrolment.Status.PREVIEW
                    enrolment.save(update_fields=["status"])
                    return redirect("enrolment_payment", enrolment.pk)
        except CheckoutError:
            logger.warning("Unable to open enrolment checkout.")
        if embedded:
            return JsonResponse({"error": "Card form unavailable."}, status=503)
        enrolment = get_object_or_404(owned, pk=enrolment_id)
        error = (
            "We couldn’t start a bank transfer. Please try again or contact us if you already started a card payment."
            if method == "bank" else "Checkout is unavailable right now. Please try again later."
        )
        return payment_page(request, enrolment, error=error, status=503, hosted_fallback=method == "card")

    enrolment = get_object_or_404(owned, pk=enrolment_id)
    session_id = request.GET.get("session_id")
    if (
        not enrolment.awaiting_bank_transfer and session_id
        and session_id == enrolment.stripe_session_id and mode == enrolment.stripe_mode
    ):
        try:
            session = retrieve_session(session_id)
        except CheckoutError:
            return payment_page(request, enrolment, error="We couldn’t check the payment yet. Refresh this page to try again.")
        with transaction.atomic():
            enrolment = get_object_or_404(owned.select_for_update(), pk=enrolment_id)
            confirmed = confirm_session(enrolment, session)
        if confirmed:
            return redirect("enrolment_payment", enrolment.pk)
        return payment_page(request, enrolment, error="Payment is still being checked. Refresh this page in a moment.")

    return payment_page(
        request, enrolment,
        cancelled=request.GET.get("cancelled") == "1",
    )


@csrf_exempt
@require_POST
def stripe_webhook(request):
    if not settings.STRIPE_WEBHOOK_SECRET:
        return HttpResponse(status=503)
    event = signed_event(request.body, request.headers.get("Stripe-Signature", ""))
    if event is None:
        return HttpResponse(status=400)
    if event.get("type") != "checkout.session.completed":
        return HttpResponse(status=200)
    data = event.get("data")
    session = data.get("object") if isinstance(data, dict) else None
    if not isinstance(session, dict) or not session.get("id"):
        return HttpResponse(status=400)

    with transaction.atomic():
        enrolment = Enrolment.objects.select_for_update().filter(stripe_session_id=session["id"]).first()
        if enrolment:
            confirmed = confirm_session(enrolment, session)
            sent_field = (
                "test_payment_confirmation_sent_at"
                if enrolment.status == Enrolment.Status.TESTED
                else "payment_confirmation_sent_at"
            )
            if confirmed and not getattr(enrolment, sent_field):
                return HttpResponse(status=500)
    return HttpResponse(status=200)
