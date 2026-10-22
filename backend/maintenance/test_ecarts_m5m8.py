"""Écarts M8 (lot m5m8) — tests de recette : centre analytique maintenance par machine, écriture 624 / 618 à la
clôture d'OT (comptes provisoires paramétrables), coût consolidé par an / mois / machine / centre → M11."""

from datetime import date
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from accounting_kernel.models import AccountMove, FiscalYear, Journal, Period
from outbox.models import OutboxEvent
from referentiels.models import Account, Partner
from users.models import User

from .ecarts_m5m8 import centres_maintenance
from .models import Actif, OrdreTravail


def _comptabilite():
    for code, label, cls, typ in (
        ("624000", "Entretien et réparations", 6, Account.AccountType.EXPENSE),
        ("618000", "Refacturations intra-groupe GLOBAL RENTAL", 6, Account.AccountType.EXPENSE),
        ("661000", "Charges de personnel", 6, Account.AccountType.EXPENSE),
        ("603300", "Variations des stocks d'autres approvisionnements", 6, Account.AccountType.EXPENSE),
    ):
        Account.objects.get_or_create(code=code, defaults={"label": label, "account_class": cls, "account_type": typ})
    Journal.objects.get_or_create(code="OD", defaults={"label": "Opérations diverses", "journal_type": Journal.JournalType.OD})
    an = timezone.localdate().year
    fy, _ = FiscalYear.objects.get_or_create(year=an, defaults={"start_date": date(an, 1, 1), "end_date": date(an, 12, 31)})
    m = timezone.localdate().month
    if not Period.objects.filter(start_date__lte=timezone.localdate(), end_date__gte=timezone.localdate()).exists():
        fin = date(an + (m == 12), m % 12 + 1, 1)
        from datetime import timedelta

        Period.objects.create(fiscal_year=fy, number=m, start_date=date(an, m, 1), end_date=fin - timedelta(days=1))


class _Base(APITestCase):
    def setUp(self):
        self.maint = User.objects.create_user(email="maint@etls.ga", password="x-Audit-2026", role=User.Role.MAINTENANCE)
        self.client.force_authenticate(self.maint)
        self.engin = Actif.objects.create(designation="Grue mobile 50 t", categorie="levage")
        self.poste = Actif.objects.create(designation="Poste MIG", categorie="machine")

    def ot_termine(self, actif, heures="4", tarif="10000", pieces="5000"):
        ot = OrdreTravail.objects.create(actif=actif, description="Réparation", statut=OrdreTravail.Statut.TERMINE,
                                         heures_mo=Decimal(heures), tarif_horaire=Decimal(tarif),
                                         cout_pieces=Decimal(pieces), date_fin=timezone.now())
        return ot


class CentreAnalytiqueTests(_Base):
    def test_centre_deduit_de_la_categorie_et_modifiable(self):
        r = self.client.get(f"/api/maintenance/actifs/{self.engin.pk}/")
        self.assertEqual(r.data["centre_code"], "MAINT-PARC")
        self.assertEqual(self.client.get(f"/api/maintenance/actifs/{self.poste.pk}/").data["centre_code"], "MAINT-ATL")
        centres = self.client.get("/api/maintenance/actifs/centres/").data
        self.assertEqual([c["code"] for c in centres], ["MAINT-ATL", "MAINT-PARC", "MAINT-GR"])
        atl = next(c for c in centres if c["code"] == "MAINT-ATL")
        r = self.client.patch(f"/api/maintenance/actifs/{self.engin.pk}/", {"centre_analytique": atl["id"]}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["centre_code"], "MAINT-ATL")


class EcritureClotureTests(_Base):
    def setUp(self):
        super().setUp()
        _comptabilite()

    def test_cloture_passe_l_ecriture_624_sur_le_centre(self):
        ot = self.ot_termine(self.engin)
        r = self.client.post(f"/api/maintenance/ordres/{ot.pk}/cloturer/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["ecriture_numero"], r.data["motif_ecriture"])
        move = AccountMove.objects.get(source="M8", source_ref=str(ot.pk))
        self.assertEqual(move.status, AccountMove.Status.POSTED)
        debit = move.lines.get(debit__gt=0)
        self.assertEqual(debit.account.code, "624000")
        self.assertEqual(debit.debit, Decimal("45000.00"))
        self.assertEqual(debit.analytic_account.code, "MAINT-PARC")
        self.assertEqual({(l.account.code, l.credit) for l in move.lines.filter(credit__gt=0)},
                         {("661000", Decimal("40000.00")), ("603300", Decimal("5000.00"))})
        self.assertTrue(OutboxEvent.objects.filter(topic="maintenance.ot.cout").exists())

    def test_machine_gr_imputee_au_618_avec_partenaire_gr(self):
        Partner.objects.create(code="GR", name="GLOBAL RENTAL", is_global_rental=True)
        self.poste.signe_618 = True
        self.poste.save()
        ot = self.ot_termine(self.poste)
        self.client.post(f"/api/maintenance/ordres/{ot.pk}/cloturer/")
        debit = AccountMove.objects.get(source_ref=str(ot.pk)).lines.get(debit__gt=0)
        self.assertEqual(debit.account.code, "618000")
        self.assertTrue(debit.partner.is_global_rental)
        self.assertEqual(debit.analytic_account.code, "MAINT-GR")

    def test_sans_journal_cloture_reste_valide_et_motif_conserve(self):
        Journal.objects.filter(code="OD").delete()
        ot = self.ot_termine(self.engin)
        r = self.client.post(f"/api/maintenance/ordres/{ot.pk}/cloturer/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["statut"], "cloture")
        self.assertIn("Écriture non passée", r.data["motif_ecriture"])

    def test_taux_horaire_par_defaut_provisoire(self):
        ot = self.ot_termine(self.engin, heures="2", tarif="0", pieces="0")
        r = self.client.post(f"/api/maintenance/ordres/{ot.pk}/cloturer/")
        self.assertEqual(Decimal(r.data["cout_main_oeuvre"]), Decimal("30000"))


class CoutsAnnuelsTests(_Base):
    def test_cumul_par_mois_machine_centre_et_exports(self):
        self.ot_termine(self.engin)
        self.ot_termine(self.poste, heures="1", tarif="10000", pieces="0")
        annee = timezone.localdate().year
        r = self.client.get(f"/api/maintenance/ordres/couts-annuels/?annee={annee}")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["total"], "55000.00")
        self.assertEqual(r.data["cumul"][-1], "55000.00")
        self.assertEqual({c["centre"]: c["total"] for c in r.data["centres"]},
                         {"MAINT-PARC": "45000.00", "MAINT-ATL": "10000.00"})
        self.assertTrue(r.data["provisoire"])
        self.assertTrue(self.client.get(f"/api/maintenance/ordres/couts-annuels/?annee={annee}&export=xlsx").content.startswith(b"PK"))
        self.assertTrue(self.client.get(f"/api/maintenance/ordres/couts-annuels/?annee={annee}&export=pdf").content.startswith(b"%PDF"))
        # Le coût mensuel publié à M11 porte le centre.
        from .services import couts_maintenance

        rows = couts_maintenance(timezone.localdate().strftime("%Y-%m"))["rows"]
        self.assertEqual({r["centre"] for r in rows}, {"MAINT-PARC", "MAINT-ATL"})

    def test_reserve_aux_roles_montants(self):
        self.client.force_authenticate(User.objects.create_user(email="l@etls.ga", password="x", role=User.Role.LOGISTIQUE))
        self.assertEqual(self.client.get("/api/maintenance/ordres/couts-annuels/").status_code, 403)

    def test_centres_idempotents(self):
        self.assertEqual(len(centres_maintenance()), 3)
        self.assertEqual(len(centres_maintenance()), 3)
