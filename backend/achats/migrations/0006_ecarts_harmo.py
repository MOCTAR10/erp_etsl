from django.db import migrations


def libelle(apps, schema_editor):
    apps.get_model("achats", "ParametreAchats").objects.filter(code="AGREMENT_DUREE_MOIS").update(label="Durée d'un agrément fournisseur (demande M2 sans date de fin et audit qualité M6)")


class Migration(migrations.Migration):
    dependencies = [("achats", "0005_ecarts_m2")]
    operations = [migrations.RunPython(libelle, migrations.RunPython.noop)]
