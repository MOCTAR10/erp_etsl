"""Reprise INT-02 (écart E2) : les DA générées par l'ancien point d'entrée M1 (`/besoins-achat/`) n'avaient pas
le champ `affaire` renseigné. On le rattache d'après le titre « Besoins d'achat affaire <code> »."""

from django.db import migrations

PREFIXE = "Besoins d'achat affaire "


def rattacher(apps, schema_editor):
    PurchaseRequest = apps.get_model("achats", "PurchaseRequest")
    Affaire = apps.get_model("commercial", "Affaire")
    for da in PurchaseRequest.objects.filter(affaire__isnull=True, title__startswith=PREFIXE):
        affaire = Affaire.objects.filter(code=da.title[len(PREFIXE):].strip()).first()
        if affaire is not None:
            PurchaseRequest.objects.filter(pk=da.pk).update(affaire=affaire)


class Migration(migrations.Migration):

    dependencies = [
        ("achats", "0007_ecarts_a7"),
        ("commercial", "0001_initial"),
    ]

    operations = [migrations.RunPython(rattacher, migrations.RunPython.noop)]
