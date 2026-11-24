from django.db import migrations


def create_student_life_page(apps, schema_editor):
    # Use Wagtail's runtime page API: page-tree operations and publishing are
    # not available on historical models reconstructed by Django migrations.
    from home.models import HomePage, StudentLifePage
    from wagtail.models import Site

    default_site = Site.objects.filter(is_default_site=True).select_related("root_page").first()
    if default_site is None:
        return

    home = HomePage.objects.filter(pk=default_site.root_page_id).first()
    if home is None:
        return

    existing = StudentLifePage.objects.filter(slug="student-life", depth=home.depth + 1, path__startswith=home.path).first()
    if existing is not None:
        return

    page = home.add_child(
        instance=StudentLifePage(title="Student life", slug="student-life")
    )
    page.save_revision().publish()


class Migration(migrations.Migration):
    dependencies = [
        ("home", "0005_family_enrolment"),
    ]

    operations = [
        migrations.RunPython(create_student_life_page, migrations.RunPython.noop),
    ]
