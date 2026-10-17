"""Garde-fou transverse (audit lot 8, 2026-10-17) — champs d'attestation jamais écrits par le client.

Un champ qui dit QUI a créé, demandé, déclaré, validé, décidé ou revu une pièce est une preuve (traçabilité
MANUEL §3.9/§9.9, séparation des tâches). Il doit être posé côté serveur (perform_create / action dédiée) et
figurer en lecture seule dans TOUT sérialiseur. Ce test balaie les sérialiseurs de toutes les apps du projet :
un nouveau champ d'attestation laissé écrivable fait échouer la CI.
"""

import importlib
import os

from django.apps import apps
from django.conf import settings
from django.test import SimpleTestCase
from rest_framework import serializers

ATTESTATION_FIELDS = {
    "created_by", "cree_par", "demande_par", "demandeur", "requester", "declared_by", "uploaded_by",
    "validateur", "validated_by", "valide_par", "approuve_par", "decided_by", "reviewed_by", "leve_par",
    "test_gaz_par", "signed_by", "visa_dg_par", "visa_daf_par", "visa_cg_par", "valide_dg_par",
}


def project_serializers():
    root = str(settings.BASE_DIR)
    for app in apps.get_app_configs():
        if not os.path.abspath(app.path).startswith(os.path.abspath(root)):
            continue
        try:
            mod = importlib.import_module(f"{app.name}.serializers")
        except ModuleNotFoundError:
            continue
        for name in dir(mod):
            cls = getattr(mod, name)
            if (
                isinstance(cls, type)
                and issubclass(cls, serializers.ModelSerializer)
                and cls.__module__ == mod.__name__
                and hasattr(getattr(cls, "Meta", None), "model")
            ):
                yield f"{app.label}.{name}", cls


class AttestationFieldsReadOnlyTests(SimpleTestCase):
    def test_aucun_champ_d_attestation_ecrivable(self):
        writable = []
        for label, cls in project_serializers():
            for fname, field in cls().fields.items():
                if fname in ATTESTATION_FIELDS and not field.read_only:
                    writable.append(f"{label}.{fname}")
        self.assertEqual(writable, [], "Champs d'attestation écrivables par le client : " + ", ".join(writable))
