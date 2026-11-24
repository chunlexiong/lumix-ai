from django.conf import settings
from django.urls import include, path
from django.contrib import admin
from django.views.generic import RedirectView, TemplateView

from wagtail.admin import urls as wagtailadmin_urls
from wagtail import urls as wagtail_urls
from wagtail.documents import urls as wagtaildocs_urls

from home import enrolment_views
from home.views import contact_page

urlpatterns = [
    path("our-approach/", TemplateView.as_view(template_name="home/approach_page.html"), name="approach"),
    path("courses/", TemplateView.as_view(template_name="home/courses_page.html"), name="courses"),
    path("parent-guide/", TemplateView.as_view(template_name="home/parents_page.html"), name="parents"),
    path("for-parents/", RedirectView.as_view(pattern_name="parents", query_string=True)),
    path("for-families/", RedirectView.as_view(pattern_name="contact", query_string=True), name="families"),
    path("contact/", contact_page, name="contact"),
    path("enrol/", enrolment_views.family_register, name="family_register"),
    path("enrol/verify-email/", enrolment_views.family_verify_email, name="family_verify_email"),
    path("enrol/sign-in/", enrolment_views.FamilySignIn.as_view(), name="family_login"),
    path("enrol/password-reset/", enrolment_views.password_reset_request, name="family_password_reset_request"),
    path("enrol/password-reset/verify/", enrolment_views.password_reset_verify, name="family_password_reset_verify"),
    path("enrol/sign-out/", enrolment_views.FamilySignOut.as_view(), name="family_logout"),
    path("enrol/account/", enrolment_views.family_account, name="family_account"),
    path("enrol/students/add/", enrolment_views.family_add_student, name="family_add_student"),
    path("enrol/classes/", enrolment_views.enrolment_classes, name="enrolment_classes"),
    path("enrol/classes/<slug:program_slug>/<int:age_min>/", enrolment_views.enrolment_select, name="enrolment_select"),
    path("enrol/payment/<uuid:enrolment_id>/", enrolment_views.enrolment_payment, name="enrolment_payment"),
    path("enrol/stripe/webhook/", enrolment_views.stripe_webhook, name="stripe_webhook"),
    path("django-admin/", admin.site.urls),
    path("admin/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
]


if settings.DEBUG:
    from django.conf.urls.static import static
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns

    # Serve static and media files from development server
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

urlpatterns = urlpatterns + [
    # For anything not caught by a more specific rule above, hand over to
    # Wagtail's page serving mechanism. This should be the last pattern in
    # the list:
    path("", include(wagtail_urls)),
    # Alternatively, if you want Wagtail pages to be served from a subpath
    # of your site, rather than the site root:
    #    path("pages/", include(wagtail_urls)),
]
