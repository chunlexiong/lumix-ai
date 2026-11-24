import logging
import uuid

from django.contrib import messages
from django.core.files.base import ContentFile
from wagtail import hooks

from .models import StudentLifePage, StudentProjectPreview, project_url_hash
from .project_screenshots import capture_project_screenshot


logger = logging.getLogger(__name__)


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
