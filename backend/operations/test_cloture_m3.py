"""Clôture M3 Opérations (CDC §6.11) — tests de recette.

- Pointages validés (par un tiers) publiés vers M9 sous forme de saisies temps, sans doublon.
- Situations validées exposées « à facturer » pour M10, puis scellées avec la référence de facture.
- Plan de charge : capacité finie hebdomadaire et alertes de surcharge.
- Dossier opérationnel scellé (SHA-256, immuable) à la libération de l'OF.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase

from qualite.models import ControleQualite
from rh_paie.models import Employe, SaisieTemps
from users.models import User

from .models import CapaciteAtelier, DossierOperationnel, OrdreFabrication, PointageChantier, SituationTravaux


class _Base(APITestCase):
    def setUp(self):
        self.chef = User.objects.create_user(email="chef@etls.ga", password="x-Cloture-2026", role=User.Role.CHEF_ATELIER)
        self.dir = User.objects.create_user(email="dir@etls.ga", password="x-Cloture-2026", role=User.Role.DIRECTEUR_OPERATIONS)
        self.client.force_authenticate(self.dir)


class PointagePaieTests(_Base):
    def setUp(self):
        super().setUp()
        self.ouvrier = User.objects.create_user(email="ouv@etls.ga", password="x-Cloture-2026", role=User.Role.CHEF_ATELIER)
        Employe.objects.create(code="EMP-O1", civilite="masculin", nom="Mba", user=self.ouvrier)
        self.of = OrdreFabrication.objects.create(label="Spool", scope="atelier")

    def pointage(self, par=None):
        return PointageChantier.objects.create(
            ordre=self.of, worker=self.ouvrier, date=date.today(), hours=Decimal("8"), created_by=par or self.chef
        )

    def act(self, p, action):
        return self.client.post(f"/api/operations/pointages/{p.pk}/{action}/", {}, format="json")

    def test_transfert_exige_validation(self):
        p = self.pointage()
        self.assertEqual(self.act(p, "transferer-paie").status_code, 400)

    def test_saisisseur_ne_valide_pas_son_pointage(self):
        p = self.pointage(par=self.dir)
        self.assertEqual(self.act(p, "valider").status_code, 400)

    def test_flux_vers_paie_sans_doublon(self):
        p = self.pointage()
        self.assertEqual(self.act(p, "valider").status_code, 200)
        self.assertEqual(self.act(p, "transferer-paie").status_code, 200)
        self.assertEqual(self.act(p, "transferer-paie").status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.status, PointageChantier.Status.TRANSFERE)
        saisie = SaisieTemps.objects.get()
        self.assertEqual((saisie.heures, saisie.employe.code, saisie.date), (Decimal("8.00"), "EMP-O1", p.date))

    def test_operateur_sans_fiche_salarie_refuse(self):
        sans = User.objects.create_user(email="sans@etls.ga", password="x-Cloture-2026", role=User.Role.CHEF_ATELIER)
        p = PointageChantier.objects.create(ordre=self.of, worker=sans, date=date.today(), hours=4, created_by=self.chef)
        self.act(p, "valider")
        self.assertEqual(self.act(p, "transferer-paie").status_code, 400)
        self.assertFalse(SaisieTemps.objects.exists())

    def test_pointage_valide_verrouille_et_statut_non_patchable(self):
        p = self.pointage()
        self.client.patch(f"/api/operations/pointages/{p.pk}/", {"status": "transfere"}, format="json")
        p.refresh_from_db()
        self.assertEqual(p.status, PointageChantier.Status.SAISI)
        self.act(p, "valider")
        r = self.client.patch(f"/api/operations/pointages/{p.pk}/", {"hours": "2"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.delete(f"/api/operations/pointages/{p.pk}/").status_code, 400)


class SituationFactureTests(_Base):
    def situation(self, status):
        return SituationTravaux.objects.create(
            label="Situation 1", period_start=date.today() - timedelta(days=30), period_end=date.today(),
            amount=Decimal("1500000"), status=status,
        )

    def test_a_facturer_puis_marquee_facturee(self):
        validee = self.situation(SituationTravaux.Status.VALIDEE)
        self.situation(SituationTravaux.Status.BROUILLON)
        r = self.client.get("/api/operations/situations/a-facturer/")
        self.assertEqual([x["code"] for x in r.json()], [validee.code])
        sans_ref = self.client.post(f"/api/operations/situations/{validee.pk}/marquer-facturee/", {}, format="json")
        self.assertEqual(sans_ref.status_code, 400)
        ok = self.client.post(
            f"/api/operations/situations/{validee.pk}/marquer-facturee/", {"facture_ref": "FAC-2026-001"}, format="json"
        )
        self.assertEqual(ok.status_code, 200)
        validee.refresh_from_db()
        self.assertEqual((validee.status, validee.facture_ref), (SituationTravaux.Status.FACTUREE, "FAC-2026-001"))
        self.assertEqual(self.client.get("/api/operations/situations/a-facturer/").json(), [])

    def test_brouillon_non_facturable(self):
        b = self.situation(SituationTravaux.Status.BROUILLON)
        r = self.client.post(f"/api/operations/situations/{b.pk}/marquer-facturee/", {"facture_ref": "X"}, format="json")
        self.assertEqual(r.status_code, 400)


class CapaciteFinieTests(_Base):
    def test_alerte_de_surcharge_hebdomadaire(self):
        CapaciteAtelier.objects.create(scope="atelier", hours_per_week=100)
        lundi = date.today() - timedelta(days=date.today().weekday())
        OrdreFabrication.objects.create(
            label="OF 1", scope="atelier", calculated_hours=150, planned_start=lundi, planned_end=lundi + timedelta(days=4)
        )
        OrdreFabrication.objects.create(
            label="OF 2", scope="chantier", calculated_hours=500, planned_start=lundi, planned_end=lundi + timedelta(days=4)
        )
        alertes = self.client.get("/api/operations/ordres/charge/").json()["alertes"]
        self.assertEqual(len(alertes), 1)
        self.assertEqual((alertes[0]["scope"], alertes[0]["week"], alertes[0]["overload_pct"]), ("atelier", lundi.isoformat(), 50.0))

    def test_pas_d_alerte_sous_la_capacite(self):
        CapaciteAtelier.objects.create(scope="atelier", hours_per_week=200)
        OrdreFabrication.objects.create(label="OF 1", scope="atelier", calculated_hours=150)
        self.assertEqual(self.client.get("/api/operations/ordres/charge/").json()["alertes"], [])

    def test_capacite_strictement_positive(self):
        r = self.client.post("/api/operations/capacites/", {"scope": "atelier", "hours_per_week": "0"}, format="json")
        self.assertEqual(r.status_code, 400)


class DossierOperationnelTests(_Base):
    def test_dossier_fige_a_la_liberation_et_immuable(self):
        of = OrdreFabrication.objects.create(label="Spool", scope="atelier", status=OrdreFabrication.Status.TERMINE)
        ControleQualite.objects.create(
            ordre=of, type_controle="visuel", resultat=ControleQualite.Resultat.CONFORME, statut=ControleQualite.Statut.VALIDE
        )
        r = self.client.post(f"/api/operations/ordres/{of.pk}/liberer/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        dossier = DossierOperationnel.objects.get(ordre=of)
        self.assertEqual(len(dossier.sha256), 64)
        self.assertEqual(dossier.contenu["ordre"]["code"], of.code)
        self.assertEqual(len(dossier.contenu["controles"]), 1)
        self.assertEqual(self.client.get("/api/operations/dossiers/").json()["count"], 1)
        dossier.contenu = {}
        with self.assertRaises(ValidationError):
            dossier.save()
        with self.assertRaises(ValidationError):
            dossier.delete()

    def test_liberation_refusee_sans_dossier(self):
        of = OrdreFabrication.objects.create(label="Spool", scope="atelier", status=OrdreFabrication.Status.TERMINE)
        self.assertEqual(self.client.post(f"/api/operations/ordres/{of.pk}/liberer/", {}, format="json").status_code, 400)
        self.assertFalse(DossierOperationnel.objects.exists())
