from decimal import Decimal

from django.db import migrations


def rto(apps, schema_editor):
    # RTO aligné sur l'objectif de conception du PRA (8 h) ; une valeur saisie ou confirmée par ETSL est conservée.
    apps.get_model("users", "ParametreTransverse").objects.filter(
        code="RTO_HEURES", valeur=Decimal("4"), statut_valeur="provisoire"
    ).update(valeur=Decimal("8"), label="Durée maximale de reprise (RTO) — objectif interne du PRA ; engagement contractuel CDC : 48 h ; objectif interne : à confirmer par ETSL")


class Migration(migrations.Migration):
    dependencies = [("users", "0005_ecarts_tr_mdp")]
    operations = [migrations.RunPython(rto, migrations.RunPython.noop)]
