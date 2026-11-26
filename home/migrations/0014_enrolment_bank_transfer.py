from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("home", "0013_emailverificationcode")]

    operations = [
        migrations.AddField(
            model_name="enrolment",
            name="bank_transfer_reference",
            field=models.CharField(blank=True, max_length=18, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name="enrolment",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Awaiting payment"),
                    ("preview", "Preview complete"),
                    ("tested", "Test payment complete"),
                    ("bank_pending", "Awaiting bank transfer"),
                    ("paid", "Paid"),
                ],
                default="pending",
                max_length=12,
            ),
        ),
    ]
