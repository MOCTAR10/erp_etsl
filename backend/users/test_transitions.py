"""Audit lot 9 (2026-10-17) — transitions de workflow : état de départ contrôlé, historique non réécrit.

Chaque action ne s'applique qu'à partir des états prévus : pas de retour en arrière (NC clôturée « rouverte »,
demande traitée « resoumise », salarié sorti réactivé) ni de réécriture d'une preuve (date/efficacité d'une CAPA
déjà clôturée, date de sortie d'un salarié déjà sorti). Un équipement en location / affecté ne redevient pas
« disponible » par simple bouton. Les lignes d'un relevé validé ne peuvent pas être ajoutées par un autre relevé.
"""

from datetime import date

from rest_framework.test import APITestCase

from comptabilite.models import CompteBancaire, LigneReleve, ReleveBancaire
from hse.models import ActionHse
from logistique.models import AffectationParc, DemandeMobilisation, EquipementParc
from qualite.models import ActionCorrective, NonConformite
from referentiels.models import Account
from rh_paie.models import Employe

from .models import User


class TransitionsTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.ga", password="x-Audit-2026", role=User.Role.ADMIN, is_staff=True
        )
        self.client.force_authenticate(self.admin)

    def post(self, url, data=None):
        return self.client.post(url, data or {}, format="json")

    # --- Qualité ---------------------------------------------------------------------------
    def test_nc_cloturee_ne_se_rouvre_pas(self):
        nc = NonConformite.objects.create(description="Porosité", statut=NonConformite.Statut.CLOTUREE)
        self.assertEqual(self.post(f"/api/qualite/non-conformites/{nc.pk}/traiter/", {"traitement": "reprise"}).status_code, 400)
        nc.refresh_from_db()
        self.assertEqual(nc.statut, NonConformite.Statut.CLOTUREE)

    def test_nc_non_traitee_ne_se_cloture_pas(self):
        nc = NonConformite.objects.create(description="Défaut d'alignement")
        self.assertEqual(self.post(f"/api/qualite/non-conformites/{nc.pk}/cloturer/").status_code, 400)

    def test_capa_qualite_cloturee_non_reecrite(self):
        nc = NonConformite.objects.create(description="X")
        capa = ActionCorrective.objects.create(non_conformite=nc, description="Former", statut=ActionCorrective.Statut.CLOTUREE, efficace=True)
        self.assertEqual(self.post(f"/api/qualite/actions-correctives/{capa.pk}/cloturer/", {"efficace": False}).status_code, 400)
        capa.refresh_from_db()
        self.assertTrue(capa.efficace)

    # --- HSE -------------------------------------------------------------------------------
    def test_capa_hse_cloturee_non_reecrite(self):
        a = ActionHse.objects.create(description="Baliser", statut=ActionHse.Statut.CLOTUREE, efficace=True)
        self.assertEqual(self.post(f"/api/hse/actions/{a.pk}/cloturer/", {"efficace": False}).status_code, 400)
        a.refresh_from_db()
        self.assertTrue(a.efficace)

    # --- Logistique ------------------------------------------------------------------------
    def test_demande_traitee_ne_se_resoumet_pas_et_brouillon_ne_se_traite_pas(self):
        traitee = DemandeMobilisation.objects.create(label="Grue 50 t", statut=DemandeMobilisation.Statut.TRAITEE)
        self.assertEqual(self.post(f"/api/logistique/demandes/{traitee.pk}/soumettre/").status_code, 400)
        brouillon = DemandeMobilisation.objects.create(label="Nacelle")
        self.assertEqual(self.post(f"/api/logistique/demandes/{brouillon.pk}/traiter/").status_code, 400)

    def test_equipement_affecte_ne_redevient_pas_disponible(self):
        eq = EquipementParc.objects.create(label="Chariot 5 t", statut=EquipementParc.Statut.AFFECTE)
        AffectationParc.objects.create(equipement=eq, date_debut=date.today())
        self.assertEqual(self.post("/api/logistique/equipements/disponibilite/", {"id": str(eq.pk)}).status_code, 400)
        eq.refresh_from_db()
        self.assertEqual(eq.statut, EquipementParc.Statut.AFFECTE)

    # --- RH --------------------------------------------------------------------------------
    def test_salarie_sorti_ni_reactive_ni_resorti(self):
        e = Employe.objects.create(code="EMP-S", civilite="feminin", nom="Partie", statut=Employe.Statut.SORTI,
                                   date_sortie=date(2026, 3, 31))
        self.assertEqual(self.post(f"/api/rh-paie/employes/{e.pk}/activer/").status_code, 400)
        self.assertEqual(self.post(f"/api/rh-paie/employes/{e.pk}/sortir/", {"date_sortie": "2026-09-30"}).status_code, 400)
        e.refresh_from_db()
        self.assertEqual(e.date_sortie, date(2026, 3, 31))

    # --- Comptabilité ----------------------------------------------------------------------
    def test_lignes_ne_s_ajoutent_pas_a_un_releve_valide_par_un_autre_releve(self):
        compte_512, _ = Account.objects.get_or_create(
            code="512000", defaults=dict(label="Banque", account_class=5, account_type=Account.AccountType.ASSET)
        )
        banque = CompteBancaire.objects.create(label="BGFI", banque="BGFI", compte_comptable=compte_512)
        valide = ReleveBancaire.objects.create(compte_bancaire=banque, date_debut=date(2026, 9, 1), date_fin=date(2026, 9, 30),
                                               statut=ReleveBancaire.Statut.VALIDE)
        brouillon = ReleveBancaire.objects.create(compte_bancaire=banque, date_debut=date(2026, 10, 1), date_fin=date(2026, 10, 31))
        self.post(f"/api/comptabilite/releves/{brouillon.pk}/lignes/",
                  {"lignes": [{"releve": str(valide.pk), "date": "2026-10-02", "libelle": "Intrus", "credit": "10"}]})
        self.assertFalse(LigneReleve.objects.filter(releve=valide).exists())
        self.assertEqual(self.post(f"/api/comptabilite/releves/{brouillon.pk}/lignes/", {"lignes": ["x"]}).status_code, 400)
