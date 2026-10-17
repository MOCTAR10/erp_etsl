"""Lot 15b (2026-10-17) — journal des accès (EX-G-10) et MFA des rôles sensibles (CDC §8.2).

Journal des accès : connexions réussies, tentatives échouées, étapes MFA et exports de données sont journalisés
(qui / quoi / quand / IP), sans modification ni suppression possible ; consultation et export réservés à l'admin.

MFA : les rôles listés dans `MFA_ROLES` (et tout compte qui l'a activée) doivent fournir un code TOTP (RFC 6238)
après le mot de passe. Le mot de passe seul ne délivre aucun jeton : il ouvre une étape MFA courte (5 min).
Premier passage = enrôlement (clé secrète à saisir dans une application d'authentification).
"""

import time

from django.test import override_settings
from rest_framework.test import APITestCase

from .mfa import totp
from .models import JournalAcces, User

PWD = "x-Audit-2026"


def creer(email, role, **kw):
    return User.objects.create_user(email=email, password=PWD, role=role, **kw)


class JournalAccesTests(APITestCase):
    def setUp(self):
        self.admin = creer("admin@etls.ga", User.Role.ADMIN, is_staff=True)
        self.rh = creer("rh@etls.ga", User.Role.RH)

    def login(self, email, password=PWD):
        return self.client.post("/api/users/token/", {"email": email, "password": password}, format="json")

    def test_connexion_reussie_et_echouee_journalisees(self):
        self.assertEqual(self.login("rh@etls.ga").status_code, 200)
        self.assertEqual(self.login("rh@etls.ga", "mauvais").status_code, 401)
        self.assertEqual(self.login("inconnu@etls.ga").status_code, 401)
        evts = list(JournalAcces.objects.order_by("cree_le").values_list("evenement", "email", "user"))
        self.assertEqual(evts, [
            ("connexion", "rh@etls.ga", self.rh.pk),
            ("echec_connexion", "rh@etls.ga", self.rh.pk),
            ("echec_connexion", "inconnu@etls.ga", None),
        ])
        self.assertTrue(all(j.ip for j in JournalAcces.objects.all()))

    def test_export_journalise(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/reports/retention/", {"export": "csv"})
        self.assertEqual(r.status_code, 200)
        export = JournalAcces.objects.get(evenement="export")
        self.assertEqual((export.user, export.chemin), (self.admin, "/api/reports/retention/"))

    def test_journal_inalterable(self):
        self.login("rh@etls.ga")
        entree = JournalAcces.objects.get()
        entree.email = "falsifie@etls.ga"
        with self.assertRaises(ValueError):
            entree.save()
        with self.assertRaises(ValueError):
            entree.delete()

    def test_consultation_reservee_admin(self):
        self.login("rh@etls.ga")
        self.client.force_authenticate(self.rh)
        self.assertEqual(self.client.get("/api/users/journal-acces/").status_code, 403)
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/users/journal-acces/", {"evenement": "connexion"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(self.client.delete(f"/api/users/journal-acces/{r.data['results'][0]['id']}/").status_code, 405)


@override_settings(MFA_ROLES=["finance", "admin"])
class MfaTests(APITestCase):
    def setUp(self):
        self.finance = creer("daf@etls.ga", User.Role.FINANCE)
        self.hse = creer("hse@etls.ga", User.Role.HSE)
        self.admin = creer("admin@etls.ga", User.Role.ADMIN, is_staff=True)

    def login(self, email):
        return self.client.post("/api/users/token/", {"email": email, "password": PWD}, format="json")

    def enroler(self, email):
        jeton = self.login(email).data["mfa_jeton"]
        secret = self.client.post("/api/users/mfa/enrolement/", {"mfa_jeton": jeton}, format="json").data["secret"]
        return jeton, secret

    def test_role_non_sensible_connexion_directe(self):
        r = self.login("hse@etls.ga")
        self.assertIn("access", r.data)

    def test_role_sensible_sans_jeton_avant_le_code(self):
        r = self.login("daf@etls.ga")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertNotIn("access", r.data)
        self.assertTrue(r.data["mfa_requis"])
        self.assertTrue(r.data["mfa_enrolement"])

    def test_enrolement_puis_connexion_par_code(self):
        jeton, secret = self.enroler("daf@etls.ga")
        r = self.client.post("/api/users/mfa/verification/", {"mfa_jeton": jeton, "code": totp(secret)}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("access", r.data)
        self.finance.refresh_from_db()
        self.assertTrue(self.finance.mfa_active)
        # Connexion suivante : plus d'enrôlement, le code reste exigé.
        r = self.login("daf@etls.ga")
        self.assertFalse(r.data["mfa_enrolement"])
        self.assertEqual(self.client.post("/api/users/mfa/enrolement/", {"mfa_jeton": r.data["mfa_jeton"]}, format="json").status_code, 400)
        evts = list(JournalAcces.objects.filter(user=self.finance).values_list("evenement", flat=True))
        self.assertIn("mfa_succes", evts)
        self.assertIn("connexion", evts)

    def test_code_faux_ou_rejoue_refuse(self):
        jeton, secret = self.enroler("daf@etls.ga")
        self.assertEqual(self.client.post("/api/users/mfa/verification/", {"mfa_jeton": jeton, "code": "000000"}, format="json").status_code, 400)
        self.assertTrue(JournalAcces.objects.filter(evenement="mfa_echec").exists())
        code = totp(secret)
        self.assertEqual(self.client.post("/api/users/mfa/verification/", {"mfa_jeton": jeton, "code": code}, format="json").status_code, 200)
        jeton2 = self.login("daf@etls.ga").data["mfa_jeton"]
        self.assertEqual(self.client.post("/api/users/mfa/verification/", {"mfa_jeton": jeton2, "code": code}, format="json").status_code, 400)

    def test_jeton_mfa_falsifie_refuse(self):
        r = self.client.post("/api/users/mfa/verification/", {"mfa_jeton": "abc", "code": "123456"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_reinitialisation_par_admin(self):
        jeton, secret = self.enroler("daf@etls.ga")
        self.client.post("/api/users/mfa/verification/", {"mfa_jeton": jeton, "code": totp(secret)}, format="json")
        self.client.force_authenticate(self.admin)
        r = self.client.post(f"/api/users/users/{self.finance.pk}/reinitialiser-mfa/")
        self.assertEqual(r.status_code, 200, r.content)
        self.finance.refresh_from_db()
        self.assertFalse(self.finance.mfa_active)
        self.assertEqual(self.finance.mfa_secret, "")
        self.assertTrue(JournalAcces.objects.filter(evenement="mfa_reinitialisation", user=self.finance).exists())

    def test_secret_jamais_expose_par_l_api(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get(f"/api/users/users/{self.finance.pk}/")
        self.assertNotIn("mfa_secret", r.data)
        self.assertIn("mfa_active", r.data)


class TotpTests(APITestCase):
    def test_vecteur_rfc_6238(self):
        # RFC 6238 annexe B, SHA-1, T = 59 s → 94287082 (8 chiffres) ; 6 derniers chiffres = 287082.
        secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # base32("12345678901234567890")
        self.assertEqual(totp(secret, instant=59), "287082")
        self.assertEqual(len(totp(secret, instant=time.time())), 6)
