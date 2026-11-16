from django.db import models
from wagtail.admin.panels import FieldPanel
from wagtail.fields import RichTextField
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
