"""Écarts M7-C (2026-10-19) — tests de recette ISO 14001 (M7-06), indicateurs (M7-07), bilan annuel et revue de direction.

- Consommations mensuelles → émissions au facteur paramétré (provisoire) ; mois futur et doublon refusés.
- Plan de réduction : objectif chiffré mesuré sur les consommations (référence → dernière année relevée).
- Indicateurs : taux de formation, de recyclage, conformité ISO (score moyen des audits), incidents environnementaux.
- Revue de direction : bilan figé à la création, validation hiérarchique exigeant conclusions et décisions, PDF en GED.
"""

from datetime import date
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from documents.models import Document
from rh_paie.models import Employe, Qualification
from users.models import User

from .models import AuditHse, ConsommationEnvironnement, FormationSecurite, Incident, ParametreHse


class _Base(APITestCase):
    def setUp(self):
        self.hse = User.objects.create_user(email="hse@etls.ga", password="x-Audit-2026", role=User.Role.HSE)
        self.client.force_authenticate(self.hse)


class EnvironnementTests(_Base):
    def test_consommations_emissions_et_rapport(self):
        r = self.client.post("/api/hse/consommations/", {"ressource": "gazole", "periode": "2025-03-17", "quantite": "1000",
                                                          "source": "Bons carburant"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual((r.data["periode"], r.data["unite"]), ("2025-03-01", "L"))
        self.assertEqual(ConsommationEnvironnement.objects.get().saisi_par, self.hse)
        # Même ressource, même mois, même site : refusé ; mois futur aussi.
        r = self.client.post("/api/hse/consommations/", {"ressource": "gazole", "periode": "2025-03-02", "quantite": "5"}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        futur = (timezone.localdate().replace(day=1) + timezone.timedelta(days=40)).isoformat()
        r = self.client.post("/api/hse/consommations/", {"ressource": "eau", "periode": futur, "quantite": "5"}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        self.client.post("/api/hse/consommations/", {"ressource": "electricite", "periode": "2025-03-01", "quantite": "2000"}, format="json")
        self.client.post("/api/hse/consommations/", {"ressource": "eau", "periode": "2025-04-01", "quantite": "30"}, format="json")
        r = self.client.get("/api/hse/consommations/rapport/?annee=2025")
        self.assertEqual(r.status_code, 200, r.content)
        lignes = {lg["ressource"]: lg for lg in r.data["environnement"]["lignes"]}
        self.assertEqual(lignes["gazole"]["emissions_kg_co2e"], "2680.00")  # 1 000 L × 2,68 (facteur provisoire)
        self.assertIsNone(lignes["eau"]["emissions_kg_co2e"])
        self.assertEqual(r.data["environnement"]["emissions_kg_co2e"], "3480.00")
        # Le facteur est un paramètre HSE modifiable : le rapport le suit.
        ParametreHse.objects.filter(code="FE_GAZOLE").update(valeur=Decimal("3"))
        r = self.client.get("/api/hse/consommations/rapport/?annee=2025")
        self.assertEqual(r.data["environnement"]["emissions_kg_co2e"], "3800.00")
        pdf = self.client.get("/api/hse/consommations/rapport/?annee=2025&export=pdf")
        self.assertEqual((pdf.status_code, pdf["Content-Type"]), (200, "application/pdf"))

    def test_plan_de_reduction_mesure_sur_les_consommations(self):
        r = self.client.post("/api/hse/plans-reduction/", {"objectif": "Réduire le gazole", "ressource": "gazole",
                                                            "annee_cible": 2025}, format="json")
        self.assertEqual(r.status_code, 400, r.content)  # objectif chiffré sans référence ni cible
        for annee, q in ((2024, "1000"), (2025, "850")):
            ConsommationEnvironnement.objects.create(ressource="gazole", periode=date(annee, 6, 1), quantite=Decimal(q))
        r = self.client.post("/api/hse/plans-reduction/", {"objectif": "Réduire le gazole", "ressource": "gazole",
                                                            "annee_reference": 2024, "annee_cible": 2026,
                                                            "reduction_cible_pct": "10"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        av = r.data["avancement"]
        self.assertEqual((av["realise_pct"], av["derniere_annee"], av["atteint"]), ("15.00", 2025, True))


class IndicateursTests(_Base):
    def test_taux_formation_recyclage_conformite_iso_environnement(self):
        a = Employe.objects.create(code="EMP-1", nom="Ndong", prenom="Paul", statut=Employe.Statut.ACTIF)
        Employe.objects.create(code="EMP-2", nom="Obame", prenom="Jean", statut=Employe.Statut.ACTIF)
        f = FormationSecurite.objects.create(theme="Hauteur", date_session=date(2026, 2, 1), statut=FormationSecurite.Statut.REALISEE)
        f.participants.add(a)
        Qualification.objects.create(employe=a, intitule="Formation HSE — Hauteur", type=Qualification.Type.CERTIFICAT,
                                     date_obtention=date(2024, 1, 1), date_validite=date(2026, 1, 1))
        Qualification.objects.create(employe=a, intitule="Formation HSE — Hauteur", type=Qualification.Type.CERTIFICAT,
                                     date_obtention=date(2026, 2, 1), date_validite=date(2028, 2, 1))
        Qualification.objects.create(employe=a, intitule="Formation HSE — Levage", type=Qualification.Type.CERTIFICAT,
                                     date_obtention=date(2023, 1, 1), date_validite=date(2025, 1, 1))
        AuditHse.objects.create(zone="Atelier", date_realisation=date(2026, 3, 1), score=80, statut="realise")
        AuditHse.objects.create(zone="Chantier", date_realisation=date(2026, 4, 1), score=90, statut="realise")
        Incident.objects.create(type_incident="deversement", date_evenement=timezone.make_aware(timezone.datetime(2026, 5, 1, 9)),
                                lieu="Parc", description="Fuite gazole", declared_by=self.hse)
        r = self.client.get("/api/hse/incidents/indicateurs/?debut=2026-01-01&fin=2026-06-30&heures=200000")
        self.assertEqual(r.status_code, 200, r.content)
        d = r.data
        self.assertEqual((d["salaries_actifs"], d["salaries_formes"], d["taux_formation"]), (2, 1, "50.00"))
        self.assertEqual((d["habilitations_suivies"], d["habilitations_a_jour"], d["taux_recyclage"]), (2, 1, "50.00"))
        self.assertEqual((d["audits_realises"], d["conformite_iso"]), (2, "85.00"))
        self.assertEqual((d["incidents_environnement"], d["taux_incidents_environnement"]), (1, "1.00"))


class RevueDirectionTests(_Base):
    def test_bilan_fige_validation_hierarchique_et_archivage(self):
        ConsommationEnvironnement.objects.create(ressource="electricite", periode=date(2025, 1, 1), quantite=Decimal("1000"))
        r = self.client.get("/api/hse/revues-direction/bilan/?annee=2025")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["environnement"]["emissions_kg_co2e"], "400.00")
        self.assertIn("taux_formation", r.data["indicateurs"])
        r = self.client.post("/api/hse/revues-direction/", {"annee": 2025, "statut": "validee", "bilan": {"x": 1}}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        rid = r.data["id"]
        self.assertEqual((r.data["statut"], r.data["bilan"]["annee"]), ("brouillon", 2025))  # statut / bilan non saisissables
        # Un rôle d'écriture hors hiérarchie ne valide pas.
        rh = User.objects.create_user(email="rh@etls.ga", password="x-Audit-2026", role=User.Role.RH)
        self.client.force_authenticate(rh)
        self.assertEqual(self.client.post(f"/api/hse/revues-direction/{rid}/valider/").status_code, 403)
        self.client.force_authenticate(self.hse)
        r = self.client.post(f"/api/hse/revues-direction/{rid}/valider/")
        self.assertEqual(r.status_code, 400)
        self.assertIn("decisions", r.data)
        self.client.patch(f"/api/hse/revues-direction/{rid}/", {"participants": "PDG, HSE, DO", "conclusions": "Système efficace",
                                                                 "decisions": "Objectif TRIR < 1"}, format="json")
        r = self.client.post(f"/api/hse/revues-direction/{rid}/valider/")
        self.assertEqual((r.status_code, r.data["statut"]), (200, "validee"), r.content)
        doc = Document.objects.get(pk=r.data["document"])
        self.assertEqual((doc.status, doc.type.retention_years), (Document.Status.ARCHIVED, 10))
        # Scellée : plus de modification ni d'actualisation du bilan.
        self.assertEqual(self.client.patch(f"/api/hse/revues-direction/{rid}/", {"decisions": "x"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(f"/api/hse/revues-direction/{rid}/actualiser/").status_code, 400)
        self.assertEqual(self.client.get(f"/api/hse/revues-direction/{rid}/pdf/")["Content-Type"], "application/pdf")
        # Une seule revue par année.
        self.assertEqual(self.client.post("/api/hse/revues-direction/", {"annee": 2025}, format="json").status_code, 400)
