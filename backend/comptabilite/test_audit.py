"""Audit métier M10 (2026-10-16) — régressions des écarts trouvés.

C1  : comptabilisation atomique, un paiement annulé ne se comptabilise pas, pas de double écriture.
C2  : `Engagement.total_paye` ne compte que les paiements validés.
C9  : paiement sur engagement non approuvé / au-delà du solde refusé.
C10 : `DeclarationTva.mois` normalisé au 1er du mois (sinon des paiements du mois sont ignorés).
C17 : paiement validé / engagement approuvé / déclaration déposée : non modifiables ni supprimables.
C20 : l'approbation d'un engagement est réservée au cercle de validation.
C6  : montants strictement positifs.
"""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from rest_framework import status

from accounting_kernel.models import AccountMove

from .models import DeclarationTva, Engagement, Paiement
from .services import build_paiement_move, compute_declaration_tva
from .tests import BASE, BaseComptaTest, _auth


class ComptabilisationTests(BaseComptaTest):
    def test_paiement_annule_ne_se_comptabilise_pas(self):
        p = self._paiement()
        p.statut = Paiement.Statut.ANNULE
        p.save()
        with self.assertRaises(ValidationError):
            build_paiement_move(p, self.finance)
        self.assertEqual(AccountMove.objects.count(), 0)

    def test_double_comptabilisation_refusee_une_seule_ecriture(self):
        p = self._paiement()
        build_paiement_move(p, self.finance)
        p.refresh_from_db()
        with self.assertRaises(ValidationError):
            build_paiement_move(p, self.finance)
        self.assertEqual(AccountMove.objects.filter(source_ref=p.code).count(), 1)

    def test_echec_ne_laisse_aucun_brouillon_orphelin(self):
        # période inexistante -> échec avant création ; compte absent -> échec après
        p = self._paiement(imputation_618=True)
        from referentiels.models import Account

        Account.objects.filter(code="618000").delete()
        with self.assertRaises(ValidationError):
            build_paiement_move(p, self.finance)
        self.assertEqual(AccountMove.objects.count(), 0)

    def test_engagement_non_approuve_refuse(self):
        eng = self._engagement(statut=Engagement.Statut.SOUMIS)
        p = self._paiement(engagement=eng)
        with self.assertRaises(ValidationError):
            build_paiement_move(p, self.finance)

    def test_depassement_du_solde_refuse(self):
        eng = self._engagement(statut=Engagement.Statut.APPROUVE)  # 250 000
        p = self._paiement(engagement=eng, montant="300000.00")
        with self.assertRaises(ValidationError):
            build_paiement_move(p, self.finance)

    def test_total_paye_ne_compte_que_les_valides(self):
        eng = self._engagement(statut=Engagement.Statut.APPROUVE)
        banque = self._banque()
        ok = self._paiement(engagement=eng, montant="100000.00", compte_bancaire=banque)
        build_paiement_move(ok, self.finance)
        self._paiement(engagement=eng, montant="50000.00", compte_bancaire=banque)  # brouillon
        annule = self._paiement(engagement=eng, montant="70000.00", compte_bancaire=banque)
        annule.statut = Paiement.Statut.ANNULE
        annule.save()
        eng.refresh_from_db()
        self.assertEqual(eng.total_paye, Decimal("100000.00"))
        self.assertEqual(eng.solde, Decimal("150000.00"))


class TvaTests(BaseComptaTest):
    def test_mois_normalise_au_premier_jour(self):
        taux = self._taux_tva()
        d = DeclarationTva.objects.create(mois=date(2026, 1, 20), taux_tva=taux)
        d.refresh_from_db()
        self.assertEqual(d.mois, date(2026, 1, 1))

    def test_paiements_du_debut_de_mois_comptes_meme_si_mois_saisi_le_20(self):
        taux = self._taux_tva()
        banque = self._banque()
        p = self._paiement(sens="entree", montant="1000.00", date=date(2026, 1, 5), compte_bancaire=banque)
        build_paiement_move(p, self.finance)
        d = DeclarationTva.objects.create(mois=date(2026, 1, 20), taux_tva=taux)
        compute_declaration_tva(d)
        self.assertEqual(d.base_imposable, Decimal("1000.00"))


class VerrouillageApiTests(BaseComptaTest):
    def test_paiement_valide_non_modifiable_ni_supprimable(self):
        p = self._paiement()
        build_paiement_move(p, self.finance)
        _auth(self.client, "finance@etls.local")
        r = self.client.patch(f"{BASE}paiements/{p.pk}/", {"montant": "1.00"}, format="json")
        self.assertGreaterEqual(r.status_code, 400, r.content)
        self.assertEqual(self.client.delete(f"{BASE}paiements/{p.pk}/").status_code, 400)
        p.refresh_from_db()
        self.assertEqual(p.montant, Decimal("250000.00"))

    def test_engagement_approuve_non_modifiable(self):
        eng = self._engagement(statut=Engagement.Statut.APPROUVE)
        _auth(self.client, "finance@etls.local")
        r = self.client.patch(f"{BASE}engagements/{eng.pk}/", {"montant": "1.00"}, format="json")
        self.assertGreaterEqual(r.status_code, 400, r.content)
        self.assertEqual(self.client.delete(f"{BASE}engagements/{eng.pk}/").status_code, 400)

    def test_declaration_deposee_non_modifiable(self):
        taux = self._taux_tva()
        d = DeclarationTva.objects.create(
            mois=date(2026, 1, 1), taux_tva=taux, statut=DeclarationTva.Statut.DEPOSEE,
            net_a_payer=Decimal("100.00"),
        )
        _auth(self.client, "finance@etls.local")
        r = self.client.patch(f"{BASE}declarations-tva/{d.pk}/", {"net_a_payer": "0"}, format="json")
        self.assertGreaterEqual(r.status_code, 400, r.content)
        self.assertEqual(self.client.delete(f"{BASE}declarations-tva/{d.pk}/").status_code, 400)

    def test_approbation_reservee_au_cercle_de_validation(self):
        from django.contrib.auth import get_user_model

        get_user_model().objects.create_user(
            email="projets@etls.local", password="Etls#Demo2026",
            role="directeur_projets", first_name="P",
        )
        eng = self._engagement(statut=Engagement.Statut.SOUMIS)
        _auth(self.client, "projets@etls.local")
        r = self.client.post(f"{BASE}engagements/{eng.pk}/approuver/")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN, r.content)
        _auth(self.client, "finance@etls.local")
        r = self.client.post(f"{BASE}engagements/{eng.pk}/approuver/", {"date_engagement": "2026-01-12"})
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.content)

    def test_approbation_date_invalide_renvoie_400(self):
        eng = self._engagement(statut=Engagement.Statut.SOUMIS)
        _auth(self.client, "finance@etls.local")
        r = self.client.post(f"{BASE}engagements/{eng.pk}/approuver/", {"date_engagement": "pas-une-date"})
        self.assertEqual(r.status_code, 400, r.content)

    def test_montants_strictement_positifs(self):
        _auth(self.client, "finance@etls.local")
        banque = self._banque()
        r = self.client.post(
            f"{BASE}paiements/",
            {"sens": "sortie", "mode": "virement", "montant": "-5.00", "compte_bancaire": str(banque.pk)},
            format="json",
        )
        self.assertEqual(r.status_code, 400, r.content)
        r = self.client.post(
            f"{BASE}engagements/",
            {"objet": "x", "montant": "0", "compte_depense": self.banque_account.pk},
            format="json",
        )
        self.assertEqual(r.status_code, 400, r.content)
