"""Libre-service salarié (CL-OM-01) et accusé de dépôt horodaté des bulletins (CL-OM-06).

Un salarié lié à son compte consulte SES bulletins diffusés (avec traçabilité de la mise à disposition
et de la première consultation), son solde de congés, et dépose / annule ses demandes de congé.
Il ne voit jamais les données d'un autre salarié.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from users.models import User

from .models import BulletinPaie, DemandesConge, Employe

BASE = "/api/rh-paie/"


def make_employe(nom, user=None):
    return Employe.objects.create(
        civilite=Employe.Sexe.MASCULIN, nom=nom, prenom="Test", categorie=Employe.Categorie.OUVRIER,
        statut=Employe.Statut.ACTIF, user=user,
    )


class MonEspaceBase(APITestCase):
    def setUp(self):
        self.u1 = User.objects.create_user(email="s1@etls.ga", password="x-Audit-2026", role=User.Role.CHEF_ATELIER)
        self.u2 = User.objects.create_user(email="s2@etls.ga", password="x-Audit-2026", role=User.Role.CHEF_ATELIER)
        self.rh = User.objects.create_user(email="rh@etls.ga", password="x-Audit-2026", role=User.Role.RH)
        self.sans_fiche = User.objects.create_user(
            email="x@etls.ga", password="x-Audit-2026", role=User.Role.CHEF_SERVICE
        )
        self.e1 = make_employe("UN", self.u1)
        self.e2 = make_employe("DEUX", self.u2)

    def bulletin(self, employe, periode=date(2026, 3, 1), statut=BulletinPaie.Statut.VALIDE, diffuse=True):
        b = BulletinPaie.objects.create(
            employe=employe, periode=periode, salaire_base=Decimal("400000"), brut=Decimal("400000"),
            net=Decimal("380000"), statut=statut,
        )
        if diffuse:
            b.disponible_le = timezone.now()
            b.save(update_fields=["disponible_le"])
        return b

    def as_user(self, u):
        self.client.force_authenticate(u)


class MesBulletinsTests(MonEspaceBase):
    def test_je_ne_vois_que_mes_bulletins_diffuses(self):
        mien = self.bulletin(self.e1)
        self.bulletin(self.e1, periode=date(2026, 4, 1), diffuse=False)  # validé mais pas encore diffusé
        self.bulletin(self.e1, periode=date(2026, 5, 1), statut=BulletinPaie.Statut.BROUILLON, diffuse=False)
        self.bulletin(self.e2)
        self.as_user(self.u1)
        r = self.client.get(f"{BASE}mon-espace/bulletins/")
        self.assertEqual(r.status_code, 200, r.content)
        ids = [b["id"] for b in r.data["results"]] if "results" in r.data else [b["id"] for b in r.data]
        self.assertEqual(ids, [str(mien.pk)])

    def test_montants_visibles_pour_le_salarie_lui_meme(self):
        self.bulletin(self.e1)
        self.as_user(self.u1)  # chef_atelier : hors cercle des montants de la paie
        r = self.client.get(f"{BASE}mon-espace/bulletins/")
        row = (r.data["results"] if "results" in r.data else r.data)[0]
        self.assertEqual(Decimal(row["net"]), Decimal("380000"))

    def test_bulletin_d_un_autre_introuvable(self):
        autre = self.bulletin(self.e2)
        self.as_user(self.u1)
        self.assertEqual(self.client.get(f"{BASE}mon-espace/bulletins/{autre.pk}/").status_code, 404)

    def test_premiere_consultation_horodatee_une_seule_fois(self):
        b = self.bulletin(self.e1)
        self.assertIsNone(b.consulte_le)
        self.as_user(self.u1)
        self.assertEqual(self.client.get(f"{BASE}mon-espace/bulletins/{b.pk}/").status_code, 200)
        b.refresh_from_db()
        premiere = b.consulte_le
        self.assertIsNotNone(premiere)
        self.client.get(f"{BASE}mon-espace/bulletins/{b.pk}/")
        b.refresh_from_db()
        self.assertEqual(b.consulte_le, premiere)

    def test_compte_sans_fiche_salarie_refuse(self):
        self.as_user(self.sans_fiche)
        self.assertEqual(self.client.get(f"{BASE}mon-espace/bulletins/").status_code, 403)

    def test_anonyme_refuse(self):
        self.assertIn(self.client.get(f"{BASE}mon-espace/bulletins/").status_code, (401, 403))


class DiffusionBulletinTests(MonEspaceBase):
    def test_diffuser_horodate_la_mise_a_disposition(self):
        b = self.bulletin(self.e1, diffuse=False)
        self.as_user(self.rh)
        r = self.client.post(f"{BASE}bulletins/{b.pk}/diffuser/")
        self.assertEqual(r.status_code, 200, r.content)
        b.refresh_from_db()
        self.assertIsNotNone(b.disponible_le)
        self.assertEqual(self.client.post(f"{BASE}bulletins/{b.pk}/diffuser/").status_code, 400)

    def test_bulletin_brouillon_non_diffusable(self):
        b = self.bulletin(self.e1, statut=BulletinPaie.Statut.BROUILLON, diffuse=False)
        self.as_user(self.rh)
        self.assertEqual(self.client.post(f"{BASE}bulletins/{b.pk}/diffuser/").status_code, 400)

    def test_diffusion_reservee_au_cercle_paie(self):
        b = self.bulletin(self.e1, diffuse=False)
        self.as_user(self.u1)
        self.assertEqual(self.client.post(f"{BASE}bulletins/{b.pk}/diffuser/").status_code, 403)


class MesCongesTests(MonEspaceBase):
    def demande(self, debut=None, jours=5, **kw):
        debut = debut or (timezone.localdate() + timedelta(days=30))
        data = {"type": "annuel", "date_debut": str(debut), "date_fin": str(debut + timedelta(days=jours - 1)),
                "nb_jours": jours}
        data.update(kw)
        return self.client.post(f"{BASE}mon-espace/conges/", data, format="json")

    def test_je_depose_une_demande_pour_moi_uniquement(self):
        self.as_user(self.u1)
        r = self.demande(employe=str(self.e2.pk))  # tentative d'usurpation : ignorée
        self.assertEqual(r.status_code, 201, r.content)
        c = DemandesConge.objects.get(pk=r.data["id"])
        self.assertEqual(c.employe, self.e1)
        self.assertEqual(c.statut, DemandesConge.Statut.DEMANDE)

    def test_validations_metier_appliquees(self):
        self.as_user(self.u1)
        self.assertEqual(self.demande(jours=5, nb_jours=99).status_code, 400)

    def test_je_liste_mes_conges_et_mon_solde(self):
        self.as_user(self.u1)
        self.demande()
        r = self.client.get(f"{BASE}mon-espace/conges/")
        self.assertEqual(len(r.data["results"] if "results" in r.data else r.data), 1)
        profil = self.client.get(f"{BASE}mon-espace/profil/")
        self.assertEqual(profil.status_code, 200)
        self.assertEqual(profil.data["solde_conges"], 30.0)

    def test_je_ne_vois_pas_les_conges_des_autres(self):
        self.as_user(self.u2)
        self.demande()
        self.as_user(self.u1)
        r = self.client.get(f"{BASE}mon-espace/conges/")
        self.assertEqual(len(r.data["results"] if "results" in r.data else r.data), 0)

    def test_annuler_ma_demande_seulement_tant_qu_elle_est_en_attente(self):
        self.as_user(self.u1)
        c_id = self.demande().data["id"]
        self.assertEqual(self.client.post(f"{BASE}mon-espace/conges/{c_id}/annuler/").status_code, 200)
        self.assertEqual(self.client.post(f"{BASE}mon-espace/conges/{c_id}/annuler/").status_code, 400)
        DemandesConge.objects.filter(pk=c_id).update(statut="valide")
        self.assertEqual(self.client.post(f"{BASE}mon-espace/conges/{c_id}/annuler/").status_code, 400)

    def test_je_n_annule_pas_la_demande_d_un_autre(self):
        self.as_user(self.u2)
        c_id = self.demande().data["id"]
        self.as_user(self.u1)
        self.assertEqual(self.client.post(f"{BASE}mon-espace/conges/{c_id}/annuler/").status_code, 404)
