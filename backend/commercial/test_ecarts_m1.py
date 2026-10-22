"""Écarts M1 (matrice de recette, 2026-10-21) — tests par ligne de la matrice.

Scoring 360° et signaux faibles · funnel (changement d'étape, alertes d'inactivité) · structure de chiffrage et dérive ·
échéances J-90 / J-60 / J-30 + relances · pipe par profil · profils (retenue, pénalités, indexation, SLA obligatoire,
durées) · échéancier type · retenue de garantie sur factures émises · RAO / RC archivés en GED · besoins d'achat de
l'affaire (M2) · plan de charge et habilitations par contrat (M9) · indicateurs commerciaux · paramètres provisoires.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from achats.models import PurchaseRequest
from rh_paie.models import Employe, Qualification
from users.models import User
from workflow.models import Notification

from . import ecarts_m1
from .models import (
    Affaire, ClientProfile, Contract, Estimate, EstimateLine, EstimateOption, HabilitationRequise, Milestone,
    Opportunity, ParametreCommercial, RevueCommande, TenderReview,
)
from .test_cloture_m1 import BaseM1, creer


class ParametresTests(BaseM1):
    def test_parametres_provisoires_modifiables_puis_confirmes_par_la_direction(self):
        r = self.client.get("/api/commercial/parametres/")
        self.assertEqual(r.status_code, 200)
        lignes = r.data["results"] if isinstance(r.data, dict) else r.data
        codes = {p["code"]: p for p in lignes}
        self.assertTrue(set(ecarts_m1.PARAMETRES_DEFAUT) <= set(codes) or r.data.get("count", 0) >= 20)
        p = ParametreCommercial.objects.get(code="RAO_SEUIL_GO")
        self.assertTrue(p.est_provisoire)
        self.assertEqual(self.client.patch(f"/api/commercial/parametres/{p.pk}/", {"valeur": "80"}, format="json").status_code, 200)
        self.assertEqual(self.client.post("/api/commercial/parametres/", {"code": "X", "valeur": 1}).status_code, 405)
        self.assertEqual(self.client.post(f"/api/commercial/parametres/{p.pk}/confirmer/").status_code, 403)  # DP
        self.client.force_authenticate(self.dg)
        r = self.client.post(f"/api/commercial/parametres/{p.pk}/confirmer/")
        self.assertEqual(r.data["statut_valeur"], "confirme")
        # Le seuil Go est désormais 80 : une note de 78 donne un Go sous réserve.
        rao = TenderReview.objects.create(tender_ref="AO-X", criteres=[{"libelle": "a", "poids": 40, "note": 90},
                                                                        {"libelle": "b", "poids": 60, "note": 70}])
        self.assertEqual(rao.decision_rao, "go_reserve")

    def test_lecteur_hors_ecriture_ne_modifie_pas(self):
        self.client.force_authenticate(creer("fi@etls.ga", User.Role.FINANCE))
        ecarts_m1.assurer_parametres()
        p = ParametreCommercial.objects.get(code="RAO_SEUIL_GO")
        self.assertEqual(self.client.get("/api/commercial/parametres/").status_code, 200)
        self.assertEqual(self.client.patch(f"/api/commercial/parametres/{p.pk}/", {"valeur": "1"}, format="json").status_code, 403)


class ScoringTests(BaseM1):
    def test_score_pondere_signaux_et_vue_360(self):
        self.cli.last_contact = timezone.localdate() - timedelta(days=120)
        self.cli.save()
        autre = self.client_profile("PERENCO", "Perenco")
        autre.last_contact = timezone.localdate()
        autre.save()
        Opportunity.objects.create(client=autre, subject="Gagnée", stage="gagne", amount=Decimal("1000"))
        Opportunity.objects.create(client=self.cli, subject="Perdue", stage="perdu", amount=Decimal("500"))
        r = self.client.post("/api/commercial/profiles/recalculer-scores/")
        self.assertEqual(r.status_code, 200)
        autre.refresh_from_db()
        self.cli.refresh_from_db()
        self.assertGreater(autre.scoring, self.cli.scoring)
        r = self.client.get("/api/commercial/profiles/signaux/")
        ligne = next(x for x in r.data["lignes"] if x["client"] == "Total Gabon")
        self.assertIn("inactif", {s["code"] for s in ligne["signaux"]})
        self.assertTrue(r.data["provisoire"])
        r = self.client.get(f"/api/commercial/profiles/{self.cli.pk}/vue-360/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data["scoring"]["composantes"]), 4)
        self.assertEqual(len(r.data["opportunites"]), 1)

    def test_relance_client_notifiee_une_fois_par_jour(self):
        self.cli.next_contact = timezone.localdate() - timedelta(days=1)
        self.cli.last_contact = timezone.localdate() - timedelta(days=40)
        self.cli.save()
        r = self.client.post("/api/commercial/pilotage/relancer/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Notification.objects.filter(user=self.dp, subject__startswith="Client à relancer").exists())
        self.client.post("/api/commercial/pilotage/relancer/")
        self.assertEqual(Notification.objects.filter(user=self.dp, subject__startswith="Client à relancer").count(), 1)


class FunnelTests(BaseM1):
    def test_changement_d_etape_par_action_et_patch_refuse(self):
        o = Opportunity.objects.create(client=self.cli, subject="Spools", amount=Decimal("100"))
        r = self.client.patch(f"/api/commercial/opportunities/{o.pk}/", {"stage": "offre"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post(f"/api/commercial/opportunities/{o.pk}/changer-etape/", {"stage": "offre"}, format="json")
        self.assertEqual(r.data["stage"], "offre")
        self.assertEqual(self.client.post(f"/api/commercial/opportunities/{o.pk}/changer-etape/", {"stage": "xx"}).status_code, 400)
        r = self.client.post(f"/api/commercial/opportunities/{o.pk}/changer-etape/", {"stage": "perdu", "motif": "Prix"})
        self.assertEqual((r.data["stage"], r.data["lost_reason"]), ("perdu", "Prix"))
        self.assertEqual(self.client.post(f"/api/commercial/opportunities/{o.pk}/changer-etape/", {"stage": "offre"}).status_code, 400)
        self.client.force_authenticate(creer("fi@etls.ga", User.Role.FINANCE))  # lecteur sans droit d'écriture
        o2 = Opportunity.objects.create(subject="Autre")
        self.assertEqual(self.client.post(f"/api/commercial/opportunities/{o2.pk}/changer-etape/", {"stage": "offre"}).status_code, 403)

    def test_alerte_inactivite(self):
        o = Opportunity.objects.create(client=self.cli, subject="Dormante", owner=self.dp)
        Opportunity.objects.filter(pk=o.pk).update(updated_at=timezone.now() - timedelta(days=40))
        r = self.client.get("/api/commercial/opportunities/alertes/")
        self.assertEqual([x["code"] for x in r.data["lignes"]], [o.code])
        ecarts_m1.relances_commerciales()
        self.assertTrue(Notification.objects.filter(user=self.dp, subject__contains=o.code).exists())

    def test_pipe_par_profil(self):
        Opportunity.objects.create(subject="A", stage="offre", amount=Decimal("1000"), profil_contractuel="maintenance")
        Opportunity.objects.create(subject="B", stage="gagne", amount=Decimal("500"), profil_contractuel="maintenance")
        Opportunity.objects.create(subject="C", stage="prospection", amount=Decimal("200"))
        r = self.client.get("/api/commercial/opportunities/pipe-par-profil/")
        lignes = {x["profil"]: x for x in r.data["lignes"]}
        self.assertEqual(lignes["maintenance"]["montant"], "1500.00")
        self.assertEqual(lignes["maintenance"]["pondere"], "1050.00")  # 1000 × 60 % + 500 × 90 %
        self.assertEqual(lignes["maintenance"]["conversion_pct"], "100.00")
        self.assertIn("non_renseigne", lignes)
        self.client.force_authenticate(self.sg)
        r = self.client.get("/api/commercial/opportunities/pipe-par-profil/")
        self.assertIsNone(r.data["lignes"][0]["montant"])


class ChiffrageTests(BaseM1):
    def offre(self):
        offre = Estimate.objects.create(title="Spools", client=self.cli)
        EstimateLine.objects.create(estimate=offre, label="Tubes", quantity=Decimal("10"), cout_unitaire=Decimal("100"),
                                    unit_price=Decimal("150"), nature="fourniture", lot="Lot 1 tuyauterie")
        EstimateLine.objects.create(estimate=offre, label="Soudeurs", quantity=Decimal("1"), cout_unitaire=Decimal("1000"),
                                    unit_price=Decimal("1300"), nature="main_oeuvre", lot="Lot 1 tuyauterie")
        return offre

    def test_structure_debourse_frais_aleas_marge(self):
        offre = self.offre()
        r = self.client.get(f"/api/commercial/estimates/{offre.pk}/structure/")
        self.assertEqual(r.status_code, 200)
        d = r.data
        self.assertEqual(d["debourse_sec"], "2000.00")
        self.assertEqual(d["frais_indirects"], "240.00")  # 12 %
        self.assertEqual(d["aleas"], "100.00")  # 5 %
        self.assertEqual(d["prix_revient"], "2340.00")
        self.assertEqual(d["prix_vente_cible"], "2691.00")  # + 15 %
        self.assertEqual(d["prix_offre"], "2800.00")
        self.assertFalse(d["sous_marge_cible"])
        self.assertTrue(d["taux_provisoires"])
        self.assertEqual(len(d["par_nature"]), 2)
        r = self.client.patch(f"/api/commercial/estimates/{offre.pk}/", {"taux_marge_cible": "25"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self.client.get(f"/api/commercial/estimates/{offre.pk}/structure/").data["sous_marge_cible"])
        self.client.force_authenticate(self.sg)
        self.assertIsNone(self.client.get(f"/api/commercial/estimates/{offre.pk}/structure/").data["prix_revient"])

    def test_derive_et_besoins_d_achat(self):
        opp = Opportunity.objects.create(client=self.cli, subject="Spools", stage="gagne", amount=Decimal("2800"))
        offre = self.offre()
        offre.opportunity = opp
        offre.status = Estimate.Status.GAGNEE
        offre.save()
        affaire = Affaire.objects.create(title="Spools", client=self.cli, opportunity=opp, contract_amount=Decimal("2800"))
        r = self.client.post(f"/api/commercial/affaires/{affaire.pk}/besoins-achat/")
        self.assertEqual(r.status_code, 400)  # affaire en brouillon
        Affaire.objects.filter(pk=affaire.pk).update(status=Affaire.Status.CONFIRMEE)
        r = self.client.post(f"/api/commercial/affaires/{affaire.pk}/besoins-achat/")
        self.assertEqual(r.status_code, 201, r.content)
        da = PurchaseRequest.objects.get(pk=r.data["id"])
        affaire.refresh_from_db()
        self.assertEqual((da.lines.count(), da.analytic_id), (1, affaire.analytic_id))  # main-d'œuvre non achetée
        self.assertEqual(self.client.post(f"/api/commercial/affaires/{affaire.pk}/besoins-achat/").status_code, 400)
        r = self.client.get(f"/api/commercial/affaires/{affaire.pk}/achats/")
        self.assertEqual(r.data["demandes"][0]["code"], da.code)
        r = self.client.get("/api/commercial/affaires/derives/")
        ligne = next(x for x in r.data["lignes"] if x["code"] == affaire.code)
        self.assertEqual(ligne["cout_prevu"], "2340.00")
        self.assertEqual(ligne["cout_reel"], "0.00")
        self.assertFalse(ligne["alerte"])


class EcheancesTests(BaseM1):
    def test_paliers_90_60_30_et_notification(self):
        today = timezone.localdate()
        offre = Estimate.objects.create(title="Offre", client=self.cli, valid_until=today + timedelta(days=60),
                                        status=Estimate.Status.SOUMISE, created_by=self.dp)
        Contract.objects.create(client=self.cli, profile="maintenance", start_date=today - timedelta(days=700),
                                end_date=today + timedelta(days=30), status=Contract.Status.ACTIF)
        r = self.client.get("/api/commercial/pilotage/echeances/")
        self.assertEqual(r.data["paliers"], [90, 60, 30, 15, 0])  # paramètre central (harmonisation)
        paliers = {x["type"]: x["palier"] for x in r.data["lignes"]}
        self.assertEqual(paliers, {"offre": "j60", "contrat": "j30"})
        self.assertTrue(r.data["provisoire"])
        self.client.post("/api/commercial/pilotage/relancer/")
        self.assertTrue(Notification.objects.filter(user=self.dp, subject__startswith=f"Échéance J-60 : {offre.code}").exists())
        self.assertTrue(Notification.objects.filter(user=self.sg, subject__startswith="Échéance J-30").exists())


class ProfilsContractuelsTests(BaseM1):
    def contrat(self, **kw):
        data = {"client": self.cli, "profile": "marche_travaux", "start_date": date(2026, 1, 1), "end_date": date(2027, 12, 31),
                "months": 24, "amount_initial": Decimal("1000000"), "currency": self.xaf}
        data.update(kw)
        return Contract.objects.create(**data)

    def test_activation_applique_la_retenue_et_exige_le_sla_en_maintenance(self):
        c = self.contrat()
        r = self.client.post(f"/api/commercial/contracts/{c.pk}/activer/", {"document": str(self.document_signe().pk)})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["retenue_rate"], "5.00")
        m = self.contrat(profile="maintenance", sla="")
        r = self.client.post(f"/api/commercial/contracts/{m.pk}/activer/", {"document": str(self.document_signe().pk)})
        self.assertEqual(r.status_code, 400)
        self.assertIn("SLA", str(r.data))

    def test_calculs_retenue_penalites_indexation(self):
        c = self.contrat(indexation=True, retenue_rate=Decimal("10"))
        r = self.client.get(f"/api/commercial/contracts/{c.pk}/calculs/?jours_retard=20&indice=110&indice_base=100")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["retenue_garantie"], "100000.00")
        self.assertEqual(r.data["penalites"], "20000.00")  # 1 ‰ × 20 j
        self.assertEqual(r.data["indexation"]["coefficient"], "1.0850")  # 0,15 + 0,85 × 1,10
        r = self.client.get(f"/api/commercial/contracts/{c.pk}/calculs/?jours_retard=500")
        self.assertEqual(r.data["penalites"], "100000.00")  # plafond 10 %
        self.assertEqual(self.client.get(f"/api/commercial/contracts/{c.pk}/calculs/?jours_retard=x").status_code, 400)

    def test_duree_hors_fourchette_avertit_puis_bloque(self):
        payload = {"client": str(self.cli.pk), "profile": "marche_travaux", "start_date": "2026-01-01", "months": 12,
                   "amount_initial": "1000"}
        r = self.client.post("/api/commercial/contracts/", payload, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIn("18-36", r.data["alerte_duree"])
        ecarts_m1.get_param("DUREE_HORS_FOURCHETTE_BLOQUANT")
        ParametreCommercial.objects.filter(code="DUREE_HORS_FOURCHETTE_BLOQUANT").update(valeur=1)
        self.assertEqual(self.client.post("/api/commercial/contracts/", payload, format="json").status_code, 400)
        payload["months"] = 24
        self.assertEqual(self.client.post("/api/commercial/contracts/", payload, format="json").status_code, 201)

    def test_echeancier_type_et_retenues(self):
        affaire = Affaire.objects.create(title="Chantier", client=self.cli)
        c = self.contrat(affaire=affaire, months=18, end_date=None, status=Contract.Status.ACTIF, retenue_rate=Decimal("5"))
        r = self.client.post(f"/api/commercial/contracts/{c.pk}/generer-echeancier/")
        self.assertEqual(r.status_code, 201, r.content)
        jalons = Milestone.objects.filter(affaire=affaire)
        self.assertEqual(jalons.count(), 18)
        self.assertEqual(sum(j.montant for j in jalons), Decimal("1000000"))
        self.assertEqual(self.client.post(f"/api/commercial/contracts/{c.pk}/generer-echeancier/").status_code, 400)
        r = self.client.get(f"/api/commercial/contracts/{c.pk}/retenues/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["taux_pct"], "5.00")
        self.assertEqual(r.data["date_liberation"], date(2028, 7, 1))  # fin (18 mois) + 12 mois


class RaoRcGedTests(BaseM1):
    def test_rao_archivee_a_la_soumission_et_criteres_par_defaut(self):
        r = self.client.get("/api/commercial/tender-reviews/criteres-defaut/")
        self.assertEqual(len(r.data["criteres"]), 6)
        rao = TenderReview.objects.create(tender_ref="AO-1", criteres=[{"libelle": "a", "poids": 1, "note": 90}])
        r = self.client.post(f"/api/commercial/tender-reviews/{rao.pk}/soumettre/")
        self.assertEqual(r.status_code, 200, r.content)
        rao.refresh_from_db()
        self.assertIsNotNone(rao.document)
        self.assertGreaterEqual(rao.document.type.retention_years, 10)
        self.assertEqual(self.client.post(f"/api/commercial/tender-reviews/{rao.pk}/archiver/").status_code, 400)

    def test_rc_archivee_a_la_validation(self):
        affaire = Affaire.objects.create(title="A", client=self.cli)
        rc = RevueCommande.objects.create(affaire=affaire, montant_offre=Decimal("100"), montant_commande=Decimal("100"), delai_offre_jours=10,
                                          delai_commande_jours=10)
        r = self.client.post(f"/api/commercial/revues-commande/{rc.pk}/valider/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNotNone(r.data["document"])


class HabilitationsTests(BaseM1):
    def test_plan_de_charge_et_habilitations_exigees_au_demarrage(self):
        from juridique.models import Reunion  # noqa: F401 (CRRL contrôlé avant les habilitations)
        from operations.models import AffectationEquipe, Equipe, OrdreFabrication

        affaire = Affaire.objects.create(title="Chantier", client=self.cli, status=Affaire.Status.CONFIRMEE)
        c = Contract.objects.create(client=self.cli, affaire=affaire, profile="marche_travaux", start_date=date(2026, 1, 1),
                                    months=24)
        emp = Employe.objects.create(code="MAT-01", civilite="masculin", nom="Mba", prenom="Paul")
        equipe = Equipe.objects.create(label="Soudeurs A", metier="soudeur")
        equipe.membres.add(emp)
        of = OrdreFabrication.objects.create(label="OF", affaire=affaire)
        AffectationEquipe.objects.create(equipe=equipe, ordre=of, date_debut=date(2026, 2, 1), date_fin=date(2026, 2, 10))
        r = self.client.get(f"/api/commercial/affaires/{affaire.pk}/plan-charge/")
        self.assertEqual(r.data["lignes"][0]["jours"], 10)
        r = self.client.post("/api/commercial/habilitations-requises/", {"profile": "marche_travaux", "mot_cle": "H0B0"})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.client.post("/api/commercial/habilitations-requises/", {"mot_cle": "X"}).status_code, 400)
        r = self.client.get(f"/api/commercial/contracts/{c.pk}/habilitations/")
        self.assertFalse(r.data["conforme"])
        self.assertEqual(r.data["personnel"][0]["manquantes"], ["H0B0"])
        self.assertIn("H0B0", ecarts_m1.controle_habilitations_affaire(affaire))
        Qualification.objects.create(employe=emp, intitule="Habilitation électrique H0B0",
                                     date_validite=timezone.localdate() + timedelta(days=100))
        self.assertTrue(self.client.get(f"/api/commercial/contracts/{c.pk}/habilitations/").data["conforme"])
        self.assertIsNone(ecarts_m1.controle_habilitations_affaire(affaire))
        HabilitationRequise.objects.create(contract=c, mot_cle="ATEX")
        self.assertEqual(self.client.get(f"/api/commercial/contracts/{c.pk}/habilitations/").data["habilitations_requises"],
                         ["ATEX", "H0B0"])


class IndicateursTests(BaseM1):
    def test_prix_moyen_et_score_moyen(self):
        for montant in (100, 300):
            e = Estimate.objects.create(title="G", client=self.cli, status=Estimate.Status.GAGNEE)
            EstimateOption.objects.create(estimate=e, label="A", amount=Decimal(montant), is_selected=True)
        Estimate.objects.create(title="P", client=self.cli, status=Estimate.Status.PERDUE)
        ClientProfile.objects.filter(pk=self.cli.pk).update(scoring=30)
        r = self.client.get("/api/commercial/pilotage/indicateurs/")
        self.assertEqual(r.data["prix_moyen"], "200.00")
        self.assertEqual(r.data["taux_transformation_pct"], "66.67")
        self.assertEqual(r.data["clients_sous_seuil"], 1)
        self.client.force_authenticate(self.sg)
        self.assertIsNone(self.client.get("/api/commercial/pilotage/indicateurs/").data["prix_moyen"])
        self.client.force_authenticate(creer("cs@etls.ga", User.Role.CHEF_SERVICE))
        self.assertEqual(self.client.get("/api/commercial/pilotage/indicateurs/").status_code, 403)

    def test_bons_de_sortie_exposes_sur_l_affaire(self):
        affaire = Affaire.objects.create(title="A", client=self.cli)
        r = self.client.get(f"/api/commercial/affaires/{affaire.pk}/")
        self.assertEqual(r.data["bons_sortie_total"], 0)
        self.assertIn("bon de sortie", self.client.get(f"/api/commercial/affaires/{affaire.pk}/achats/").data["definition_bs"])
