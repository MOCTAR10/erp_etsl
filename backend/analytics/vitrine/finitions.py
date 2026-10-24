"""Vitrine — finitions de vraisemblance : ce qu'une entreprise qui utilise l'ERP depuis un an a forcément en base.

- Relances et escalades des tâches de circuit en retard (constat A-05), produites par les fonctions de la tâche
  planifiée `workflow.tasks.check_overdue_tasks` et datées du lendemain de l'échéance : l'écran Notifications reflète
  les retards affichés à l'accueil ; les plus anciennes sont lues.
- Signatures avancées (A-22) : une par mois sur 11 mois (bons de commande signés par le PDG, sceau chaîné recalculé
  sur l'horodatage métier), trois demandes « à signer » en cours, horodatages des signatures du parcours étalés.
- Pièces GED déposées le jour du chargement par les seeds (horodatage technique identique) : datées de leur date
  métier, sinon réparties sur les six dernières semaines ouvrées.
- Remise au propre des libellés hérités (`nettoyage`) et des circuits (acteur « chef comptable » = Finance).
"""

import hashlib
import io
from datetime import date, timedelta
from datetime import timezone as dt_timezone

from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from documents.models import Document, SignatureRequest, Signer, Version
from users.models import User
from workflow.models import Notification, Task

from .nettoyage import tout_nettoyer
from .outils import MOIS, ajouter_mois, debut_mois, instant, ouvre

# Demandes de signature en cours : (type GED du document, titre de la demande, signataires, émetteur, jours écoulés)
A_SIGNER = (
    ("devis_bons_de_commande", "Commande d'approvisionnement chantier — visa Direction", ("admin@etls.local",),
     "finance@etls.local", 2),
    ("documents_techniques_plans", "Plans d'exécution et nomenclature — validation Direction",
     ("admin@etls.local", "pdg@etls.local"), "projets@etls.local", 1),
    ("courriers", "Réponse à l'ordre de service client — signature du PDG", ("pdg@etls.local",),
     "secretariat@etls.local", 3),
)
SIGNES_DU_MOIS = "devis_bons_de_commande"  # une signature PDG par mois sur ce type (historique)


def _heure(cle, debut=8, fin=17):
    """Heure et minute déterministes (« 10:37 ») : jamais deux horodatages identiques à la seconde près."""
    h = int(hashlib.sha256(str(cle).encode()).hexdigest()[:8], 16)
    return timedelta(hours=debut + h % (fin - debut), minutes=(h // 97) % 60)


class VitrineFinitions:
    def nettoyer(self):
        bilan = tout_nettoyer()
        call_command("seed_workflow", stdout=io.StringIO())
        self._reassigner_etapes_finance()
        if any(bilan.values()):
            self.stdout.write("    " + ", ".join(f"{k} {v}" for k, v in bilan.items() if v))

    def _reassigner_etapes_finance(self):
        """Tâches en attente encore assignées à l'administrateur technique sur une étape désormais tenue par Finance."""
        from workflow.services import _find_assignee

        for tache in Task.objects.filter(status=Task.Status.PENDING, assigned_to__role=User.Role.ADMIN).exclude(
            step__actor_role=User.Role.ADMIN
        ).select_related("step"):
            titulaire = _find_assignee(tache.step.actor_role)
            if titulaire is not None:
                Task.objects.filter(pk=tache.pk).update(assigned_to=titulaire)

    # -- analyses d'écart budgétaire ----------------------------------------------------------------------------
    def analyses_ecart(self):
        """Écarts > 10 % : détectés le lendemain de la fin de période (tâche de nuit), pas le jour du chargement ;
        ceux de plus de six semaines sont analysés par le contrôle de gestion dans les cinq jours (hors parcours,
        laissé à analyser pour la démonstration) ; notifications re-datées et rédigées au format courant."""
        from controle_gestion.models import AnalyseEcart
        from controle_gestion.services import message_ecart

        maintenant = timezone.now()
        for analyse in AnalyseEcart.objects.select_related("budget", "period"):
            fin = analyse.period.end_date
            detection = fin + timedelta(days=1)
            ancien_sujet = Notification.objects.filter(subject__startswith="Écart budgétaire ",
                                                       message__contains=f"({analyse.code}).")
            if analyse.detecte_le != detection:
                AnalyseEcart.objects.filter(pk=analyse.pk).update(
                    detecte_le=detection, echeance=detection + timedelta(days=AnalyseEcart.DELAI_JOURS),
                    created_at=instant(detection, 6) + _heure(analyse.pk, 0, 1),
                )
                analyse.refresh_from_db()
            sujet, message = message_ecart(analyse, str(analyse.period))
            quand = instant(detection, 6) + _heure(analyse.pk, 0, 1)
            ancien_sujet.update(subject=sujet, message=message, created_at=quand,
                                is_read=quand < maintenant - timedelta(days=5))
            parcours = "Parcours demo" in analyse.budget.label
            if analyse.statut != AnalyseEcart.Statut.A_ANALYSER or parcours or fin >= self.today - timedelta(days=45):
                continue
            hausse = analyse.ecart_pct > 0
            self.call("finance@etls.local", "post", f"/api/controle-gestion/analyses-ecart/{analyse.pk}/analyser/", {
                "analyse": "Consommation supérieure au prévisionnel : approvisionnements avancés sur le planning."
                if hausse else "Facturation décalée par rapport au plan : avancement validé par le client le mois suivant.",
                "actions": "Recaler le budget mensuel sur le planning d'exécution révisé." if hausse
                else "Relancer la validation des situations de travaux avant la clôture du mois.",
            })
            AnalyseEcart.objects.filter(pk=analyse.pk).update(
                analyse_le=instant(detection + timedelta(days=2 + analyse.pk.int % 3), 10) + _heure(analyse.pk, 0, 6),
            )

    # -- relances et escalades ------------------------------------------------------------------------------
    def relances(self):
        from workflow.notifications import escalate_task, remind_assignee

        maintenant = timezone.now()
        admins = list(User.objects.filter(role=User.Role.ADMIN, is_active=True))
        taches = Task.objects.filter(due_date__lt=maintenant, assigned_to__isnull=False).select_related(
            "document", "step", "circuit", "assigned_to"
        )
        with transaction.atomic():
            for tache in taches:
                traitee = tache.status != Task.Status.PENDING
                fin = tache.completed_at if traitee else maintenant
                if fin is None or fin <= tache.due_date:
                    continue  # traitée dans le délai : aucune relance
                relance = self._prochain_matin(tache.due_date, fin)
                if relance and not Notification.objects.filter(task=tache, kind="reminder").exists():
                    self._dater(remind_assignee(tache), relance, lue=traitee or relance < maintenant - timedelta(days=5))
                escalade = tache.due_date + timedelta(days=tache.step.max_days or 1)
                if fin >= escalade and not Notification.objects.filter(task=tache, kind="escalation").exists():
                    quand = self._prochain_matin(escalade, fin) or escalade
                    for admin in admins:
                        self._dater(escalate_task(tache, admin), quand, lue=traitee or quand < maintenant - timedelta(days=3))

    @staticmethod
    def _prochain_matin(apres, avant):
        """Passage de la tâche planifiée : le lendemain 7 h, ou une heure après l'échéance si le délai est court."""
        local = timezone.localtime(apres)
        quand = instant(local.date() + timedelta(days=1), 7) + timedelta(minutes=local.minute % 50 + 3)
        if quand >= avant:
            quand = apres + timedelta(hours=1)
        return quand if quand < avant else None

    @staticmethod
    def _dater(notification, quand, lue):
        Notification.objects.filter(pk=notification.pk).update(created_at=quand, is_read=lue)

    def dater_notifications(self):
        """Notifications restées à l'horodatage du chargement (visas de permis, alertes…) : datées de l'échéance de
        leur tâche, sinon du mois qu'elles citent, sinon réparties sur les trois dernières semaines ; lues au-delà
        de cinq jours."""
        import re

        maintenant = timezone.now()
        for n in Notification.objects.filter(created_at__gte=maintenant - timedelta(days=10)).select_related("task"):
            if n.created_at.second == 0 and n.created_at.microsecond == 0:
                continue  # déjà datée
            mois = re.search(r"(20\d\d)-(0[1-9]|1[0-2])", n.subject)
            if n.task_id and n.task.due_date < maintenant:
                quand = n.task.due_date + timedelta(hours=1)
            elif mois:
                fin = ajouter_mois(date(int(mois[1]), int(mois[2]), 1), 1)
                quand = instant(min(fin, self.today - timedelta(days=1)), 7)
            else:
                h = int(hashlib.sha256(str(n.pk).encode()).hexdigest()[:8], 16)
                quand = instant(ouvre(self.today - timedelta(days=h % 21)), 0)
            quand = (quand.replace(hour=7) if quand.hour < 7 else quand) + _heure(n.pk, 0, 9)
            if quand >= maintenant:
                quand = maintenant - _heure(n.pk, 1, 5)
            Notification.objects.filter(pk=n.pk).update(
                created_at=quand.replace(second=0, microsecond=0), is_read=n.is_read or quand < maintenant - timedelta(days=5),
            )

    # -- signatures avancées -----------------------------------------------------------------------------------
    def signatures(self):
        with transaction.atomic():
            self._signatures_historiques()
            self._signatures_en_cours()
            self._dater_signatures_parcours()

    def _documents(self, code_type):
        return Document.objects.filter(type__code=code_type, current_version__isnull=False).select_related(
            "current_version"
        ).order_by("document_date", "title")

    def _signatures_historiques(self):
        from documents.signatures import compute_seal

        pdg, finance = self.user("pdg@etls.local"), self.user("finance@etls.local")
        documents = list(self._documents(SIGNES_DU_MOIS))
        for k in range(MOIS - 1, 0, -1):
            mois = debut_mois(self.today, k)
            doc = next((d for d in documents if d.document_date and (d.document_date.year, d.document_date.month)
                        == (mois.year, mois.month)), None)
            if doc is None or SignatureRequest.objects.filter(version=doc.current_version).exists():
                continue
            version = doc.current_version
            demande = instant(doc.document_date, 9) + _heure(f"sig-{doc.pk}", 0, 2)
            # En UTC, comme `timezone.now()` à la signature réelle : la preuve scellée est relue telle quelle en base.
            signe = (demande + timedelta(days=1) + _heure(f"sig2-{doc.pk}", 0, 6)).astimezone(dt_timezone.utc)
            if signe >= timezone.now():
                continue
            req = SignatureRequest.objects.create(
                version=version, title=f"Bon de commande — {doc.counterparty}", created_by=finance,
                document_sha256=version.sha256, status=SignatureRequest.Status.COMPLETED,
                expires_at=demande + timedelta(days=14), completed_at=signe,
            )
            signataire = Signer(request=req, user=pdg, order=1, status=Signer.Status.SIGNED, signed_at=signe,
                                ip_address="10.20.1.15", user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                                document_sha256=version.sha256, methode="totp")
            signataire.seal = compute_seal(signataire, "")
            signataire.save()
            SignatureRequest.objects.filter(pk=req.pk).update(created_at=demande)

    def _signatures_en_cours(self):
        from documents.signatures import create_request

        maintenant = timezone.now()
        for code_type, titre, signataires, emetteur, jours in A_SIGNER:
            if SignatureRequest.objects.filter(title=titre).exists():
                continue
            doc = self._documents(code_type).filter(document_date__lt=self.today).last()
            if doc is None:
                continue
            req = create_request(doc.current_version, [self.user(e) for e in signataires], self.user(emetteur),
                                 title=titre, message="Merci de signer avant la fin de semaine.")
            depose = instant(ouvre(self.today - timedelta(days=jours)), 8) + _heure(titre, 0, 8)
            if depose >= maintenant:
                depose = maintenant - timedelta(hours=jours * 5)
            SignatureRequest.objects.filter(pk=req.pk).update(created_at=depose, expires_at=depose + timedelta(days=14))

    def _dater_signatures_parcours(self):
        """Signatures du parcours (posées toutes ensemble au chargement) : quelques heures après le dépôt de leur
        document (daté par `dater_ged`, joué avant), signées dans la journée."""
        maintenant = timezone.now()
        recentes = SignatureRequest.objects.filter(
            status=SignatureRequest.Status.COMPLETED, signers__isnull=True, created_at__gte=maintenant - timedelta(days=10),
        ).select_related("version__document")
        for req in recentes:
            if req.created_at.second == 0 and req.created_at.microsecond == 0:
                continue  # déjà datée
            demande = req.version.document.created_at + _heure(f"parcours-{req.pk}", 1, 4)
            fin = demande + _heure(f"fin-{req.pk}", 2, 7)
            if fin >= maintenant:
                demande, fin = maintenant - timedelta(hours=6), maintenant - timedelta(hours=2)
            SignatureRequest.objects.filter(pk=req.pk).update(
                created_at=demande.replace(second=0, microsecond=0), completed_at=fin,
                title=req.title or req.version.document.title,
            )

    # -- GED : pièces déposées au chargement ------------------------------------------------------------------
    def dater_ged(self):
        """Pièces des seeds horodatées au chargement (à la microseconde) : date métier ou six dernières semaines."""
        recents = Document.objects.filter(created_at__gte=timezone.now() - timedelta(days=10))
        for doc in recents.only("pk", "created_at", "document_date", "archived_at", "submitted_at"):
            if doc.created_at.second == 0 and doc.created_at.microsecond == 0:
                continue  # déjà datée par le jeu vitrine
            if doc.document_date and doc.document_date < self.today:
                jour = doc.document_date
            else:
                h = int(hashlib.sha256(str(doc.pk).encode()).hexdigest()[:8], 16)
                jour = ouvre(self.today - timedelta(days=1 + h % 42))
            quand = instant(jour, 0) + _heure(doc.pk)
            champs = {"created_at": quand}
            if doc.archived_at:
                champs["archived_at"] = quand + timedelta(hours=1)
            if doc.submitted_at:
                champs["submitted_at"] = quand + timedelta(minutes=20)
            Document.objects.filter(pk=doc.pk).update(**champs)
            Version.objects.filter(document_id=doc.pk, created_at__gte=timezone.now() - timedelta(days=10)).update(
                created_at=quand
            )
        # Pièces posées au même instant (lots d'un même jour, anciens chargements) : espacées de quelques minutes,
        # jusqu'à ce qu'aucun horodatage ne soit partagé.
        from django.db.models import Count

        for _ in range(30):
            groupes = list(Document.objects.values("created_at").annotate(n=Count("id")).filter(n__gt=1))
            if not groupes:
                break
            for groupe in groupes:
                pks = Document.objects.filter(created_at=groupe["created_at"]).order_by("title").values_list("pk", flat=True)
                for i, pk in enumerate(list(pks)[1:], start=1):
                    Document.objects.filter(pk=pk).update(created_at=groupe["created_at"] + timedelta(minutes=5 * i + 1))
