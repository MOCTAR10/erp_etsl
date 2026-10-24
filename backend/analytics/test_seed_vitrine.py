"""Jeu de démonstration « vitrine » : `seed_all_demo` puis `seed_demo_vitrine` joué deux fois.

Vérifie l'idempotence (la seconde exécution ne crée rien), les volumes clés par domaine, la tendance du chiffre
d'affaires sur 12 mois, le fil rouge GLOBAL RENTAL (618), l'équilibre des écritures, et que les écrans Direction /
tableau de bord répondent avec des données. Test long (plusieurs minutes) : le seed rejoue l'API réelle.
"""

import re
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.db.models import Count, Sum
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounting_kernel.models import AccountMove, AccountMoveLine
from achats.models import PurchaseInvoice, PurchaseOrder
from analytics.models import CubeFait
from analytics.vitrine import nettoyage
from analytics.vitrine.donnees import AFFAIRES, CLIENTS, EMPLOYES, FOURNISSEURS
from analytics.vitrine.outils import debut_mois
from commercial.models import Affaire, Opportunity
from comptabilite.models import Engagement, FactureClient, Paiement
from config.nombres import nombre_fr, pourcentage_fr
from controle_gestion.models import AnalyseEcart, Budget, ClotureGestion, ParametreGestion
from documents.models import Document, SignatureRequest
from documents.signatures import certificate
from hse.models import Incident, PermisTravail
from juridique.models import Caution, Convention, Courrier
from maintenance.models import OrdreTravail
from operations.models import PointageChantier, SituationTravaux
from qualite.models import ControleQualite, NonConformite
from referentiels.models import Partner
from rh_paie.models import BulletinPaie, Employe
from stocks.models import LotMatiere, MouvementStock
from users.models import User
from workflow.models import CircuitStep, Notification, Task

MODELES = (
    Partner, Opportunity, Affaire, SituationTravaux, FactureClient, Paiement, PurchaseOrder, PurchaseInvoice, Engagement,
    Employe, PointageChantier, BulletinPaie, MouvementStock, LotMatiere, OrdreTravail, Incident, PermisTravail,
    ControleQualite, NonConformite, Document, Task, Convention, Caution, Courrier, Budget, ClotureGestion, AccountMove,
    Notification, SignatureRequest, AnalyseEcart,
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

    # -- vraisemblance (audit premium : A-05, A-15, A-22, A-31, B02, B03, B06, B13, B20) ----------------------
    def test_relances_et_escalades_des_taches_en_retard(self):
        maintenant = timezone.now()
        en_retard = Task.objects.filter(status=Task.Status.PENDING, due_date__lt=maintenant, assigned_to__isnull=False)
        self.assertTrue(en_retard.exists())
        for tache in en_retard.select_related("step"):
            self.assertTrue(Notification.objects.filter(task=tache, kind="reminder", user=tache.assigned_to).exists())
            if tache.due_date + timedelta(days=tache.step.max_days or 1) < maintenant - timedelta(hours=1):
                self.assertTrue(Notification.objects.filter(task=tache, kind="escalation",
                                                            user__email="admin@etls.local").exists())
        # Historique sur l'année (relances des tâches traitées en retard, clôtures, écarts), jamais dans le futur.
        jours = {timezone.localdate(d) for d in Notification.objects.values_list("created_at", flat=True)}
        self.assertGreater(len(jours), 30)
        self.assertFalse(Notification.objects.filter(created_at__gt=maintenant).exists())
        self.assertTrue(Notification.objects.filter(is_read=False).exists())
        self.assertFalse(Notification.objects.filter(subject__regex=r"\d\.\d\d %").exists())

    def test_signatures_a_signer_et_historique(self):
        a_signer = SignatureRequest.objects.filter(
            status=SignatureRequest.Status.PENDING, signers__user__email="admin@etls.local", signers__status="pending",
        ).distinct()
        self.assertGreaterEqual(a_signer.count(), 2)
        self.assertTrue(all(r.expires_at > timezone.now() for r in a_signer))
        signees = SignatureRequest.objects.filter(status=SignatureRequest.Status.COMPLETED, signers__isnull=False).distinct()
        self.assertGreaterEqual(signees.count(), 8)
        for req in signees:
            self.assertTrue(certificate(req)["valid"], req.title)
        horodatages = list(SignatureRequest.objects.values_list("created_at", flat=True))
        self.assertEqual(len(horodatages), len(set(horodatages)))
        self.assertGreaterEqual(len({(d.year, d.month) for d in horodatages}), 9)

    def test_clotures_publiees_a_j3_j4_sans_contradiction(self):
        debut = debut_mois(self.today, 11)
        clotures = list(ClotureGestion.objects.filter(period__start_date__gte=debut,
                                                      period__end_date__lt=debut_mois(self.today, 0)))
        self.assertGreaterEqual(len(clotures), 10)
        for c in clotures:
            self.assertIsNotNone(c.date_publication, c.code)
            self.assertLess(c.date_publication, self.today)
            # Jamais « conforme J+4 » et « hors délai » à la fois.
            self.assertEqual(c.conforme_j4, c.reporting_statut == "a_temps", c.code)
        statuts = Counter(c.reporting_statut for c in clotures)
        self.assertEqual((statuts["j6"], statuts["hors_delai"]), (1, 1), statuts)
        self.assertTrue({(c.date_publication - c.period.end_date).days for c in clotures} >= {3, 4})

    def test_libelles_et_codes_propres(self):
        from django.apps import apps

        for nom_modele, champ in nettoyage.CHAMPS_DEMO:
            qs = apps.get_model(nom_modele).objects.filter(**{f"{champ}__contains": "(demo)"})
            if nom_modele == "documents.Document":
                qs = qs.exclude(title__startswith="Situation n")
            self.assertFalse(qs.exists(), nom_modele)
        self.assertFalse(Document.objects.filter(title__contains=" — archivage (").exists())
        self.assertFalse(Document.objects.filter(title__contains="Contrat signe ").exists())
        self.assertTrue(Document.objects.filter(title__startswith="Contrat signé ").exists())
        self.assertTrue(Affaire.objects.filter(title__startswith="Parcours demo - ").exists())  # contrat E2E
        for modele in (Affaire, Budget, ClotureGestion):
            codes = modele.objects.values_list("code", flat=True)
            self.assertFalse([c for c in codes if re.fullmatch(r"[A-Z]+-\d+", c)], modele.__name__)
        self.assertFalse(OrdreTravail.objects.filter(description__regex=r"\d\.\d\d ≥").exists())
        kpi = ParametreGestion.objects.filter(table="KPI_CIBLES")
        self.assertTrue(kpi.exists())
        self.assertFalse(kpi.filter(label__startswith="Cible du KPI").exists())
        self.assertEqual(CircuitStep.objects.get(circuit__code="circuit_comptabilite", order=3).actor_role, "finance")
        self.assertFalse(CircuitStep.objects.filter(actor_role="admin").exists())
        self.assertEqual(Partner.objects.filter(is_global_rental=True, is_active=True).count(), 1)

    def test_pieces_ged_etalees(self):
        self.assertFalse(Document.objects.values("created_at").annotate(n=Count("id")).filter(n__gt=1).exists())
        self.assertFalse(Document.objects.filter(created_at__date__gte=self.today).exists())
        mois = {(d.year, d.month) for d in Document.objects.values_list("created_at", flat=True)}
        self.assertGreaterEqual(len(mois), 12)


class NettoyageHeritesTests(TestCase):
    """Bases chargées par les anciens seeds : libellés, codes et titres remis au propre, de façon rejouable."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_accounting", year=2026, stdout=StringIO())

    def test_libelles_titres_codes_et_tiers(self):
        from accounting_kernel.models import Period

        docs = {
            "CRRL AFF00003 (demo)": "CRRL AFF00003",
            "Contrat signe CTT00002 (demo)": "Contrat signé CTT00002",
            "Avenant 1 CTT00002 (demo)": "Avenant n°1 CTT00002",
            "Situation n1 (demo) - installation": "Situation n1 (demo) - installation",  # recherche du spec E2E
        }
        for titre in docs:
            Document.objects.create(title=titre)
        Document.objects.create(title="PV00007 — PV de réception X (Réceptionné) — archivage (receptionne)",
                                reference="PV00007")
        Document.objects.create(title="CNV00001 — Bail — archivage (Signé (en cours de validité))", reference="CNV00001")
        ParametreGestion.objects.create(code="KPI_01", label="Cible du KPI KP-M11-01", valeur=25, unite="")
        periode = Period.objects.filter(fiscal_year__year=2026).order_by("number").first()
        cloture = ClotureGestion.objects.create(code="CLO-00001", period=periode)
        for code in ("GR-0001", "GR-01", "GR-1000"):
            Partner.objects.create(code=code, name="GLOBAL RENTAL", kind="fournisseur", is_global_rental=True)

        bilan = nettoyage.tout_nettoyer()
        for nouveau in docs.values():
            self.assertTrue(Document.objects.filter(title=nouveau).exists(), nouveau)
        self.assertTrue(Document.objects.filter(title="PV de réception X (Réceptionné)").exists())
        self.assertTrue(Document.objects.filter(title="Bail — Signé (en cours de validité)").exists())
        self.assertEqual(ParametreGestion.objects.get(code="KPI_01").label, "Cible — Taux de marge brute (KP-M11-01)")
        cloture.refresh_from_db()
        self.assertRegex(cloture.code, r"^CLO\d{5}$")
        self.assertEqual(list(Partner.objects.filter(is_active=True).values_list("code", flat=True)), ["GR-0001"])
        self.assertEqual(bilan["tiers_gr"], 2)
        # Rejouable : une base propre n'est plus modifiée.
        self.assertFalse(any(nettoyage.tout_nettoyer().values()))

    def test_nombres_francais(self):
        self.assertEqual(nombre_fr(Decimal("900.00")), "900")
        self.assertEqual(nombre_fr(Decimal("1250.5")), "1 250,5")
        self.assertEqual(pourcentage_fr(Decimal("-100.00"), signe=True), "−100 %")
        self.assertEqual(pourcentage_fr(Decimal("11.34"), signe=True), "+11,34 %")
