from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("home", "0017_enrolment_payment_confirmation_sent_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="enrolment",
            name="test_payment_confirmation_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
