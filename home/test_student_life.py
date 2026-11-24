from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from wagtail.images import get_image_model
from wagtail.models import Page, Site
from home.models import HomePage, StudentLifePage
import base64


class StudentLifeTests(TestCase):
    def setUp(self):
        root = Page.get_first_root_node()
        self.home = root.add_child(instance=HomePage(title="Test home", slug="life-test-home"))
        Site.objects.all().delete()
        Site.objects.create(hostname="testserver", root_page=self.home, is_default_site=True)
        self.gallery = self.home.add_child(instance=StudentLifePage(title="Student life", slug="student-life"))
        self.gallery.save_revision().publish()

    def test_empty_gallery_is_honest_and_navigation_reaches_it(self):
        response = self.client.get("/student-life/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "coming soon")
        self.assertNotContains(response, 'id="gallery-empty"')
        for category in ("all", "photo", "video", "project"):
            self.assertContains(response, f'data-gallery-filter="{category}"', count=1)
        self.assertContains(response, 'aria-current="page">Student life')
        self.assertContains(self.client.get("/"), 'href="/student-life/"')

    def test_published_editor_content_renders_with_safe_text_and_filters(self):
        image = get_image_model().objects.create(
            title="Test image",
            file=SimpleUploadedFile("gallery-test.png", base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jXioAAAAASUVORK5CYII="
            ), content_type="image/png"),
        )
        self.gallery.gallery = [
            ("photo", {"title": "Ideas <in action>", "image": image, "alt_text": "Test class activity", "caption": "A discovery."}),
            ("project", {"title": "City project", "image": image, "alt_text": "Test city project", "caption": "A project demo.", "project_url": "https://example.com/"}),
        ]
        self.gallery.save_revision().publish()
        response = self.client.get("/student-life/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ideas &lt;in action&gt;")
        self.assertContains(response, 'data-gallery-kind="photo"')
        self.assertContains(response, 'data-gallery-kind="project"')
        self.assertContains(response, 'alt="Test class activity"')
        self.assertContains(response, 'href="https://example.com/"')
        self.assertContains(response, 'id="gallery-empty" hidden')
        self.assertNotContains(response, '<h3>Ideas <in action></h3>')
