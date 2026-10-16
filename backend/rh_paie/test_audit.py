"""Audit métier M9 (2026-10-16) — régressions des écarts trouvés.

P2  : solde de congés = congé ANNUEL de l'année en cours uniquement (maladie, maternité, sans solde… ne l'entament pas).
P3  : pas de chevauchement de congés, `nb_jours` cohérent avec les dates, solde suffisant à l'approbation.
P4  : bulletin : période normalisée au 1er du mois, un bulletin annulé n'empêche pas de le refaire.
P5  : le statut des congés / sanctions / recrutements ne se change que par les actions du workflow.
P6  : création d'un bulletin atomique (pas de bulletin orphelin sans lignes).
"""

from datetime import date, timedelta

from django.utils import timezone
from rest_framework import status

from .models import BulletinPaie, DemandesConge, RubriquePaie, Sanction
from .tests import BASE, BaseRHTest, _auth


def annee():
    return timezone.localdate().year


def conge(employe, jours, type_=DemandesConge.Type.ANNUEL, statut=DemandesConge.Statut.VALIDE_RH,
          debut=None):
    debut = debut or date(annee(), 3, 1)
    return DemandesConge.objects.create(
        employe=employe, type=type_, date_debut=debut,
        date_fin=debut + timedelta(days=jours - 1), nb_jours=jours, statut=statut,
    )


class SoldeCongesTests(BaseRHTest):
    def test_seul_le_conge_annuel_entame_le_solde(self):
        conge(self.employe, 10)
        conge(self.employe, 5, type_=DemandesConge.Type.MALADIE, debut=date(annee(), 5, 1))
        conge(self.employe, 20, type_=DemandesConge.Type.SANS_SOLDE, debut=date(annee(), 6, 1))
        self.assertEqual(self.employe.solde_conges, 20.0)

    def test_solde_limite_a_l_annee_en_cours(self):
        conge(self.employe, 25, debut=date(annee() - 1, 3, 1))
        self.assertEqual(self.employe.solde_conges, 30.0)

    def test_demande_non_encore_approuvee_ne_compte_pas(self):
        conge(self.employe, 10, statut=DemandesConge.Statut.DEMANDE)
        self.assertEqual(self.employe.solde_conges, 30.0)


class ValidationCongesTests(BaseRHTest):
    def post_conge(self, **kw):
        _auth(self.client, "rh@etls.local")
        data = {
            "employe": str(self.employe.pk), "type": "annuel",
            "date_debut": f"{annee()}-07-01", "date_fin": f"{annee()}-07-10", "nb_jours": 10,
        }
        data.update(kw)
        return self.client.post(f"{BASE}conges/", data, format="json")

    def test_nb_jours_incoherent_refuse(self):
        self.assertEqual(self.post_conge(nb_jours=45).status_code, 400)
        self.assertEqual(self.post_conge(nb_jours=0).status_code, 400)

    def test_chevauchement_refuse(self):
        conge(self.employe, 10, debut=date(annee(), 7, 5))  # validé 5-14 juillet
        self.assertEqual(self.post_conge().status_code, 400)

    def test_approbation_refusee_si_solde_insuffisant(self):
        conge(self.employe, 25, debut=date(annee(), 2, 1))  # reste 5 jours
        r = self.post_conge()  # 10 jours demandés
        # la demande peut être saisie, mais pas approuvée
        if r.status_code == 201:
            r2 = self.client.post(f"{BASE}conges/{r.data['id']}/approuver/")
            self.assertEqual(r2.status_code, 400, r2.content)
        else:
            self.assertEqual(r.status_code, 400)

    def test_statut_non_modifiable_par_patch(self):
        c = conge(self.employe, 3, statut=DemandesConge.Statut.DEMANDE)
        _auth(self.client, "rh@etls.local")
        self.client.patch(f"{BASE}conges/{c.pk}/", {"statut": "valide"}, format="json")
        c.refresh_from_db()
        self.assertEqual(c.statut, DemandesConge.Statut.DEMANDE)

    def test_conge_valide_non_modifiable(self):
        c = conge(self.employe, 3)  # VALIDE_RH
        _auth(self.client, "rh@etls.local")
        r = self.client.patch(f"{BASE}conges/{c.pk}/", {"nb_jours": 1, "date_fin": str(c.date_debut)}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        c.refresh_from_db()
        self.assertEqual(c.nb_jours, 3)

    def test_statut_sanction_non_modifiable_par_patch(self):
        s = Sanction.objects.create(
            employe=self.employe, type=Sanction.Type.AVERTISSEMENT, faits="x",
            date_constat=date.today(),
        )
        initial = s.statut
        _auth(self.client, "rh@etls.local")
        self.client.patch(f"{BASE}sanctions/{s.pk}/", {"statut": "archivee"}, format="json")
        s.refresh_from_db()
        self.assertEqual(s.statut, initial)


class BulletinTests(BaseRHTest):
    def rubrique(self, code="SAL", nature=RubriquePaie.Nature.GAIN):
        return RubriquePaie.objects.create(code=code, label=code, nature=nature)

    def post_bulletin(self, periode, lignes=None):
        _auth(self.client, "admin@etls.local")
        return self.client.post(
            f"{BASE}bulletins/",
            {"employe": str(self.employe.pk), "periode": periode, "salaire_base": "100000",
             "lignes": lignes or []},
            format="json",
        )

    def test_periode_normalisee_au_premier_du_mois(self):
        r = self.post_bulletin("2026-03-17")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(BulletinPaie.objects.get().periode, date(2026, 3, 1))
        # même mois, autre jour => doublon refusé (et non un 2e bulletin)
        r2 = self.post_bulletin("2026-03-28")
        self.assertIn(r2.status_code, (400, 409))
        self.assertEqual(BulletinPaie.objects.count(), 1)

    def test_bulletin_annule_n_empeche_pas_de_le_refaire(self):
        r = self.post_bulletin("2026-04-01")
        self.assertEqual(r.status_code, 201, r.content)
        self.client.post(f"{BASE}bulletins/{r.data['id']}/annuler/")
        r2 = self.post_bulletin("2026-04-01")
        self.assertEqual(r2.status_code, 201, r2.content)

    def test_creation_atomique_pas_de_bulletin_orphelin(self):
        rub = self.rubrique()
        lignes = [
            {"rubrique": str(rub.pk), "libelle": "A", "montant": "10"},
            {"rubrique": str(rub.pk), "libelle": "B", "montant": "20"},  # doublon de rubrique
        ]
        r = self.post_bulletin("2026-05-01", lignes)
        self.assertGreaterEqual(r.status_code, 400)
        self.assertEqual(BulletinPaie.objects.count(), 0)
