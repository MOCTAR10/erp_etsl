"""Recette de clôture M6 Qualité (CDC §8.11).

Critères : ITP approuvé avant soudage · qualifications contrôlées · métrologie (étalonnage, blocage d'usage) ·
CND par méthode avec images archivées · épreuves hydrauliques tracées par courbe P/T · NCR-SD clôturés par re-CND.
"""

from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APITestCase

from operations.models import OrdreFabrication
from users.models import User

from .models import (
    ControleQualite, EpreuvePression, InstrumentMesure, JointSoude, NonConformite,
    PointInspection, QualificationSoudeur, Soudeur, WpsWpqr,
)


def user(email, role):
    return User.objects.create_user(email=email, password="x-Cloture-2026", role=role, first_name=email[:3])


class M6Base(APITestCase):
    def setUp(self):
        self.qaqc = user("qaqc@etls.ga", User.Role.QAQC)
        self.chef = user("atelier@etls.ga", User.Role.CHEF_ATELIER)
        self.client.force_authenticate(self.qaqc)
        self.of = OrdreFabrication.objects.create(label="Spool ligne A", scope="atelier")
        self.soudeur = Soudeur.objects.create(nom="NDONG")
        aujourdhui = timezone.localdate()
        QualificationSoudeur.objects.create(
            soudeur=self.soudeur, date_qualification=aujourdhui - timedelta(days=30),
            date_validite=aujourdhui + timedelta(days=300),
        )
        self.wps = WpsWpqr.objects.create(reference="WPS-01", statut="valide")

    def itp(self, approuve=False):
        itp = ControleQualite.objects.create(
            type_controle="itp", point_controle="ITP ligne A", ordre=self.of, statut="en_cours"
        )
        PointInspection.objects.create(controle=itp, ordre=1, description="Fit-up", type_point="arret")
        if approuve:
            r = self.client.post(f"/api/qualite/controles/{itp.pk}/approuver/")
            assert r.status_code == 200, r.content
        return itp

    def joint(self, repere="J1", **kw):
        data = {"ordre": str(self.of.pk), "repere": repere, "soudeur": str(self.soudeur.pk),
                "wps": str(self.wps.pk), "numero_coulee": "C-4471", **kw}
        return self.client.post("/api/qualite/joints/", data, format="json")


class ItpAvantSoudageTests(M6Base):
    def test_soudage_refuse_sans_itp_approuve(self):
        r = self.joint()
        self.assertEqual(r.status_code, 400, r.content)
        self.itp(approuve=False)
        self.assertEqual(self.joint().status_code, 400)  # ITP présent mais non approuvé

    def test_soudage_accepte_apres_approbation(self):
        self.itp(approuve=True)
        r = self.joint()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.data["code"].startswith("JNT-"))
        self.assertEqual(r.data["numero_coulee"], "C-4471")

    def test_approbation_exige_des_points_et_un_role_qualite(self):
        vide = ControleQualite.objects.create(type_controle="itp", point_controle="vide", ordre=self.of)
        self.assertEqual(self.client.post(f"/api/qualite/controles/{vide.pk}/approuver/").status_code, 400)
        itp = self.itp()
        self.client.force_authenticate(self.chef)
        self.assertEqual(self.client.post(f"/api/qualite/controles/{itp.pk}/approuver/").status_code, 403)

    def test_itp_approuve_est_fige(self):
        itp = self.itp(approuve=True)
        self.assertIsNotNone(ControleQualite.objects.get(pk=itp.pk).approuve_le)
        r = self.client.post("/api/qualite/points-inspection/",
                             {"controle": str(itp.pk), "ordre": 2, "description": "x", "type_point": "arret"},
                             format="json")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(self.client.post(f"/api/qualite/controles/{itp.pk}/approuver/").status_code, 400)

    def test_soudeur_non_qualifie_refuse(self):
        self.itp(approuve=True)
        autre = Soudeur.objects.create(nom="MBA")
        r = self.joint(soudeur=str(autre.pk))
        self.assertEqual(r.status_code, 400, r.content)

    def test_repere_unique_par_of(self):
        self.itp(approuve=True)
        self.assertEqual(self.joint("J1").status_code, 201)
        self.assertEqual(self.joint("J1").status_code, 400)


class MetrologieTests(M6Base):
    def instrument(self, **kw):
        data = {"designation": "Manomètre 0-250 bar", "numero_serie": "MN-77",
                "date_etalonnage": str(timezone.localdate()),
                "echeance_etalonnage": str(timezone.localdate() + timedelta(days=180)), **kw}
        return self.client.post("/api/qualite/instruments/", data, format="json")

    def test_instrument_utilisable_puis_hors_echeance(self):
        r = self.instrument()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.data["utilisable"])
        self.assertTrue(r.data["code"].startswith("MET-"))
        perime = self.instrument(numero_serie="MN-78",
                                 date_etalonnage=str(timezone.localdate() - timedelta(days=400)),
                                 echeance_etalonnage=str(timezone.localdate() - timedelta(days=1)))
        self.assertFalse(perime.data["utilisable"])

    def test_controle_avec_instrument_hors_echeance_bloque(self):
        perime = self.instrument(date_etalonnage=str(timezone.localdate() - timedelta(days=400)),
                                 echeance_etalonnage=str(timezone.localdate() - timedelta(days=1))).data
        r = self.client.post("/api/qualite/controles/",
                             {"type_controle": "dimensionnel", "point_controle": "Ø", "instrument": perime["id"]},
                             format="json")
        self.assertEqual(r.status_code, 400, r.content)
        bon = self.instrument(numero_serie="MN-79").data
        r = self.client.post("/api/qualite/controles/",
                             {"type_controle": "dimensionnel", "point_controle": "Ø", "instrument": bon["id"]},
                             format="json")
        self.assertEqual(r.status_code, 201, r.content)

    def test_etalonnage_hors_tolerance_bloque_l_usage(self):
        inst = self.instrument().data
        r = self.client.post(f"/api/qualite/instruments/{inst['id']}/etalonner/",
                             {"conforme": False, "certificat": "CERT-9"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["statut"], "bloque")
        self.assertFalse(r.data["utilisable"])

    def test_nouvel_etalonnage_conforme_debloque_et_renouvelle(self):
        inst = self.instrument().data
        self.client.post(f"/api/qualite/instruments/{inst['id']}/etalonner/", {"conforme": False}, format="json")
        echeance = str(timezone.localdate() + timedelta(days=365))
        r = self.client.post(f"/api/qualite/instruments/{inst['id']}/etalonner/",
                             {"conforme": True, "echeance": echeance, "certificat": "CERT-10"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["utilisable"])
        self.assertEqual(r.data["echeance_etalonnage"], echeance)
        self.assertEqual(len(r.data["etalonnages"]), 2)

    def test_liste_filtre_a_etalonner(self):
        self.instrument()
        self.instrument(numero_serie="MN-80", echeance_etalonnage=str(timezone.localdate() + timedelta(days=10)))
        r = self.client.get("/api/qualite/instruments/?a_etalonner=30")
        self.assertEqual(len(r.json()["results"] if "results" in r.json() else r.json()), 1)


class CndImagesTests(M6Base):
    def cnd(self, **kw):
        return self.client.post("/api/qualite/controles/",
                                {"type_controle": "cnd", "point_controle": "J1", "ordre": str(self.of.pk), **kw},
                                format="json")

    def test_methode_cnd_structuree(self):
        self.assertEqual(self.cnd(methode_cnd="RT").status_code, 201)
        self.assertEqual(self.cnd(methode_cnd="XX").status_code, 400)
        r = self.client.post("/api/qualite/controles/",
                             {"type_controle": "visuel", "point_controle": "v", "methode_cnd": "RT"}, format="json")
        self.assertEqual(r.status_code, 400)  # méthode réservée au type CND

    def test_images_archivees_avec_empreinte(self):
        ctrl = self.cnd(methode_cnd="RT").data
        f = SimpleUploadedFile("film-rt.png", b"\x89PNG-radio", content_type="image/png")
        r = self.client.post("/api/qualite/images-controle/", {"controle": ctrl["id"], "fichier": f, "legende": "Film RT J1"},
                             format="multipart")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(len(r.data["sha256"]), 64)
        liste = self.client.get(f"/api/qualite/images-controle/?controle={ctrl['id']}").json()
        self.assertEqual(len(liste["results"] if "results" in liste else liste), 1)
        detail = self.client.get(f"/api/qualite/controles/{ctrl['id']}/").json()
        self.assertEqual(detail["images_count"], 1)

    def test_image_non_modifiable_ni_supprimable(self):
        ctrl = self.cnd(methode_cnd="UT").data
        f = SimpleUploadedFile("ut.png", b"data", content_type="image/png")
        img = self.client.post("/api/qualite/images-controle/", {"controle": ctrl["id"], "fichier": f}, format="multipart").data
        self.assertEqual(self.client.delete(f"/api/qualite/images-controle/{img['id']}/").status_code, 405)
        self.assertEqual(self.client.patch(f"/api/qualite/images-controle/{img['id']}/", {"legende": "x"}, format="json").status_code, 405)

    def test_image_reservee_au_cnd(self):
        visuel = ControleQualite.objects.create(type_controle="visuel", point_controle="v")
        f = SimpleUploadedFile("a.png", b"d", content_type="image/png")
        r = self.client.post("/api/qualite/images-controle/", {"controle": str(visuel.pk), "fichier": f}, format="multipart")
        self.assertEqual(r.status_code, 400)


class EpreuvePressionTests(M6Base):
    def epreuve(self, **kw):
        data = {"ordre": str(self.of.pk), "type_epreuve": "hydraulique", "pression_essai": "150",
                "duree_minutes": 30, "chute_max": "2", **kw}
        return self.client.post("/api/qualite/epreuves/", data, format="json")

    def releve(self, pk, minute, pression, temperature="20"):
        return self.client.post(f"/api/qualite/epreuves/{pk}/releve/",
                                {"minute": minute, "pression": pression, "temperature": temperature}, format="json")

    def test_courbe_conforme(self):
        ep = self.epreuve().data
        self.assertTrue(ep["code"].startswith("EPR-"))
        for minute, p in ((0, "150"), (15, "149.5"), (30, "149")):
            self.assertEqual(self.releve(ep["id"], minute, p).status_code, 200)
        r = self.client.post(f"/api/qualite/epreuves/{ep['id']}/conclure/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["resultat"], "conforme")
        self.assertEqual(r.data["statut"], "conclue")
        self.assertEqual(len(r.data["releves"]), 3)

    def test_chute_excessive_non_conforme(self):
        ep = self.epreuve().data
        self.releve(ep["id"], 0, "150")
        self.releve(ep["id"], 30, "140")
        r = self.client.post(f"/api/qualite/epreuves/{ep['id']}/conclure/")
        self.assertEqual(r.data["resultat"], "non_conforme")

    def test_duree_insuffisante_ou_courbe_trop_courte_refusees(self):
        ep = self.epreuve().data
        self.releve(ep["id"], 0, "150")
        self.assertEqual(self.client.post(f"/api/qualite/epreuves/{ep['id']}/conclure/").status_code, 400)  # 1 point
        self.releve(ep["id"], 10, "150")
        self.assertEqual(self.client.post(f"/api/qualite/epreuves/{ep['id']}/conclure/").status_code, 400)  # 10 < 30 min

    def test_pression_inferieure_a_l_essai_non_conforme(self):
        ep = self.epreuve().data
        self.releve(ep["id"], 0, "120")
        self.releve(ep["id"], 30, "120")
        r = self.client.post(f"/api/qualite/epreuves/{ep['id']}/conclure/")
        self.assertEqual(r.data["resultat"], "non_conforme")  # n'a jamais atteint la pression d'essai

    def test_epreuve_conclue_est_scellee(self):
        ep = self.epreuve().data
        self.releve(ep["id"], 0, "150")
        self.releve(ep["id"], 30, "150")
        self.client.post(f"/api/qualite/epreuves/{ep['id']}/conclure/")
        self.assertEqual(self.releve(ep["id"], 31, "150").status_code, 400)
        self.assertEqual(self.client.post(f"/api/qualite/epreuves/{ep['id']}/conclure/").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/qualite/epreuves/{ep['id']}/").status_code, 405)

    def test_minutes_croissantes(self):
        ep = self.epreuve().data
        self.releve(ep["id"], 10, "150")
        self.assertEqual(self.releve(ep["id"], 5, "150").status_code, 400)

    def test_instrument_hors_echeance_refuse(self):
        perime = InstrumentMesure.objects.create(
            designation="Manomètre", numero_serie="P1", date_etalonnage=timezone.localdate() - timedelta(days=400),
            echeance_etalonnage=timezone.localdate() - timedelta(days=1))
        self.assertEqual(self.epreuve(instrument=str(perime.pk)).status_code, 400)


class NcrSoudageTests(M6Base):
    def setUp(self):
        super().setUp()
        self.itp(approuve=True)
        self.joint_id = self.joint().data["id"]

    def ncr(self):
        r = self.client.post("/api/qualite/non-conformites/",
                             {"description": "Porosités RT", "type_ncr": "soudage", "joint": self.joint_id,
                              "gravite": "majeure"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.client.post(f"/api/qualite/non-conformites/{r.data['id']}/traiter/", {"traitement": "reparation"}, format="json")
        return r.data["id"]

    def recontrole(self, resultat="conforme", statut="valide", type_controle="cnd"):
        return ControleQualite.objects.create(type_controle=type_controle, point_controle="J1 re-CND",
                                              ordre=self.of, resultat=resultat, statut=statut)

    def test_ncr_sd_exige_un_joint(self):
        r = self.client.post("/api/qualite/non-conformites/",
                             {"description": "x", "type_ncr": "soudage"}, format="json")
        self.assertEqual(r.status_code, 400, r.content)

    def test_cloture_refusee_sans_recontrole(self):
        nc = self.ncr()
        r = self.client.post(f"/api/qualite/non-conformites/{nc}/cloturer/")
        self.assertEqual(r.status_code, 400, r.content)

    def test_recontrole_non_conforme_ou_non_cnd_refuse(self):
        nc = self.ncr()
        for ctrl in (self.recontrole("non_conforme"), self.recontrole(statut="en_cours"),
                     self.recontrole(type_controle="visuel")):
            r = self.client.post(f"/api/qualite/non-conformites/{nc}/cloturer/", {"recontrole": str(ctrl.pk)}, format="json")
            self.assertEqual(r.status_code, 400, r.content)

    def test_cloture_par_recontrole_cnd_conforme(self):
        nc = self.ncr()
        ctrl = self.recontrole()
        r = self.client.post(f"/api/qualite/non-conformites/{nc}/cloturer/", {"recontrole": str(ctrl.pk)}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["statut"], "cloturee")
        self.assertEqual(str(r.data["recontrole"]), str(ctrl.pk))
        self.assertEqual(NonConformite.objects.get(pk=nc).joint_id.hex, self.joint_id.replace("-", ""))

    def test_nc_generique_inchangee(self):
        r = self.client.post("/api/qualite/non-conformites/", {"description": "Peinture"}, format="json")
        self.assertEqual(r.data["type_ncr"], "generique")
        self.client.post(f"/api/qualite/non-conformites/{r.data['id']}/traiter/", {"traitement": "reprise"}, format="json")
        self.assertEqual(self.client.post(f"/api/qualite/non-conformites/{r.data['id']}/cloturer/").status_code, 200)

    def test_rejet_d_une_ncr_sd_ne_cloture_pas_sans_recontrole(self):
        r = self.client.post("/api/qualite/non-conformites/",
                             {"description": "Fissure", "type_ncr": "soudage", "joint": self.joint_id}, format="json")
        t = self.client.post(f"/api/qualite/non-conformites/{r.data['id']}/traiter/", {"traitement": "rejet"}, format="json")
        self.assertEqual(t.data["statut"], "en_traitement")
