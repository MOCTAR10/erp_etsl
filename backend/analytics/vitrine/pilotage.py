"""Vitrine — pilotage (M11 / Couche D) : budgets de produits et de charges par affaire (double visa), détection des
écarts, clôtures de gestion mensuelles publiées, cubes OLAP alimentés sur 12 mois (les 3 plus anciens archivés).

Budgets de charges : montant calé sur le réalisé de l'exercice pour illustrer les seuils 90 / 100 / 110 %
(alerte, atteint, dépassé) ; budgets de produits : plan de facturation de l'affaire sur l'exercice.
"""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction

from accounting_kernel.models import FiscalYear, Period
from controle_gestion.models import Budget, BudgetLigne, ClotureGestion

from .outils import MOIS, arrondi, dater_documents, debut_mois, fin_mois, instant

FIN, PDG, ADMIN = "finance@etls.local", "pdg@etls.local", "admin@etls.local"
# Taux de consommation visés des budgets de charges (réalisé / budget) : 2 sous le seuil, puis alerte, atteint, dépassé.
CONSOMMATION = (Decimal("0.74"), Decimal("0.83"), Decimal("0.93"), Decimal("1.04"), Decimal("1.16"))


class VitrinePilotage:
    def budgets(self):
        # Budgets de l'exercice votés en janvier : PV de validation budgétaire datés en conséquence.
        with dater_documents(self.today.replace(month=1, day=20)):
            self._budgets()
        self.call(FIN, "post", "/api/controle-gestion/analyses-ecart/detecter/")

    def _budgets(self):
        from controle_gestion.services import compute_variance

        annee = self.today.year
        fy = FiscalYear.objects.get(year=annee)
        periodes = {p.number: p for p in Period.objects.filter(fiscal_year=fy)}
        affaires = [a for a in self.affaires_vitrine.values() if a.end_date.year >= annee and a.analytic_id]
        for affaire in affaires:
            label = f"Budget produits {annee} - {affaire.code} {affaire.title}"[:250]
            if Budget.objects.filter(label=label).exists():
                continue
            plan = self._plan_facturation(affaire, annee)
            if not plan:
                continue
            with transaction.atomic():
                self._budget(label, "produit", fy, affaire, plan, periodes)
        charges = [a for a in affaires if not a.is_global_rental and a.affaire_type in ("chantier", "atelier", "maintenance")]
        for i, affaire in enumerate(charges[: len(CONSOMMATION)]):
            label = f"Budget charges {annee} - {affaire.code} {affaire.title}"[:250]
            if Budget.objects.filter(label=label).exists():
                continue
            with transaction.atomic():
                # Brouillon provisoire pour mesurer le réalisé par période, puis montants calés avant le double visa.
                plan = {n: Decimal(1) for n in periodes if n <= self.today.month}
                budget = self._budget(label, "charge", fy, affaire, plan, periodes, approuver=False)
                variance = compute_variance(budget)
                realise = variance["totals"]["realise"] or Decimal(0)
                if realise <= 0:
                    self.call(PDG, "post", f"/api/controle-gestion/budgets/{budget.pk}/approuver/", {"visa": "cg"})
                    continue
                cible = realise / CONSOMMATION[i]
                total = Decimal(0)
                lignes = list(budget.lignes.select_related("period").order_by("period__number"))
                for n, ligne in enumerate(lignes):
                    part = Decimal(arrondi(cible / len(lignes))) if n < len(lignes) - 1 else Decimal(arrondi(cible)) - total
                    total += part
                    BudgetLigne.objects.filter(pk=ligne.pk).update(montant=part)
                Budget.objects.filter(pk=budget.pk).update(montant=Decimal(arrondi(cible)))
                self._approuver(budget.pk)

    def _plan_facturation(self, affaire, annee):
        """Montant mensuel prévu (contrat lissé sur la durée) pour les mois de l'exercice couverts par l'affaire."""
        mois = max(1, round((affaire.end_date - affaire.start_date).days / 30.4))
        mensuel = Decimal(arrondi(affaire.contract_amount / mois * Decimal("1.04")))
        plan = {}
        d = affaire.start_date.replace(day=1)
        while d <= affaire.end_date:
            if d.year == annee:
                plan[d.month] = mensuel
            d = fin_mois(d) + timedelta(days=1)
        return plan

    def _budget(self, label, nature, fy, affaire, plan, periodes, approuver=True):
        data = self.call(FIN, "post", "/api/controle-gestion/budgets/", {
            "label": label, "type_budget": nature, "fiscal_year": str(fy.pk), "analytic": str(affaire.analytic_id),
            "montant": str(sum(plan.values())),
        })
        for numero, montant in sorted(plan.items()):
            self.call(FIN, "post", "/api/controle-gestion/budget-lignes/", {
                "budget": data["id"], "period": str(periodes[numero].pk), "montant": str(montant),
            })
        if approuver:
            self._approuver(data["id"])
        return Budget.objects.get(pk=data["id"])

    def _approuver(self, pk):
        # Double visa : DAF (finance) puis contrôle de gestion (une autre personne) ; la version V0 entre en vigueur.
        self.call(FIN, "post", f"/api/controle-gestion/budgets/{pk}/approuver/", {"visa": "daf"})
        self.call(PDG, "post", f"/api/controle-gestion/budgets/{pk}/approuver/", {"visa": "cg"})

    def clotures(self):
        """Clôtures de gestion des mois écoulés, réalisées et publiées le même jour à J+3 / J+4 (« à temps ») ; deux
        mois en retard : publié à J+6 (k = 9) et hors délai à J+8 après la relance J+7 (k = 4).

        Réalisation par l'API ; publication posée à sa date métier (l'API date du jour) avec les mêmes effets que
        l'action `publier` (attestation, notification de la Direction), relance J+6 comprise. Les clôtures déjà en
        base (seed_all_demo, anciens jeux publiés en masse le jour du chargement) sont re-datées de la même façon.
        """
        for k in range(MOIS - 1, 0, -1):
            debut = debut_mois(self.today, k)
            periode = Period.objects.filter(start_date=debut).first()
            if periode is None:
                continue
            realisation, publication = self._calendrier_cloture(periode, k)
            cloture = ClotureGestion.objects.filter(period=periode).first()
            with transaction.atomic(), dater_documents(realisation):
                if cloture is None:
                    pk = self.call(FIN, "post", "/api/controle-gestion/clotures/", {"period": str(periode.pk)})["id"]
                    self.call(ADMIN, "post", f"/api/controle-gestion/clotures/{pk}/realiser/",
                              {"date_cloture": str(realisation)})
                    cloture = ClotureGestion.objects.get(pk=pk)
                elif cloture.statut != ClotureGestion.Statut.REALISEE:
                    self.call(ADMIN, "post", f"/api/controle-gestion/clotures/{cloture.pk}/realiser/",
                              {"date_cloture": str(realisation)})
                    cloture.refresh_from_db()
                self._publier_cloture(cloture, realisation, publication)

    @staticmethod
    def _calendrier_cloture(periode, k):
        fin = periode.end_date
        if k == 9:
            return fin + timedelta(days=5), fin + timedelta(days=6)
        if k == 4:
            return fin + timedelta(days=6), fin + timedelta(days=8)
        jour = fin + timedelta(days=3 + k % 2)
        return jour, jour

    def _publier_cloture(self, cloture, realisation, publication):
        from workflow.models import Notification
        from workflow.notifications import notify

        attendu = {"date_cloture": realisation, "date_publication": publication}
        if all(getattr(cloture, champ) == valeur for champ, valeur in attendu.items()):
            return  # déjà au calendrier : rien à refaire (idempotent)
        if publication - cloture.period.end_date > timedelta(days=6):
            relance = cloture.period.end_date + timedelta(days=7)  # tâche planifiée `suivre_reporting`, le lendemain de J+6
            attendu["alerte_j6_le"] = relance
            sujet = f"Reporting Direction en retard : {cloture.period}"
            if not Notification.objects.filter(subject=sujet).exists():
                for user in self._destinataires(("finance", "dga", "pdg")):
                    n = notify(user, sujet, f"Le reporting de gestion de {cloture.period} n'est pas publié à J+6 "
                                            f"({cloture.echeance_j6:%d/%m/%Y}).", kind="escalation")
                    Notification.objects.filter(pk=n.pk).update(created_at=instant(relance, 8), is_read=True)
        ClotureGestion.objects.filter(pk=cloture.pk).update(
            **attendu, publie_par=cloture.publie_par or self.user(FIN), statut=ClotureGestion.Statut.REALISEE,
            created_at=instant(realisation, 9), updated_at=instant(publication, 17),
        )
        cloture.refresh_from_db()
        sujet = f"Reporting de gestion publié : {cloture.period}"
        message = f"Le reporting de {cloture.period} est publié ({cloture.reporting_statut_libelle})."
        deja = Notification.objects.filter(subject=sujet)
        if deja.exists():
            deja.update(message=message, created_at=instant(publication, 17), is_read=True)
            return
        for user in self._destinataires(("pdg", "dga", "direction")):
            n = notify(user, sujet, message, kind="info")
            Notification.objects.filter(pk=n.pk).update(created_at=instant(publication, 17), is_read=True)

    @staticmethod
    def _destinataires(roles):
        from users.models import User

        return list(User.objects.filter(role__in=roles, is_active=True))

    def cubes(self):
        from analytics import cubes
        from analytics.models import CubeArchive

        for k in range(MOIS - 1, -1, -1):
            periode = debut_mois(self.today, k).strftime("%Y-%m")
            if not CubeArchive.objects.filter(periode=periode).exists():
                cubes.alimenter_cube(periode)
        for k in (MOIS - 1, MOIS - 2, MOIS - 3):  # trimestre le plus ancien : archivé, scellé SHA-256
            periode = debut_mois(self.today, k).strftime("%Y-%m")
            if not CubeArchive.objects.filter(periode=periode).exists():
                with dater_documents(fin_mois(debut_mois(self.today, k - 1)).replace(day=10)):
                    cubes.archiver_cube(periode, self.user(ADMIN))
