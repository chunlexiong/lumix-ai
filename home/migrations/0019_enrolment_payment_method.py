from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("home", "0018_enrolment_test_payment_confirmation_sent_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="enrolment",
            name="payment_method",
            field=models.CharField(
                blank=True,
                choices=[("card", "Card"), ("bank_transfer", "Bank transfer")],
                max_length=16,
            ),
        ),
    ]
