"""Écarts M3 (lot 2) — recette par ligne du tri A/B : préparation, besoins matière / rupture ⇒ DA, rapports
d'exécution archivés, BL / transferts, avancement chantier, attachements / reçu, croisement pointages ↔ M9,
MO directe / indirecte, plan de charge journalier et machine, escalade, marge à terminaison, indicateurs, rapports
périodiques, impressions PDF, conservation, dossier opérationnel enrichi, paramètres provisoires."""

from datetime import date, timedelta
from decimal import Decimal

from rest_framework.test import APITestCase

from achats.models import PurchaseRequest
from commercial.models import Affaire
from outbox.models import OutboxEvent
from referentiels.models import Article, UnitOfMeasure
from rh_paie.models import Absence, Employe
from stocks.models import Depot, StockQuant
from users.models import User
from workflow.models import Notification

from .models import (
    AffectationEquipe,
    BesoinMatiere,
    CapaciteAtelier,
    Equipe,
    EscaladeSurcharge,
    GammeOperation,
    GammeOperatoire,
    OrdreFabrication,
    ParametreOperations,
    PointageChantier,
    RapportExecution,
    SituationTravaux,
)

AUJ = date.today()


class _Base(APITestCase):
    def setUp(self):
        self.dir = User.objects.create_user(email="dir@etls.ga", password="x-Ecarts-2026", role=User.Role.DIRECTEUR_OPERATIONS)
        self.chef = User.objects.create_user(email="chef@etls.ga", password="x-Ecarts-2026", role=User.Role.CHEF_ATELIER)
        self.client.force_authenticate(self.dir)
        unite, _ = UnitOfMeasure.objects.get_or_create(code="U", defaults={"label": "Unité"})
        self.tube = Article.objects.create(code="TUBE-6", label="Tube 6 pouces", unit=unite, is_stockable=True)
        self.depot = Depot.objects.create(code="DEP-M3", label="Magasin atelier")

    def of(self, **kw):
        kw.setdefault("label", "Spool DN150")
        return OrdreFabrication.objects.create(**kw)

    def post(self, url, data=None):
        return self.client.post(url, data or {}, format="json")


class ParametresTests(_Base):
    def test_parametres_provisoires_modifiables_et_confirmables(self):
        r = self.client.get("/api/operations/parametres/")
        self.assertEqual(r.status_code, 200)
        codes = {p["code"]: p for p in r.json()["results"]} if "results" in r.json() else {p["code"]: p for p in r.json()}
        self.assertIn("PLAFOND_HEURES_JOUR", codes)
        self.assertTrue(codes["PLAFOND_HEURES_JOUR"]["est_provisoire"])
        pk = codes["METHODE_AVANCEMENT"]["id"]
        self.assertEqual(self.post(f"/api/operations/parametres/{pk}/modifier/", {"valeur": "9"}).status_code, 400)
        self.assertEqual(self.post(f"/api/operations/parametres/{pk}/modifier/", {"valeur": "2"}).status_code, 200)
        self.client.force_authenticate(self.chef)
        self.assertEqual(self.post(f"/api/operations/parametres/{pk}/confirmer/").status_code, 403)
        self.client.force_authenticate(self.dir)
        r = self.post(f"/api/operations/parametres/{pk}/confirmer/")
        self.assertEqual(r.json()["statut_valeur"], "confirme")
        self.assertEqual(self.client.post("/api/operations/parametres/", {"code": "X"}, format="json").status_code, 405)


class PreparationRuptureTests(_Base):
    def test_reservation_puis_rupture_genere_da_et_alerte(self):
        StockQuant.objects.create(depot=self.depot, article=self.tube, quantity=Decimal("10"))
        of1, of2 = self.of(), self.of(label="Spool 2")
        BesoinMatiere.objects.create(ordre=of1, article=self.tube, quantite=Decimal("8"))
        b2 = BesoinMatiere.objects.create(ordre=of2, article=self.tube, quantite=Decimal("5"))
        r = self.post(f"/api/operations/ordres/{of1.pk}/verifier-besoins/")
        self.assertEqual(r.json()[0]["statut"], "reserve")
        r = self.post(f"/api/operations/ordres/{of2.pk}/verifier-besoins/")
        self.assertEqual(r.json()[0]["statut"], "rupture")
        b2.refresh_from_db()
        da = PurchaseRequest.objects.get(pk=b2.demande_achat_id)
        self.assertEqual(da.lines.get().quantity, Decimal("3.00"))
        self.assertTrue(Notification.objects.filter(subject__icontains="Rupture matière").exists())
        # Idempotent : pas de seconde DA au contrôle suivant.
        self.post(f"/api/operations/ordres/{of2.pk}/verifier-besoins/")
        self.assertEqual(PurchaseRequest.objects.count(), 1)

    def test_fiche_preparation_validee_seulement_sans_rupture_et_pdf(self):
        of = self.of()
        BesoinMatiere.objects.create(ordre=of, article=self.tube, quantite=Decimal("2"))
        r = self.post("/api/operations/fiches-preparation/", {"ordre": str(of.pk), "outillage": "Chanfreineuse", "consignes": "EPI"})
        self.assertEqual(r.status_code, 201, r.content)
        fiche = r.json()["id"]
        self.assertEqual(self.post(f"/api/operations/fiches-preparation/{fiche}/valider/").status_code, 400)
        StockQuant.objects.create(depot=self.depot, article=self.tube, quantity=Decimal("5"))
        r = self.post(f"/api/operations/fiches-preparation/{fiche}/valider/")
        self.assertEqual(r.json()["statut"], "validee")
        self.assertEqual(r.json()["valide_par"], str(self.dir.pk))
        pdf = self.client.get(f"/api/operations/fiches-preparation/{fiche}/?export=pdf")
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertEqual(self.client.patch(f"/api/operations/fiches-preparation/{fiche}/", {"consignes": "x"}, format="json").status_code, 400)

    def test_replanification_par_decalage(self):
        of = self.of(planned_start=AUJ, planned_end=AUJ + timedelta(days=4))
        self.assertEqual(self.post(f"/api/operations/ordres/{of.pk}/replanifier/", {"decalage_jours": 7}).status_code, 400)
        r = self.post(f"/api/operations/ordres/{of.pk}/replanifier/", {"decalage_jours": 7, "motif": "Rupture matière"})
        self.assertEqual(r.json()["planned_start"], (AUJ + timedelta(days=7)).isoformat())


class RapportsTransfertsTests(_Base):
    def test_rapport_execution_archive_en_ged_a_la_terminaison(self):
        from juridique.models import LienDocument

        of = self.of(status="en_cours", quantity=Decimal("4"))
        r = self.post("/api/operations/rapports/", {"ordre": str(of.pk), "date": str(AUJ), "quantite_realisee": "4",
                                                     "quantite_rebut": "1", "observations": "RAS"})
        self.assertEqual(r.status_code, 201, r.content)
        self.post(f"/api/operations/rapports/{r.json()['id']}/valider/")
        self.assertEqual(self.post(f"/api/operations/ordres/{of.pk}/terminer/").status_code, 200)
        lien = LienDocument.objects.get(objet_type="operations.ordrefabrication", objet_id=str(of.pk))
        self.assertIn("Rapport d'exécution", lien.document.title)
        self.assertEqual(lien.module, "M3")
        registre = self.client.get("/api/operations/dossiers/registre/").json()
        self.assertEqual(registre[0]["titre"], lien.document.title)

    def test_rapport_refuse_sur_of_prevu_et_avancement_borne(self):
        of = self.of()
        self.assertEqual(self.post("/api/operations/rapports/", {"ordre": str(of.pk), "date": str(AUJ)}).status_code, 400)
        of.status = "en_cours"
        of.save()
        r = self.post("/api/operations/rapports/", {"ordre": str(of.pk), "date": str(AUJ), "type": "avancement", "avancement": 120})
        self.assertEqual(r.status_code, 400)

    def test_bl_prepare_expedie_receptionne_et_pdf(self):
        of = self.of(status="termine", scope="chantier")
        r = self.post("/api/operations/transferts/", {"ordre": str(of.pk), "destination": "Site Rabi",
                                                       "lignes": [{"designation": "Spool S-01", "quantite": "2"}]})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.json()["code"].startswith("BL"))
        bt = r.json()["id"]
        self.assertEqual(self.post(f"/api/operations/transferts/{bt}/receptionner/").status_code, 400)
        self.assertEqual(self.post(f"/api/operations/transferts/{bt}/expedier/").json()["statut"], "expedie")
        r = self.post(f"/api/operations/transferts/{bt}/receptionner/", {"reserves": "1 bride rayée"})
        self.assertEqual(r.json()["statut"], "receptionne")
        self.assertEqual(self.client.delete(f"/api/operations/transferts/{bt}/").status_code, 400)
        self.assertEqual(self.client.get(f"/api/operations/transferts/{bt}/?export=pdf")["Content-Type"], "application/pdf")
        self.assertEqual(self.post("/api/operations/transferts/", {"ordre": str(of.pk), "destination": "X", "lignes": []}).status_code, 400)

    def test_fiche_controle_non_conforme_alerte(self):
        of = self.of(scope="chantier", status="en_cours")
        r = self.post("/api/operations/fiches-controle/", {"ordre": str(of.pk), "date": str(AUJ), "objet": "Supportage",
                                                            "points": [{"libelle": "Ancrage", "conforme": True},
                                                                       {"libelle": "Alignement", "conforme": False}]})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertFalse(r.json()["conforme"])
        self.assertEqual(r.json()["controle_par"], str(self.dir.pk))
        self.assertTrue(Notification.objects.filter(subject__icontains="non conforme").exists())


class AvancementMargeTests(_Base):
    def test_avancement_chantier_et_marge_a_terminaison(self):
        affaire = Affaire.objects.create(title="Pipeline A", contract_amount=Decimal("1000000"))
        of = self.of(affaire=affaire, calculated_hours=Decimal("100"))
        PointageChantier.objects.create(ordre=of, worker_name="X", date=AUJ, hours=Decimal("50"))
        data = self.client.get("/api/operations/ordres/suivi/").json()
        ligne = next(a for a in data["affaires"] if a["affaire_code"] == affaire.code)
        self.assertEqual(Decimal(ligne["avancement_pct"]), Decimal("50.0"))
        # 50 h non valorisées × 6 000 F (taux provisoire) = 300 000 F engagés ⇒ coût à terminaison 600 000, marge 400 000.
        self.assertEqual(Decimal(ligne["couts_engages"]), Decimal("300000"))
        self.assertEqual(Decimal(ligne["marge_a_terminaison"]), Decimal("400000"))
        self.assertEqual(self.post("/api/operations/ordres/publier-marges/").json()["publiees"], 1)
        self.assertTrue(OutboxEvent.objects.filter(topic="operations.marge_terminaison").exists())
        self.client.force_authenticate(self.chef)  # hors cercle des montants
        ligne = next(a for a in self.client.get("/api/operations/ordres/suivi/").json()["affaires"])
        self.assertIsNone(ligne["marge_a_terminaison"])
        self.assertEqual(self.post("/api/operations/ordres/publier-marges/").status_code, 403)

    def test_multi_affaires_repartition(self):
        a1, a2 = Affaire.objects.create(title="A1"), Affaire.objects.create(title="A2")
        of = self.of(calculated_hours=Decimal("10"))
        self.assertEqual(self.post("/api/operations/repartitions/", {"ordre": str(of.pk), "affaire": str(a1.pk), "part_pct": "60"}).status_code, 201)
        self.assertEqual(self.post("/api/operations/repartitions/", {"ordre": str(of.pk), "affaire": str(a2.pk), "part_pct": "50"}).status_code, 400)
        self.assertEqual(self.post("/api/operations/repartitions/", {"ordre": str(of.pk), "affaire": str(a2.pk), "part_pct": "40"}).status_code, 201)
        codes = {a["affaire_code"] for a in self.client.get("/api/operations/ordres/suivi/").json()["affaires"]}
        self.assertEqual(codes, {a1.code, a2.code})

    def test_attachements_reçu_et_facturation(self):
        situation = SituationTravaux.objects.create(label="S1", period_start=AUJ, period_end=AUJ, created_by=self.chef)
        of = self.of(status="en_cours")
        r = self.post("/api/operations/attachements/", {"ordre": str(of.pk), "situation": str(situation.pk), "date": str(AUJ),
                                                         "designation": "Tuyauterie posée", "unite": "ml", "quantite": "120",
                                                         "prix_unitaire": "2500"})
        self.assertEqual(r.status_code, 201, r.content)
        att = r.json()["id"]
        self.assertEqual(self.post(f"/api/operations/situations/{situation.pk}/valoriser-attachements/").status_code, 400)
        self.assertEqual(self.post(f"/api/operations/attachements/{att}/signer/").status_code, 400)
        self.post(f"/api/operations/attachements/{att}/signer/", {"signataire_client": "M. Client"})
        r = self.post(f"/api/operations/situations/{situation.pk}/valoriser-attachements/")
        self.assertEqual(Decimal(r.json()["amount"]), Decimal("300000"))
        self.post(f"/api/operations/situations/{situation.pk}/validate/")
        self.client.get("/api/operations/parametres/")  # paramètres créés à la première lecture
        p = ParametreOperations.objects.get(code="RECU_CLIENT_OBLIGATOIRE")
        self.post(f"/api/operations/parametres/{p.pk}/modifier/", {"valeur": "1"})
        url = f"/api/operations/situations/{situation.pk}/marquer-facturee/"
        self.assertEqual(self.post(url, {"facture_ref": "FAC-1"}).status_code, 400)
        r = self.post(f"/api/operations/situations/{situation.pk}/accuser-reception/", {"recue_signataire": "M. Client"})
        self.assertIsNotNone(r.json()["recue_le"])
        self.assertEqual(self.post(url, {"facture_ref": "FAC-1"}).json()["status"], "facturee")


class CroisementM9Tests(_Base):
    def setUp(self):
        super().setUp()
        self.ouvrier = User.objects.create_user(email="ouv@etls.ga", password="x-Ecarts-2026", role=User.Role.CHEF_ATELIER)
        self.fiche = Employe.objects.create(code="EMP-M3", civilite="masculin", nom="Ndong", user=self.ouvrier)
        self.of_ = self.of()

    def pointer(self, **kw):
        body = {"ordre": str(self.of_.pk), "date": str(AUJ), "hours": "8", "employe": str(self.fiche.pk)}
        body.update(kw)
        return self.post("/api/operations/pointages/", body)

    def test_pointage_sur_fiche_rh_avec_nature_mo_puis_plafond(self):
        r = self.pointer(nature_mo="indirecte")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["nature_mo"], "indirecte")
        r = self.pointer(hours="6")  # 14 h > plafond provisoire 12 h
        self.assertEqual(r.status_code, 400)
        self.assertIn("plafond", str(r.data))

    def test_absence_validee_bloque_pointage_presence_et_mobilisation(self):
        Absence.objects.create(employe=self.fiche, type="maladie", date_debut=AUJ, date_fin=AUJ + timedelta(days=2), statut="validee")
        self.assertEqual(self.pointer().status_code, 400)
        r = self.post("/api/operations/presences/", {"ordre": str(self.of_.pk), "employe": str(self.fiche.pk), "date": str(AUJ), "statut": "present"})
        self.assertEqual(r.status_code, 400)
        equipe = Equipe.objects.create(label="Tuyauteurs", metier="tuyauteur")
        equipe.membres.add(self.fiche)
        aff = AffectationEquipe.objects.create(equipe=equipe, ordre=self.of_, date_debut=AUJ, date_fin=AUJ + timedelta(days=1), effectif=1)
        self.assertEqual(len(self.client.get(f"/api/operations/affectations/{aff.pk}/").json()["absents"]), 1)
        self.assertEqual(self.post(f"/api/operations/affectations/{aff.pk}/mobiliser/").status_code, 400)

    def test_pointage_fiche_rh_transferable_en_paie(self):
        p = PointageChantier.objects.create(ordre=self.of_, employe=self.fiche, date=AUJ, hours=Decimal("4"),
                                            status=PointageChantier.Status.VALIDE)
        r = self.post(f"/api/operations/pointages/{p.pk}/transferer-paie/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["status"], "transfere")


class PlanChargeIndicateursTests(_Base):
    def test_capacite_machine_vue_journaliere_et_escalade(self):
        g = GammeOperatoire.objects.create(label="Spool")
        GammeOperation.objects.create(gamme=g, label="Cintrage", planned_hours=Decimal("10"), machine_hours=Decimal("40"))
        lundi = AUJ - timedelta(days=AUJ.weekday())
        self.of(gamme=g, planned_start=lundi, planned_end=lundi + timedelta(days=4))
        CapaciteAtelier.objects.create(scope="atelier", resource="machine", hours_per_week=Decimal("20"))
        alertes = self.client.get("/api/operations/ordres/charge/").json()["alertes"]
        self.assertEqual(alertes[0]["resource"], "machine")
        self.assertTrue(alertes[0]["escalade_gr"])
        jour = self.client.get(f"/api/operations/ordres/charge-journaliere/?debut={lundi}&jours=7").json()
        machine = [l for l in jour["lignes"] if l["resource"] == "machine" and l["date"] == lundi.isoformat()][0]
        self.assertEqual(Decimal(machine["planned_hours"]), Decimal("8.00"))
        self.assertTrue(machine["overload"])
        self.assertEqual(self.post("/api/operations/ordres/escalader-surcharges/").json()["escalades"], 1)
        self.assertEqual(self.post("/api/operations/ordres/escalader-surcharges/").json()["escalades"], 0)
        self.assertEqual(EscaladeSurcharge.objects.count(), 1)

    def test_indicateurs_productivite_rebut_et_rapports_periodiques(self):
        g = GammeOperatoire.objects.create(label="Spool")
        GammeOperation.objects.create(gamme=g, label="Soudure", planned_hours=Decimal("5"))
        of = self.of(gamme=g, quantity=Decimal("4"), status="en_cours")
        RapportExecution.objects.create(ordre=of, date=AUJ, quantite_realisee=Decimal("4"), quantite_rebut=Decimal("1"), statut="valide")
        PointageChantier.objects.create(ordre=of, worker_name="X", date=AUJ, hours=Decimal("25"))
        ind = self.client.get(f"/api/operations/ordres/indicateurs/?debut={AUJ}&fin={AUJ}").json()
        self.assertEqual(Decimal(ind["productivite_pct"]), Decimal("80.00"))  # 20 h standard / 25 h pointées
        self.assertEqual(Decimal(ind["taux_rebut_pct"]), Decimal("20.00"))
        for periode in ("hebdo", "mensuel"):
            r = self.client.get(f"/api/operations/ordres/rapport-periodique/?periode={periode}")
            self.assertEqual(r.status_code, 200)
            self.assertIn("synthese", r.json())
        self.assertEqual(self.client.get("/api/operations/ordres/rapport-periodique/?export=pdf")["Content-Type"], "application/pdf")
        self.assertIn("spreadsheetml", self.client.get("/api/operations/ordres/rapport-periodique/?periode=mensuel&export=xlsx")["Content-Type"])
        self.assertEqual(self.client.get("/api/operations/ordres/rapport-periodique/?periode=x").status_code, 400)


class ConservationImpressionTests(_Base):
    def test_impressions_pdf_of_et_gamme(self):
        g = GammeOperatoire.objects.create(label="Spool")
        GammeOperation.objects.create(gamme=g, label="Soudure", planned_hours=Decimal("5"))
        of = self.of(gamme=g)
        self.assertEqual(self.client.get(f"/api/operations/ordres/{of.pk}/?export=pdf")["Content-Type"], "application/pdf")
        self.assertEqual(self.client.get(f"/api/operations/gammes/{g.pk}/?export=pdf")["Content-Type"], "application/pdf")

    def test_of_lance_ou_pointe_non_supprimable_et_of_termine_scelle(self):
        lance = self.of(status="lance")
        self.assertEqual(self.client.delete(f"/api/operations/ordres/{lance.pk}/").status_code, 400)
        pointe = self.of()
        PointageChantier.objects.create(ordre=pointe, worker_name="X", date=AUJ, hours=Decimal("2"))
        self.assertEqual(self.client.delete(f"/api/operations/ordres/{pointe.pk}/").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/operations/ordres/{self.of().pk}/").status_code, 204)
        clos = self.of(status="cloture")
        self.assertEqual(self.client.patch(f"/api/operations/ordres/{clos.pk}/", {"label": "x"}, format="json").status_code, 400)
        termine = self.of(status="termine")
        p = PointageChantier.objects.create(ordre=termine, worker_name="X", date=AUJ, hours=Decimal("2"))
        self.assertEqual(self.client.delete(f"/api/operations/pointages/{p.pk}/").status_code, 400)

    def test_dossier_operationnel_enrichi(self):
        from .cloture import figer_dossier

        of = self.of(status="cloture")
        SituationTravaux.objects.create(label="S", period_start=AUJ, period_end=AUJ).ordres.add(of)
        dossier = figer_dossier(of)
        for cle in ("situations", "rapports", "transferts", "attachements", "fiches_controle", "documents_ged"):
            self.assertIn(cle, dossier.contenu)
        self.assertEqual(len(dossier.contenu["situations"]), 1)
        self.assertEqual(dossier.retention_years, 10)
