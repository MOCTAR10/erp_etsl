"""Jeu volumétrique (CDC §8.2, CL-OM-01) pour la campagne de performance `backend/perf/`.

Bornes hautes du CDC par défaut (PROVISOIRE : volumes réels à confirmer par ETSL) : 400 salariés sous contrat,
80 affaires, 15 000 écritures comptabilisées sur le mois courant (2 lignes chacune). Tout est préfixé `VOL-` :
la commande est idempotente (rejouable, complète seulement ce qui manque) et ne touche aucune donnée existante.

Usage : `python manage.py seed_volumetrie [--salaries 400] [--affaires 80] [--ecritures 15000]`.
Ne jamais lancer sur la production : réservé aux bases de recette / CI de performance.
"""

import calendar
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

PREFIXE = "VOL-"
LOT = 2000


class Command(BaseCommand):
    help = "Génère le jeu volumétrique de la campagne de performance (préfixe VOL-, idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--salaries", type=int, default=400)
        parser.add_argument("--affaires", type=int, default=80)
        parser.add_argument("--ecritures", type=int, default=15000)

    def handle(self, *args, **opts):
        today = timezone.localdate()
        n_emp = self._salaries(opts["salaries"], today)
        n_aff = self._affaires(opts["affaires"], today)
        n_ecr = self._ecritures(opts["ecritures"], today)
        self.stdout.write(self.style.SUCCESS(
            f"Volumetrie : {n_emp} salaries, {n_aff} affaires, {n_ecr} ecritures (prefixe {PREFIXE})"))

    @transaction.atomic
    def _salaries(self, n, today):
        from rh_paie.models import ContratTravail, Employe

        existants = set(Employe.objects.filter(code__startswith=PREFIXE).values_list("code", flat=True))
        nouveaux = [
            Employe(code=f"{PREFIXE}E{i:04d}", civilite="M", nom=f"Volume{i:04d}", prenom="Test",
                    date_embauche=date(today.year - 1, 1, 1))
            for i in range(1, n + 1) if f"{PREFIXE}E{i:04d}" not in existants
        ]
        Employe.objects.bulk_create(nouveaux, batch_size=LOT)
        sans_contrat = Employe.objects.filter(code__startswith=PREFIXE).exclude(
            pk__in=ContratTravail.objects.values("employe_id"))
        ContratTravail.objects.bulk_create([
            ContratTravail(code=f"{PREFIXE}C{e.code[-4:]}", employe=e, date_debut=date(today.year - 1, 1, 1),
                           salaire_base=Decimal(250000 + 1000 * (int(e.code[-4:]) % 500)))
            for e in sans_contrat
        ], batch_size=LOT)
        return Employe.objects.filter(code__startswith=PREFIXE).count()

    @transaction.atomic
    def _affaires(self, n, today):
        from commercial.models import Affaire

        existants = set(Affaire.objects.filter(code__startswith=PREFIXE).values_list("code", flat=True))
        Affaire.objects.bulk_create([
            Affaire(code=f"{PREFIXE}AFF{i:03d}", title=f"Affaire volumétrique {i:03d}", start_date=today,
                    contract_amount=Decimal(10_000_000 + 100_000 * i))
            for i in range(1, n + 1) if f"{PREFIXE}AFF{i:03d}" not in existants
        ], batch_size=LOT)
        return Affaire.objects.filter(code__startswith=PREFIXE).count()

    @transaction.atomic
    def _ecritures(self, n, today):
        from accounting_kernel.models import AccountMove, AccountMoveLine, FiscalYear, Journal, Period
        from referentiels.models import Account

        debut = today.replace(day=1)
        fin = today.replace(day=calendar.monthrange(today.year, today.month)[1])
        exercice = FiscalYear.objects.filter(start_date__lte=today, end_date__gte=today).first() or \
            FiscalYear.objects.create(year=today.year, start_date=date(today.year, 1, 1), end_date=date(today.year, 12, 31))
        periode = Period.objects.filter(fiscal_year=exercice, start_date__lte=today, end_date__gte=today).first() or \
            Period.objects.create(fiscal_year=exercice, number=today.month, start_date=debut, end_date=fin)
        journal = Journal.objects.filter(code="VOL").first() or \
            Journal.objects.create(code="VOL", label="Volumétrie (perf)", journal_type=Journal.JournalType.OD)
        charge = Account.objects.filter(code__startswith="6").exclude(code__startswith="618").order_by("code").first()
        tiers = Account.objects.filter(code__startswith="4").order_by("code").first()
        if not (charge and tiers):
            self.stdout.write(self.style.WARNING("Plan comptable absent (seed_referentiels) : ecritures ignorees"))
            return 0
        racine = f"{PREFIXE}{today:%Y%m}-"
        deja = AccountMove.objects.filter(journal=journal, number__startswith=racine).count()
        maintenant = timezone.now()
        for depart in range(deja, n, LOT):
            moves = AccountMove.objects.bulk_create([
                AccountMove(journal=journal, period=periode, date=debut.replace(day=1 + i % (fin.day)),
                            number=f"{racine}{i:06d}", label=f"Écriture volumétrique {i}",
                            status=AccountMove.Status.POSTED, source="MANUEL", motif="Jeu volumétrique",
                            posted_at=maintenant)
                for i in range(depart, min(n, depart + LOT))
            ])
            lignes = []
            for m in moves:
                montant = Decimal(1000 + int(m.number[-6:]) * 7919 % 900_000)
                lignes += [AccountMoveLine(move=m, account=charge, debit=montant, credit=0, order=1),
                           AccountMoveLine(move=m, account=tiers, debit=0, credit=montant, order=2)]
            AccountMoveLine.objects.bulk_create(lignes, batch_size=LOT)
        return AccountMove.objects.filter(journal=journal, number__startswith=racine).count()
