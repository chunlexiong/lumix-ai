import logging
import uuid

from django.contrib import messages
from django.core.files.base import ContentFile
from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.admin.viewsets.model import ModelViewSet

from .models import Enrolment, StudentLifePage, StudentProjectPreview, StudentVideoPoster, project_url_hash
from .project_screenshots import capture_project_screenshot
from .video_posters import extract_video_poster, video_source_signature


logger = logging.getLogger(__name__)


class EnrolmentViewSet(ModelViewSet):
    model = Enrolment
    # Enrolments are created by checkout; staff should review them, not create
    # or edit them through this listing.
    form_fields = []
    menu_label = "Enrolments"
    icon = "list-ul"
    add_to_admin_menu = True
    copy_view_enabled = False
    inspect_view_enabled = True
    inspect_view_fields = [
        "student",
        "parent_email",
        "program_title",
        "class_title",
        "age_group",
        "schedule",
        "session_count",
        "total",
        "status",
        "stripe_mode",
        "created_at",
        "paid_at",
    ]
    list_display = [
        "created_at",
        "student",
        "parent_email",
        "program_title",
        "class_title",
        "status",
        "total",
        "paid_at",
    ]
    list_filter = ["status", "program_slug", "stripe_mode", "created_at"]
    search_fields = [
        "student__name",
        "student__parent__email",
        "program_title",
        "class_title",
    ]
    ordering = ["-created_at"]
    list_per_page = 25


@hooks.register("register_admin_viewset")
def register_enrolment_viewset():
    return EnrolmentViewSet("enrolments")


@hooks.register("register_admin_menu_item")
def register_public_home_menu_item():
    return MenuItem("Website home", "/", icon_name="home", order=50)


@hooks.register("after_publish_page")
def cache_student_project_screenshots(request, page):
    if not isinstance(page, StudentLifePage):
        return

    project_urls = list(dict.fromkeys(
        block.value["project_url"]
        for block in page.gallery
        if block.block_type == "project"
    ))
    project_hashes = {project_url_hash(url) for url in project_urls}
    generation_failed = False

    for url in project_urls:
        url_hash = project_url_hash(url)
        preview = StudentProjectPreview.objects.filter(url_hash=url_hash).first()
        if preview and preview.image and preview.image.storage.exists(preview.image.name):
            continue

        try:
            screenshot = capture_project_screenshot(url)
        except Exception:
            logger.exception("Could not create a preview for a student project URL.")
            generation_failed = True
            continue

        if preview is None:
            preview = StudentProjectPreview(url_hash=url_hash, url=url)

        old_image_name = preview.image.name if preview.image else ""
        preview.url = url
        preview.image.save(
            f"{url_hash}-{uuid.uuid4().hex}.jpg",
            ContentFile(screenshot),
            save=False,
        )
        preview.save()

        if old_image_name:
            preview.image.storage.delete(old_image_name)

    stale_previews = StudentProjectPreview.objects.exclude(url_hash__in=project_hashes)
    for preview in stale_previews:
        if preview.image:
            preview.image.delete(save=False)
        preview.delete()

    if generation_failed:
        messages.warning(
            request,
            "The page was published, but one or more project previews could not be generated. "
            "The Explore project links are still available.",
        )


@hooks.register("after_publish_page")
def cache_student_video_posters(request, page):
    if not isinstance(page, StudentLifePage):
        return

    referenced_document_ids = set()
    generation_failed = False

    for block in page.gallery:
        if block.block_type != "video":
            continue

        document = block.value["video"]
        referenced_document_ids.add(document.pk)
        cached_poster = StudentVideoPoster.objects.filter(video_document=document).first()

        if block.value["poster"]:
            if cached_poster:
                if cached_poster.image:
                    cached_poster.image.delete(save=False)
                cached_poster.delete()
            continue

        try:
            signature = video_source_signature(document)
            if (
                cached_poster
                and cached_poster.source_signature == signature
                and cached_poster.image
                and cached_poster.image.storage.exists(cached_poster.image.name)
            ):
                continue

            image_data = extract_video_poster(document)
        except Exception:
            logger.exception("Could not generate a poster for a Student life video.")
            generation_failed = True
            continue

        if cached_poster is None:
            cached_poster = StudentVideoPoster(video_document=document)

        old_image_name = cached_poster.image.name if cached_poster.image else ""
        cached_poster.source_signature = signature
        cached_poster.image.save(
            f"video-{document.pk}-{uuid.uuid4().hex}.jpg",
            ContentFile(image_data),
            save=False,
        )
        cached_poster.save()
        if old_image_name:
            cached_poster.image.storage.delete(old_image_name)

    stale_posters = StudentVideoPoster.objects.exclude(video_document_id__in=referenced_document_ids)
    for poster in stale_posters:
        if poster.image:
            poster.image.delete(save=False)
        poster.delete()

    if generation_failed:
        messages.warning(
            request,
            "The page was published, but one or more video posters could not be generated. "
            "You can upload a poster image or check that the video is a playable MP4.",
        )
