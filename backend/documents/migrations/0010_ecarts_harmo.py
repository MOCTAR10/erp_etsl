from django.db import migrations


def allonger(apps, schema_editor):
    # Conservation des pièces contractuelles : 10 ans (CDC), alignée sur M1 / M2 / M3 / M4. Ne raccourcit jamais une
    # durée existante et ne touche pas une durée déjà confirmée par ETSL.
    from django.db.models import Q

    apps.get_model("documents", "DocumentType").objects.filter(code="contrats", retention_confirmee_le__isnull=True).filter(
        Q(retention_years__isnull=True) | Q(retention_years__lt=10)
    ).update(retention_years=10)


class Migration(migrations.Migration):
    dependencies = [("documents", "0009_ecarts_m12")]
    operations = [migrations.RunPython(allonger, migrations.RunPython.noop)]
