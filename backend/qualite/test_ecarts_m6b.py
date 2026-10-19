"""Écarts M6-B (CDC M6.1-04/05/06, M6.1-11/12/13) : contrôles mesurés à seuils paramétrables, métrologie typée."""

from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from analytics.services import alertes_agregees
from operations.models import OrdreFabrication
from users.models import User

from .models import (
    ControleQualite, CritereControle, DiffusionWps, InstrumentMesure, NonConformite, PointInspection,
    QualificationSoudeur, Soudeur, WpsWpqr,
)


def user(email, role):
    return User.objects.create_user(email=email, password="x-Ecarts-2026", role=role, first_name=email[:3])


class Base(APITestCase):
    def setUp(self):
        self.qa = user("qa@etls.ga", User.Role.QAQC)
        self.client.force_authenticate(self.qa)
        self.today = timezone.localdate()
        self.of = OrdreFabrication.objects.create(label="Bac de rétention", scope="chantier")

    def instrument(self, type_equipement="instrument", jours=200, **kw):
        return InstrumentMesure.objects.create(
            designation=f"Equipement {type_equipement}", numero_serie=f"SN-{type_equipement}-{jours}",
            type_equipement=type_equipement, date_etalonnage=self.today - timedelta(days=100),
            echeance_etalonnage=self.today + timedelta(days=jours), **kw,
        )


class ControlesMesuresTests(Base):
    def controle(self, type_controle):
        r = self.client.post("/api/qualite/controles/", {"type_controle": type_controle, "ordre": str(self.of.pk)}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.data["id"]

    def critere(self, type_controle, code):
        self.client.get("/api/qualite/criteres/")  # crée les critères par défaut
        return CritereControle.objects.get(type_controle=type_controle, code=code)

    def test_peinture_dft_sous_le_minimum_ouvre_une_nc(self):
        cid = self.controle("peinture")
        dft = self.critere("peinture", "DFT")
        self.assertTrue(dft.est_provisoire)
        r = self.client.post(f"/api/qualite/controles/{cid}/mesure/", {"critere": str(dft.pk), "valeur": "180", "repere": "Virole 2"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertFalse(r.data["conforme"])
        # Critères non mesurés : la conclusion demande une confirmation de contrôle partiel.
        self.assertEqual(self.client.post(f"/api/qualite/controles/{cid}/conclure/").status_code, 400)
        r = self.client.post(f"/api/qualite/controles/{cid}/conclure/", {"partiel": True}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["resultat"], "non_conforme")
        nc = NonConformite.objects.get(controle_id=cid)
        self.assertIn("Épaisseur de film sec", nc.description)
        # Scellé après conclusion.
        self.assertEqual(self.client.post(f"/api/qualite/controles/{cid}/mesure/", {"critere": str(dft.pk), "valeur": "300"}, format="json").status_code, 400)

    def test_genie_civil_conforme(self):
        cid = self.controle("genie_civil")
        for code, valeur in (("FC28", "31.5"), ("SLUMP", "90"), ("ENROBAGE", "35"), ("PLANEITE", "3")):
            r = self.client.post(f"/api/qualite/controles/{cid}/mesure/", {"critere": str(self.critere("genie_civil", code).pk), "valeur": valeur}, format="json")
            self.assertTrue(r.data["conforme"], r.data)
        r = self.client.post(f"/api/qualite/controles/{cid}/conclure/")
        self.assertEqual((r.data["resultat"], r.data["statut"]), ("conforme", "valide"))
        self.assertEqual(len(r.data["mesures"]), 4)

    def test_seuils_parametrables_et_figes_a_la_saisie(self):
        cid = self.controle("electrique")
        iso = self.critere("electrique", "ISOLEMENT")
        r = self.client.patch(f"/api/qualite/criteres/{iso.pk}/", {"mini": "2"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        r = self.client.post(f"/api/qualite/controles/{cid}/mesure/", {"critere": str(iso.pk), "valeur": "1.5"}, format="json")
        self.assertFalse(r.data["conforme"])
        self.assertEqual(r.data["mini"], "2.000")
        self.assertEqual(self.client.post(f"/api/qualite/criteres/{iso.pk}/confirmer/").data["statut_valeur"], "confirme")
        mauvais = self.client.patch(f"/api/qualite/criteres/{iso.pk}/", {"mini": "5", "maxi": "1"}, format="json")
        self.assertEqual(mauvais.status_code, 400)

    def test_critere_d_un_autre_type_refuse(self):
        cid = self.controle("essai")
        dft = self.critere("peinture", "DFT")
        r = self.client.post(f"/api/qualite/controles/{cid}/mesure/", {"critere": str(dft.pk), "valeur": "300"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_mesures_reservees_aux_types_mesures(self):
        cid = self.controle("visuel")
        self.assertEqual(self.client.post(f"/api/qualite/controles/{cid}/mesure/", {"critere": "x", "valeur": "1"}, format="json").status_code, 400)


class MetrologieTests(Base):
    def test_hors_tolerance_ouvre_une_nc_d_impact(self):
        inst = self.instrument()
        ctrl = ControleQualite.objects.create(type_controle="dimensionnel", instrument=inst, ordre=self.of)
        r = self.client.post(f"/api/qualite/instruments/{inst.pk}/etalonner/", {"conforme": False, "certificat": "C-1"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        nc = NonConformite.objects.get(instrument=inst)
        self.assertIn(ctrl.code, nc.description)
        self.assertEqual(r.data["etalonnages"][0]["type_operation"], "etalonnage")

    def test_operation_par_type(self):
        poste = self.instrument("poste_souder")
        four = self.instrument("four_tth")
        self.client.post(f"/api/qualite/instruments/{poste.pk}/etalonner/", {"conforme": True, "echeance": str(self.today + timedelta(days=180))}, format="json")
        self.client.post(f"/api/qualite/instruments/{four.pk}/etalonner/", {"conforme": True, "echeance": str(self.today + timedelta(days=365))}, format="json")
        self.assertEqual(poste.etalonnages.get().type_operation, "verification")
        self.assertEqual(four.etalonnages.get().type_operation, "validation")

    def test_etiquette_pdf(self):
        inst = self.instrument()
        r = self.client.get(f"/api/qualite/instruments/{inst.pk}/etiquette/")
        self.assertEqual(r["Content-Type"], "application/pdf")

    def test_alerte_echeance_etalonnage(self):
        inst = self.instrument(jours=15)
        self.instrument("manometre", jours=300)
        items = [i for i in alertes_agregees()["qualite"] if i["type"] == "etalonnage"]
        self.assertEqual([i["code"] for i in items], [inst.code])
        self.assertEqual(items[0]["bande"], "j15")

    def test_poste_a_souder_bloque_interdit_le_joint(self):
        soudeur = Soudeur.objects.create(nom="NDONG")
        QualificationSoudeur.objects.create(soudeur=soudeur, date_qualification=self.today, date_validite=self.today + timedelta(days=300))
        wpqr = WpsWpqr.objects.create(type="wpqr", statut="valide")
        wps = WpsWpqr.objects.create(type="wps", wpqr=wpqr, statut="valide")
        DiffusionWps.objects.create(wps=wps, ordre=self.of)
        itp = ControleQualite.objects.create(type_controle="itp", ordre=self.of, approuve_le=timezone.now())
        PointInspection.objects.create(controle=itp, ordre=1, description="Fit-up")
        poste = self.instrument("poste_souder")
        body = {"ordre": str(self.of.pk), "soudeur": str(soudeur.pk), "wps": str(wps.pk), "poste": str(poste.pk)}
        self.assertEqual(self.client.post("/api/qualite/joints/", {**body, "repere": "J1"}, format="json").status_code, 201)
        poste.statut = InstrumentMesure.Statut.BLOQUE
        poste.save()
        r = self.client.post("/api/qualite/joints/", {**body, "repere": "J2"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("poste", r.data)
        manometre = self.instrument("manometre")
        r = self.client.post("/api/qualite/joints/", {**body, "repere": "J3", "poste": str(manometre.pk)}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_tth_exige_un_four_valide(self):
        manometre = self.instrument("manometre")
        r = self.client.post("/api/qualite/controles/", {"type_controle": "tth", "ordre": str(self.of.pk), "instrument": str(manometre.pk)}, format="json")
        self.assertEqual(r.status_code, 400)
        four = self.instrument("four_tth", jours=-1)  # validation échue
        r = self.client.post("/api/qualite/controles/", {"type_controle": "tth", "ordre": str(self.of.pk), "instrument": str(four.pk)}, format="json")
        self.assertEqual(r.status_code, 400)
        four_ok = self.instrument("four_tth", jours=100)
        r = self.client.post("/api/qualite/controles/", {"type_controle": "tth", "ordre": str(self.of.pk), "instrument": str(four_ok.pk)}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
