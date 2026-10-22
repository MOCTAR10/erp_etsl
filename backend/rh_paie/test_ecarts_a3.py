"""Lot a3 (M3 → M9) : prime de chantier dérivée des pointages d'OF de chantier (paramètres provisoires)."""

from datetime import date
from decimal import Decimal

from django.core.management import call_command

from operations.models import OrdreFabrication, PointageChantier

from .models import BulletinLigne, ParametrePaie, SaisieTemps
from .services import jours_chantier
from .test_cloture_m9 import M9Base
from .tests import BASE, _auth


class PrimeChantierTests(M9Base):
    def setUp(self):
        super().setUp()
        call_command("seed_baremes_legaux_provisoires")
        self.chantier = OrdreFabrication.objects.create(label="Pose ligne", scope="chantier")
        self.atelier = OrdreFabrication.objects.create(label="Spool", scope="atelier")

    def pointer(self, of, jour, heures):
        st = SaisieTemps.objects.create(employe=self.employe, date=jour, heures=Decimal(heures))
        PointageChantier.objects.create(
            ordre=of, employe=self.employe, worker_name="Opérateur", date=jour, hours=Decimal(heures),
            saisie_temps=st, status=PointageChantier.Status.TRANSFERE,
        )

    def integrer(self, b):
        _auth(self.client, "finance@etls.local")
        r = self.client.post(f"{BASE}bulletins/{b.pk}/integrer-temps/")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def test_jours_de_chantier_au_dela_du_seuil(self):
        self.pointer(self.chantier, date(2026, 3, 2), "8")
        self.pointer(self.chantier, date(2026, 3, 3), "2")  # sous le seuil provisoire de 4 h
        self.pointer(self.atelier, date(2026, 3, 4), "8")  # atelier : pas de prime de chantier
        self.assertEqual(jours_chantier(self.employe, date(2026, 3, 1), Decimal("4")), [date(2026, 3, 2)])

    def test_prime_versee_seulement_si_le_montant_est_saisi_par_etsl(self):
        self.pointer(self.chantier, date(2026, 3, 2), "8")
        self.pointer(self.chantier, date(2026, 3, 5), "6")
        b = self.bulletin()
        self.integrer(b)
        self.assertFalse(BulletinLigne.objects.filter(bulletin=b, rubrique__code="PRIME-CHANTIER").exists())
        ParametrePaie.objects.filter(code="PRIME_CHANTIER_JOUR").update(valeur=Decimal("2500"))
        data = self.integrer(b)
        ligne = BulletinLigne.objects.get(bulletin=b, rubrique__code="PRIME-CHANTIER")
        self.assertEqual(ligne.montant, Decimal("5000.00"))
        self.assertIn("2 j", ligne.libelle)
        self.assertIn("PRIME_CHANTIER_JOUR", data["baremes_provisoires"])
        self.integrer(b)  # idempotent
        self.assertEqual(BulletinLigne.objects.filter(bulletin=b, rubrique__code="PRIME-CHANTIER").count(), 1)
