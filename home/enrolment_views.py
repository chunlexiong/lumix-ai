import logging
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from .catalogue import PROGRAMS
from .checkout import (
    CheckoutError, checkout_mode, confirm_session, create_session, retrieve_session,
    session_matches, signed_event,
)
from .enrolment_forms import FamilyLoginForm, FamilyRegistrationForm, SelectClassForm, StudentForm
from .models import Enrolment


logger = logging.getLogger(__name__)

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
        try:
            with transaction.atomic():
                parent = form.save()
                parent.students.create(name=form.cleaned_data["student_name"])
        except IntegrityError:
            form.add_error("username", "An account already uses this email. Sign in to continue.")
        else:
            login(request, parent)
            return redirect(destination)

    return render(request, "home/enrolment/register.html", {
        "form": form, "next": destination,
        "sign_in_url": reverse("family_login") + "?" + urlencode({"next": destination}),
    })


@never_cache
@login_required(login_url="family_login")
def family_account(request):
    return render(request, "home/enrolment/account.html", {
        "students": request.user.students.all(),
        "enrolments": Enrolment.objects.filter(student__parent=request.user).select_related("student"),
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


def payment_page(request, enrolment, *, error="", cancelled=False, status=200):
    mode = checkout_mode()
    return render(request, "home/enrolment/payment.html", {
        "enrolment": enrolment,
        "mode": mode,
        "preview_available": settings.DEBUG and not mode and enrolment.stripe_mode != "live",
        "error": error,
        "cancelled": cancelled,
    }, status=status)


def start_checkout(enrolment, mode):
    if enrolment.stripe_mode == "live" and mode != "live":
        raise CheckoutError("A live payment session already exists.")
    if enrolment.stripe_session_id and enrolment.stripe_mode == mode:
        session = retrieve_session(enrolment.stripe_session_id)
        if not session_matches(enrolment, session):
            raise CheckoutError("The saved Checkout Session does not match.")
        if confirm_session(enrolment, session):
            return None
        if session.get("status") == "open":
            return checkout_url(session)
        if session.get("status") != "expired":
            raise CheckoutError("The payment is still being checked.")

    if enrolment.stripe_session_id:
        enrolment.checkout_revision += 1
    enrolment.stripe_mode = mode
    session = create_session(enrolment)
    if not session_matches(enrolment, session) or not session.get("id"):
        raise CheckoutError("The new Checkout Session does not match.")
    url = checkout_url(session)
    enrolment.stripe_session_id = session["id"]
    enrolment.status = Enrolment.Status.PENDING
    enrolment.paid_at = None
    enrolment.save(update_fields=["stripe_mode", "stripe_session_id", "checkout_revision", "status", "paid_at"])
    return url


def checkout_url(session):
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
        try:
            with transaction.atomic():
                enrolment = get_object_or_404(owned.select_for_update(), pk=enrolment_id)
                if enrolment.status == Enrolment.Status.PAID or (
                    enrolment.status == Enrolment.Status.TESTED and mode != "live"
                ):
                    return redirect("enrolment_payment", enrolment.pk)
                if mode:
                    url = start_checkout(enrolment, mode)
                    return redirect(url) if url else redirect("enrolment_payment", enrolment.pk)
                if settings.DEBUG and enrolment.stripe_mode != "live":
                    enrolment.status = Enrolment.Status.PREVIEW
                    enrolment.save(update_fields=["status"])
                    return redirect("enrolment_payment", enrolment.pk)
        except CheckoutError:
            logger.warning("Unable to open enrolment checkout.")
        enrolment = get_object_or_404(owned, pk=enrolment_id)
        return payment_page(request, enrolment, error="Checkout is unavailable right now. Please try again later.", status=503)

    enrolment = get_object_or_404(owned, pk=enrolment_id)
    session_id = request.GET.get("session_id")
    if session_id and session_id == enrolment.stripe_session_id and mode == enrolment.stripe_mode:
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

    return payment_page(request, enrolment, cancelled=request.GET.get("cancelled") == "1")


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
            confirm_session(enrolment, session)
    return HttpResponse(status=200)
