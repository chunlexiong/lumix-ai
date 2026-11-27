from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("home", "0015_short_bank_transfer_references"),
    ]

    operations = [
        migrations.CreateModel(
            name="BankTransferReferenceCounter",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
