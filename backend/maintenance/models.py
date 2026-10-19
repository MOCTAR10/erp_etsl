"""Module M8 — Maintenance & GMAO : parc machines & équipements (RF-ERP-70…73).

Procédure MANUEL 5.9 (maintenance et inspection des équipements) : parc machines,
outils, engins, postes de soudage, appareils de levage, équipements d'atelier et
de chantier. RF-ERP-70 : parc interne ETSL · RF-ERP-71 : ordres de travail correctif /
préventif · RF-ERP-72 : inspections périodiques + compteurs GLOBAL RENTAL en
**lecture seule** (via logistique) · RF-ERP-73 : historique & cost tracking.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class MaintenanceSequence(models.Model):
    """Numérotation séquentielle par type (EQ, OT, INS)."""

    kind = models.CharField(max_length=10, unique=True, verbose_name="Type")
    prefix = models.CharField(max_length=10, verbose_name="Préfixe")
    padding = models.PositiveSmallIntegerField(default=5, verbose_name="Zéro-padding")
    next_number = models.PositiveIntegerField(default=1, verbose_name="Prochain numéro")

    class Meta:
        verbose_name = "Séquence Maintenance"
        verbose_name_plural = "Séquences Maintenance"

    def __str__(self):
        return f"{self.kind} → {self.prefix}{self.next_number:0{self.padding}d}"

    @classmethod
    def next_for(cls, kind, prefix):
        seq, _ = cls.objects.get_or_create(
            kind=kind, defaults={"prefix": prefix, "padding": 5}
        )
        with transaction.atomic():
            seq = cls.objects.select_for_update().get(pk=seq.pk)
            number = f"{seq.prefix}{str(seq.next_number).zfill(seq.padding)}"
            seq.next_number += 1
            seq.save(update_fields=["next_number"])
        return number


class Actif(models.Model):
    """Parcc machines & équipements ETSL — machines, engins, levage, atelier (RF-ERP-70)."""

    class Categorie(models.TextChoices):
        MACHINE = "machine", "Machine / poste de soudage"
        ENGIN = "engin", "Engin / engin de chantier"
        LEVAGE = "levage", "Appareil de levage"
        ATELIER = "atelier", "Équipement d'atelier"
        CHANTIER = "chantier", "Équipement de chantier"
        OUTILLAGE = "outillage", "Outillage"

    class Statut(models.TextChoices):
        OPERATIONNEL = "operationnel", "Opérationnel"
        EN_MAINTENANCE = "en_maintenance", "En maintenance"
        EN_PANNE = "en_panne", "En panne"
        HORS_SERVICE = "hors_service", "Hors service"
        REFORME = "reforme", "Réformé"

    class Compteur(models.TextChoices):
        HEURES = "heures", "Heures moteur"
        KM = "km", "Kilomètres"
        AUCUN = "aucun", "Sans compteur"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    designation = models.CharField(max_length=200, verbose_name="Désignation")
    categorie = models.CharField(
        max_length=10, choices=Categorie.choices, default=Categorie.MACHINE,
        verbose_name="Catégorie",
    )
    fabricant = models.CharField(max_length=120, blank=True, verbose_name="Fabricant")
    modele = models.CharField(max_length=120, blank=True, verbose_name="Modèle")
    numero_serie = models.CharField(
        max_length=100, blank=True, verbose_name="N° de série"
    )
    site = models.CharField(max_length=120, blank=True, verbose_name="Site / dépôt")
    statut = models.CharField(
        max_length=14, choices=Statut.choices, default=Statut.OPERATIONNEL,
        verbose_name="Statut",
    )
    date_mise_en_service = models.DateField(
        null=True, blank=True, verbose_name="Mise en service"
    )
    garanti_jusqu = models.DateField(null=True, blank=True, verbose_name="Garantie jusqu'au")
    compteur_type = models.CharField(
        max_length=7, choices=Compteur.choices, default=Compteur.HEURES,
        verbose_name="Type de compteur",
    )
    compteur_value = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Valeur compteur"
    )
    is_global_rental = models.BooleanField(
        default=False, verbose_name="Équipement GLOBAL RENTAL (GR)"
    )
    equipement_gr = models.ForeignKey(
        "logistique.EquipementParc",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_actifs",
        verbose_name="Équipement GLOBAL RENTAL lié",
        help_text="Compteur lu en lecture seule depuis la logistique (RF-ERP-72).",
    )
    signe_618 = models.BooleanField(
        default=False,
        verbose_name="Refacturation compte 618",
        help_text="Coût/Gain GR isolé au compte 618 (SYSCOHADA).",
    )
    notes = models.TextField(blank=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Actif (machine / équipement)"
        verbose_name_plural = "Actifs — parc machines & équipements"
        indexes = [models.Index(fields=["statut", "categorie"])]

    def __str__(self):
        return f"{self.code} — {self.designation} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = MaintenanceSequence.next_for("EQ", "EQ")
        return super().save(*args, **kwargs)

    def clean(self):
        if self.is_global_rental and not self.equipement_gr:
            raise ValidationError(
                {"equipement_gr": "Un actif GLOBAL RENTAL doit référencer l'équipement lié."}
            )
        if self.equipement_gr and not self.is_global_rental:
            self.is_global_rental = True

    @property
    def compteur_lecture(self):
        """Compteur lu : lecture seule depuis la logistique pour un équipement GR."""
        if self.is_global_rental and self.equipement_gr:
            return self.equipement_gr.compteur_value
        return self.compteur_value

    @property
    def en_arret(self):
        return self.statut in (
            self.Statut.EN_MAINTENANCE,
            self.Statut.EN_PANNE,
        )


class OrdreTravail(models.Model):
    """Ordre de travail de maintenance — correctif / préventif / inspection (RF-ERP-71)."""

    class TypeOT(models.TextChoices):
        CORRECTIF = "correctif", "Correctif"
        PREVENTIF = "preventif", "Préventif"
        URGENCE = "urgence", "Urgence / dépannage"
        INSPECTION = "inspection", "Inspection"

    class Priorite(models.TextChoices):
        BASSE = "basse", "Basse"
        MOYENNE = "moyenne", "Moyenne"
        HAUTE = "haute", "Haute"
        CRITIQUE = "critique", "Critique"

    class Statut(models.TextChoices):
        DEMANDE = "demande", "Demandé"
        PLANIFIE = "planifie", "Planifié"
        EN_COURS = "en_cours", "En cours"
        TERMINE = "termine", "Terminé"
        CLOTURE = "cloture", "Clôturé"
        ARCHIVE = "archive", "Archivé"
        ANNULE = "annule", "Annulé"

    # Statuts terminaux : l'OT n'est plus « ouvert » ; clôturé / archivé = pièce scellée (lot 14, CDC M8 §13.4).
    STATUTS_CLOS = ("cloture", "archive", "annule")
    STATUTS_SCELLES = ("cloture", "archive")

    class Decision(models.TextChoices):
        REPARATION = "reparation", "Réparation lourde"
        MISE_HORS_SERVICE = "mise_hors_service", "Mise hors service"
        REFORME = "reforme", "Réforme"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    actif = models.ForeignKey(
        Actif,
        on_delete=models.PROTECT,
        related_name="ordres_travail",
        verbose_name="Équipement",
    )
    type_ot = models.CharField(
        max_length=11, choices=TypeOT.choices, default=TypeOT.CORRECTIF,
        verbose_name="Type",
    )
    priorite = models.CharField(
        max_length=10, choices=Priorite.choices, default=Priorite.MOYENNE,
        verbose_name="Priorité",
    )
    description = models.TextField(verbose_name="Description de l'intervention")
    cause = models.TextField(blank=True, verbose_name="Cause / diagnostic")
    demandeur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_ot_demandes",
        verbose_name="Demandeur",
    )
    technicien = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_ot_interventions",
        verbose_name="Technicien",
    )
    date_demande = models.DateField(default=timezone.localdate, verbose_name="Date de demande")
    date_planifiee = models.DateField(null=True, blank=True, verbose_name="Date planifiée")
    date_debut = models.DateTimeField(null=True, blank=True, verbose_name="Début d'intervention")
    date_fin = models.DateTimeField(null=True, blank=True, verbose_name="Fin d'intervention")
    heures_mo = models.DecimalField(
        max_digits=8, decimal_places=2, default=0, verbose_name="Heures main-d'œuvre"
    )
    tarif_horaire = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name="Tarif horaire (FCFA)"
    )
    cout_pieces = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Coût pièces (FCFA)"
    )
    decision = models.CharField(
        max_length=18, choices=Decision.choices, blank=True, verbose_name="Décision"
    )
    rapport = models.TextField(blank=True, verbose_name="Rapport d'intervention")
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.DEMANDE,
        verbose_name="Statut",
    )
    plan = models.ForeignKey(
        "PlanPreventif",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ordres",
        verbose_name="Plan préventif d'origine",
    )
    archive_le = models.DateTimeField(null=True, blank=True, verbose_name="Archivé le")
    archive_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_ot_archives",
        verbose_name="Archivé par",
    )
    qualifie_le = models.DateTimeField(null=True, blank=True, verbose_name="Qualifié le")
    qualifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_ot_qualifies",
        verbose_name="Qualifié par",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_ot_crees",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Traçabilité du workflow (CDC M8 §13.5) : statut lu en base, auteur et commentaire de la transition en cours.
    _statut_initial = None
    _acteur = None
    _commentaire_statut = ""

    class Meta:
        ordering = ["-date_demande", "-created_at"]
        verbose_name = "Ordre de travail (OT)"
        verbose_name_plural = "Ordres de travail — GMAO"
        indexes = [models.Index(fields=["type_ot", "statut"])]

    def __str__(self):
        return f"{self.code} — {self.actif.code} ({self.get_statut_display()})"

    @classmethod
    def from_db(cls, db, field_names, values):
        obj = super().from_db(db, field_names, values)
        obj._statut_initial = obj.__dict__.get("statut")
        return obj

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = MaintenanceSequence.next_for("OT", "OT")
        creation = self._state.adding
        ancien = None if creation else self._statut_initial
        result = super().save(*args, **kwargs)
        # Chaque changement de statut (création comprise) est tracé, quel que soit le chemin (action, seed, plan).
        if creation or ancien != self.statut:
            HistoriqueStatutOT.objects.create(
                ot=self, de=ancien or "", vers=self.statut,
                par=self._acteur or (self.created_by if creation else None),
                commentaire=self._commentaire_statut[:255],
            )
            self._statut_initial = self.statut
            self._commentaire_statut = ""
        return result

    @property
    def cout_main_oeuvre(self):
        return self.heures_mo * self.tarif_horaire

    @property
    def cout_total(self):
        return self.cout_main_oeuvre + self.cout_pieces


class HistoriqueStatutOT(models.Model):
    """Trace horodatée et inaltérable du cycle d'un OT : création, transitions, qualification (CDC M8 §13.5)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ot = models.ForeignKey(
        OrdreTravail, on_delete=models.CASCADE, related_name="historique", verbose_name="OT"
    )
    de = models.CharField(max_length=10, blank=True, verbose_name="Statut de départ")
    vers = models.CharField(max_length=10, verbose_name="Statut d'arrivée")
    par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Par",
    )
    le = models.DateTimeField(default=timezone.now, verbose_name="Le")
    commentaire = models.CharField(max_length=255, blank=True, verbose_name="Commentaire")

    class Meta:
        ordering = ["le"]
        verbose_name = "Historique de statut d'OT"
        verbose_name_plural = "Historique des statuts d'OT"

    def __str__(self):
        return f"{self.ot_id} {self.de or '∅'} → {self.vers}"


class PlanPreventif(models.Model):
    """Plan de maintenance préventive par machine / composant (lot 14, CDC M8 §13.4 / §13.11).

    Déclencheur calendaire (périodicité en jours) et / ou compteur (intervalle d'heures ou de km) : à
    l'échéance, un OT préventif est généré automatiquement (`maintenance.preventif.declencher_plans`).
    La clôture de l'OT réarme le plan (dernière date / dernier compteur).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    actif = models.ForeignKey(
        Actif,
        on_delete=models.PROTECT,
        related_name="plans_preventifs",
        verbose_name="Équipement",
    )
    libelle = models.CharField(max_length=200, verbose_name="Intervention préventive")
    composant = models.CharField(max_length=120, blank=True, verbose_name="Composant")
    periodicite_jours = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="Périodicité (jours)"
    )
    intervalle_compteur = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        verbose_name="Intervalle compteur (h / km)",
    )
    derniere_date = models.DateField(default=timezone.localdate, verbose_name="Dernière exécution")
    dernier_compteur = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Compteur à la dernière exécution"
    )
    priorite = models.CharField(
        max_length=10, choices=OrdreTravail.Priorite.choices, default=OrdreTravail.Priorite.MOYENNE,
        verbose_name="Priorité de l'OT généré",
    )
    en_vigueur = models.BooleanField(default=True, verbose_name="En vigueur")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_plans_crees",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["actif__code", "libelle"]
        verbose_name = "Plan préventif"
        verbose_name_plural = "Plans préventifs"

    def __str__(self):
        return f"{self.code} — {self.actif.code} — {self.libelle}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = MaintenanceSequence.next_for("PP", "PP")
        return super().save(*args, **kwargs)

    def clean(self):
        if not self.periodicite_jours and self.intervalle_compteur is None:
            raise ValidationError(
                "Un plan préventif exige une périodicité calendaire et / ou un intervalle compteur."
            )
        if self.periodicite_jours == 0:
            raise ValidationError({"periodicite_jours": "La périodicité doit être d'au moins 1 jour."})
        if self.intervalle_compteur is not None:
            if self.intervalle_compteur <= 0:
                raise ValidationError({"intervalle_compteur": "L'intervalle doit être strictement positif."})
            if self.actif_id and self.actif.compteur_type == Actif.Compteur.AUCUN:
                raise ValidationError({"intervalle_compteur": "Cet équipement n'a pas de compteur."})

    @property
    def prochaine_date(self):
        if not self.periodicite_jours:
            return None
        return self.derniere_date + timedelta(days=self.periodicite_jours)

    @property
    def prochain_compteur(self):
        if self.intervalle_compteur is None:
            return None
        return self.dernier_compteur + self.intervalle_compteur

    def motif_echeance(self, today=None):
        """Raison de l'échéance (texte) ou None si le plan n'est pas échu."""
        today = today or timezone.localdate()
        if self.prochain_compteur is not None and self.actif.compteur_lecture >= self.prochain_compteur:
            return (
                f"seuil compteur atteint ({self.actif.compteur_lecture} ≥ {self.prochain_compteur} "
                f"{self.actif.get_compteur_type_display().lower()})"
            )
        if self.prochaine_date is not None and today >= self.prochaine_date:
            return f"échéance calendaire du {self.prochaine_date:%d/%m/%Y}"
        return None

    def motif_prealerte(self, today=None, jours=7, pct=10):
        """Échéance proche (fenêtre paramétrable) ou None ; un plan déjà échu relève de `motif_echeance`."""
        today = today or timezone.localdate()
        if self.motif_echeance(today):
            return None
        if self.prochain_compteur is not None and self.intervalle_compteur:
            reste = self.prochain_compteur - self.actif.compteur_lecture
            if reste <= self.intervalle_compteur * Decimal(pct) / 100:
                return f"seuil compteur proche (reste {reste} {self.actif.get_compteur_type_display().lower()})"
        if self.prochaine_date is not None and (self.prochaine_date - today).days <= jours:
            return f"échéance calendaire le {self.prochaine_date:%d/%m/%Y}"
        return None


class Inspection(models.Model):
    """Inspection périodique des équipements — 5.9.5 (RF-ERP-72)."""

    class TypeInspection(models.TextChoices):
        VISUELLE = "visuelle", "Visuelle"
        FONCTIONNELLE = "fonctionnelle", "Fonctionnelle"
        SECURITE = "securite", "Sécurité"
        LEVAGE = "levage", "Appareil de levage"
        ATEX = "atex", "ATEX"
        METROLOGIE = "metrologie", "Métrologie / étalonnage"

    class Resultat(models.TextChoices):
        CONFORME = "conforme", "Conforme"
        SOUS_RESERVE = "sous_reserve", "Sous réserve"
        NON_CONFORME = "non_conforme", "Non conforme"

    class Statut(models.TextChoices):
        PLANIFIEE = "planifiee", "Planifiée"
        REALISEE = "realisee", "Réalisée"
        ANNULEE = "annulee", "Annulée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    actif = models.ForeignKey(
        Actif,
        on_delete=models.PROTECT,
        related_name="inspections",
        verbose_name="Équipement",
    )
    type_inspection = models.CharField(
        max_length=14, choices=TypeInspection.choices, default=TypeInspection.VISUELLE,
        verbose_name="Type",
    )
    date_inspection = models.DateField(verbose_name="Date d'inspection")
    prochaine_inspection = models.DateField(null=True, blank=True, verbose_name="Prochaine inspection")
    organisme = models.CharField(max_length=60, default="interne", verbose_name="Organisme")
    organisme_libelle = models.CharField(max_length=120, blank=True, verbose_name="Organisme (libellé)")
    resultat = models.CharField(
        max_length=14, choices=Resultat.choices, blank=True, verbose_name="Résultat"
    )
    constat = models.TextField(blank=True, verbose_name="Constat / observations")
    intervenant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_inspections",
        verbose_name="Inspécteur",
    )
    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.PLANIFIEE,
        verbose_name="Statut",
    )
    ot_genere = models.ForeignKey(
        OrdreTravail,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inspections_source",
        verbose_name="OT généré",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_inspection"]
        verbose_name = "Inspection périodique"
        verbose_name_plural = "Inspections périodiques"
        indexes = [models.Index(fields=["type_inspection", "statut"])]

    def __str__(self):
        return f"{self.code} — {self.actif.code} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = MaintenanceSequence.next_for("INS", "INS")
        return super().save(*args, **kwargs)

    def clean(self):
        if self.prochaine_inspection and self.prochaine_inspection < self.date_inspection:
            raise ValidationError(
                {"prochaine_inspection": "La prochaine inspection doit être postérieure à l'inspection."}
            )

class ParametreMaintenance(models.Model):
    """Paramètre M8 modifiable par ETSL sans développeur (période d'observation, heures de service par jour).

    Tant que `statut_valeur` = « provisoire », les écrans et états de fiabilité (MTBF / MTTR / disponibilité)
    avertissent. Le défaut est créé à la volée par `services.get_param_maintenance` (donnée, jamais figée en code).
    """

    class StatutValeur(models.TextChoices):
        PROVISOIRE = "provisoire", "Provisoire"
        CONFIRME = "confirme", "Confirmé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=40, unique=True, verbose_name="Identifiant")
    label = models.CharField(max_length=200, verbose_name="Libellé")
    valeur = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Valeur")
    unite = models.CharField(max_length=20, blank=True, verbose_name="Unité")
    statut_valeur = models.CharField(
        max_length=10, choices=StatutValeur.choices, default=StatutValeur.PROVISOIRE,
        verbose_name="Statut de la valeur",
    )
    confirme_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Confirmé par",
    )
    confirme_le = models.DateTimeField(null=True, blank=True, verbose_name="Confirmé le")

    class Meta:
        ordering = ["code"]
        verbose_name = "Paramètre maintenance"
        verbose_name_plural = "Paramètres maintenance"

    def __str__(self):
        return f"{self.code} = {self.valeur} {self.unite}"

    @property
    def est_provisoire(self):
        return self.statut_valeur != self.StatutValeur.CONFIRME


class PieceOT(models.Model):
    """Pièce de rechange sortie du stock M5 pour un OT (clôture M8) : mouvement de consommation valorisé au CUMP.

    Créée uniquement par l'action `sortir-piece` de l'OT (jamais à la main) ; le coût de l'OT en découle.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ot = models.ForeignKey(OrdreTravail, on_delete=models.PROTECT, related_name="pieces", verbose_name="OT")
    article = models.ForeignKey(
        "referentiels.Article", on_delete=models.PROTECT, related_name="+", verbose_name="Pièce"
    )
    depot = models.ForeignKey("stocks.Depot", on_delete=models.PROTECT, related_name="+", verbose_name="Dépôt")
    quantite = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Quantité")
    cout_unitaire = models.DecimalField(
        max_digits=16, decimal_places=4, verbose_name="Coût unitaire (CUMP à la sortie)"
    )
    mouvement = models.OneToOneField(
        "stocks.MouvementStock", on_delete=models.PROTECT, related_name="piece_ot", verbose_name="Mouvement de stock"
    )
    sorti_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Sorti par",
    )
    sorti_le = models.DateTimeField(default=timezone.now, verbose_name="Sorti le")

    class Meta:
        ordering = ["sorti_le"]
        verbose_name = "Pièce de rechange d'OT"
        verbose_name_plural = "Pièces de rechange d'OT"

    def __str__(self):
        return f"{self.ot.code} — {self.article.code} × {self.quantite}"

    @property
    def cout_total(self):
        return self.quantite * self.cout_unitaire
