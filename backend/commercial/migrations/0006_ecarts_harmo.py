from django.db import migrations


def supprimer(apps, schema_editor):
    # Paliers d'échéance M1 remplacés par le paramètre central `paliers_notification` (config.echeances).
    apps.get_model("commercial", "ParametreCommercial").objects.filter(
        code__in=["ECHEANCE_PALIER_1", "ECHEANCE_PALIER_2", "ECHEANCE_PALIER_3"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("commercial", "0005_ecarts_suivi")]
    operations = [migrations.RunPython(supprimer, migrations.RunPython.noop)]
