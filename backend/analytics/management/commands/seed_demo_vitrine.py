"""Jeu de démonstration « vitrine » : 12 mois glissants d'activité fictive pour présenter l'ERP à la Direction.

À lancer APRÈS `seed_all_demo`, qu'il COMPLÈTE (volontairement absent de `seed_all_demo` : la base E2E n'en dépend
pas). Seules retouches des données du parcours : horodatages ramenés à une date vraisemblable (pièces GED,
signatures, notifications, clôtures), libellés et codes hérités remis au propre (`vitrine.nettoyage`, mêmes règles
que les seeds actuels) ; aucun montant n'est modifié, les statuts ne changent que par les actions de l'API.
Idempotent : chaque objet est repéré par une clé métier stable (code tiers, intitulé d'affaire, libellé de
situation, matricule…) ; une seconde exécution ne crée rien.

Méthode : les chaînes qui touchent la comptabilité ou un statut (affaires, situations, factures, encaissements,
achats, engagements, paie, budgets, clôtures) passent par l'API réelle ou par les services métier (écritures
immuables du noyau comptable, séquences, attestations) ; les données de terrain sans écriture (salariés, pointages,
OT, incidents, contrôles, GED, juridique) sont posées par l'ORM avec les mêmes règles que les seeds par module.
Les horodatages d'audit sont ramenés à la date métier pour que les séries mensuelles aient un historique.

Toutes les valeurs sont des DONNÉES DE DÉMONSTRATION (sociétés, personnes, montants inventés). Sortie ASCII-safe.
Usage : `python manage.py seed_demo_vitrine` (base de démonstration / recette uniquement, jamais la production).
"""

import io
import time

from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from analytics.vitrine.achats import VitrineAchats
from analytics.vitrine.commercial import VitrineCommercial
from analytics.vitrine.finitions import VitrineFinitions
from analytics.vitrine.ged import VitrineGed
from analytics.vitrine.pilotage import VitrinePilotage
from analytics.vitrine.rh import VitrineRH
from analytics.vitrine.terrain import VitrineTerrain
from controle_gestion.management.commands.seed_parcours_d import Command as ParcoursD
from users.models import User


class Command(VitrineCommercial, VitrineAchats, VitrineRH, VitrineTerrain, VitrineGed, VitrinePilotage, VitrineFinitions,
              ParcoursD):
    help = "Jeu de demonstration vitrine : 12 mois d'activite (affaires, achats, paie, terrain, GED, pilotage)."

    def handle(self, *args, **options):
        # Courriels de notification (permis, visas…) retenus en mémoire : le jeu ne doit écrire à personne.
        with override_settings(ALLOWED_HOSTS=["testserver", "localhost"],
                               EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            self._vitrine()

    def user(self, email):
        if not hasattr(self, "_users"):
            self._users = {}
        if email not in self._users:
            self._users[email] = User.objects.get(email=email)
        return self._users[email]

    def etape(self, nom, fonction):
        debut = time.monotonic()
        fonction()
        self.stdout.write(f"  - {nom} : {time.monotonic() - debut:.1f} s")

    def _vitrine(self):
        from users.management.commands.seed_all_demo import _sync_sequences

        _sync_sequences()
        self.clients = {}
        self.today = timezone.localdate()
        # Exercice précédent : les 12 mois glissants débordent sur l'année N-1 (périodes ouvertes, journaux existants).
        call_command("seed_accounting", year=self.today.year - 1, stdout=io.StringIO())
        self.stdout.write(self.style.MIGRATE_HEADING("Jeu vitrine (12 mois glissants)"))
        self.etape("libelles et codes herites", self.nettoyer)
        self.etape("tiers et articles", self.tiers_et_articles)
        self.etape("pipeline commercial", self.pipeline)
        self.etape("affaires, situations, factures, encaissements", self.affaires)
        self.etape("salaries, contrats, qualifications", self.salaries)
        self.etape("pointages et transfert en paie", self.pointages)
        self.etape("achats, receptions, factures fournisseurs", self.achats)
        self.etape("engagements de frais generaux", self.engagements)
        self.etape("paie (bulletins comptabilises)", self.paie)
        self.etape("consommations de stock", self.consommations)
        self.etape("parc et maintenance", self.maintenance)
        self.etape("HSE", self.hse)
        self.etape("qualite", self.qualite)
        self.etape("GED et circuits", self.ged)
        self.etape("juridique", self.juridique)
        self.etape("budgets et ecarts", self.budgets)
        self.etape("clotures de gestion", self.clotures)
        self.etape("cubes BI", self.cubes)
        self.etape("analyses d'ecart", self.analyses_ecart)
        self.etape("dates des pieces GED du chargement", self.dater_ged)
        self.etape("signatures avancees", self.signatures)
        self.etape("relances et escalades des taches en retard", self.relances)
        self.etape("dates des notifications du chargement", self.dater_notifications)
        self.stdout.write(self.style.SUCCESS("Jeu vitrine pret."))
