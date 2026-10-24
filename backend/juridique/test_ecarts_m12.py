"""Écarts M12 (2026-10) — tests de recette des lignes A du tri (et du paramètre provisoire « DEEE », ligne B).

Paramètres provisoires · dossier complet · suivi contentieux (juridiction, jalons, journal) · validation DG
bloquante · alertes J-60 (contrats M1, jalons, mandats GR) et notification · archivage légal (rétention éditable,
purge validée) · recherche juridique (M9 / M12 liables, liage automatique) · vue Risk · dossier GR « à jour » ·
archivage automatique en GED à la transition.
"""

import hashlib
from datetime import date, timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from commercial.models import Contract
from documents.models import DemandePurge, Document, DocumentType, Version
from referentiels.models import Partner
from users.models import User
from workflow.models import Notification

from . import ecarts
from .models import (
    ActionContentieux,
    Caution,
    Contentieux,
    Convention,
    DossierGlobalRental,
    JalonContentieux,
    LienDocument,
    ParametreJuridique,
)

BASE = "/api/juridique/"
TODAY = date.today()


def _user(email, role):
    return User.objects.create_user(email=email, password="x-Audit-2026", role=role, first_name=email[:3])


def _document(titre, statut=Document.Status.DRAFT, type_=None, **kw):
    contenu = f"%PDF-1.4 {titre}".encode()
    doc = Document.objects.create(title=titre, status=statut, type=type_, **kw)
    v = Version.objects.create(
        document=doc, number=1, file=SimpleUploadedFile("d.pdf", contenu),
        sha256=hashlib.sha256(contenu).hexdigest(), size=len(contenu), original_filename="d.pdf",
    )
    doc.current_version = v
    doc.sha256 = v.sha256
    doc.save()
    return doc


class EcartsM12Base(APITestCase):
    def setUp(self):
        self.admin = _user("adm@etls.ga", User.Role.ADMIN)
        self.dg = _user("dg@etls.ga", User.Role.PDG)
        self.dga = _user("dga@etls.ga", User.Role.DGA)
        self.sg = _user("sg@etls.ga", User.Role.SECRETAIRE_GENERAL)
        self.finance = _user("fin@etls.ga", User.Role.FINANCE)
        self.projets = _user("proj@etls.ga", User.Role.DIRECTEUR_PROJETS)
        self.gr = Partner.objects.create(code="GR-T", name="GLOBAL RENTAL", kind=Partner.Kind.FOURNISSEUR, is_global_rental=True)

    def as_(self, user):
        self.client.force_authenticate(user)
        return self.client

    def set_param(self, cle, valeur):
        p = ecarts.parametre_obj(cle)
        p.valeur = valeur
        p.save()


class ParametresTests(EcartsM12Base):
    def test_parametres_provisoires_listes_modifies_par_la_dg_et_confirmes(self):
        r = self.as_(self.sg).get(f"{BASE}parametres/")
        self.assertEqual(r.status_code, 200)
        rows = r.data["results"] if isinstance(r.data, dict) else r.data
        cles = {p["cle"] for p in rows}
        self.assertTrue({"pieces_requises", "juridictions", "roles_dg", "paliers_notification", "deee"} <= cles)
        self.assertTrue(all(p["provisoire"] for p in rows))
        p = ParametreJuridique.objects.get(cle="paliers_notification")
        url = f"{BASE}parametres/{p.pk}/modifier/"
        self.assertEqual(self.as_(self.sg).post(url, {"valeur": [90, 60]}, format="json").status_code, 403)
        self.assertEqual(self.as_(self.dg).post(url, {"valeur": "[90, 45]"}, format="json").status_code, 200)
        self.assertEqual(self.as_(self.dg).post(url, {"valeur": ["x"]}, format="json").status_code, 400)
        self.assertEqual(self.as_(self.dg).post(url, {"valeur": {"a": 1}}, format="json").status_code, 400)
        r = self.as_(self.dg).post(f"{BASE}parametres/{p.pk}/confirmer/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["provisoire"])
        self.assertEqual(ecarts.parametre("paliers_notification"), [90, 45])

    def test_roles_dg_parametrables(self):
        caution = Caution.objects.create(type="avance", beneficiaire="X", objet="Y", montant=Decimal("1000"),
                                         date_emission=TODAY, date_echeance=TODAY + timedelta(days=200))
        url = f"{BASE}cautions/{caution.pk}/valider-dg/"
        self.assertEqual(self.as_(self.dga).post(url).status_code, 403)
        self.set_param("roles_dg", ["pdg", "dga"])
        self.assertEqual(self.as_(self.dga).post(url).status_code, 200)


class DossierCompletTests(EcartsM12Base):
    def test_completude_par_type_et_blocage_parametre(self):
        conv = Convention.objects.create(type="marche_travaux", titre="Marché pipeline", date_debut=TODAY,
                                         date_fin=TODAY + timedelta(days=400))
        r = self.as_(self.sg).get(f"{BASE}conventions/{conv.pk}/")
        self.assertFalse(r.data["completude"]["complet"])
        self.assertIn("cahier_des_charges", r.data["completude"]["manquantes"])
        doc = _document("Cahier des charges")
        body = {"dossier_type": "convention", "dossier_id": str(conv.pk), "piece": "cahier_des_charges",
                "document": str(doc.pk)}
        self.assertEqual(self.as_(self.sg).post(f"{BASE}pieces/", body, format="json").status_code, 201)
        self.assertEqual(self.as_(self.sg).post(f"{BASE}pieces/", body, format="json").status_code, 400)  # doublon
        intrus = dict(body, piece="inconnue")
        self.assertEqual(self.as_(self.sg).post(f"{BASE}pieces/", intrus, format="json").status_code, 400)
        r = self.as_(self.sg).get(f"{BASE}conventions/{conv.pk}/")
        self.assertEqual(r.data["completude"]["taux_pct"], "25")
        # Blocage paramétrable (désactivé par défaut) : signature refusée tant que le dossier est incomplet.
        self.set_param("bloquer_dossier_incomplet", True)
        r = self.as_(self.sg).post(f"{BASE}conventions/{conv.pk}/signer/")
        self.assertEqual(r.status_code, 400)
        for piece in ("convention_signee", "caution_bonne_execution", "pieces_administratives"):
            d = _document(piece)
            self.as_(self.sg).post(f"{BASE}pieces/", dict(body, piece=piece, document=str(d.pk)), format="json")
        self.assertEqual(self.as_(self.sg).post(f"{BASE}conventions/{conv.pk}/signer/").status_code, 200)

    def test_contentieux_social_pieces_specifiques(self):
        lit = Contentieux.objects.create(nature="social", objet="Licenciement", partie_adverse="M. X")
        self.assertIn("contrat_travail", ecarts.completude("contentieux", lit)["requises"])


class SuiviContentieuxTests(EcartsM12Base):
    def test_juridiction_jalons_journal_et_phase(self):
        lit = Contentieux.objects.create(nature="commercial", objet="Impayé", partie_adverse="Client Z",
                                         montant_en_jeu=Decimal("20000000"))
        url = f"{BASE}contentieux/{lit.pk}/"
        self.assertEqual(self.as_(self.sg).patch(url, {"juridiction": "Tribunal imaginaire"}, format="json").status_code, 400)
        self.assertEqual(self.as_(self.sg).patch(url, {"juridiction": "Tribunal de commerce de Libreville"},
                                                  format="json").status_code, 200)
        r = self.as_(self.sg).post(f"{BASE}jalons/", {"contentieux": str(lit.pk), "libelle": "Audience de mise en état",
                                                       "date_prevue": str(TODAY + timedelta(days=60))}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        jalon_id = r.data["id"]
        self.assertEqual(self.as_(self.sg).post(f"{BASE}actions-contentieux/", {
            "contentieux": str(lit.pk), "type": "conclusions", "description": "Dépôt des conclusions en défense"},
            format="json").status_code, 201)
        r = self.as_(self.sg).post(f"{url}qualifier/", {"probabilite": "forte"}, format="json")
        self.assertEqual((r.status_code, r.data["probabilite"]), (200, "forte"))
        self.assertEqual(self.as_(self.sg).post(f"{url}qualifier/", {"probabilite": "x"}, format="json").status_code, 400)
        self.assertEqual(self.as_(self.sg).post(f"{url}qualifier/", {"juridiction": "Nulle part"}, format="json").status_code, 400)
        r = self.as_(self.sg).post(f"{url}avancer-phase/", {"phase": "tribunal"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["phase"], "tribunal")
        self.assertEqual(self.as_(self.sg).post(f"{url}avancer-phase/", {"phase": "lune"}, format="json").status_code, 400)
        # Jalon dans les alertes (J-60) puis réalisé.
        alertes = self.as_(self.sg).get(f"{BASE}alertes/").data
        self.assertEqual([j["bande"] for j in alertes["jalons"]], ["j60"])
        self.assertEqual(self.as_(self.sg).post(f"{BASE}jalons/{jalon_id}/realiser/").status_code, 200)
        self.assertEqual(self.as_(self.sg).post(f"{BASE}jalons/{jalon_id}/realiser/").status_code, 400)
        self.assertEqual(JalonContentieux.objects.get(pk=jalon_id).date_realisee, TODAY)
        types = list(ActionContentieux.objects.filter(contentieux=lit).values_list("type", flat=True))
        self.assertIn("phase", types)
        self.assertIn("conclusions", types)
        self.assertEqual(self.as_(self.sg).get(f"{BASE}actions-contentieux/?contentieux={lit.pk}").data["count"], len(types))
        # Le journal est inaltérable (ni modification ni suppression).
        action_id = ActionContentieux.objects.filter(contentieux=lit).first().pk
        self.assertEqual(self.as_(self.admin).delete(f"{BASE}actions-contentieux/{action_id}/").status_code, 405)


class ValidationDgBloquanteTests(EcartsM12Base):
    def test_convention_garantie_non_validee_dg_non_signable(self):
        conv = Convention.objects.create(type="prestation", titre="Prestation", date_debut=TODAY,
                                         date_fin=TODAY + timedelta(days=200))
        caution = Caution.objects.create(type="bonne_execution", beneficiaire="Client", objet="BE",
                                         montant=Decimal("5000000"), date_emission=TODAY,
                                         date_echeance=TODAY + timedelta(days=300), convention=conv)
        r = self.as_(self.sg).post(f"{BASE}conventions/{conv.pk}/signer/")
        self.assertEqual(r.status_code, 400)
        self.assertIn(caution.code, str(r.data))
        self.assertEqual(self.as_(self.dg).post(f"{BASE}cautions/{caution.pk}/valider-dg/").status_code, 200)
        self.assertEqual(self.as_(self.sg).post(f"{BASE}conventions/{conv.pk}/signer/").status_code, 200)
        self.assertFalse(self.as_(self.sg).get(f"{BASE}cautions/{caution.pk}/").data["en_attente_dg"])

    def test_blocage_desactivable(self):
        caution = Caution.objects.create(type="avance", beneficiaire="X", objet="Y", montant=Decimal("1000"),
                                         date_emission=TODAY, date_echeance=TODAY + timedelta(days=200))
        self.assertEqual(self.as_(self.dg).post(f"{BASE}cautions/{caution.pk}/appeler/").status_code, 400)
        self.set_param("bloquer_sans_validation_dg", False)
        self.assertEqual(self.as_(self.dg).post(f"{BASE}cautions/{caution.pk}/appeler/").status_code, 200)


class AlertesNotificationTests(EcartsM12Base):
    def test_contrat_m1_et_mandat_gr_alertes_et_notification_j60(self):
        Contract.objects.create(profile="maintenance", start_date=TODAY - timedelta(days=300),
                                end_date=TODAY + timedelta(days=60), status="actif")
        DossierGlobalRental.objects.create(partenaire_gr=self.gr, objet="Location grue", date_debut=TODAY,
                                           date_fin=TODAY + timedelta(days=400), mandat_date_fin=TODAY + timedelta(days=30))
        alertes = self.as_(self.sg).get(f"{BASE}alertes/").data
        self.assertEqual([c["bande"] for c in alertes["contrats_m1"]], ["j60"])
        self.assertEqual([m["bande"] for m in alertes["mandats_gr"]], ["j30"])
        self.assertGreaterEqual(alertes["compteurs"]["j60"], 1)
        self.assertEqual(self.as_(self.projets).post(f"{BASE}alertes/notifier/").status_code, 403)
        r = self.as_(self.sg).post(f"{BASE}alertes/notifier/")
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.data["envoyees"], 2)
        self.assertTrue(Notification.objects.filter(user=self.projets, subject__startswith="Échéance J-60").exists())
        self.assertTrue(Notification.objects.filter(user=self.finance, subject__startswith="Échéance J-30").exists())
        # Dédupliqué dans la journée.
        self.assertEqual(self.as_(self.sg).post(f"{BASE}alertes/notifier/").data["envoyees"], 0)
        # Palier J-60 retiré du paramètre : plus de notification à J-60.
        Notification.objects.all().delete()
        self.set_param("paliers_notification", [30])
        ecarts.notifier_echeances_juridiques()
        self.assertFalse(Notification.objects.filter(subject__startswith="Échéance J-60").exists())


class RisqueTests(EcartsM12Base):
    def test_vue_risk_cotation_et_masquage(self):
        Contentieux.objects.create(nature="client", objet="Gros litige", partie_adverse="A",
                                   montant_en_jeu=Decimal("100000000"), probabilite="forte")
        Contentieux.objects.create(nature="client", objet="Petit litige", partie_adverse="B",
                                   montant_en_jeu=Decimal("1000000"), probabilite="faible")
        Contentieux.objects.create(nature="client", objet="Non coté", partie_adverse="C")
        r = self.as_(self.finance).get(f"{BASE}risques/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["par_niveau"], {"eleve": 1, "moyen": 0, "faible": 1, "non_cote": 1})
        self.assertEqual(r.data["contentieux"][0]["exposition"], "70000000")
        self.assertEqual(r.data["total_exposition"], "70100000")
        masque = self.as_(self.projets).get(f"{BASE}risques/").data  # lit M12, hors cercle des montants
        self.assertIsNone(masque["total_enjeu"])
        self.assertIsNone(masque["contentieux"][0]["montant_en_jeu"])
        self.assertEqual(masque["contentieux"][0]["niveau"], "eleve")


class DossierGrTests(EcartsM12Base):
    def test_dossier_gr_a_jour(self):
        from logistique.models import TarifGR

        d = DossierGlobalRental.objects.create(partenaire_gr=self.gr, objet="Location nacelle", date_debut=TODAY,
                                               date_fin=TODAY + timedelta(days=300))
        r = self.as_(self.sg).get(f"{BASE}dossiers-gr/{d.pk}/")
        self.assertFalse(r.data["controle"]["a_jour"])
        self.assertEqual(len(r.data["controle"]["motifs"]), 4)
        self.assertEqual(self.as_(self.sg).post(f"{BASE}dossiers-gr/{d.pk}/mandat/",
                                                {"mandat_date_fin": str(TODAY + timedelta(days=365)),
                                                 "mandat_reference": "MAND-2026"}, format="json").status_code, 200)
        self.assertEqual(self.as_(self.sg).post(f"{BASE}dossiers-gr/{d.pk}/revoir/").status_code, 200)
        TarifGR.objects.create(code="TGR-TEST", partenaire=self.gr, tarif=Decimal("150000"),
                               date_effet=TODAY - timedelta(days=1))
        for piece in ("contrat_cadre_gr", "mandat", "grille_tarifaire"):
            doc = _document(piece)
            self.as_(self.sg).post(f"{BASE}pieces/", {"dossier_type": "gr", "dossier_id": str(d.pk), "piece": piece,
                                                       "document": str(doc.pk)}, format="json")
        r = self.as_(self.sg).get(f"{BASE}dossiers-gr/{d.pk}/")
        self.assertTrue(r.data["controle"]["a_jour"], r.data["controle"])
        self.assertEqual(r.data["mandat_reference"], "MAND-2026")


class LiageEtArchivageAutoTests(EcartsM12Base):
    def test_m9_m12_liables_et_liage_automatique(self):
        doc = _document("Convention de bail")
        with self.captureOnCommitCallbacks(execute=True):
            conv = Convention.objects.create(type="bail", titre="Bail siège", date_debut=TODAY,
                                             date_fin=TODAY + timedelta(days=300), document=doc)
        lien = LienDocument.objects.get(document=doc)
        self.assertEqual((lien.objet_type, lien.module), ("juridique.convention", "M12"))
        self.assertEqual(lien.objet_id, str(conv.pk))
        r = self.as_(self.sg).get(f"{BASE}recherche/?q=Bail&module=M12")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data["documents"]), 1)
        from rh_paie.models import Employe

        emp = Employe.objects.create(code="EMP-T1", civilite="masculin", nom="Test")
        autre = _document("Contrat de travail")
        r = self.as_(self.admin).post(f"{BASE}liens/", {"document": str(autre.pk), "objet_type": "rh_paie.employe",
                                                         "objet_id": str(emp.pk)}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["module"], "M9")

    def test_archivage_automatique_a_la_transition(self):
        self.set_param("archivage_auto", {"juridique.convention": {"statuts": ["signe"], "type_document": "contrats"}})
        conv = Convention.objects.create(type="prestation", titre="Prestation", date_debut=TODAY,
                                         date_fin=TODAY + timedelta(days=200))
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.as_(self.sg).post(f"{BASE}conventions/{conv.pk}/signer/").status_code, 200)
        lien = LienDocument.objects.get(objet_type="juridique.convention", objet_id=str(conv.pk))
        self.assertEqual(lien.document.status, Document.Status.ARCHIVED)
        self.assertEqual(len(lien.document.sha256), 64)
        # Titre GED lisible : libellé du statut, jamais le code brut « (signe) ».
        self.assertIn("archivage (Signé (en cours de validité))", lien.document.title)
        self.assertNotIn("(signe)", lien.document.title)
        # Idempotent : un nouvel enregistrement dans le même statut ne réarchive pas.
        with self.captureOnCommitCallbacks(execute=True):
            conv.save()
        self.assertEqual(LienDocument.objects.filter(objet_id=str(conv.pk)).count(), 1)


class ArchivageLegalTests(EcartsM12Base):
    def test_retention_editable_et_purge_validee_dg(self):
        t = DocumentType.objects.create(code="test_ret", label="Test rétention", retention_years=5)
        url = f"/api/documents/types/{t.pk}/"
        self.assertEqual(self.as_(self.sg).post(f"{url}definir-retention/", {"retention_years": 1}, format="json").status_code, 403)
        r = self.as_(self.dg).post(f"{url}definir-retention/", {"retention_years": 1}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["retention_provisoire"])
        self.assertEqual(self.as_(self.dg).post(f"{url}definir-retention/", {"retention_years": "x"}, format="json").status_code, 400)
        self.assertFalse(self.as_(self.dg).post(f"{url}confirmer-retention/").data["retention_provisoire"])

        vieux = _document("Vieux relevé", statut=Document.Status.ARCHIVED, type_=t,
                          document_date=TODAY - timedelta(days=800))
        recent = _document("Relevé récent", statut=Document.Status.ARCHIVED, type_=t, document_date=TODAY)
        # WORM : un document archivé ne se supprime pas directement.
        self.assertEqual(self.as_(self.admin).delete(f"/api/documents/documents/{vieux.pk}/").status_code, 400)
        cands = self.as_(self.sg).get("/api/documents/purges/candidats/").data
        self.assertEqual([c["id"] for c in cands], [str(vieux.pk)])
        self.assertEqual(self.as_(self.sg).post("/api/documents/purges/", {"document": str(recent.pk)},
                                                format="json").status_code, 400)
        r = self.as_(self.sg).post("/api/documents/purges/", {"document": str(vieux.pk), "motif": "Fin de rétention"},
                                   format="json")
        self.assertEqual(r.status_code, 201, r.data)
        pid = r.data["id"]
        self.assertEqual(self.as_(self.finance).post(f"/api/documents/purges/{pid}/valider/").status_code, 403)
        r = self.as_(self.dg).post(f"/api/documents/purges/{pid}/valider/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertFalse(Document.objects.filter(pk=vieux.pk).exists())
        purge = DemandePurge.objects.get(pk=pid)
        self.assertEqual((purge.statut, purge.document_sha256), ("executee", vieux.sha256))
        self.assertEqual(self.as_(self.dg).post(f"/api/documents/purges/{pid}/valider/").status_code, 400)
