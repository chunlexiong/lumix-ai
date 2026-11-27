from itertools import islice

from django.db import migrations, models


def shorten_bank_transfer_references(apps, schema_editor):
    enrolment = apps.get_model("home", "Enrolment")
    enrolments = enrolment.objects.using(schema_editor.connection.alias)
    issued = (
        enrolments.filter(bank_transfer_reference__startswith="LX")
        .order_by("pk")
        .only("pk", "bank_transfer_reference", "previous_bank_transfer_reference")
        .iterator(chunk_size=500)
    )

    code = 10_000
    for batch in iter(lambda: list(islice(issued, 500)), []):
        for record in batch:
            record.previous_bank_transfer_reference = record.bank_transfer_reference
            record.bank_transfer_reference = str(code)
            code += 1
        enrolments.bulk_update(batch, ["bank_transfer_reference", "previous_bank_transfer_reference"])


class Migration(migrations.Migration):
    dependencies = [("home", "0014_enrolment_bank_transfer")]

    operations = [
        migrations.AddField(
            model_name="enrolment",
            name="previous_bank_transfer_reference",
            field=models.CharField(blank=True, max_length=18, null=True, unique=True),
        ),
        # Both references can appear on a bank statement after this migration.
        migrations.RunPython(shorten_bank_transfer_references),
    ]
