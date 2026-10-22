"""Écarts transverses (CDC général) — registre central des paramètres ETSL, gestion des comptes, chiffrement MFA.

- EX-G-01 : l'administrateur gère les comptes (rôle, activation) et consulte la matrice rôle → modules ;
- « Paramètres ETSL » : un seul endpoint recense TOUS les paramètres `Parametre*` des modules (+ rétentions GED),
  avec, pour chacun, l'endpoint EXISTANT de l'application pour le modifier / le confirmer ;
- §8.2 chiffrement au repos : secret TOTP chiffré en base ;
- §8.2 continuité (B) : fenêtre de maintenance, responsable, RPO / RTO en paramètres provisoires.
"""

import re

from django.core import mail
from django.db import connection
from django.test import override_settings
from django.urls import resolve
from rest_framework.test import APITestCase

from config.parametres_etsl import REGISTRE, classes_parametres

from . import mfa
from .models import JournalAcces, ParametreTransverse, User

PWD = "x-Ecarts-Tr-2026"


class _Base(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(email="admin.tr@etls.ga", password=PWD, role=User.Role.ADMIN)
        cls.pdg = User.objects.create_user(email="pdg.tr@etls.ga", password=PWD, role=User.Role.PDG)
        cls.service = User.objects.create_user(email="service.tr@etls.ga", password=PWD, role=User.Role.CHEF_SERVICE)
        cls.hse = User.objects.create_user(email="hse.tr@etls.ga", password=PWD, role=User.Role.HSE)
        from documents.models import DocumentType

        DocumentType.objects.create(code="contrat_tr", label="Contrat (test)", retention_years=10)


class RegistreParametresTests(_Base):
    def test_registre_couvre_toutes_les_classes_parametre(self):
        """Une nouvelle classe `Parametre*` non enregistrée dans `config/parametres_etsl.py` fait échouer ce test."""
        enregistres = {e.modele for e in REGISTRE}
        manquants = [c for c in classes_parametres() if c not in enregistres]
        self.assertEqual(manquants, [], f"Paramètres non recensés dans l'écran « Paramètres ETSL » : {manquants}")
        self.assertGreaterEqual(len(classes_parametres()), 13)

    def test_admin_liste_tous_les_modules_avec_endpoints_existants(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/parametres-etsl/")
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        modules = {x["module"] for x in data["results"]}
        for attendu in ("users", "documents", "commercial", "achats", "operations", "logistique", "stocks", "qualite",
                        "hse", "maintenance", "comptabilite", "controle_gestion", "juridique"):
            self.assertIn(attendu, modules)
        self.assertGreater(data["provisoires"], 0)
        for ligne in data["results"]:
            resolve(ligne["edition"]["path"])  # l'endpoint d'édition de l'application existe
            resolve(ligne["confirmation"])
            self.assertIn(ligne["edition"]["method"], ("PATCH", "POST"))
        r = self.client.get("/api/parametres-etsl/?module=hse&statut=provisoire")
        self.assertTrue(r.json()["results"])
        self.assertEqual({x["module"] for x in r.json()["results"]}, {"hse"})

    def test_droits_de_lecture_de_chaque_application(self):
        self.client.force_authenticate(self.service)
        r = self.client.get("/api/parametres-etsl/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse({x["module"] for x in r.json()["results"]} & {"commercial", "comptabilite", "rh_paie", "hse"})
        self.client.force_authenticate(self.hse)
        modules = {x["module"] for x in self.client.get("/api/parametres-etsl/").json()["results"]}
        self.assertIn("hse", modules)
        self.assertNotIn("rh_paie", modules)

    def test_modifier_puis_confirmer_par_l_endpoint_de_l_application(self):
        self.client.force_authenticate(self.admin)
        lignes = self.client.get("/api/parametres-etsl/?module=hse").json()["results"]
        ligne = lignes[0]
        r = self.client.patch(ligne["edition"]["path"], {ligne["edition"]["champ"]: "45"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        r = self.client.post(ligne["confirmation"])
        self.assertEqual(r.status_code, 200, r.content)
        apres = [x for x in self.client.get("/api/parametres-etsl/?module=hse").json()["results"] if x["id"] == ligne["id"]][0]
        self.assertFalse(apres["provisoire"])
        self.assertEqual(apres["confirme_par"], self.admin.email)
        # Le compteur du tableau de bord diminue d'autant.
        resume = self.client.get("/api/parametres-etsl/resume/").json()
        self.assertEqual(resume["provisoires"], self.client.get("/api/parametres-etsl/?statut=provisoire").json()["count"])

    def test_export_xlsx_et_pdf(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/parametres-etsl/?export=xlsx")
        self.assertEqual(r.status_code, 200)
        self.assertIn("spreadsheetml", r["Content-Type"])
        self.assertIn("attachment", r["Content-Disposition"])
        r = self.client.get("/api/parametres-etsl/?export=pdf&statut=provisoire")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b"%PDF"))

    def test_anonyme_refuse(self):
        self.assertIn(self.client.get("/api/parametres-etsl/").status_code, (401, 403))


class ParametresTransversesTests(_Base):
    def test_continuite_et_retention_provisoires_modifiables_par_la_direction(self):
        self.client.force_authenticate(self.hse)
        r = self.client.get("/api/users/parametres/")
        self.assertEqual(r.status_code, 200)
        codes = {p["code"]: p for p in r.json()["results"]}
        for code in ("MAINTENANCE_FENETRE", "MAINTENANCE_RESPONSABLE", "RPO_HEURES", "RTO_HEURES", "AUDIT_RETENTION_ANS",
                     "NOTIF_EMAIL_ACTIF", "PERF_SEUIL_MS", "RESTAURATION_PERIODICITE_JOURS"):
            self.assertTrue(codes[code]["est_provisoire"])
        pid = codes["MAINTENANCE_FENETRE"]["id"]
        self.assertEqual(self.client.patch(f"/api/users/parametres/{pid}/", {"texte": "Samedi 22h"}, format="json").status_code, 403)
        self.client.force_authenticate(self.pdg)
        r = self.client.patch(f"/api/users/parametres/{pid}/", {"texte": "Samedi 22:00-02:00"}, format="json")
        self.assertEqual(r.json()["texte"], "Samedi 22:00-02:00")
        rid = codes["RPO_HEURES"]["id"]
        self.assertEqual(self.client.patch(f"/api/users/parametres/{rid}/", {"valeur": "abc"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(f"/api/users/parametres/{rid}/", {"valeur": "-1"}, format="json").status_code, 400)
        r = self.client.post(f"/api/users/parametres/{pid}/confirmer/")
        self.assertEqual(r.json()["statut_valeur"], "confirme")
        # Modifier une valeur confirmée la repasse en provisoire.
        r = self.client.patch(f"/api/users/parametres/{pid}/", {"texte": "Dimanche 01:00-05:00"}, format="json")
        self.assertTrue(r.json()["est_provisoire"])
        self.assertEqual(self.client.post("/api/users/parametres/", {"code": "X"}, format="json").status_code, 405)


class GestionComptesTests(_Base):
    def test_admin_modifie_role_et_activation(self):
        self.client.force_authenticate(self.admin)
        r = self.client.patch(f"/api/users/users/{self.hse.pk}/", {"role": "qaqc", "first_name": "Awa"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.hse.refresh_from_db()
        self.assertEqual((self.hse.role, self.hse.first_name), ("qaqc", "Awa"))
        self.assertIn("qualite", r.json()["modules"])
        r = self.client.patch(f"/api/users/users/{self.hse.pk}/", {"is_active": False}, format="json")
        self.assertFalse(r.json()["is_active"])
        # Ni auto-désactivation, ni changement de son propre rôle.
        self.assertEqual(self.client.patch(f"/api/users/users/{self.admin.pk}/", {"is_active": False}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(f"/api/users/users/{self.admin.pk}/", {"role": "hse"}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/users/users/{self.admin.pk}/").status_code, 400)
        r = self.client.get("/api/users/users/?role=qaqc&actif=0")
        self.assertEqual([u["email"] for u in r.json()["results"]], [self.hse.email])

    def test_matrice_roles_modules_et_export(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/users/users/matrice/")
        self.assertEqual(r.status_code, 200)
        roles = {x["role"]: x for x in r.json()["roles"]}
        self.assertEqual(len(roles["pdg"]["modules"]), 12)
        self.assertEqual(roles["chef_service"]["modules"], [])
        r = self.client.get("/api/users/users/?export=xlsx")
        self.assertIn("spreadsheetml", r["Content-Type"])
        self.client.force_authenticate(self.pdg)
        self.assertEqual(self.client.get("/api/users/users/matrice/").status_code, 403)


class ChiffrementMfaTests(_Base):
    def test_secret_totp_chiffre_en_base(self):
        secret = mfa.generer_secret()
        self.pdg.mfa_secret = secret
        self.pdg.save(update_fields=["mfa_secret"])
        with connection.cursor() as c:
            c.execute("SELECT mfa_secret FROM users_user WHERE id = %s", [self.pdg.pk])
            brut = c.fetchone()[0]
        self.assertTrue(brut.startswith("enc1:"))
        self.assertNotIn(secret, brut)
        self.pdg.refresh_from_db()
        self.assertEqual(self.pdg.mfa_secret, secret)
        self.assertIsNotNone(mfa.verifier(self.pdg.mfa_secret, mfa.totp(secret)))
        self.assertTrue(ParametreTransverse._meta.verbose_name)


class MotDePasseTests(_Base):
    """Mot de passe en libre-service : changement, oubli par lien à usage unique, réinitialisation par l'admin."""

    NOUVEAU = "Nouveau#Passe-2026"

    def _login(self, email, password):
        return self.client.post("/api/users/token/", {"email": email, "password": password}, format="json")

    def test_changer_son_mot_de_passe_revoque_les_autres_sessions(self):
        jetons = self._login(self.hse.email, PWD).json()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {jetons['access']}")
        url = "/api/users/me/mot-de-passe/"
        r = self.client.post(url, {"ancien": "faux", "nouveau": self.NOUVEAU, "confirmation": self.NOUVEAU}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("ancien", r.json())
        r = self.client.post(url, {"ancien": PWD, "nouveau": self.NOUVEAU, "confirmation": "autre"}, format="json")
        self.assertIn("confirmation", r.json())
        r = self.client.post(url, {"ancien": PWD, "nouveau": "123", "confirmation": "123"}, format="json")
        self.assertIn("nouveau", r.json())  # validateurs Django
        r = self.client.post(url, {"ancien": PWD, "nouveau": self.NOUVEAU, "confirmation": self.NOUVEAU}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        nouveaux = r.json()
        # L'ancien jeton (autre session) est révoqué ; les nouveaux jetons fonctionnent.
        self.assertIn(self.client.get("/api/users/me/").status_code, (401, 403))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {nouveaux['access']}")
        self.assertEqual(self.client.get("/api/users/me/").status_code, 200)
        self.client.credentials()
        self.assertEqual(self._login(self.hse.email, self.NOUVEAU).status_code, 200)
        self.assertTrue(JournalAcces.objects.filter(user=self.hse, evenement="mdp_change").exists())

    def test_sans_messagerie_renvoi_vers_l_administrateur(self):
        with self.settings(EMAIL_ENABLED=False):
            self.assertFalse(self.client.get("/api/users/mot-de-passe/config/").json()["email_actif"])
            r = self.client.post("/api/users/mot-de-passe/oubli/", {"email": self.hse.email}, format="json")
            self.assertEqual(r.status_code, 200)
            self.assertFalse(r.json()["email_actif"])
            self.assertIn("administrateur", r.json()["detail"])
            self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_ENABLED=True)
    def test_mot_de_passe_oublie_lien_unique_et_reponse_identique(self):
        self.assertTrue(self.client.get("/api/users/mot-de-passe/config/").json()["email_actif"])
        r_inconnu = self.client.post("/api/users/mot-de-passe/oubli/", {"email": "inconnu@etls.ga"}, format="json")
        self.assertEqual(len(mail.outbox), 0)
        r = self.client.post("/api/users/mot-de-passe/oubli/", {"email": self.hse.email.upper()}, format="json")
        self.assertEqual((r.status_code, r.json()), (r_inconnu.status_code, r_inconnu.json()))
        self.assertEqual(len(mail.outbox), 1)
        jeton = re.search(r"jeton=(\S+)", mail.outbox[0].body).group(1)
        self.assertIn("http://localhost:5173/reinitialiser-mot-de-passe", mail.outbox[0].body)
        url = "/api/users/mot-de-passe/reinitialiser/"
        self.assertEqual(self.client.post(url, {"jeton": "x", "nouveau": self.NOUVEAU, "confirmation": self.NOUVEAU}, format="json").status_code, 400)
        r = self.client.post(url, {"jeton": jeton, "nouveau": self.NOUVEAU, "confirmation": self.NOUVEAU}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self._login(self.hse.email, self.NOUVEAU).status_code, 200)
        # Usage unique : le même lien ne sert plus.
        r = self.client.post(url, {"jeton": jeton, "nouveau": "Encore#Autre-2026", "confirmation": "Encore#Autre-2026"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_lien_expire_selon_parametre(self):
        from .motdepasse import emettre_jeton, lire_jeton
        from .parametres import get_param_transverse

        jeton = emettre_jeton(self.hse)
        self.assertEqual(lire_jeton(jeton), self.hse)
        p = get_param_transverse("MDP_LIEN_VALIDITE_MIN")
        p.valeur = 0
        p.save()
        import time

        time.sleep(1.1)
        self.assertIsNone(lire_jeton(jeton))

    def test_reinitialisation_admin_impose_le_changement(self):
        self.client.force_authenticate(self.hse)
        self.assertEqual(
            self.client.post(f"/api/users/users/{self.pdg.pk}/reinitialiser-mot-de-passe/", {"mot_de_passe": "Provisoire#2026x"}, format="json").status_code,
            403,
        )
        self.client.force_authenticate(self.admin)
        r = self.client.post(f"/api/users/users/{self.hse.pk}/reinitialiser-mot-de-passe/", {"mot_de_passe": "123"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post(f"/api/users/users/{self.hse.pk}/reinitialiser-mot-de-passe/", {"mot_de_passe": "Provisoire#2026x"}, format="json")
        self.assertTrue(r.json()["doit_changer_mdp"])
        self.client.force_authenticate(None)
        jetons = self._login(self.hse.email, "Provisoire#2026x").json()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {jetons['access']}")
        me = self.client.get("/api/users/me/")
        self.assertTrue(me.json()["doit_changer_mdp"])
        self.assertEqual(self.client.get("/api/hse/incidents/").status_code, 403)  # bloqué tant que non changé
        r = self.client.post("/api/users/me/mot-de-passe/", {"ancien": "Provisoire#2026x", "nouveau": self.NOUVEAU, "confirmation": self.NOUVEAU}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
        self.assertFalse(self.client.get("/api/users/me/").json()["doit_changer_mdp"])
        self.assertEqual(self.client.get("/api/hse/incidents/").status_code, 200)
