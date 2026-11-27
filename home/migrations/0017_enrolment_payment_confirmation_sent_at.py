from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("home", "0016_banktransferreferencecounter"),
    ]

    operations = [
        migrations.AddField(
            model_name="enrolment",
            name="payment_confirmation_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
