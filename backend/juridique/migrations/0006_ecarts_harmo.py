from django.db import migrations


def libelle(apps, schema_editor):
    apps.get_model("juridique", "ParametreJuridique").objects.filter(cle="paliers_notification").update(
        libelle="Paliers d'alerte des échéances, communs à tous les modules (M1, M12, Couche D) (jours)"
    )


class Migration(migrations.Migration):
    dependencies = [("juridique", "0005_ecarts_m12")]
    operations = [migrations.RunPython(libelle, migrations.RunPython.noop)]
