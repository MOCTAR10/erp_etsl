from django.db import migrations


def supprimer(apps, schema_editor):
    # Durée d'agrément : source unique = ParametreAchats AGREMENT_DUREE_MOIS. Les dates d'agrément déjà posées sur
    # les fiches tiers (Partner.agree_qualite_jusqu) ne sont PAS modifiées.
    apps.get_model("qualite", "ParametreQualite").objects.filter(code="AGREMENT_DUREE_MOIS").delete()


class Migration(migrations.Migration):
    dependencies = [("qualite", "0008_ecarts_m6c")]
    operations = [migrations.RunPython(supprimer, migrations.RunPython.noop)]
