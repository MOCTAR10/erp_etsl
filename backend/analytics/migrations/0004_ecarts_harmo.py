from django.db import migrations


def supprimer(apps, schema_editor):
    # Palier J-60 remplacé par le paramètre central `paliers_notification` (config.echeances).
    apps.get_model("analytics", "ParametreCube").objects.filter(code="PALIER_ALERTE_J60").delete()


class Migration(migrations.Migration):
    dependencies = [("analytics", "0003_ecarts_suivi")]
    operations = [migrations.RunPython(supprimer, migrations.RunPython.noop)]
