"""Clôture M12 Juridique & GED — tests de recette (CDC M12).

Critères :
- documents officiels scellés et signés : un type de document « officiel » (liste paramétrable par ETSL, provisoire
  tant que non confirmée) ne s'archive qu'avec une signature avancée achevée sur la version courante, puis son
  contenu est scellé (ni nouvelle version, ni suppression) ;
- recherche juridique liée M1-M11 : documents GED reliés aux objets métier (affaire, contrat, BC, OT…), recherche
  transverse qui respecte les ACL de la GED ;
- alertes J-90/60/30 et dossier intra-groupe GR : déjà couverts (tests.py, test_validation_dg.py).
"""

import hashlib

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from commercial.models import Affaire
from documents.models import Document, DocumentAccess, DocumentType, SignatureRequest, Version
from maintenance.models import Actif, OrdreTravail
from users.models import User
from workflow.models import Circuit, CircuitStep

from .models import LienDocument

CONTENT = b"%PDF-1.4 convention ETSL"
STORAGE = {"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}


def _user(email, role):
    return User.objects.create_user(email=email, password="x-Audit-2026", role=role)


def _document(titre, type_=None, statut=Document.Status.DRAFT, contenu=CONTENT, **kw):
    doc = Document.objects.create(title=titre, status=statut, type=type_, **kw)
    version = Version.objects.create(
        document=doc, number=1, file=SimpleUploadedFile("doc.pdf", contenu),
        sha256=hashlib.sha256(contenu).hexdigest(), size=len(contenu), original_filename="doc.pdf",
    )
    doc.current_version = version
    doc.sha256 = version.sha256
    doc.save()
    return doc


def _signer(doc, valide=True):
    version = doc.current_version
    return SignatureRequest.objects.create(
        version=version, status=SignatureRequest.Status.COMPLETED if valide else SignatureRequest.Status.PENDING,
        document_sha256=version.sha256, expires_at=timezone.now() + timezone.timedelta(days=7),
    )


@override_settings(STORAGES=STORAGE)
class DocumentsOfficielsTests(APITestCase):
    def setUp(self):
        self.admin = _user("adm@etls.ga", User.Role.ADMIN)
        self.sg = _user("sg@etls.ga", User.Role.SECRETAIRE_GENERAL)
        self.rh = _user("rh@etls.ga", User.Role.RH)
        self.circuit = Circuit.objects.create(code="circ_m12", label="Circuit M12", max_days=5)
        CircuitStep.objects.create(circuit=self.circuit, order=1, name="Visa", actor_role=User.Role.ADMIN, max_days=2)
        self.officiel = DocumentType.objects.create(
            code="convention_off", label="Convention", retention_years=10, circuit=self.circuit, officiel=True)
        self.ordinaire = DocumentType.objects.create(
            code="note_int", label="Note interne", retention_years=5, circuit=self.circuit)
        self.client.force_authenticate(self.admin)

    def archiver(self, doc):
        t = self.client.post("/api/workflow/tasks/submit/", {"document": str(doc.pk)}, format="json")
        self.assertEqual(t.status_code, 201, t.content)
        return self.client.post(f"/api/workflow/tasks/{t.data['id']}/complete/")

    def test_archivage_d_un_document_officiel_exige_la_signature(self):
        doc = _document("Convention GR", self.officiel)
        r = self.archiver(doc)
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("signature", str(r.data).lower())
        doc.refresh_from_db()
        self.assertNotEqual(doc.status, Document.Status.ARCHIVED)

    def test_signature_en_attente_ou_sur_ancienne_version_ne_suffit_pas(self):
        doc = _document("Convention GR", self.officiel)
        _signer(doc, valide=False)
        self.assertEqual(self.archiver(doc).status_code, 400)

    def test_document_officiel_signe_s_archive(self):
        doc = _document("Convention GR", self.officiel)
        _signer(doc)
        r = self.archiver(doc)
        self.assertEqual(r.status_code, 200, r.content)
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.Status.ARCHIVED)

    def test_type_ordinaire_inchange(self):
        doc = _document("Note", self.ordinaire)
        self.assertEqual(self.archiver(doc).status_code, 200)

    def test_document_officiel_signe_est_scelle_meme_avant_archivage(self):
        doc = _document("Convention GR", self.officiel)
        _signer(doc)
        r = self.client.post(
            f"/api/documents/documents/{doc.pk}/new_version/",
            {"file": SimpleUploadedFile("v2.pdf", b"autre contenu")}, format="multipart")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(self.client.delete(f"/api/documents/documents/{doc.pk}/").status_code, 400)

    def test_document_officiel_non_signe_reste_modifiable(self):
        doc = _document("Convention GR", self.officiel)
        r = self.client.post(
            f"/api/documents/documents/{doc.pk}/new_version/",
            {"file": SimpleUploadedFile("v2.pdf", b"autre contenu")}, format="multipart")
        self.assertEqual(r.status_code, 201, r.content)

    def test_liste_des_types_officiels_provisoire_puis_confirmee_par_la_direction(self):
        r = self.client.get("/api/documents/types/")
        rows = r.data["results"] if isinstance(r.data, dict) else r.data
        off = next(x for x in rows if x["code"] == "convention_off")
        self.assertTrue(off["officiel"])
        self.assertTrue(off["officiel_provisoire"])
        r = self.client.post(f"/api/documents/types/{self.officiel.pk}/confirmer-officiel/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(r.data["officiel_provisoire"])

    def test_definir_officiel_repasse_en_provisoire_et_est_reserve(self):
        self.client.post(f"/api/documents/types/{self.officiel.pk}/confirmer-officiel/")
        r = self.client.post(f"/api/documents/types/{self.ordinaire.pk}/definir-officiel/", {"officiel": True}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["officiel"])
        self.assertTrue(r.data["officiel_provisoire"])
        self.client.force_authenticate(self.rh)
        r = self.client.post(f"/api/documents/types/{self.ordinaire.pk}/definir-officiel/", {"officiel": False}, format="json")
        self.assertEqual(r.status_code, 403)
        r = self.client.post(f"/api/documents/types/{self.ordinaire.pk}/confirmer-officiel/")
        self.assertEqual(r.status_code, 403)


@override_settings(STORAGES=STORAGE)
class RechercheJuridiqueLieeTests(APITestCase):
    def setUp(self):
        self.admin = _user("adm@etls.ga", User.Role.ADMIN)
        self.sg = _user("sg@etls.ga", User.Role.SECRETAIRE_GENERAL)
        self.rh = _user("rh@etls.ga", User.Role.RH)
        self.chef = _user("cs@etls.ga", User.Role.CHEF_SERVICE)
        self.affaire = Affaire.objects.create(title="Maintenance plateforme Alpha")
        self.actif = Actif.objects.create(designation="Compresseur", categorie="machine")
        self.ot = OrdreTravail.objects.create(actif=self.actif, description="Révision")
        self.doc = _document("Contrat cadre Alpha", reference="CT-ALPHA-01", counterparty="Alpha Oil")
        self.client.force_authenticate(self.sg)

    def lier(self, doc, objet_type, objet_id, **kw):
        body = {"document": str(doc.pk), "objet_type": objet_type, "objet_id": str(objet_id)}
        body.update(kw)
        return self.client.post("/api/juridique/liens/", body, format="json")

    def test_lien_document_affaire_avec_libelle_fige_et_attestation_serveur(self):
        r = self.lier(self.doc, "commercial.affaire", self.affaire.pk)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIn("Alpha", r.data["objet_label"])
        self.assertEqual(r.data["module"], "M1")
        self.assertEqual(LienDocument.objects.get().created_by, self.sg)

    def test_lien_refuse_type_inconnu_objet_inexistant_ou_doublon(self):
        self.assertEqual(self.lier(self.doc, "auth.user", 1).status_code, 400)
        self.assertEqual(self.lier(self.doc, "commercial.affaire", "00000000-0000-0000-0000-000000000000").status_code, 400)
        self.assertEqual(self.lier(self.doc, "commercial.affaire", self.affaire.pk).status_code, 201)
        self.assertEqual(self.lier(self.doc, "commercial.affaire", self.affaire.pk).status_code, 400)

    def test_recherche_par_texte_du_document_et_par_objet_lie(self):
        self.lier(self.doc, "commercial.affaire", self.affaire.pk)
        r = self.client.get("/api/juridique/recherche/?q=Alpha")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([d["title"] for d in r.data["documents"]], ["Contrat cadre Alpha"])
        self.assertEqual(r.data["documents"][0]["liens"][0]["objet_type"], "commercial.affaire")
        # Recherche par le libellé de l'objet métier lié (le document n'a pas ce mot dans ses métadonnées).
        autre = _document("Annexe technique")
        self.lier(autre, "commercial.affaire", self.affaire.pk)
        titres = {d["title"] for d in self.client.get("/api/juridique/recherche/?q=plateforme").data["documents"]}
        self.assertEqual(titres, {"Contrat cadre Alpha", "Annexe technique"})

    def test_recherche_filtrable_par_module(self):
        self.lier(self.doc, "commercial.affaire", self.affaire.pk)
        ot_doc = _document("Rapport de révision compresseur")
        self.lier(ot_doc, "maintenance.ordretravail", self.ot.pk)
        r = self.client.get("/api/juridique/recherche/?q=Alpha&module=M8")
        self.assertEqual(r.data["documents"], [])
        r = self.client.get(f"/api/juridique/recherche/?q=compresseur&module=M8")
        self.assertEqual([d["title"] for d in r.data["documents"]], ["Rapport de révision compresseur"])

    def test_documents_d_un_objet_metier(self):
        self.lier(self.doc, "commercial.affaire", self.affaire.pk)
        r = self.client.get(f"/api/juridique/liens/?objet_type=commercial.affaire&objet_id={self.affaire.pk}")
        rows = r.data["results"] if isinstance(r.data, dict) else r.data
        self.assertEqual([str(x["document"]) for x in rows], [str(self.doc.pk)])

    def test_recherche_respecte_les_acl_de_la_ged(self):
        secret = _document("Contrat secret Alpha")
        self.lier(secret, "commercial.affaire", self.affaire.pk)
        DocumentAccess.objects.create(document=secret, user=self.sg, permission=DocumentAccess.Permission.DENY)
        titres = [d["title"] for d in self.client.get("/api/juridique/recherche/?q=Alpha").data["documents"]]
        self.assertNotIn("Contrat secret Alpha", titres)
        liens = self.client.get(f"/api/juridique/liens/?objet_type=commercial.affaire&objet_id={self.affaire.pk}")
        rows = liens.data["results"] if isinstance(liens.data, dict) else liens.data
        self.assertNotIn(str(secret.pk), [str(x["document"]) for x in rows])

    def test_creation_d_un_lien_sur_document_non_visible_refusee(self):
        secret = _document("Contrat secret")
        DocumentAccess.objects.create(document=secret, user=self.sg, permission=DocumentAccess.Permission.DENY)
        self.assertEqual(self.lier(secret, "commercial.affaire", self.affaire.pk).status_code, 400)

    def test_requete_trop_courte_et_droits(self):
        self.assertEqual(self.client.get("/api/juridique/recherche/?q=a").status_code, 400)
        self.assertEqual(self.client.get("/api/juridique/recherche/").status_code, 400)
        self.client.force_authenticate(self.chef)
        self.assertEqual(self.client.get("/api/juridique/recherche/?q=Alpha").status_code, 403)
        self.client.force_authenticate(self.rh)
        self.assertEqual(self.lier(self.doc, "commercial.affaire", self.affaire.pk).status_code, 403)

    def test_suppression_d_un_lien(self):
        lien = self.lier(self.doc, "commercial.affaire", self.affaire.pk).data
        self.assertEqual(self.client.delete(f"/api/juridique/liens/{lien['id']}/").status_code, 204)
        self.assertEqual(LienDocument.objects.count(), 0)
