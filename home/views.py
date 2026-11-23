import logging

from django.conf import settings
from django.contrib import messages
from django.core.mail import EmailMessage
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .catalogue import PROGRAMS
from .forms import EnquiryForm, PROGRAM_AGES, PROGRAM_CHOICES


logger = logging.getLogger(__name__)


def send_enquiry(data):
    if settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
        return False

    topic = dict(PROGRAM_CHOICES)[data["program"]]
    fields = [
        f'Name: {data["name"]}',
        f'Email: {data["email"]}',
        f"Topic: {topic}",
    ]
    if data["age"]:
        fields.append(f'Age group: {data["age"]}')
    body = "\n".join(fields) + "\n\n" + data["message"]

    try:
        return EmailMessage(
            subject="LumiX AI website enquiry",
            body=body,
            to=[settings.CONTACT_EMAIL],
            reply_to=[data["email"]],
        ).send() == 1
    except OSError:
        logger.warning("Contact enquiry could not be sent by the email backend.")
        return False


@require_http_methods(["GET", "POST"])
def contact_page(request):
    delivery_failed = False
    status = 200

    if request.method == "POST":
        form = EnquiryForm(request.POST)
        if not form.is_valid():
            status = 400
        elif send_enquiry(form.cleaned_data):
            messages.success(request, "Thanks. Your enquiry has been sent.", extra_tags="enquiry-success")
            return redirect(f'{reverse("contact")}#enquiry')
        else:
            delivery_failed = True
            status = 503
    else:
        program = request.GET.get("program", "")
        age = request.GET.get("age", "")
        form = EnquiryForm(initial={
            "program": program if program in dict(PROGRAM_CHOICES) else "",
            "age": age if age in PROGRAM_AGES.get(program, ()) else "",
        })

    return render(request, "home/contact_page.html", {
        "form": form,
        "programs": PROGRAMS,
        "contact_email": settings.CONTACT_EMAIL,
        "delivery_failed": delivery_failed,
    }, status=status)
