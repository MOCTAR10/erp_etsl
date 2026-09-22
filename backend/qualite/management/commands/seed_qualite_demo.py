"""Jeu de données de démonstration M6 — Qualité & Soudage (idempotent).

⚠️ ASCII-safe pour la console Windows (cp1252) : pas de →, — , é multiples
dans les stdout.write (UnicodeEncodeError). Lancer avec `python -X utf8`
ou rester sur des messages ASCII.
"""

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from commercial.models import Affaire
from operations.models import OrdreFabrication
from qualite.models import (
    ActionCorrective,
    ControleQualite,
    NonConformite,
    PvControle,
    QualificationSoudeur,
    Soudeur,
    WpsWpqr,
)
from stocks.models import LotMatiere
from users.models import User


class Command(BaseCommand):
    help = "Seed demo M6 (qualite) : soudeurs, qualifications, WPS, controles, NC, CAPA, PV."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seed M6 - Qualite & Soudage (demo)")

        qaqc = User.objects.filter(role=User.Role.QAQC).first()
        if qaqc is None:
            qaqc = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if qaqc is None:
            self.stdout.write("Aucun utilisateur QAQC - seed interrompu.")
            return

        if Soudeur.objects.exists():
            self.stdout.write("Deja seed - rien a faire.")
            return

        affaire = Affaire.objects.first()
        of = OrdreFabrication.objects.first()
        lot = LotMatiere.objects.first()

        soudeurs = []
        for nom, prenom in [
            ("MBENG", "Charles"),
            ("NDONG", "Marius"),
            ("OBIANG", "Sylvie"),
        ]:
            soudeur = Soudeur.objects.create(
                nom=nom,
                prenoms=prenom,
                matricule=f"SOU-{nom}",
                qualification="SMAW 6G tube",
            )
            soudeurs.append(soudeur)

        today = timezone.localdate()
        qualifs = [
            QualificationSoudeur.objects.create(
                soudeur=soudeurs[0],
                norme=QualificationSoudeur.Norme.ISO_9606,
                procede=QualificationSoudeur.Procede.SMAW,
                position="6G",
                groupe_materiaux="Acier carbone",
                epaisseur_min=6,
                epaisseur_max=25,
                gamme_diametre="4-12 pouces",
                date_qualification=today - timedelta(days=100),
                date_validite=today + timedelta(days=900),
                certificat=f"ISO9606-{random.randint(10000, 99999)}",
            ),
            QualificationSoudeur.objects.create(
                soudeur=soudeurs[1],
                norme=QualificationSoudeur.Norme.ASME_IX,
                procede=QualificationSoudeur.Procede.GTAW,
                position="6G",
                date_qualification=today - timedelta(days=400),
                date_validite=today - timedelta(days=20),
                certificat=f"ASMEIX-{random.randint(10000, 99999)}",
            ),
        ]

        def _expiree_with_statut(q):
            if q.date_validite < today and q.statut != QualificationSoudeur.Statut.EXPIREE:
                q.statut = QualificationSoudeur.Statut.EXPIREE
                q.save(update_fields=["statut", "updated_at"])

        for q in qualifs:
            _expiree_with_statut(q)

        wps = WpsWpqr.objects.create(
            type=WpsWpqr.Type.WPS,
            reference="WPS-ETSL-TIG-01",
            norme=QualificationSoudeur.Norme.ISO_9606,
            procede=QualificationSoudeur.Procede.GTAW,
            materiau="Acier carbone API 5L",
            position="6G",
            epaisseur="6-25 mm",
            gaz_protection="Argon",
            parametres={"courant": "DCEN", "amperage": "90-120 A"},
            statut=WpsWpqr.Statut.BROUILLON,
        )

        controles = [
            ControleQualite.objects.create(
                type_controle=ControleQualite.TypeControle.VISUEL,
                organisme=ControleQualite.OrganismeCnd.INTERNE,
                affaire=affaire,
                ordre=of,
                wps=wps,
                lot=lot,
                point_controle="Joint 01 - raccord line A",
                date_controle=today,
                resultat=ControleQualite.Resultat.CONFORME,
                statut=ControleQualite.Statut.VALIDE,
                created_by=qaqc,
            ),
            ControleQualite.objects.create(
                type_controle=ControleQualite.TypeControle.CND,
                organisme=ControleQualite.OrganismeCnd.ORGANISME_AGREE,
                organisme_libelle="BV Gabon",
                affaire=affaire,
                lot=lot,
                point_controle="Gamme TIG joint 4",
                date_controle=today,
                resultat=ControleQualite.Resultat.NON_CONFORME,
                statut=ControleQualite.Statut.VALIDE,
                created_by=qaqc,
            ),
        ]

        nc = NonConformite.objects.create(
            controle=controles[1],
            source=NonConformite.Source.CONTROLE,
            gravite=NonConformite.Gravite.MAJEURE,
            description="Porosite sur le joint 4 (gamme TIG) - controle ressuyage non conforme",
            traitement=NonConformite.Traitement.REPRISE,
            statut=NonConformite.Statut.EN_TRAITEMENT,
            decided_by=qaqc,
            date_decision=today,
        )

        ActionCorrective.objects.create(
            non_conformite=nc,
            type=ActionCorrective.TypeAction.CORRECTIVE,
            description="Reprise du joint 4 + recontrôle ressuyage et radio.",
            responsable=qaqc,
            echeance=today + timedelta(days=5),
            statut=ActionCorrective.Statut.EN_COURS,
        )
        ActionCorrective.objects.create(
            non_conformite=nc,
            type=ActionCorrective.TypeAction.PREVENTIVE,
            description="Re-briefing soudeurs sur le nettoyage inter-passes.",
            responsable=qaqc,
            echeance=today + timedelta(days=10),
            statut=ActionCorrective.Statut.OUVERTE,
        )

        PvControle.objects.create(
            affaire=affaire,
            ordre=of,
            intitule="Reception interne - tirage TV horizontale",
            date_pv=today,
            statut=PvControle.Statut.EN_COURS,
            resultat=ControleQualite.Resultat.CONFORME,
            validated_by=qaqc,
        )
        PvControle.objects.create(
            affaire=affaire,
            intitule="PV tuyauterie - levage et pose line A",
            date_pv=today,
            statut=PvControle.Statut.RECEPTIONNE,
            resultat=ControleQualite.Resultat.CONFORME,
            levee_reserve=today,
            validated_by=qaqc,
            notes="Reception apres controles visuels OK.",
        )

        self.stdout.write(
            f"OK: {Soudeur.objects.count()} soudeurs, {QualificationSoudeur.objects.count()} quals, "
            f"{WpsWpqr.objects.count()} WPS, {ControleQualite.objects.count()} controles, "
            f"{NonConformite.objects.count()} NC, {ActionCorrective.objects.count()} CAPA, "
            f"{PvControle.objects.count()} PV."
        )