"""Le statut des objets à workflow ne se change que par les actions dédiées (jamais par PATCH/POST).

Régression de l'audit 2026-10-16 : un rédacteur pouvait « valider » un permis de travail, clôturer
un inventaire ou passer un bulletin en `valide` en envoyant directement `statut` -> les contrôles,
rôles de validation et effets de bord (mouvements de stock, compteurs, archivage) étaient contournés.
"""

import importlib

from django.test import SimpleTestCase

# (app, serializer, champ) — chacun a des actions de transition dédiées côté views.
WORKFLOW_SERIALIZERS = [
    ("hse", "PermisTravailSerializer", "statut"),
    ("hse", "IncidentSerializer", "statut"),
    ("hse", "ActionHseSerializer", "statut"),
    ("logistique", "AffectationParcSerializer", "statut"),
    ("logistique", "DemandeMobilisationSerializer", "statut"),
    ("logistique", "LocationGRSerializer", "statut"),
    ("maintenance", "OrdreTravailSerializer", "statut"),
    ("maintenance", "InspectionSerializer", "statut"),
    ("qualite", "NonConformiteSerializer", "statut"),
    ("qualite", "ActionCorrectiveSerializer", "statut"),
    ("qualite", "PvControleSerializer", "statut"),
    ("rh_paie", "BulletinSerializer", "statut"),
    ("rh_paie", "EmployeSerializer", "statut"),
    ("rh_paie", "DemandeCongeSerializer", "statut"),
    ("rh_paie", "SanctionSerializer", "statut"),
    ("comptabilite", "ControleInterneSerializer", "statut"),
    ("comptabilite", "EngagementSerializer", "statut"),
    ("comptabilite", "PaiementSerializer", "statut"),
    ("stocks", "InventaireSerializer", "statut"),
    ("operations", "SituationTravauxSerializer", "status"),
]


class WorkflowStatusReadOnlyTests(SimpleTestCase):
    def test_statut_en_lecture_seule(self):
        writable = []
        for app, name, field in WORKFLOW_SERIALIZERS:
            serializer = getattr(importlib.import_module(f"{app}.serializers"), name)()
            if not serializer.fields[field].read_only:
                writable.append(f"{app}.{name}.{field}")
        self.assertEqual(writable, [], f"statut modifiable hors workflow : {writable}")
