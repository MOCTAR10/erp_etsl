"""Lot a1 (socle) : bilinguisme serveur (EX-G-07), PDF/A (EX-G-08), filtre multicritère (EX-G-09), sonde de santé.

Plus les reprises de l'écran Signatures : enrôlement TOTP toujours proposé, QR code, déblocage, message traduit.
"""

import hashlib
from datetime import date, timedelta
from unittest import mock, skipUnless

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone, translation
from rest_framework.test import APITestCase

from config import pdfa
from config.exports import export_response, to_pdf
from users.models import User

from . import signatures
from .models import Document, DocumentType, ParametreGed, Signer, Version
from .parametres import get_parametre

PWD = "x-Ecarts-A1-2026"
PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"


def compte(email, role, **kw):
    return User.objects.create_user(email=email, password=PWD, role=role, **kw)


# ── /api/health/ ──
class SondeSanteTests(TestCase):
    def test_base_ok_200(self):
        r = self.client.get("/api/health/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "ok", "database": "ok", "storage": "non_verifie", "redis": "non_verifie"})

    def test_base_en_echec_503(self):
        with mock.patch("config.views._base", side_effect=RuntimeError("panne")):
            r = self.client.get("/api/health/")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["status"], "error")
        self.assertEqual(r.json()["database"], "error")
        self.assertNotIn("panne", r.content.decode())  # aucun détail exposé

    @override_settings(HEALTH_CHECK_S3=True, HEALTH_CHECK_REDIS=True)
    def test_dependances_optionnelles_verifiees(self):
        with mock.patch("config.views._redis"):
            r = self.client.get("/api/health/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["storage"], r.json()["redis"]), ("ok", "ok"))
        with mock.patch("config.views._stockage", side_effect=OSError("s3")), mock.patch("config.views._redis"):
            r = self.client.get("/api/health/")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["storage"], "error")


# ── EX-G-07 : français / anglais côté serveur ──
class BilinguismeTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = compte("admin.a1@etls.ga", User.Role.ADMIN, is_staff=True)

    def test_catalogue_compile_a_jour(self):
        call_command("compiler_traductions", "--check")

    def test_message_metier_selon_accept_language(self):
        self.client.force_authenticate(self.admin)
        url = "/api/documents/documents/?document_date__gte=31-12-2026"
        fr = self.client.get(url, HTTP_ACCEPT_LANGUAGE="fr")
        en = self.client.get(url, HTTP_ACCEPT_LANGUAGE="en")
        self.assertEqual((fr.status_code, en.status_code), (400, 400))
        self.assertIn("Date invalide", str(fr.json()))
        self.assertIn("Invalid date (expected format YYYY-MM-DD).", str(en.json()))

    def test_message_drf_standard_en_anglais(self):
        r = self.client.get("/api/documents/documents/", HTTP_ACCEPT_LANGUAGE="en")
        self.assertIn(r.status_code, (401, 403))
        self.assertIn("Authentication credentials were not provided", r.json()["detail"])

    def test_message_inconnu_reste_en_francais(self):
        from config.i18n import traduire

        with translation.override("en"):
            self.assertEqual(traduire({"detail": "Message absent du catalogue."}), {"detail": "Message absent du catalogue."})
            self.assertEqual(traduire({"x": ["Choix invalide."]}), {"x": ["Invalid choice."]})

    def test_exports_bilingues(self):
        colonnes = [("statut", "Statut"), ("ok", "Libellé")]
        with translation.override("en"):
            r = export_response([{"statut": "x", "ok": True}], colonnes, "csv", "Paramètres ETSL", "f")
        contenu = r.content.decode("utf-8-sig")
        self.assertTrue(contenu.startswith("Status;Label"), contenu)
        self.assertIn("Yes", contenu)
        with translation.override("fr"):
            r = export_response([{"statut": "x", "ok": True}], colonnes, "csv", "Paramètres ETSL", "f")
        self.assertTrue(r.content.decode("utf-8-sig").startswith("Statut;Libellé"))

    @override_settings(EMAIL_ENABLED=False)
    def test_message_signature_sans_facteur_traduit(self):
        self.client.force_authenticate(self.admin)
        fr = self.client.get("/api/documents/signatures/mode/", HTTP_ACCEPT_LANGUAGE="fr").json()
        en = self.client.get("/api/documents/signatures/mode/", HTTP_ACCEPT_LANGUAGE="en").json()
        self.assertIn("activez la double authentification", fr["message"])
        self.assertIn("enable two-factor authentication", en["message"])


# ── EX-G-08 : PDF/A ──
@override_settings(PDFA_ACTIF=True)
class PdfaTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = compte("admin.pdfa@etls.ga", User.Role.ADMIN, is_staff=True)
        cls.hse = compte("hse.pdfa@etls.ga", User.Role.HSE)
        cls.type = DocumentType.objects.create(code="A1PDF", label="Type a1")

    def _verser(self, contenu, nom="piece.pdf"):
        self.client.force_authenticate(self.admin)
        r = self.client.post(
            "/api/documents/documents/",
            {"title": "Pièce a1", "type": self.type.pk, "file": SimpleUploadedFile(nom, contenu)},
            format="multipart",
        )
        self.assertEqual(r.status_code, 201, r.content)
        return Document.objects.get(pk=r.json()["id"]).current_version

    def test_conversion_pdfa_au_versement(self):
        with mock.patch("config.pdfa.convertir_pdfa", return_value=(b"%PDF-1.7 pdfa", pdfa.CONVERTI)) as conv:
            v = self._verser(PDF)
        conv.assert_called_once_with(PDF, "2b")
        self.assertEqual((v.pdfa_statut, v.pdfa_norme), ("converti", "2b"))
        v.file.open("rb")
        self.assertEqual(v.file.read(), b"%PDF-1.7 pdfa")
        self.assertEqual(v.sha256, hashlib.sha256(b"%PDF-1.7 pdfa").hexdigest())  # empreinte du fichier archivé

    def test_ghostscript_absent_degradation_propre(self):
        with mock.patch("config.pdfa.ghostscript", return_value=None):
            v = self._verser(PDF)
        self.assertEqual((v.pdfa_statut, v.pdfa_norme), ("gs_absent", ""))
        self.assertEqual(v.sha256, hashlib.sha256(PDF).hexdigest())

    def test_non_pdf_et_pdf_signe_inchanges(self):
        self.assertEqual(self._verser(b"col1;col2\n", "a.csv").pdfa_statut, "non_pdf")
        signe = PDF + b"<< /Type /Sig /ByteRange [0 1 2 3] >>"
        self.assertEqual(pdfa.convertir_pdfa(signe), (signe, pdfa.PDF_SIGNE))

    def test_echec_ghostscript_conserve_original(self):
        with mock.patch("config.pdfa.ghostscript", return_value="/bin/false"):
            self.assertEqual(pdfa.convertir_pdfa(PDF), (PDF, pdfa.ECHEC))

    def test_parametre_norme_provisoire_modifiable(self):
        p = get_parametre("PDFA_NORME")
        self.assertEqual((p.texte, p.statut_valeur), ("2b", "provisoire"))
        self.client.force_authenticate(self.hse)
        self.assertEqual(self.client.patch(f"/api/documents/parametres/{p.pk}/", {"texte": "1b"}, format="json").status_code, 403)
        self.client.force_authenticate(self.admin)
        r = self.client.patch(f"/api/documents/parametres/{p.pk}/", {"texte": "4z"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.patch(f"/api/documents/parametres/{p.pk}/", {"texte": "aucune"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self._verser(PDF).pdfa_statut, "desactive")
        r = self.client.post(f"/api/documents/parametres/{p.pk}/confirmer/")
        self.assertFalse(r.json()["provisoire"])
        lignes = self.client.get("/api/parametres-etsl/?module=documents").json()["results"]
        self.assertIn("PDFA_NORME", {x["code"] for x in lignes})

    def test_export_pdf_post_traite(self):
        with mock.patch("config.pdfa.convertir_pdfa", return_value=(b"%PDF-A", pdfa.CONVERTI)):
            r = export_response([{"a": 1}], [("a", "A")], "pdf", "Essai", "essai")
        self.assertEqual(r.content, b"%PDF-A")
        ParametreGed.objects.filter(code="PDFA_EXPORTS").update(valeur=0)
        r = export_response([{"a": 1}], [("a", "A")], "pdf", "Essai", "essai")
        self.assertTrue(r.content.startswith(b"%PDF-"))

    @skipUnless(pdfa.ghostscript(), "Ghostscript non installé sur ce poste")
    def test_conversion_reelle_ghostscript(self):
        contenu, statut = pdfa.convertir_pdfa(to_pdf([{"a": "é"}], [("a", "A")], "Essai"), "2b")
        self.assertEqual(statut, pdfa.CONVERTI)
        self.assertTrue(pdfa.est_pdfa(contenu))


# ── EX-G-09 : filtre multicritère ──
class FiltreMulticritereTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = compte("admin.filtre@etls.ga", User.Role.ADMIN, is_staff=True)
        cls.t1 = DocumentType.objects.create(code="A1F1", label="Contrat")
        cls.t2 = DocumentType.objects.create(code="A1F2", label="Facture")
        D = Document.Status
        cls.d1 = Document.objects.create(title="A", status=D.DRAFT, type=cls.t1, document_date=date(2026, 1, 10), counterparty="Total Gabon")
        cls.d2 = Document.objects.create(title="B", status=D.ARCHIVED, type=cls.t2, document_date=date(2026, 6, 1), counterparty="Perenco")
        cls.d3 = Document.objects.create(title="C", status=D.REJECTED, type=cls.t1, document_date=date(2025, 3, 3))

    def setUp(self):
        self.client.force_authenticate(self.admin)

    def _ids(self, qs):
        r = self.client.get(f"/api/documents/documents/?page_size=100&{qs}")
        self.assertEqual(r.status_code, 200, r.content)
        return {x["id"] for x in r.json()["results"]}

    def test_criteres_combines(self):
        self.assertEqual(self._ids("status=draft,archived"), {str(self.d1.pk), str(self.d2.pk)})
        self.assertEqual(self._ids("document_date__gte=2026-01-01&document_date__lte=2026-03-31"), {str(self.d1.pk)})
        self.assertEqual(self._ids(f"type={self.t1.pk}&status=rejected"), {str(self.d3.pk)})
        self.assertEqual(self._ids("counterparty=gabon"), {str(self.d1.pk)})
        hier = (timezone.localdate() - timedelta(days=1)).isoformat()
        self.assertEqual(len(self._ids(f"created_at__gte={hier}")), 3)

    def test_valeurs_invalides_400(self):
        for qs in ("status=inconnu", "type=abc", "document_date__lte=2026-13-45"):
            r = self.client.get(f"/api/documents/documents/?{qs}")
            self.assertEqual(r.status_code, 400, qs)

    def test_facettes_suivent_les_criteres(self):
        r = self.client.get("/api/documents/documents/facets/?document_date__gte=2026-01-01")
        self.assertEqual(r.json()["total"], 2)

    def test_description_des_criteres_traduite(self):
        fr = self.client.get("/api/documents/documents/filtres/").json()["results"]
        en = self.client.get("/api/documents/documents/filtres/", HTTP_ACCEPT_LANGUAGE="en").json()["results"]
        par_champ = {x["champ"]: x for x in fr}
        self.assertEqual(par_champ["status"]["type"], "choix")
        self.assertEqual(par_champ["document_date"]["parametres"], ["document_date__gte", "document_date__lte"])
        self.assertNotIn("amount", par_champ)  # montant masqué : jamais filtrable (RF-59)
        self.assertEqual({x["champ"]: x["libelle"] for x in en}["document_date"], "Document date")
        self.assertIn({"valeur": "archived", "libelle": "Archived"}, {x["champ"]: x for x in en}["status"]["choix"])


# ── Signatures : enrôlement (QR), déblocage à l'écran ──
@override_settings(EMAIL_ENABLED=True)
class SignaturesEcranTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.emetteur = compte("sg.a1@etls.ga", User.Role.SECRETAIRE_GENERAL)
        cls.signataire = compte("dga.a1@etls.ga", User.Role.DGA)
        cls.autre = compte("log.a1@etls.ga", User.Role.LOGISTIQUE)

    def test_enrolement_totp_avec_qr_meme_si_messagerie_active(self):
        self.client.force_authenticate(self.signataire)
        mode = self.client.get("/api/documents/signatures/mode/").json()
        self.assertEqual((mode["methodes"], mode["mfa_active"]), (["email"], False))
        r = self.client.post("/api/documents/signatures/enrolement-totp/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["qr_svg"].startswith("data:image/svg+xml"))

    def test_deblocage_signale_a_l_emetteur(self):
        doc = Document.objects.create(title="Contrat a1", status=Document.Status.DRAFT)
        version = Version.objects.create(
            document=doc, number=1, file=SimpleUploadedFile("c.pdf", PDF), sha256=hashlib.sha256(PDF).hexdigest(),
            size=len(PDF), original_filename="c.pdf", created_by=self.emetteur,
        )
        req = signatures.create_request(version, [self.signataire], self.emetteur)
        Signer.objects.filter(request=req).update(otp_attempts=signatures.MAX_ATTEMPTS)
        self.client.force_authenticate(self.emetteur)
        data = self.client.get(f"/api/documents/signatures/{req.pk}/").json()
        self.assertTrue(data["peut_debloquer"])
        self.assertTrue(data["signataires"][0]["verrouille"])
        self.client.force_authenticate(self.signataire)
        self.assertFalse(self.client.get(f"/api/documents/signatures/{req.pk}/").json()["peut_debloquer"])
        self.client.force_authenticate(self.emetteur)
        self.assertEqual(self.client.post(f"/api/documents/signatures/{req.pk}/unlock/").status_code, 200)
        self.assertFalse(self.client.get(f"/api/documents/signatures/{req.pk}/").json()["peut_debloquer"])
