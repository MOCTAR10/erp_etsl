"""Écarts M7 (lot ecarts-m6m7) — tests de recette.

- §9.2 : types de permis, d'incidents et de déchets en listes paramétrables (provisoires, confirmables).
- M7-02 : check-list d'audit appliquée, réponses (non conforme => constat), score calculé, rapport PDF.
- M7-03 : plan de prévention (inspection commune, risques, mesures) ; seuils de cotation et revue du DUER paramétrés.
- BSD : prestataire déchets agréé (validité, type) exigé à l'émission et au traitement.
- Sites GLOBAL RENTAL : plan de prévention validé exigé au démarrage du permis, partage à l'équipe intégrée.
- M7-08 : fiches sécurité publiées (lecture terrain), versionnées.
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from users.models import User
from workflow.models import Notification

from .models import (
    AuditHse,
    BordereauDechet,
    ConstatAudit,
    Duer,
    EvaluationRisque,
    FicheSecurite,
    ListeHse,
    ParametreHse,
    PermisTravail,
    PlanPrevention,
    PrestataireDechet,
)
from .services import get_param_hse


def _user(role, suffixe=""):
    return User.objects.create_user(email=f"{role}{suffixe}@m6m7.test", password="x-Audit-2026", role=role)


class _Base(APITestCase):
    def setUp(self):
        self.hse = _user(User.Role.HSE)
        self.client.force_authenticate(self.hse)

    def param(self, code, valeur):
        get_param_hse(code)
        ParametreHse.objects.filter(code=code).update(valeur=valeur)


class ListesParametrablesTests(_Base):
    def test_listes_par_defaut_provisoires_et_nouveau_type_utilisable(self):
        r = self.client.get("/api/hse/listes/?categorie=type_permis")
        self.assertEqual(r.status_code, 200)
        codes = {x["code"]: x for x in r.data["results"]}
        self.assertTrue(codes["chaud"]["gaz_obligatoire"])
        self.assertTrue(codes["chaud"]["est_provisoire"])
        r = self.client.post("/api/hse/listes/", {"categorie": "type_permis", "code": "radiographie",
                                                  "libelle": "Tirs radiographiques", "gaz_obligatoire": False}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        r = self.client.post("/api/hse/permis/", {"type_permis": "radiographie", "emplacement": "Baie 1",
                                                  "description": "Tir gamma"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["type_label"], "Tirs radiographiques")
        self.assertEqual(self.client.post("/api/hse/permis/", {"type_permis": "inconnu", "emplacement": "B",
                                                               "description": "x"}, format="json").status_code, 400)

    def test_desactivation_confirmation_et_validation_du_code(self):
        self.client.get("/api/hse/listes/")
        dib = ListeHse.objects.get(categorie="type_dechet", code="dib")
        self.assertEqual(self.client.patch(f"/api/hse/listes/{dib.pk}/", {"actif": False}, format="json").status_code, 200)
        r = self.client.post("/api/hse/bordereaux-dechets/", {"type_dechet": "dib", "quantite": "2"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.patch(f"/api/hse/listes/{dib.pk}/", {"code": "autre"}, format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/hse/listes/", {"categorie": "type_dechet", "code": "Bad Code",
                                                               "libelle": "x"}, format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/hse/listes/", {"categorie": "partage_gr", "code": "inconnu",
                                                               "libelle": "x"}, format="json").status_code, 400)
        r = self.client.post(f"/api/hse/listes/{dib.pk}/confirmer/")
        self.assertEqual((r.status_code, r.data["est_provisoire"]), (200, False))
        self.client.force_authenticate(_user(User.Role.LOGISTIQUE))
        self.assertEqual(self.client.post(f"/api/hse/listes/{dib.pk}/confirmer/").status_code, 403)
        self.assertEqual(self.client.get("/api/hse/listes/").status_code, 200)

    def test_type_incident_parametrable(self):
        self.client.post("/api/hse/listes/", {"categorie": "type_incident", "code": "morsure", "libelle": "Morsure animale"},
                         format="json")
        r = self.client.post("/api/hse/incidents/", {"type_incident": "morsure", "gravite": "mineure", "lieu": "Base",
                                                     "date_evenement": timezone.now().isoformat(), "description": "Chien"},
                             format="json")
        self.assertEqual((r.status_code, r.data["type_label"]), (201, "Morsure animale"))


class ChecklistAuditTests(_Base):
    def test_checklist_constats_score_et_rapport_pdf(self):
        modeles = self.client.get("/api/hse/modeles-checklist/").data["results"]
        self.assertEqual(len(modeles), 1)
        self.assertTrue(modeles[0]["est_provisoire"])
        r = self.client.post("/api/hse/modeles-checklist/", {"intitule": "Atelier", "questions_texte": "Q1\n\nQ2\nQ3"},
                             format="json")
        self.assertEqual((r.status_code, r.data["questions"]), (201, ["Q1", "Q2", "Q3"]))
        modele = r.data["id"]
        audit = AuditHse.objects.create(zone="Atelier")
        r = self.client.post(f"/api/hse/audits/{audit.pk}/appliquer-checklist/", {"modele": modele}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.client.post(f"/api/hse/audits/{audit.pk}/appliquer-checklist/", {"modele": modele},
                                          format="json").status_code, 400)
        reps = self.client.get(f"/api/hse/reponses-checklist/?audit={audit.pk}").data["results"]
        self.assertEqual(len(reps), 3)
        # Réalisation refusée tant que la check-list n'est pas complète.
        self.assertEqual(self.client.post(f"/api/hse/audits/{audit.pk}/realiser/", {}, format="json").status_code, 400)
        url = "/api/hse/reponses-checklist/{}/repondre/"
        self.assertEqual(self.client.post(url.format(reps[0]["id"]), {"reponse": "conforme"}).status_code, 200)
        r = self.client.post(url.format(reps[1]["id"]), {"reponse": "non_conforme", "gravite": "majeur", "commentaire": "Pas de FDS"})
        self.assertEqual(r.status_code, 200)
        constat = ConstatAudit.objects.get(pk=r.data["constat"])
        self.assertEqual((constat.gravite, constat.audit_id), ("majeur", audit.pk))
        self.assertIn("Pas de FDS", constat.description)
        self.assertEqual(self.client.post(url.format(reps[2]["id"]), {"reponse": "en_attente"}).status_code, 400)
        self.client.post(url.format(reps[2]["id"]), {"reponse": "sans_objet"})
        r = self.client.post(f"/api/hse/audits/{audit.pk}/realiser/", {}, format="json")
        self.assertEqual((r.status_code, r.data["score"]), (200, 50))
        # Clôture impossible tant que l'écart issu de la check-list n'a pas d'action clôturée.
        self.assertEqual(self.client.post(f"/api/hse/audits/{audit.pk}/cloturer/").status_code, 400)
        r = self.client.get(f"/api/hse/audits/{audit.pk}/rapport-pdf/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b"%PDF"))

    def test_point_reevalue_conforme_retire_le_constat(self):
        self.client.get("/api/hse/modeles-checklist/")
        audit = AuditHse.objects.create(zone="Chantier")
        from .models import ModeleChecklistHse

        self.client.post(f"/api/hse/audits/{audit.pk}/appliquer-checklist/",
                         {"modele": str(ModeleChecklistHse.objects.get().pk)}, format="json")
        rep = audit.reponses_checklist.first()
        self.client.post(f"/api/hse/reponses-checklist/{rep.pk}/repondre/", {"reponse": "non_conforme"})
        self.assertEqual(audit.constats.count(), 1)
        self.client.post(f"/api/hse/reponses-checklist/{rep.pk}/repondre/", {"reponse": "conforme"})
        self.assertEqual(audit.constats.count(), 0)


class PlanPreventionTests(_Base):
    def test_cycle_plan_de_prevention(self):
        r = self.client.post("/api/hse/plans-prevention/", {"entreprise_exterieure": "Levage Sud", "site": "Port-Gentil",
                                                            "mesures": "Balisage, chef de manœuvre"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        pdp = r.data["id"]
        self.assertEqual(self.client.post(f"/api/hse/plans-prevention/{pdp}/valider/").status_code, 400)  # sans inspection
        self.client.patch(f"/api/hse/plans-prevention/{pdp}/", {"date_inspection_commune": str(timezone.localdate())}, format="json")
        self.assertEqual(self.client.post(f"/api/hse/plans-prevention/{pdp}/valider/").status_code, 400)  # sans risque
        risque = EvaluationRisque.objects.create(lieux="Quai", description="Chute de charge", probabilite=3, gravite=4)
        self.assertEqual(self.client.post(f"/api/hse/plans-prevention/{pdp}/ajouter-risque/", {"risque": str(risque.pk)}).status_code, 200)
        r = self.client.post(f"/api/hse/plans-prevention/{pdp}/valider/")
        self.assertEqual(r.status_code, 400)  # risque élevé (12) sans mesure
        risque.mesure = "Zone d'exclusion"
        risque.save()
        r = self.client.post(f"/api/hse/plans-prevention/{pdp}/valider/")
        self.assertEqual((r.status_code, r.data["statut"], r.data["en_vigueur"]), (200, "valide", True))
        self.assertEqual(self.client.patch(f"/api/hse/plans-prevention/{pdp}/", {"site": "x"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(f"/api/hse/plans-prevention/{pdp}/cloturer/").status_code, 200)

    def test_seuils_de_cotation_et_revue_duer_parametrables(self):
        risque = EvaluationRisque.objects.create(lieux="A", description="Bruit", probabilite=2, gravite=2)
        self.assertEqual(risque.criticite, "moyenne")
        self.param("RISQUE_SEUIL_MOYEN", 5)
        self.assertEqual(risque.criticite, "faible")
        duer = Duer.objects.create(annee=2025, perimetre="Atelier", statut="approuve",
                                   approuve_le=timezone.now() - timedelta(days=200))
        self.assertFalse(duer.a_revoir)
        self.param("DUER_REVUE_MOIS", 6)
        self.assertTrue(duer.a_revoir)


class BsdPrestataireTests(_Base):
    def test_emission_exige_un_prestataire_agree_pour_le_type(self):
        r = self.client.post("/api/hse/prestataires-dechets/", {
            "nom": "Gabon Recyclage", "numero_agrement": "MEF-42", "types_dechets": "huiles, solvants",
            "date_fin_validite": str(timezone.localdate() + timedelta(days=100)),
        }, format="json")
        self.assertEqual((r.status_code, r.data["types_dechets"]), (201, "huiles,solvants"))
        prestataire = PrestataireDechet.objects.get(pk=r.data["id"])
        self.assertEqual(self.client.post("/api/hse/prestataires-dechets/", {"nom": "X", "numero_agrement": "1",
                         "types_dechets": "plutonium", "date_fin_validite": "2030-01-01"}, format="json").status_code, 400)
        bsd = BordereauDechet.objects.create(type_dechet="dib", quantite=3)
        url = f"/api/hse/bordereaux-dechets/{bsd.pk}/"
        r = self.client.post(url + "emettre/", {"numero_bsd": "BSD-1"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("prestataire", r.data)
        self.assertEqual(self.client.post(url + "affecter-prestataire/", {"prestataire": str(prestataire.pk)}).status_code, 400)
        self.client.patch(url, {"prestataire": str(prestataire.pk)}, format="json")
        self.assertEqual(self.client.post(url + "emettre/", {"numero_bsd": "BSD-1"}).status_code, 400)  # DIB non couvert
        self.client.patch(url, {"type_dechet": "huiles", "prestataire": None}, format="json")
        r = self.client.post(url + "affecter-prestataire/", {"prestataire": str(prestataire.pk)})
        self.assertEqual((r.status_code, r.data["prestataire_nom"]), (200, "Gabon Recyclage"))
        self.assertEqual(self.client.post(url + "emettre/", {}).status_code, 400)  # n° de BSD requis
        r = self.client.post(url + "emettre/", {"numero_bsd": "BSD-1"})
        self.assertEqual((r.status_code, r.data["statut"]), (200, "emis"))
        PrestataireDechet.objects.filter(pk=prestataire.pk).update(date_fin_validite=timezone.localdate() - timedelta(days=1))
        self.assertEqual(self.client.post(url + "traiter/").status_code, 400)  # agrément expiré
        PrestataireDechet.objects.filter(pk=prestataire.pk).update(date_fin_validite=timezone.localdate() + timedelta(days=1))
        r = self.client.post(url + "traiter/")
        self.assertEqual((r.status_code, r.data["statut"]), (200, "traite"))
        bsd.refresh_from_db()
        self.assertIsNotNone(bsd.document_id)

    def test_parametre_desactive_le_controle_et_patch_controle(self):
        bsd = BordereauDechet.objects.create(type_dechet="dib", quantite=1)
        self.assertEqual(self.client.patch(f"/api/hse/bordereaux-dechets/{bsd.pk}/", {"statut": "emis"},
                                           format="json").status_code, 400)
        get_param_hse("BSD_AGREMENT_OBLIGATOIRE")
        p = ParametreHse.objects.get(code="BSD_AGREMENT_OBLIGATOIRE")
        self.assertEqual(self.client.patch(f"/api/hse/parametres/{p.pk}/", {"valeur": "0"}, format="json").status_code, 200)
        self.assertEqual(self.client.patch(f"/api/hse/parametres/{p.pk}/", {"valeur": "2"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(f"/api/hse/bordereaux-dechets/{bsd.pk}/", {"statut": "emis"},
                                           format="json").status_code, 200)


class SiteGrTests(_Base):
    def test_permis_sur_site_gr_exige_un_plan_de_prevention_et_partage(self):
        logistique = _user(User.Role.LOGISTIQUE)
        r = self.client.post("/api/hse/permis/", {"type_permis": "levage", "emplacement": "Parc GR", "description": "Levage",
                                                  "site_gr": True}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(Notification.objects.filter(user=logistique, subject__contains="Site GLOBAL RENTAL").exists())
        permis = PermisTravail.objects.get(pk=r.data["id"])
        PermisTravail.objects.filter(pk=permis.pk).update(statut="valide")
        r = self.client.post(f"/api/hse/permis/{permis.pk}/demarrer/")
        self.assertEqual(r.status_code, 400)
        self.assertIn("plan de prévention", r.data["detail"])
        pdp = PlanPrevention.objects.create(entreprise_exterieure="GLOBAL RENTAL", site="Parc", site_gr=True,
                                            statut="valide", date_debut=timezone.localdate())
        PermisTravail.objects.filter(pk=permis.pk).update(plan_prevention=pdp)
        self.assertEqual(self.client.post(f"/api/hse/permis/{permis.pk}/demarrer/").status_code, 200)

    def test_incident_sur_site_gr_partage_aux_roles_parametres(self):
        dir_op = _user(User.Role.DIRECTEUR_OPERATIONS)
        self.client.post("/api/hse/incidents/", {"type_incident": "incident", "gravite": "mineure", "lieu": "Base GR",
                                                 "zone": "site_gr", "date_evenement": timezone.now().isoformat(),
                                                 "description": "Fuite"}, format="json")
        self.assertTrue(Notification.objects.filter(user=dir_op, subject__contains="Site GLOBAL RENTAL").exists())
        ListeHse.objects.filter(categorie="partage_gr", code="directeur_operations").update(actif=False)
        Notification.objects.all().delete()
        self.client.post("/api/hse/incidents/", {"type_incident": "incident", "gravite": "mineure", "lieu": "Base GR",
                                                 "zone": "site_gr", "date_evenement": timezone.now().isoformat(),
                                                 "description": "Fuite 2"}, format="json")
        self.assertFalse(Notification.objects.filter(user=dir_op, subject__contains="Site GLOBAL RENTAL").exists())


class FichesSecuriteTests(_Base):
    def test_fiches_par_defaut_publiees_versionnees(self):
        r = self.client.get("/api/hse/fiches-securite/?publiees=1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 3)
        self.assertTrue(all(f["provisoire"] for f in r.data["results"]))
        fiche = FicheSecurite.objects.get(code="FS-CHAUD")
        r = self.client.patch(f"/api/hse/fiches-securite/{fiche.pk}/", {"consignes": "Consignes ETSL"}, format="json")
        self.assertEqual((r.data["version"], r.data["statut"], r.data["provisoire"]), (2, "brouillon", False))
        self.assertEqual(self.client.get("/api/hse/fiches-securite/?publiees=1").data["count"], 2)
        self.assertEqual(self.client.post(f"/api/hse/fiches-securite/{fiche.pk}/publier/").status_code, 200)
        self.assertEqual(self.client.post(f"/api/hse/fiches-securite/{fiche.pk}/publier/").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/hse/fiches-securite/{fiche.pk}/").status_code, 405)
        # Lecture terrain : un chef d'atelier (lecteur HSE) consulte les fiches publiées.
        self.client.force_authenticate(_user(User.Role.CHEF_ATELIER))
        self.assertEqual(self.client.get("/api/hse/fiches-securite/?publiees=1").status_code, 200)
