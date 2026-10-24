"""Jeu de démonstration « vitrine » : `seed_all_demo` puis `seed_demo_vitrine` joué deux fois.

Vérifie l'idempotence (la seconde exécution ne crée rien), les volumes clés par domaine, la tendance du chiffre
d'affaires sur 12 mois, le fil rouge GLOBAL RENTAL (618), l'équilibre des écritures, et que les écrans Direction /
tableau de bord répondent avec des données. Test long (plusieurs minutes) : le seed rejoue l'API réelle.
"""

from collections import defaultdict
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.db.models import Sum
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounting_kernel.models import AccountMove, AccountMoveLine
from achats.models import PurchaseInvoice, PurchaseOrder
from analytics.models import CubeFait
from analytics.vitrine.donnees import AFFAIRES, CLIENTS, EMPLOYES, FOURNISSEURS
from analytics.vitrine.outils import debut_mois
from commercial.models import Affaire, Opportunity
from comptabilite.models import Engagement, FactureClient, Paiement
from controle_gestion.models import Budget, ClotureGestion
from documents.models import Document
from hse.models import Incident, PermisTravail
from juridique.models import Caution, Convention, Courrier
from maintenance.models import OrdreTravail
from operations.models import PointageChantier, SituationTravaux
from qualite.models import ControleQualite, NonConformite
from referentiels.models import Partner
from rh_paie.models import BulletinPaie, Employe
from stocks.models import LotMatiere, MouvementStock
from users.models import User
from workflow.models import Task

MODELES = (
    Partner, Opportunity, Affaire, SituationTravaux, FactureClient, Paiement, PurchaseOrder, PurchaseInvoice, Engagement,
    Employe, PointageChantier, BulletinPaie, MouvementStock, LotMatiere, OrdreTravail, Incident, PermisTravail,
    ControleQualite, NonConformite, Document, Task, Convention, Caution, Courrier, Budget, ClotureGestion, AccountMove,
)


def _etat():
    return {m.__name__: m.objects.count() for m in MODELES}


class SeedDemoVitrineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_all_demo", verbosity=0, stdout=StringIO())
        cls.avant = _etat()
        call_command("seed_demo_vitrine", stdout=StringIO())
        cls.apres = _etat()
        call_command("seed_demo_vitrine", stdout=StringIO())
        cls.rejoue = _etat()
        cls.today = timezone.localdate()

    def test_seconde_execution_ne_cree_rien(self):
        self.assertEqual(self.apres, self.rejoue)

    def test_aucun_prefixe_technique_dans_les_libelles(self):
        self.assertFalse(OrdreTravail.objects.filter(description__contains="[Vitrine]").exists())
        self.assertFalse(ControleQualite.objects.filter(point_controle__contains="[Vitrine]").exists())
        self.assertTrue(ControleQualite.objects.filter(point_controle__startswith="Contrôle CND — joints lot ").exists())

    def test_complete_seed_all_demo(self):
        for modele, n in self.avant.items():
            self.assertGreaterEqual(self.apres[modele], n, modele)
        titres = [titre for _, titre, *_ in AFFAIRES]
        self.assertEqual(Affaire.objects.filter(title__in=titres).count(), len(AFFAIRES))
        self.assertTrue(Affaire.objects.filter(title__startswith="Parcours demo - ").exists())

    def test_volumes_par_domaine(self):
        self.assertEqual(Partner.objects.filter(code__startswith="CLT-").count(), len(CLIENTS))
        self.assertEqual(Partner.objects.filter(code__startswith="FRN-").count(), len(FOURNISSEURS))
        self.assertEqual(Employe.objects.filter(nom__in=[e[0] for e in EMPLOYES]).count(), len(EMPLOYES))
        delta = {m: self.apres[m] - self.avant[m] for m in self.apres}
        minimums = {
            "FactureClient": 60, "Paiement": 100, "PurchaseOrder": 90, "PurchaseInvoice": 70, "Engagement": 40,
            "PointageChantier": 800, "BulletinPaie": 350, "OrdreTravail": 40, "Incident": 12, "PermisTravail": 30,
            "ControleQualite": 60, "Document": 150, "Task": 150, "Courrier": 30, "Budget": 10, "ClotureGestion": 8,
            "LotMatiere": 20,
        }
        for modele, minimum in minimums.items():
            self.assertGreaterEqual(delta[modele], minimum, modele)

    def test_chiffre_affaires_croissant_sur_douze_mois(self):
        par_mois = defaultdict(Decimal)
        for f in FactureClient.objects.filter(statut="emise", nature="facture", affaire__title__in=[a[1] for a in AFFAIRES]):
            par_mois[(f.date.year, f.date.month)] += f.montant_ht
        mois = [debut_mois(self.today, k) for k in range(11, 0, -1)]
        serie = [par_mois[(m.year, m.month)] for m in mois]
        self.assertTrue(all(v > 0 for v in serie), serie)
        self.assertGreater(sum(serie[-3:]), sum(serie[:3]) * 2)

    def test_global_rental_impute_au_618(self):
        gr = PurchaseInvoice.objects.filter(supplier__is_global_rental=True, status="comptabilisee")
        self.assertTrue(gr.exists())
        lignes = AccountMoveLine.objects.filter(move__in=gr.values("move"), debit__gt=0)
        self.assertTrue(lignes.filter(account__code="618000").exists())

    def test_ecritures_comptabilisees_et_equilibrees(self):
        pieces = [
            FactureClient.objects.filter(statut="emise").values("move"),
            PurchaseInvoice.objects.filter(status="comptabilisee").values("move"),
            BulletinPaie.objects.filter(move__isnull=False).values("move"),
            Paiement.objects.filter(statut="valide").values("move"),
        ]
        for moves in pieces:
            self.assertFalse(AccountMove.objects.filter(pk__in=moves).exclude(status=AccountMove.Status.POSTED).exists())
        moves = AccountMove.objects.filter(date__gte=debut_mois(self.today, 11), status=AccountMove.Status.POSTED)
        self.assertGreater(moves.count(), 500)
        totaux = AccountMoveLine.objects.filter(move__in=moves).aggregate(d=Sum("debit"), c=Sum("credit"))
        self.assertEqual(totaux["d"], totaux["c"])

    def test_cube_alimente_sur_douze_mois(self):
        periodes = set(CubeFait.objects.filter(produits__gt=0).values_list("periode", flat=True))
        for k in range(11, 0, -1):
            self.assertIn(debut_mois(self.today, k).strftime("%Y-%m"), periodes)

    @override_settings(ALLOWED_HOSTS=["testserver"])
    def test_ecrans_direction_et_tableau_de_bord(self):
        client = APIClient()
        client.force_authenticate(User.objects.get(email="admin@etls.local"))
        for url in ("/api/analytics/dashboard/", "/api/analytics/tendances/", "/api/analytics/pilotage/",
                    "/api/analytics/petrolier/", "/api/analytics/alertes/", "/api/reports/dashboard/",
                    "/api/analytics/cubes/?axes=periode"):
            self.assertEqual(client.get(url).status_code, 200, url)
        direction = client.get("/api/analytics/dashboard/").json()
        self.assertGreaterEqual(direction["rh_paie"]["effectif"], len(EMPLOYES))
        self.assertGreaterEqual(direction["commercial"]["affaires_actives"], 8)
        self.assertIsNotNone(direction["hse"]["jours_sans_accident"])
        tendances = client.get("/api/analytics/tendances/").json()["series"]
        self.assertTrue(all(n > 0 for n in tendances["documents"]), tendances)
        self.assertTrue(all(n > 0 for n in tendances["ordres_travail"]), tendances)
        pilotage = client.get("/api/analytics/pilotage/").json()
        self.assertGreater(Decimal(pilotage["pipe_budget"]["budget_produits"]), 0)
        self.assertTrue({s["niveau"] for s in pilotage["seuils_budget"]} >= {"alerte", "atteint", "depasse"})
