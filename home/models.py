import hashlib
import uuid

from django.conf import settings
from django.db import models
from wagtail.admin.panels import FieldPanel
from wagtail.fields import RichTextField, StreamField
from wagtail import blocks
from wagtail.images.blocks import ImageChooserBlock
from wagtail.documents.blocks import DocumentChooserBlock
from wagtail.models import Page


class HomePage(Page):
    """Editable marketing homepage for Lumix AI."""

    hero_eyebrow = models.CharField(max_length=100, default="AI learning for curious minds")
    hero_heading = models.CharField(
        max_length=180,
        default="Big ideas start with a little curiosity.",
    )
    hero_text = models.TextField(
        default="Give your child the confidence to understand AI, ask better questions, and turn their imagination into something real.",
    )
    hero_cta_label = models.CharField(max_length=40, default="Explore our courses")
    hero_cta_url = models.CharField(max_length=180, default="#courses")
    intro = RichTextField(
        default="We help young people move from using technology to understanding it—and creating with it.",
        features=["bold", "italic", "link"],
    )

    content_panels = Page.content_panels + [
        FieldPanel("hero_eyebrow"),
        FieldPanel("hero_heading"),
        FieldPanel("hero_text"),
        FieldPanel("hero_cta_label"),
        FieldPanel("hero_cta_url"),
        FieldPanel("intro"),
    ]

    max_count = 1


class StudentLifePage(Page):
    """A gallery editors can maintain using Wagtail image and document libraries."""

    introduction = models.TextField(
        default="Big discoveries. Creative breakthroughs. The moments that make learning their own."
    )
    gallery = StreamField([
        ("photo", blocks.StructBlock([
            ("image", ImageChooserBlock()),
        ], icon="image", label="Class photo")),
        ("video", blocks.StructBlock([
            ("title", blocks.CharBlock(max_length=100)),
            ("poster", ImageChooserBlock()),
            ("video", DocumentChooserBlock(help_text="Upload an MP4 video for reliable browser playback.")),
            ("caption", blocks.TextBlock(required=False, max_length=400)),
            ("transcript", blocks.TextBlock(required=False, help_text="Include a text version of spoken content.")),
            ("captions_file", DocumentChooserBlock(required=False, help_text="Optional WebVTT (.vtt) captions file.")),
        ], icon="media", label="Class video")),
        ("project", blocks.StructBlock([
            ("project_url", blocks.URLBlock(help_text="The project must allow embedding in an iframe.")),
        ], icon="code", label="Student project")),
    ], blank=True, help_text="Add parent/carer-approved media. Avoid student full names and private details. Publish the page to make changes visible.")

    content_panels = Page.content_panels + [FieldPanel("introduction"), FieldPanel("gallery")]
    template = "home/student_life_page.html"
    max_count = 1
    parent_page_types = ["home.HomePage"]
    subpage_types = []

    def get_context(self, request):
        context = super().get_context(request)
        gallery_blocks = list(self.gallery)
        group_definitions = [
            ("photo", "Class photos"),
            ("video", "LumiX AI videos"),
            ("project", "Student projects"),
        ]
        context["gallery_groups"] = []
        for key, title in group_definitions:
            group_blocks = [block for block in gallery_blocks if block.block_type == key]
            if group_blocks:
                context["gallery_groups"].append({
                    "key": key,
                    "title": title,
                    "blocks": group_blocks,
                    "pages": [group_blocks[index:index + 3] for index in range(0, len(group_blocks), 3)],
                })
        project_urls = [
            block.value["project_url"]
            for block in gallery_blocks
            if block.block_type == "project"
        ]
        project_hashes = [project_url_hash(url) for url in project_urls]
        context["project_previews"] = {
            preview.url_hash: preview
            for preview in StudentProjectPreview.objects.filter(url_hash__in=project_hashes)
            if preview.image and preview.image.storage.exists(preview.image.name)
        }
        return context


def project_url_hash(url):
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


class StudentProjectPreview(models.Model):
    url_hash = models.CharField(max_length=64, unique=True)
    url = models.URLField(max_length=2048)
    image = models.ImageField(upload_to="student_project_previews/")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.url


class Student(models.Model):
    parent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="students")
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["name", "pk"]

    def __str__(self):
        return self.name


class Enrolment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting payment"
        PREVIEW = "preview", "Preview complete"
        TESTED = "tested", "Test payment complete"
        PAID = "paid", "Paid"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="enrolments")
    program_slug = models.SlugField()
    age_group = models.CharField(max_length=12)
    session_key = models.SlugField()
    program_title = models.CharField(max_length=100)
    class_title = models.CharField(max_length=100)
    schedule = models.CharField(max_length=150)
    session_count = models.PositiveSmallIntegerField()
    amount_cents = models.PositiveIntegerField()
    status = models.CharField(max_length=12, choices=Status, default=Status.PENDING)
    stripe_session_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    stripe_mode = models.CharField(max_length=4, blank=True)
    checkout_revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "program_slug", "age_group", "session_key"],
                name="unique_student_class_session",
            ),
            models.CheckConstraint(condition=models.Q(amount_cents__gt=0), name="enrolment_positive_amount"),
        ]

    @property
    def total(self):
        if self.amount_cents % 100 == 0:
            return f"${self.amount_cents // 100:,}"
        return f"${self.amount_cents / 100:,.2f}"
