"""Signature électronique AVANCÉE (CL-OM-06 : contrats M1.3 / M12) — identification du signataire + intégrité.

Chaîne de preuve interne : chaque signature enregistre (signataire authentifié par mot de passe ET code à usage
unique reçu par e-mail, horodatage, IP, empreinte SHA-256 du document) et est scellée par un HMAC chaîné au sceau
précédent → toute altération (document ou preuve) est détectable. Intégration d'un prestataire de confiance
qualifié possible sans changer le flux (le sceau interne reste la piste d'audit).
"""

import hashlib
import re
from datetime import timedelta

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from users.models import User

from .models import Document, SignatureRequest, Signer, Version

PWD = "Str0ng-Pass-2026"
CONTENT = b"%PDF-1.4 contrat de maintenance ETSL"


def user(email, role):
    return User.objects.create_user(email=email, password=PWD, role=role, first_name=email.split("@")[0])


@override_settings(
    STORAGES={"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}},
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class SignatureBase(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.ga", password=PWD, role=User.Role.ADMIN, is_staff=True, first_name="Admin"
        )
        self.s1 = user("sg@etls.ga", User.Role.SECRETAIRE_GENERAL)
        self.s2 = user("dga@etls.ga", User.Role.DGA)
        self.outsider = user("autre@etls.ga", User.Role.LOGISTIQUE)
        self.doc = Document.objects.create(title="Contrat maintenance GR", status=Document.Status.DRAFT)
        self.version = Version.objects.create(
            document=self.doc, number=1, file=SimpleUploadedFile("contrat.pdf", CONTENT),
            sha256=hashlib.sha256(CONTENT).hexdigest(), size=len(CONTENT), original_filename="contrat.pdf",
            created_by=self.admin,
        )

    def as_(self, u):
        self.client.force_authenticate(u)
        return self.client

    def create(self, signers=None, **kw):
        body = {"version": str(self.version.pk), "title": "Signature du contrat",
                "signers": [str(s.pk) for s in (signers if signers is not None else [self.s1, self.s2])]}
        body.update(kw)
        return self.as_(self.admin).post("/api/documents/signatures/", body, format="json")

    def otp_for(self, who, req_id):
        mail.outbox.clear()
        r = self.as_(who).post(f"/api/documents/signatures/{req_id}/otp/")
        self.assertEqual(r.status_code, 200, r.content)
        return re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)

    def sign(self, who, req_id, otp, password=PWD):
        return self.as_(who).post(
            f"/api/documents/signatures/{req_id}/sign/", {"otp": otp, "password": password}, format="json",
            HTTP_USER_AGENT="pytest-agent", REMOTE_ADDR="10.1.2.3",
        )


class CreationTests(SignatureBase):
    def test_creation_fige_l_empreinte_de_la_version(self):
        r = self.create()
        self.assertEqual(r.status_code, 201, r.content)
        req = SignatureRequest.objects.get()
        self.assertEqual(req.document_sha256, self.version.sha256)
        self.assertEqual(req.status, SignatureRequest.Status.PENDING)
        self.assertEqual([s.user for s in req.signers.order_by("order")], [self.s1, self.s2])

    def test_reservee_a_qui_peut_ecrire_le_document(self):
        rh = user("rh@etls.ga", User.Role.RH)  # lecture seule sur les documents (hors rôles d'écriture)
        self.as_(rh)
        r = self.client.post(
            "/api/documents/signatures/",
            {"version": str(self.version.pk), "signers": [str(self.s1.pk)]}, format="json",
        )
        self.assertIn(r.status_code, (403, 404))
        self.assertEqual(SignatureRequest.objects.count(), 0)

    def test_signataires_invalides(self):
        self.assertEqual(self.create(signers=[]).status_code, 400)
        self.assertEqual(self.create(signers=[self.s1, self.s1]).status_code, 400)
        self.s2.is_active = False
        self.s2.save()
        self.assertEqual(self.create(signers=[self.s1, self.s2]).status_code, 400)

    def test_version_inconnue(self):
        r = self.create(version="00000000-0000-0000-0000-000000000000")
        self.assertEqual(r.status_code, 400)


class SignatureFlowTests(SignatureBase):
    def setUp(self):
        super().setUp()
        self.req_id = self.create().data["id"]

    def test_otp_envoye_par_mail_et_non_stocke_en_clair(self):
        code = self.otp_for(self.s1, self.req_id)
        s = Signer.objects.get(user=self.s1)
        self.assertNotIn(code, s.otp_hash)
        self.assertEqual(len(code), 6)

    def test_ordre_des_signataires_impose(self):
        r = self.as_(self.s2).post(f"/api/documents/signatures/{self.req_id}/otp/")
        self.assertEqual(r.status_code, 400)
        self.assertIn("tour", str(r.data).lower())

    def test_signature_complete_et_preuve(self):
        code = self.otp_for(self.s1, self.req_id)
        r = self.sign(self.s1, self.req_id, code)
        self.assertEqual(r.status_code, 200, r.content)
        s = Signer.objects.get(user=self.s1)
        self.assertEqual(s.status, Signer.Status.SIGNED)
        self.assertEqual(s.ip_address, "10.1.2.3")
        self.assertEqual(s.user_agent, "pytest-agent")
        self.assertEqual(s.document_sha256, self.version.sha256)
        self.assertEqual(len(s.seal), 64)
        # 2e signataire -> la demande est terminée
        code2 = self.otp_for(self.s2, self.req_id)
        self.assertEqual(self.sign(self.s2, self.req_id, code2).status_code, 200)
        self.assertEqual(SignatureRequest.objects.get().status, SignatureRequest.Status.COMPLETED)

    def test_mauvais_code_ou_mot_de_passe_refuses(self):
        code = self.otp_for(self.s1, self.req_id)
        bad = "000000" if code != "000000" else "111111"
        self.assertEqual(self.sign(self.s1, self.req_id, bad).status_code, 400)
        self.assertEqual(self.sign(self.s1, self.req_id, code, password="mauvais").status_code, 400)
        self.assertEqual(Signer.objects.get(user=self.s1).status, Signer.Status.PENDING)

    def test_blocage_apres_cinq_essais(self):
        code = self.otp_for(self.s1, self.req_id)
        bad = "000000" if code != "000000" else "111111"
        for _ in range(5):
            self.sign(self.s1, self.req_id, bad)
        r = self.sign(self.s1, self.req_id, code)  # même le bon code est refusé : verrouillé
        self.assertEqual(r.status_code, 400)
        self.assertIn("verrouill", str(r.data).lower())

    def test_code_expire(self):
        code = self.otp_for(self.s1, self.req_id)
        Signer.objects.filter(user=self.s1).update(otp_expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.sign(self.s1, self.req_id, code).status_code, 400)

    def test_double_signature_refusee(self):
        code = self.otp_for(self.s1, self.req_id)
        self.sign(self.s1, self.req_id, code)
        self.assertEqual(self.as_(self.s1).post(f"/api/documents/signatures/{self.req_id}/otp/").status_code, 400)

    def test_tiers_ne_peut_ni_demander_un_code_ni_signer(self):
        self.assertIn(self.as_(self.outsider).post(f"/api/documents/signatures/{self.req_id}/otp/").status_code, (403, 404))
        self.assertIn(self.sign(self.outsider, self.req_id, "123456").status_code, (403, 404))

    def test_demande_expiree_non_signable(self):
        SignatureRequest.objects.update(expires_at=timezone.now() - timedelta(days=1))
        r = self.as_(self.s1).post(f"/api/documents/signatures/{self.req_id}/otp/")
        self.assertEqual(r.status_code, 400)
        self.assertIn("expir", str(r.data).lower())

    def test_document_modifie_apres_la_demande_bloque_la_signature(self):
        code = self.otp_for(self.s1, self.req_id)
        Version.objects.filter(pk=self.version.pk).update(sha256="f" * 64)  # version altérée
        r = self.sign(self.s1, self.req_id, code)
        self.assertEqual(r.status_code, 400)
        self.assertIn("intégrité", str(r.data).lower())

    def test_refus_motive_arrete_la_demande(self):
        r = self.as_(self.s1).post(f"/api/documents/signatures/{self.req_id}/refuse/", {"reason": "Clause 4 à revoir"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(SignatureRequest.objects.get().status, SignatureRequest.Status.REFUSED)
        self.assertEqual(self.as_(self.s1).post(f"/api/documents/signatures/{self.req_id}/refuse/", {}, format="json").status_code, 400)

    def test_motif_de_refus_obligatoire(self):
        r = self.as_(self.s1).post(f"/api/documents/signatures/{self.req_id}/refuse/", {}, format="json")
        self.assertEqual(r.status_code, 400)


class CertificatTests(SignatureBase):
    def finish(self):
        rid = self.create().data["id"]
        self.sign(self.s1, rid, self.otp_for(self.s1, rid))
        self.sign(self.s2, rid, self.otp_for(self.s2, rid))
        return rid

    def test_certificat_valide_et_chaine(self):
        rid = self.finish()
        r = self.as_(self.admin).get(f"/api/documents/signatures/{rid}/certificate/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["valid"])
        self.assertTrue(r.data["document_intact"])
        self.assertEqual(len(r.data["signatures"]), 2)
        self.assertEqual(r.data["document_sha256"], self.version.sha256)

    def test_alteration_d_une_preuve_detectee(self):
        rid = self.finish()
        Signer.objects.filter(user=self.s1).update(signed_at=timezone.now() - timedelta(days=30))
        r = self.as_(self.admin).get(f"/api/documents/signatures/{rid}/certificate/")
        self.assertFalse(r.data["valid"])

    def test_alteration_du_fichier_detectee(self):
        rid = self.finish()
        storage, name = self.version.file.storage, self.version.file.name
        storage.delete(name)
        storage.save(name, SimpleUploadedFile("x.pdf", b"contenu falsifie"))
        r = self.as_(self.admin).get(f"/api/documents/signatures/{rid}/certificate/")
        self.assertFalse(r.data["document_intact"])

    def test_visibilite_createur_et_signataires_seulement(self):
        rid = self.finish()
        self.assertEqual(self.as_(self.s1).get(f"/api/documents/signatures/{rid}/").status_code, 200)
        self.assertEqual(self.as_(self.outsider).get(f"/api/documents/signatures/{rid}/").status_code, 404)
        self.assertEqual(self.as_(self.outsider).get("/api/documents/signatures/").data["count"], 0)
        self.assertEqual(self.as_(self.s2).get("/api/documents/signatures/").data["count"], 1)
        self.assertEqual(self.as_(self.s1).get("/api/documents/signatures/?a_signer=1").data["count"], 0)
