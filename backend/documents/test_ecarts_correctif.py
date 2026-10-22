"""Lot correctif — signature électronique sans messagerie (second facteur TOTP) et purge GED revérifiée.

1. Sans serveur SMTP réel (`EMAIL_ENABLED=False`), le signataire signe avec le code courant de son application
   d'authentification (TOTP, même secret que la MFA) : mêmes essais max, même scellé chaîné, méthode dans la preuve.
   Sans MFA ni messagerie : message clair et enrôlement depuis l'écran Signatures. Avec messagerie : code e-mail
   inchangé.
2. Purge : à la validation DG, l'échéance est recalculée avec la durée de rétention EN VIGUEUR (ex. contrats 5 → 10
   ans) ; un document redevenu non échu n'est pas purgé (demande rejetée, trace mise à jour).
"""

import hashlib
import json
import re
from datetime import date, timedelta

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from users import mfa
from users.models import User

from . import signatures
from .models import DemandePurge, Document, DocumentType, SignatureRequest, Signer, Version

PWD = "Str0ng-Pass-2026"
CONTENT = b"%PDF-1.4 contrat GR ETSL"


def _user(email, role, totp=False):
    u = User.objects.create_user(email=email, password=PWD, role=role, first_name=email.split("@")[0])
    if totp:
        u.mfa_secret = mfa.generer_secret()
        u.mfa_active = True
        u.save()
    return u


def _faux(code):
    return f"{(int(code) + 500000) % 10**6:06d}"


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", EMAIL_ENABLED=False)
class SignatureTotpTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.ga", password=PWD, role=User.Role.ADMIN, is_staff=True, first_name="Admin"
        )
        self.s1 = _user("sg@etls.ga", User.Role.SECRETAIRE_GENERAL, totp=True)
        self.s2 = _user("dga@etls.ga", User.Role.DGA, totp=True)
        self.sans_mfa = _user("log@etls.ga", User.Role.LOGISTIQUE)
        self.doc = Document.objects.create(title="Contrat GR", status=Document.Status.DRAFT)
        self.version = Version.objects.create(
            document=self.doc, number=1, file=SimpleUploadedFile("c.pdf", CONTENT),
            sha256=hashlib.sha256(CONTENT).hexdigest(), size=len(CONTENT), original_filename="c.pdf",
            created_by=self.admin,
        )

    def as_(self, u):
        self.client.force_authenticate(u)
        return self.client

    def demande(self, signers):
        r = self.as_(self.admin).post("/api/documents/signatures/", {
            "version": str(self.version.pk), "title": "Signature", "signers": [str(s.pk) for s in signers],
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.data["id"]

    def signer(self, who, rid, code, methode="totp", password=PWD):
        return self.as_(who).post(f"/api/documents/signatures/{rid}/sign/",
                                  {"otp": code, "password": password, "methode": methode}, format="json")

    def test_mode_sans_messagerie(self):
        m = self.as_(self.s1).get("/api/documents/signatures/mode/").data
        self.assertEqual((m["methodes"], m["methode_defaut"], m["enrolement_requis"]), (["totp"], "totp", False))
        m = self.as_(self.sans_mfa).get("/api/documents/signatures/mode/").data
        self.assertEqual((m["methodes"], m["enrolement_requis"]), ([], True))
        self.assertIn("activez la double authentification", m["message"])

    def test_signature_complete_en_totp_sans_email(self):
        rid = self.demande([self.s1, self.s2])
        # Pas de messagerie : aucun envoi de code, renvoi vers l'application d'authentification.
        r = self.as_(self.s1).post(f"/api/documents/signatures/{rid}/otp/")
        self.assertEqual(r.status_code, 400)
        self.assertIn("application d'authentification", r.data["detail"])
        code1 = mfa.totp(self.s1.mfa_secret)
        self.assertEqual(self.signer(self.s1, rid, code1).status_code, 200)
        # Code TOTP non rejouable (même règle que la MFA de connexion).
        self.s1.refresh_from_db()
        self.assertIsNotNone(self.s1.mfa_dernier_pas)
        r = self.signer(self.s2, rid, mfa.totp(self.s2.mfa_secret))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(len(mail.outbox), 0)
        req = SignatureRequest.objects.get(pk=rid)
        self.assertEqual(req.status, SignatureRequest.Status.COMPLETED)
        s = req.signers.get(user=self.s1)
        self.assertEqual(s.methode, "totp")
        self.assertEqual(json.loads(signatures._evidence(s))["method"], "totp")
        cert = self.as_(self.admin).get(f"/api/documents/signatures/{rid}/certificate/").data
        self.assertTrue(cert["valid"])
        self.assertEqual([x["methode"] for x in cert["signatures"]], ["totp", "totp"])
        self.assertIn("TOTP", cert["method"])
        self.assertTrue(signatures.version_signee(self.version))

    def test_code_faux_refuse_et_compte(self):
        rid = self.demande([self.s1])
        r = self.signer(self.s1, rid, _faux(mfa.totp(self.s1.mfa_secret)))
        self.assertEqual(r.status_code, 400)
        self.assertIn("1/5", r.data["detail"])
        r = self.signer(self.s1, rid, mfa.totp(self.s1.mfa_secret), password="mauvais")
        self.assertIn("2/5", r.data["detail"])
        Signer.objects.filter(request_id=rid).update(otp_attempts=signatures.MAX_ATTEMPTS)
        r = self.signer(self.s1, rid, mfa.totp(self.s1.mfa_secret))
        self.assertIn("verrouillée", r.data["detail"])
        self.assertEqual(SignatureRequest.objects.get(pk=rid).status, SignatureRequest.Status.PENDING)

    def test_refus_sans_mfa_et_enrolement(self):
        rid = self.demande([self.sans_mfa])
        r = self.signer(self.sans_mfa, rid, "123456")
        self.assertEqual(r.status_code, 400)
        self.assertIn("activez la double authentification", r.data["detail"])
        r = self.as_(self.sans_mfa).post(f"/api/documents/signatures/{rid}/otp/")
        self.assertIn("activez la double authentification", r.data["detail"])
        # Enrôlement depuis l'écran Signatures, puis signature en TOTP.
        secret = self.as_(self.sans_mfa).post("/api/documents/signatures/enrolement-totp/").data["secret"]
        r = self.as_(self.sans_mfa).post("/api/documents/signatures/activation-totp/", {"code": _faux(mfa.totp(secret))})
        self.assertEqual(r.status_code, 400)
        r = self.as_(self.sans_mfa).post("/api/documents/signatures/activation-totp/", {"code": mfa.totp(secret)})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["methodes"], ["totp"])
        self.sans_mfa.refresh_from_db()
        self.assertTrue(self.sans_mfa.mfa_active)
        # Le code d'activation est consommé : il faut le pas suivant (on simule en reculant le dernier pas).
        User.objects.filter(pk=self.sans_mfa.pk).update(mfa_dernier_pas=None)
        self.assertEqual(self.signer(self.sans_mfa, rid, mfa.totp(secret)).status_code, 200)
        self.assertEqual(self.as_(self.sans_mfa).post("/api/documents/signatures/enrolement-totp/").status_code, 400)

    @override_settings(EMAIL_ENABLED=True)
    def test_email_inchange_quand_messagerie_active(self):
        rid = self.demande([self.sans_mfa])
        m = self.as_(self.sans_mfa).get("/api/documents/signatures/mode/").data
        self.assertEqual((m["methodes"], m["methode_defaut"]), (["email"], "email"))
        self.assertEqual(self.as_(self.sans_mfa).post(f"/api/documents/signatures/{rid}/otp/").status_code, 200)
        code = re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)
        # Sans `methode` (ancien client) : le code e-mail demandé fait foi.
        r = self.as_(self.sans_mfa).post(f"/api/documents/signatures/{rid}/sign/", {"otp": code, "password": PWD},
                                         format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(Signer.objects.get(request_id=rid).methode, "email")
        self.assertTrue(signatures.certificate(SignatureRequest.objects.get(pk=rid))["valid"])

    @override_settings(EMAIL_ENABLED=True)
    def test_choix_totp_possible_avec_messagerie(self):
        rid = self.demande([self.s1])
        m = self.as_(self.s1).get("/api/documents/signatures/mode/").data
        self.assertEqual(m["methodes"], ["email", "totp"])
        self.assertEqual(self.signer(self.s1, rid, mfa.totp(self.s1.mfa_secret)).status_code, 200)

    def test_sceau_anterieur_sans_methode_reste_valide(self):
        rid = self.demande([self.s1])
        self.assertEqual(self.signer(self.s1, rid, mfa.totp(self.s1.mfa_secret)).status_code, 200)
        s = Signer.objects.get(request_id=rid)
        # Signature d'avant le lot (méthode vide) : la preuve n'inclut pas « method », le sceau rejoue à l'identique.
        s.methode = ""
        s.seal = signatures.compute_seal(s, "")
        s.save()
        self.assertNotIn("method", json.loads(signatures._evidence(s)))
        self.assertTrue(signatures.certificate(SignatureRequest.objects.get(pk=rid))["valid"])


class PurgeDureeEnVigueurTests(APITestCase):
    def setUp(self):
        self.dg = User.objects.create_user(email="dg@etls.ga", password=PWD, role=User.Role.PDG)
        self.sg = User.objects.create_user(email="sg@etls.ga", password=PWD, role=User.Role.SECRETAIRE_GENERAL)
        self.type = DocumentType.objects.create(code="contrats_t", label="Contrats test", retention_years=5)
        self.doc = Document.objects.create(title="Vieux contrat", status=Document.Status.ARCHIVED, type=self.type,
                                           document_date=date.today() - timedelta(days=365 * 6))

    def proposer(self):
        self.client.force_authenticate(self.sg)
        r = self.client.post("/api/documents/purges/", {"document": str(self.doc.pk), "motif": "Fin"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.client.force_authenticate(self.dg)
        return r.data["id"]

    def test_duree_allongee_refuse_la_purge(self):
        pid = self.proposer()
        self.type.retention_years = 10  # PR #63 : contrats 5 → 10 ans, après la proposition
        self.type.save()
        r = self.client.post(f"/api/documents/purges/{pid}/valider/")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("10 ans", r.data["detail"])
        self.assertTrue(Document.objects.filter(pk=self.doc.pk).exists())
        d = DemandePurge.objects.get(pk=pid)
        self.assertEqual(d.statut, DemandePurge.Statut.REJETEE)
        self.assertEqual(d.fin_retention, self.doc.document_date + timedelta(days=3650))
        self.assertEqual(d.valide_par, self.dg)

    def test_duree_inchangee_purge_executee(self):
        pid = self.proposer()
        r = self.client.post(f"/api/documents/purges/{pid}/valider/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(Document.objects.filter(pk=self.doc.pk).exists())

    def test_allongee_mais_toujours_echue_trace_alignee(self):
        self.doc.document_date = date.today() - timedelta(days=365 * 12)
        self.doc.save()
        pid = self.proposer()
        self.type.retention_years = 10
        self.type.save()
        self.assertEqual(self.client.post(f"/api/documents/purges/{pid}/valider/").status_code, 200)
        d = DemandePurge.objects.get(pk=pid)
        self.assertEqual((d.statut, d.fin_retention), (DemandePurge.Statut.EXECUTEE,
                                                       self.doc.document_date + timedelta(days=3650)))
