"""Lot 11 (2026-10-17) — validation DG obligatoire des cautions et assurances (CDC M12 §14.4 / §14.8).

Les actes qui engagent la société sur une caution ou une assurance (validation, mainlevée, appel, renouvellement,
résiliation) relèvent de la Direction Générale, et non plus du cercle de validation juridique élargi (SG, Finance).
Bug corrigé au passage : la permission de `declarer-sinistre` ne s'appliquait jamais (nom d'action erroné).
"""

from datetime import date, timedelta
from decimal import Decimal

from rest_framework.test import APITestCase

from users.models import User

from .models import Assurance, Caution


def user(email, role):
    return User.objects.create_user(email=email, password="x-Audit-2026", role=role, first_name=email[:3])


class ValidationDgTests(APITestCase):
    def setUp(self):
        self.dg = user("dg@etls.ga", User.Role.PDG)
        self.finance = user("fin@etls.ga", User.Role.FINANCE)
        self.dir_ops = user("ops@etls.ga", User.Role.DIRECTEUR_OPERATIONS)
        today = date.today()
        self.caution = Caution.objects.create(type="bonne_execution", beneficiaire="TotalEnergies", objet="Marché pipeline",
                                              montant=Decimal("25000000"), date_emission=today, date_echeance=today + timedelta(days=200))
        self.assurance = Assurance.objects.create(type="rc_pro", numero_police="POL-9", date_debut=today - timedelta(days=100),
                                                  date_echeance=today + timedelta(days=30))

    def post(self, who, url, data=None):
        self.client.force_authenticate(who)
        return self.client.post(url, data or {}, format="json")

    def test_mainlevee_et_appel_de_caution_reserves_au_dg(self):
        for action in ("lever", "appeler"):
            self.assertEqual(self.post(self.finance, f"/api/juridique/cautions/{self.caution.pk}/{action}/").status_code, 403, action)
        self.post(self.dg, f"/api/juridique/cautions/{self.caution.pk}/valider-dg/")  # écarts M12 : préalable
        self.assertEqual(self.post(self.dg, f"/api/juridique/cautions/{self.caution.pk}/lever/").status_code, 200)

    def test_renouvellement_et_resiliation_d_assurance_reserves_au_dg(self):
        url = f"/api/juridique/assurances/{self.assurance.pk}/renouveler/"
        self.assertEqual(self.post(self.finance, url).status_code, 403)
        self.post(self.dg, f"/api/juridique/assurances/{self.assurance.pk}/valider-dg/")  # écarts M12 : préalable
        self.assertEqual(self.post(self.dg, url).status_code, 200)
        self.assertEqual(self.post(self.finance, f"/api/juridique/assurances/{self.assurance.pk}/resilier/").status_code, 403)

    def test_validation_dg_tracee(self):
        url = f"/api/juridique/cautions/{self.caution.pk}/valider-dg/"
        self.assertEqual(self.post(self.finance, url).status_code, 403)
        self.assertEqual(self.post(self.dg, url).status_code, 200)
        self.caution.refresh_from_db()
        self.assertEqual(self.caution.valide_dg_par, self.dg)
        self.assertEqual(self.post(self.dg, url).status_code, 400)  # déjà validée
        self.assertEqual(self.post(self.dg, f"/api/juridique/assurances/{self.assurance.pk}/valider-dg/").status_code, 200)

    def test_declaration_de_sinistre_reservee_au_cercle_de_validation(self):
        r = self.post(self.dir_ops, f"/api/juridique/assurances/{self.assurance.pk}/declarer-sinistre/",
                      {"date": str(date.today()), "description": "Bris de machine"})
        self.assertEqual(r.status_code, 403, r.content)
