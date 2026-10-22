"""Écarts M6-C (CDC M6.2, ISO 9001) : liste maîtresse versionnée, organisation, processus, audits (NC d'écart,
agrément fournisseur), compétences, revue de direction scellée en GED."""

from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from analytics.services import alertes_agregees
from referentiels.models import Partner
from users.models import User

from .models import AuditQualite, DocumentQualite, NonConformite, QualificationSoudeur, Soudeur


def user(email, role):
    return User.objects.create_user(email=email, password="x-Ecarts-2026", role=role, first_name=email[:3])


class Base(APITestCase):
    def setUp(self):
        self.qa = user("qa@etls.ga", User.Role.QAQC)
        self.pdg = user("pdg@etls.ga", User.Role.PDG)
        self.client.force_authenticate(self.qa)
        self.today = timezone.localdate()

    def post(self, url, data=None, code=None):
        r = self.client.post(url, data or {}, format="json")
        if code:
            self.assertEqual(r.status_code, code, r.content)
        return r


class DocumentsQualiteTests(Base):
    def test_cycle_version_approbation_revision(self):
        doc = self.post("/api/qualite/documents-qualite/", {"type_doc": "procedure", "titre": "Maîtrise des NC"}, 201).data
        self.assertTrue(doc["reference"].startswith("DQ-"))
        v1 = self.post(f"/api/qualite/documents-qualite/{doc['id']}/approuver/", code=200).data
        self.assertEqual(v1["statut"], "approuve")
        self.assertIsNotNone(v1["document"])  # scellé en GED
        self.assertIsNotNone(v1["date_revue"])
        self.assertEqual(self.client.patch(f"/api/qualite/documents-qualite/{doc['id']}/", {"titre": "x"}, format="json").status_code, 400)
        self.post(f"/api/qualite/documents-qualite/{doc['id']}/reviser/", {}, 400)  # motif obligatoire
        v2 = self.post(f"/api/qualite/documents-qualite/{doc['id']}/reviser/", {"motif": "Ajout escalade"}, 201).data
        self.assertEqual((v2["reference"], v2["version"], v2["statut"]), (doc["reference"], 2, "brouillon"))
        self.post(f"/api/qualite/documents-qualite/{doc['id']}/reviser/", {"motif": "doublon"}, 400)
        self.post(f"/api/qualite/documents-qualite/{v2['id']}/approuver/", code=200)
        self.assertEqual(DocumentQualite.objects.get(pk=doc["id"]).statut, "obsolete")
        en_vigueur = self.client.get("/api/qualite/documents-qualite/?en_vigueur=1").data["results"]
        self.assertEqual([(d["reference"], d["version"]) for d in en_vigueur], [(doc["reference"], 2)])

    def test_fichier_joint_puis_scelle(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        doc = self.post("/api/qualite/documents-qualite/", {"type_doc": "manuel", "titre": "Manuel qualité"}, 201).data
        url = f"/api/qualite/documents-qualite/{doc['id']}/fichier/"
        self.assertEqual(self.client.post(url, {"fichier": SimpleUploadedFile("x.exe", b"MZ")}, format="multipart").status_code, 400)
        r = self.client.post(url, {"fichier": SimpleUploadedFile("manuel.pdf", b"%PDF-1.4 manuel")}, format="multipart")
        self.assertEqual(r.status_code, 200, r.content)
        self.client.force_authenticate(self.pdg)
        self.post(f"/api/qualite/documents-qualite/{doc['id']}/approuver/", code=200)
        r = self.client.post(url, {"fichier": SimpleUploadedFile("v2.pdf", b"%PDF-1.4 v2")}, format="multipart")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(len(self.client.get("/api/qualite/organisation/utilisateurs/").data), 2)

    def test_politique_approuvee_par_la_direction(self):
        doc = self.post("/api/qualite/documents-qualite/", {"type_doc": "politique", "titre": "Politique qualité 2026"}, 201).data
        self.post(f"/api/qualite/documents-qualite/{doc['id']}/approuver/", code=403)
        self.client.force_authenticate(self.pdg)
        self.post(f"/api/qualite/documents-qualite/{doc['id']}/approuver/", code=200)

    def test_plan_qualite_exige_une_affaire(self):
        r = self.post("/api/qualite/documents-qualite/", {"type_doc": "plan_qualite", "titre": "PQ"}, 400)
        self.assertIn("affaire", r.data)

    def test_alerte_revue_documentaire(self):
        doc = self.post("/api/qualite/documents-qualite/", {"type_doc": "instruction", "titre": "Ressuage"}, 201).data
        self.post(f"/api/qualite/documents-qualite/{doc['id']}/approuver/", code=200)
        DocumentQualite.objects.filter(pk=doc["id"]).update(date_revue=self.today + timedelta(days=10))
        items = [i for i in alertes_agregees()["qualite"] if i["type"] == "revue_document"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["bande"], "j15")


class OrganisationProcessusTests(Base):
    def test_processus_et_indicateur(self):
        p = self.post("/api/qualite/processus/", {"libelle": "Fabrication", "indicateur": "Taux de conformité", "unite": "%",
                                                  "cible": "95", "sens": "mini", "pilote": str(self.qa.pk)}, 201).data
        self.assertTrue(p["code"].startswith("PROC-"))
        self.assertIsNone(p["cible_atteinte"])
        self.assertTrue(self.post(f"/api/qualite/processus/{p['id']}/mesurer/", {"valeur": "97.5"}, 200).data["cible_atteinte"])
        self.assertFalse(self.post(f"/api/qualite/processus/{p['id']}/mesurer/", {"valeur": "90"}, 200).data["cible_atteinte"])
        self.post(f"/api/qualite/processus/{p['id']}/mesurer/", {"valeur": "abc"}, 400)
        r = self.post("/api/qualite/organisation/", {"fonction": "Responsable QA/QC", "titulaire": str(self.qa.pk),
                                                     "missions": "Pilote le système qualité", "processus": p["id"]}, 201)
        self.assertEqual(r.data["processus_code"], p["code"])


class AuditsQualiteTests(Base):
    def audit(self, **kw):
        body = {"type_audit": "interne", "perimetre": "Atelier chaudronnerie", **kw}
        return self.post("/api/qualite/audits/", body, 201).data

    def test_ecart_ouvre_une_nc_et_bloque_la_cloture(self):
        a = self.audit()
        self.post(f"/api/qualite/audits/{a['id']}/cloturer/", code=400)  # pas encore réalisé
        self.post("/api/qualite/constats-audit/", {"audit": a["id"], "type_constat": "point_fort", "description": "Traçabilité"}, 201)
        c = self.post("/api/qualite/constats-audit/", {"audit": a["id"], "type_constat": "ecart_majeur", "exigence": "§8.7",
                                                       "description": "NC non enregistrées"}, 201).data
        nc = NonConformite.objects.get(pk=c["nc"])
        self.assertEqual((nc.source, nc.gravite), ("audit", "majeure"))
        self.post(f"/api/qualite/audits/{a['id']}/realiser/", {"score": 80}, 200)
        r = self.post(f"/api/qualite/audits/{a['id']}/cloturer/", code=400)
        self.assertIn("NC", r.data["detail"])
        NonConformite.objects.filter(pk=nc.pk).update(statut=NonConformite.Statut.CLOTUREE)
        clos = self.post(f"/api/qualite/audits/{a['id']}/cloturer/", code=200).data
        self.assertEqual(clos["statut"], "cloture")
        self.assertIsNotNone(clos["rapport"])
        self.post("/api/qualite/constats-audit/", {"audit": a["id"], "description": "après coup"}, 400)

    def test_audit_fournisseur_conclut_l_agrement(self):
        self.post("/api/qualite/audits/", {"type_audit": "fournisseur", "perimetre": "Peinture"}, 400)
        f = Partner.objects.create(code="F-PEINT", name="Peinture Gabon", kind="fournisseur")
        a = self.audit(type_audit="fournisseur", fournisseur=str(f.pk))
        self.post(f"/api/qualite/audits/{a['id']}/realiser/", {"score": 82}, 200)
        r = self.post(f"/api/qualite/audits/{a['id']}/cloturer/", code=200).data
        self.assertTrue(r["agrement_accorde"])
        f.refresh_from_db()
        # Durée unique d'agrément : paramètre M2 AGREMENT_DUREE_MOIS (12 mois provisoires).
        self.assertTrue(self.today + timedelta(days=330) < f.agree_qualite_jusqu <= self.today + timedelta(days=366))
        b = self.audit(type_audit="fournisseur", fournisseur=str(f.pk))
        self.post(f"/api/qualite/audits/{b['id']}/realiser/", {"score": 60}, 200)
        self.assertFalse(self.post(f"/api/qualite/audits/{b['id']}/cloturer/", code=200).data["agrement_accorde"])
        f.refresh_from_db()
        self.assertIsNone(f.agree_qualite_jusqu)
        self.assertEqual(AuditQualite.objects.filter(statut="cloture").count(), 2)


class CompetencesEtRevueTests(Base):
    def test_matrice_des_competences(self):
        from rh_paie.models import Employe, Qualification

        e = Employe.objects.create(code="M-001", nom="NDONG", prenom="Paul", statut=Employe.Statut.ACTIF)
        s = Soudeur.objects.create(nom="NDONG", employe=e)
        QualificationSoudeur.objects.create(soudeur=s, norme="iso9606", procede="gtaw", position="6G",
                                            date_qualification=self.today - timedelta(days=400), date_validite=self.today - timedelta(days=1))
        Qualification.objects.create(employe=e, intitule="Habilitation électrique B1V", date_validite=self.today + timedelta(days=200))
        rows = self.client.get("/api/qualite/competences/").data
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["code"], "M-001")
        self.assertEqual(sorted(i["origine"] for i in rows[0]["items"]), ["rh", "soudage"])
        self.assertEqual(rows[0]["a_renouveler"], 1)

    def test_revue_de_direction_validee_par_la_direction(self):
        r = self.post("/api/qualite/revues-direction/", {"annee": self.today.year}, 201).data
        self.assertIn("audits_realises", r["bilan"])
        self.assertIn("taux_conformite", r["bilan"]["indicateurs"])
        self.post(f"/api/qualite/revues-direction/{r['id']}/valider/", code=403)
        self.client.force_authenticate(self.pdg)
        self.assertIn("conclusions", self.post(f"/api/qualite/revues-direction/{r['id']}/valider/", code=400).data)
        self.client.patch(f"/api/qualite/revues-direction/{r['id']}/", {"participants": "PDG, QA/QC", "conclusions": "Système efficace",
                                                                         "decisions": "Certification ISO 9001"}, format="json")
        v = self.post(f"/api/qualite/revues-direction/{r['id']}/valider/", code=200).data
        self.assertEqual(v["statut"], "validee")
        self.assertIsNotNone(v["document"])
        self.assertEqual(self.client.patch(f"/api/qualite/revues-direction/{r['id']}/", {"decisions": "x"}, format="json").status_code, 400)
        pdf = self.client.get(f"/api/qualite/revues-direction/bilan/?annee={self.today.year}&export=pdf")
        self.assertEqual(pdf["Content-Type"], "application/pdf")
