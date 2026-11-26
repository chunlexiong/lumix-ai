import base64

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from wagtail.images import get_image_model
from wagtail.models import Page, Site

from home.models import HomePage, StudentLifePage, StudentProjectPreview, project_url_hash


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

    def test_published_photos_and_projects_render_with_filters(self):
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jXioAAAAASUVORK5CYII="
        )
        image = get_image_model().objects.create(
            title="Test class activity",
            file=SimpleUploadedFile("gallery-test.png", png, content_type="image/png"),
        )
        project_url = "https://www.example.com/"
        preview = StudentProjectPreview.objects.create(
            url_hash=project_url_hash(project_url),
            url=project_url,
            image=SimpleUploadedFile("project-preview.png", png, content_type="image/png"),
        )
        self.gallery.gallery = [
            ("photo", {"image": image}),
            ("project", {"project_url": project_url}),
            ("project", {"project_url": "https://example.org/"}),
        ]
        self.gallery.save_revision().publish()
        response = self.client.get("/student-life/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-gallery-kind="photo"')
        self.assertContains(response, 'data-gallery-kind="project"', count=2)
        self.assertContains(response, 'alt="Test class activity"')
        self.assertContains(response, f'src="{preview.image.url}"')
        self.assertContains(response, "Project preview unavailable", count=1)
        self.assertContains(response, '<span class="life-project-host">example.com</span>', html=True)
        self.assertContains(response, f'href="{project_url}" target="_blank" rel="noopener noreferrer"')
        self.assertContains(response, 'id="gallery-empty" hidden')
