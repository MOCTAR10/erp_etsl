"""Écarts M6-A (CDC M6.1) : soudage, WPS / WPQR, NCR-SD, CAPA, ITP / punch list, dossier qualité, indicateurs."""

from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APITestCase

from analytics.services import alertes_agregees
from operations.models import OrdreFabrication
from operations.views import controle_liberation
from rh_paie.models import Employe
from users.models import User
from workflow.models import Notification

from .ecarts import qualif_couvre, relances_qualite
from .models import (
    ActionCorrective, ControleQualite, DiffusionWps, JointSoude, NonConformite, ParametreQualite, PointInspection,
    PunchItem, PvControle, QualificationSoudeur, Soudeur, WpsWpqr,
)


def user(email, role):
    return User.objects.create_user(email=email, password="x-Ecarts-2026", role=role, first_name=email[:3])


class Base(APITestCase):
    def setUp(self):
        self.qa = user("qa@etls.ga", User.Role.QAQC)
        self.dop = user("dop@etls.ga", User.Role.DIRECTEUR_OPERATIONS)
        self.client.force_authenticate(self.qa)
        self.today = timezone.localdate()
        self.of = OrdreFabrication.objects.create(label="Spool ligne B", scope="atelier")
        self.soudeur = Soudeur.objects.create(nom="MBENG")
        self.qualif = QualificationSoudeur.objects.create(
            soudeur=self.soudeur, procede="gtaw", position="5G", date_qualification=self.today - timedelta(days=30),
            date_validite=self.today + timedelta(days=300),
        )
        self.wpqr = WpsWpqr.objects.create(type="wpqr", reference="PQR-01", procede="gtaw", statut="valide")
        self.wps = WpsWpqr.objects.create(type="wps", reference="WPS-02", procede="gtaw", position="5G", wpqr=self.wpqr,
                                          statut="valide")
        itp = ControleQualite.objects.create(type_controle="itp", ordre=self.of, approuve_le=timezone.now())
        PointInspection.objects.create(controle=itp, ordre=1, description="Fit-up")
        self.itp = itp

    def joint(self, repere="J1", wps=None, soudeur=None):
        return self.client.post("/api/qualite/joints/", {
            "ordre": str(self.of.pk), "repere": repere, "soudeur": str((soudeur or self.soudeur).pk),
            "wps": str((wps or self.wps).pk),
        }, format="json")


class WpsTests(Base):
    def test_wps_valide_exige_un_wpqr_valide(self):
        r = self.client.post("/api/qualite/wps/", {"type": "wps", "reference": "WPS-03", "procede": "smaw"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        r2 = self.client.post(f"/api/qualite/wps/{r.data['id']}/valider/")
        self.assertEqual(r2.status_code, 400)
        self.assertIn("wpqr", r2.data)
        self.client.patch(f"/api/qualite/wps/{r.data['id']}/", {"wpqr": str(self.wpqr.pk)}, format="json")
        self.assertEqual(self.client.post(f"/api/qualite/wps/{r.data['id']}/valider/").status_code, 200)
        # Validé = scellé : plus de modification.
        self.assertEqual(self.client.patch(f"/api/qualite/wps/{r.data['id']}/", {"materiau": "X"}, format="json").status_code, 400)

    def test_wpqr_support_doit_etre_un_wpqr(self):
        r = self.client.post("/api/qualite/wps/", {"type": "wps", "wpqr": str(self.wps.pk)}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_fichier_joint_en_brouillon(self):
        brouillon = WpsWpqr.objects.create(type="wps", reference="WPS-04")
        pdf = SimpleUploadedFile("wps.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        r = self.client.post(f"/api/qualite/wps/{brouillon.pk}/fichier/", {"fichier": pdf}, format="multipart")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["fichier"])
        exe = SimpleUploadedFile("x.exe", b"MZ")
        self.assertEqual(self.client.post(f"/api/qualite/wps/{brouillon.pk}/fichier/", {"fichier": exe}, format="multipart").status_code, 400)

    def test_obsolete_puis_joint_refuse(self):
        DiffusionWps.objects.create(wps=self.wps, ordre=self.of)
        self.assertEqual(self.client.post(f"/api/qualite/wps/{self.wps.pk}/obsolete/").status_code, 400)  # motif requis
        r = self.client.post(f"/api/qualite/wps/{self.wps.pk}/obsolete/", {"motif": "Révision B"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["statut"], "obsolete")
        self.assertEqual(self.joint().status_code, 400)

    def test_diffusion_vers_of_requise_pour_souder(self):
        self.assertEqual(self.joint().status_code, 400)
        r = self.client.post(f"/api/qualite/wps/{self.wps.pk}/diffuser/", {"ordre": str(self.of.pk)}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.client.get(f"/api/qualite/wps/?ordre={self.of.pk}").data["results"][0]["code"], self.wps.code)
        self.assertEqual(self.joint().status_code, 201)

    def test_wps_brouillon_ne_se_diffuse_pas(self):
        brouillon = WpsWpqr.objects.create(type="wps")
        r = self.client.post(f"/api/qualite/wps/{brouillon.pk}/diffuser/", {"ordre": str(self.of.pk)}, format="json")
        self.assertEqual(r.status_code, 400)


class QualificationAuJointTests(Base):
    def setUp(self):
        super().setUp()
        DiffusionWps.objects.create(wps=self.wps, ordre=self.of)

    def test_procede_different_refuse(self):
        self.qualif.procede = "smaw"
        self.qualif.save()
        r = self.joint()
        self.assertEqual(r.status_code, 400)
        self.assertIn("soudeur", r.data)

    def test_position_non_couverte_refusee_6g_couvre_tout(self):
        self.qualif.position = "1G"
        self.qualif.save()
        self.assertEqual(self.joint().status_code, 400)
        self.qualif.position = "6G"
        self.qualif.save()
        self.assertEqual(self.joint().status_code, 201)

    def test_couverture_unitaire(self):
        self.assertTrue(qualif_couvre(self.qualif, self.wps))
        self.qualif.date_validite = self.today - timedelta(days=1)
        self.assertFalse(qualif_couvre(self.qualif, self.wps))

    def test_soudeur_lie_a_la_fiche_m9(self):
        emp = Employe.objects.create(nom="MBENG", prenom="Charles", civilite="masculin")
        r = self.client.patch(f"/api/qualite/soudeurs/{self.soudeur.pk}/", {"employe": str(emp.pk)}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["employe_code"], emp.code)
        perso = self.client.get("/api/qualite/personnel/")
        self.assertIn(str(emp.pk), [p["id"] for p in perso.data])


class AlertesQualifTests(Base):
    def test_peremption_qualification_soudeur_alerte(self):
        self.qualif.date_validite = self.today + timedelta(days=30)
        self.qualif.save()
        items = alertes_agregees()["qualite"]
        self.assertEqual([i["code"] for i in items], [self.qualif.code])
        self.assertEqual(items[0]["bande"], "j30")
        # La qualification renouvelée (plus récente) fait disparaître l'alerte.
        QualificationSoudeur.objects.create(soudeur=self.soudeur, procede="gtaw", date_qualification=self.today,
                                            date_validite=self.today + timedelta(days=700))
        self.assertEqual(alertes_agregees()["qualite"], [])

    def test_alerte_masquee_sans_lecture_qualite(self):
        self.qualif.date_validite = self.today + timedelta(days=15)
        self.qualif.save()
        rh = user("rh@etls.ga", User.Role.RH)
        self.assertEqual(alertes_agregees(rh)["qualite"], [])


class NcrCapaTests(Base):
    def test_ncr_sd_numerotee(self):
        DiffusionWps.objects.create(wps=self.wps, ordre=self.of)
        joint = self.joint().data
        r = self.client.post("/api/qualite/non-conformites/", {
            "type_ncr": "soudage", "joint": joint["id"], "description": "Manque de fusion J1",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.data["code"].startswith("NCR-SD-"))
        generique = self.client.post("/api/qualite/non-conformites/", {"description": "Écart"}, format="json")
        self.assertTrue(generique.data["code"].startswith("NC"))
        self.assertFalse(generique.data["code"].startswith("NCR"))

    def test_cloture_nc_exige_capa_cloturees(self):
        nc = NonConformite.objects.create(description="Ovalisation", statut="en_traitement")
        capa = ActionCorrective.objects.create(non_conformite=nc, description="Reprise", echeance=self.today)
        r = self.client.post(f"/api/qualite/non-conformites/{nc.pk}/cloturer/")
        self.assertEqual(r.status_code, 400)
        self.assertIn(capa.code, r.data["detail"])
        self.client.post(f"/api/qualite/actions-correctives/{capa.pk}/cloturer/", {"efficace": True}, format="json")
        self.assertEqual(self.client.post(f"/api/qualite/non-conformites/{nc.pk}/cloturer/").status_code, 200)
        # NC clôturée : plus de CAPA rattachable.
        r = self.client.post("/api/qualite/actions-correctives/", {"non_conformite": str(nc.pk), "description": "x"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_rejet_ne_cloture_pas_avec_capa_ouverte(self):
        nc = NonConformite.objects.create(description="Tôle hors tolérance")
        ActionCorrective.objects.create(non_conformite=nc, description="Retour fournisseur")
        r = self.client.post(f"/api/qualite/non-conformites/{nc.pk}/traiter/", {"traitement": "rejet"}, format="json")
        self.assertEqual(r.data["statut"], "en_traitement")

    def test_delai_capa_parametrable(self):
        self.client.get("/api/qualite/parametres/")
        p = ParametreQualite.objects.get(code="CAPA_DELAI_JOURS")
        r = self.client.patch(f"/api/qualite/parametres/{p.pk}/", {"valeur": "10"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["est_provisoire"])
        nc = NonConformite.objects.create(description="Défaut peinture")
        r = self.client.post("/api/qualite/actions-correctives/", {
            "non_conformite": str(nc.pk), "description": "Reprise", "echeance": str(self.today + timedelta(days=8)),
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.client.post(f"/api/qualite/parametres/{p.pk}/confirmer/").data["statut_valeur"], "confirme")
        self.client.force_authenticate(user("chef@etls.ga", User.Role.CHEF_ATELIER))
        self.assertEqual(self.client.patch(f"/api/qualite/parametres/{p.pk}/", {"valeur": "1"}, format="json").status_code, 403)

    def test_relance_et_escalade_capa_en_retard(self):
        nc = NonConformite.objects.create(description="Porosité")
        capa = ActionCorrective.objects.create(non_conformite=nc, description="Reprise", responsable=self.qa,
                                               echeance=self.today - timedelta(days=1))
        relances_qualite()
        self.assertTrue(Notification.objects.filter(user=self.qa, subject__startswith=f"CAPA {capa.code} en retard").exists())
        self.assertFalse(Notification.objects.filter(user=self.dop).exists())  # escalade à J+2 (paramètre)
        capa.echeance = self.today - timedelta(days=3)
        capa.save()
        relances_qualite()
        self.assertTrue(Notification.objects.filter(user=self.dop, subject__startswith="Escalade").exists())
        capa.refresh_from_db()
        self.assertIsNotNone(capa.escaladee_le)
        relances_qualite()  # pas de doublon le même jour
        self.assertEqual(Notification.objects.filter(user=self.dop).count(), 1)


class ItpPunchTests(Base):
    def test_point_itp_en_retard_signale(self):
        point = self.itp.points.get()
        point.date_prevue = self.today - timedelta(days=2)
        point.save()
        r = self.client.get(f"/api/qualite/points-inspection/?controle={self.itp.pk}&en_retard=1")
        self.assertTrue(r.data["results"][0]["en_retard"])
        relances_qualite()
        self.assertTrue(Notification.objects.filter(user=self.qa, subject__contains="en retard").exists())

    def test_punch_list_a_bloque_la_liberation(self):
        r = self.client.post("/api/qualite/punch-list/", {
            "ordre": str(self.of.pk), "itp": str(self.itp.pk), "repere": "SP-12", "description": "Support manquant",
            "categorie": "A", "echeance": str(self.today + timedelta(days=3)),
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.data["code"].startswith("PCH-"))
        ControleQualite.objects.create(type_controle="visuel", ordre=self.of, statut="valide", resultat="conforme")
        self.itp.statut = "valide"
        self.itp.resultat = "conforme"
        self.itp.save()
        self.assertIn("punch list", controle_liberation(self.of))
        self.assertEqual(self.client.post(f"/api/qualite/punch-list/{r.data['id']}/lever/", {"commentaire": "posé"}, format="json").status_code, 200)
        self.assertIsNone(controle_liberation(self.of))


class DossierIndicateursTests(Base):
    def test_dossier_qualite_scelle_en_ged_a_la_levee_de_reserve(self):
        from documents.models import Document

        pv = PvControle.objects.create(ordre=self.of, intitule="Réception spool B")
        r = self.client.post(f"/api/qualite/pvs/{pv.pk}/levee-reserve/", {"reserve": False}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        pv.refresh_from_db()
        doc = Document.objects.get(pk=pv.dossier_document_id)
        self.assertEqual(doc.status, Document.Status.ARCHIVED)
        self.assertEqual(doc.type.retention_years, 10)
        self.assertEqual(len(doc.sha256), 64)
        self.assertEqual(pv.date_archivage, self.today)
        pdf = self.client.get(f"/api/qualite/pvs/{pv.pk}/dossier/")
        self.assertEqual(pdf["Content-Type"], "application/pdf")

    def test_reserve_ne_scelle_pas(self):
        pv = PvControle.objects.create(ordre=self.of, intitule="Réception partielle")
        self.client.post(f"/api/qualite/pvs/{pv.pk}/levee-reserve/", {"reserve": True, "motif": "peinture"}, format="json")
        pv.refresh_from_db()
        self.assertIsNone(pv.dossier_document_id)

    def test_indicateurs_et_rapport_mensuel(self):
        DiffusionWps.objects.create(wps=self.wps, ordre=self.of)
        for n in range(4):
            self.assertEqual(self.joint(f"J{n}").status_code, 201)
        ControleQualite.objects.create(type_controle="cnd", ordre=self.of, statut="valide", resultat="conforme")
        ControleQualite.objects.create(type_controle="cnd", ordre=self.of, statut="valide", resultat="non_conforme")
        NonConformite.objects.create(type_ncr="soudage", joint=JointSoude.objects.first(), description="Fissure",
                                     traitement="rejet")
        r = self.client.get(f"/api/qualite/indicateurs/?annee={self.today.year}&mois={self.today.month}")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["controles"], 3)  # 2 CND + l'ITP du jour
        self.assertEqual(r.data["taux_conformite"], 50.0)
        self.assertEqual(r.data["densite_defauts"], 25.0)
        self.assertEqual(r.data["rebuts"], 1)
        pdf = self.client.get(f"/api/qualite/indicateurs/?annee={self.today.year}&mois={self.today.month}&export=pdf")
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertEqual(self.client.get("/api/qualite/indicateurs/?mois=13").status_code, 400)
