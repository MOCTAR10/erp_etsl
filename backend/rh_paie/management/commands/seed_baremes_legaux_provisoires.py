"""Barèmes et paramètres de paie PROVISOIRES (Gabon, 2026) — idempotent, statut « provisoire ».

Valeurs issues d'une recherche web du 2026-10-18 (sources secondaires : presse gabonaise, appels à cotisation
CNAMGS, guides fiscaux) — aucun texte officiel (Journal officiel, cnss.ga, impots.ga) n'a pu être consulté
directement. Chaque valeur est chargée en « provisoire » : ETSL / le cabinet de paie doit la confirmer
(écran Paramétrage paie → « Confirmer »). Voir la fiche de clôture M9 (CLOTURE_MODULES_ETSL.md).
Le seed ne touche jamais une ligne existante (les valeurs saisies/confirmées par ETSL sont préservées).
"""

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from rh_paie.models import BaremeCotisation, BaremeImpot, ParametrePaie

EFFET = date(2026, 1, 1)

CNSS = "Communiqué CNSS du 12/01/2026 relayé par gabon24.tv (« CNSS : employeurs et travailleurs face aux nouveaux taux »)"
CNSS_REF = "Décret n°0487/PR/MASI du 18/12/2025 (à confirmer)"
CNAMGS = "https://directinfosgabon.com/cnamgs-les-entreprises-appelees-a-declarer-leurs-cotisations-du-3e-trimestre-2026/ (23/09/2026)"
CNAMGS_REF = "Appel à cotisation CNAMGS T3 2026 (taux salarié 1 %/2 % contradictoire selon les guides — à confirmer)"

# code, libellé, organisme, nature, base, taux %, plafond mensuel, source, référence
COTISATIONS = [
    ("CNSS-VIEIL-S", "CNSS vieillesse, invalidité, décès (salarié)", "CNSS", "salariale", "5", "1500000", CNSS, CNSS_REF),
    ("CNSS-VIEIL-P", "CNSS vieillesse, invalidité, décès (employeur)", "CNSS", "patronale", "11", "1500000", CNSS, CNSS_REF),
    ("CNSS-PF-P", "CNSS prestations familiales et maternité (employeur)", "CNSS", "patronale", "5", "1500000", CNSS,
     CNSS_REF + " — répartition employeur/salarié non confirmée"),
    ("CNSS-AT-P", "CNSS accidents du travail et maladies professionnelles (employeur)", "CNSS", "patronale", "2",
     "1500000", CNSS, CNSS_REF + " — répartition employeur/salarié non confirmée"),
    ("CNAMGS-S", "CNAMGS assurance maladie (salarié)", "CNAMGS", "salariale", "2", "2500000", CNAMGS, CNAMGS_REF),
    ("CNAMGS-P", "CNAMGS assurance maladie (employeur)", "CNAMGS", "patronale", "4.1", "2500000", CNAMGS, CNAMGS_REF),
    ("FNH-P", "Fonds national de l'habitat (employeur)", "CNSS/DGI", "patronale", "2", "1500000",
     "Calendrier fiscal et social janvier 2022 (businessconsulting-gabon.com) ; un autre site cite 0,5 %",
     "Taux contradictoire (2 % / 0,5 %) — à confirmer"),
    ("CFP-P", "Contribution à la formation professionnelle (employeur)", "DGI", "patronale", "0.5", "1500000",
     "Calendrier fiscal et social janvier 2022 (businessconsulting-gabon.com) ; un autre site cite 2 %",
     "Taux contradictoire (0,5 % / 2 %) — à confirmer"),
]

# Barème annuel DGI (guide atekbot.space, 2026) ramené au MOIS (÷ 12) : plafonds de tranche par part.
TRANCHES_MENSUELLES = [
    {"plafond": 125000, "taux": 0},
    {"plafond": 160000, "taux": 5},
    {"plafond": 225000, "taux": 10},
    {"plafond": 300000, "taux": 15},
    {"plafond": 430000, "taux": 20},
    {"plafond": 625000, "taux": 25},
    {"plafond": 916667, "taux": 30},
    {"plafond": None, "taux": 35},
]

# code, libellé, valeur, unité, source, référence
PARAMETRES = [
    ("SMIG", "SMIG mensuel", "80000", "FCFA", "https://gabonmediatime.com/gabon-le-smig-bel-et-bien-a-80-000-fcfa-en-2026/",
     "Inchangé depuis 2006 ; ne pas confondre avec le revenu minimum mensuel 150 000 (décret 127/PR/MTEPS du 23/04/2010)"),
    ("RMM", "Revenu minimum mensuel", "150000", "FCFA", "https://financesao.com/gabon-le-smig-reste-fixe-a-80-000-fcfa-en-2026-loin-des-150-000-fcfa-annonces/",
     "Décret n°127/PR/MTEPS du 23/04/2010 (à confirmer)"),
    ("DUREE_LEGALE_HEBDO", "Durée légale hebdomadaire", "40", "h", "https://africarrieres.com/gabon/fr/guide/droit-du-travail/heures-et-conges",
     "Code du travail (loi n°3/94 du 21/11/1994) — article à confirmer"),
    ("HS_MAJ_1", "Majoration heures supplémentaires, tranche 1 (41e à 48e h)", "25", "%", "https://africarrieres.com/gabon/fr/guide/droit-du-travail/heures-et-conges",
     "Sources contradictoires (15 % / 25 %) — Code du travail et convention collective à confirmer"),
    ("HS_MAJ_2", "Majoration heures supplémentaires, tranche 2 (au-delà de la 48e h)", "50", "%", "https://africarrieres.com/gabon/fr/guide/droit-du-travail/heures-et-conges",
     "Sources contradictoires (35 % / 50 %) — à confirmer"),
    ("HS_SEUIL_2", "Seuil de la tranche 2 d'heures supplémentaires", "48", "h", "https://africarrieres.com/gabon/fr/guide/droit-du-travail/heures-et-conges",
     "À confirmer"),
    ("CNAMGS_PENALITE_DEFAUT", "CNAMGS — majoration pour défaut de déclaration", "25", "%", CNAMGS, CNAMGS_REF),
    ("CNAMGS_PENALITE_RETARD", "CNAMGS — majoration pour paiement tardif", "2", "%", CNAMGS, CNAMGS_REF),
]


class Command(BaseCommand):
    help = "Charge les barèmes/paramètres de paie Gabon 2026 au statut PROVISOIRE (à confirmer par ETSL)."

    def handle(self, *args, **options):
        for ordre, (code, label, organisme, nature, taux, plafond, source, ref) in enumerate(COTISATIONS):
            BaremeCotisation.objects.get_or_create(
                code=code, date_effet=EFFET,
                defaults=dict(
                    label=label, organisme=organisme, nature=nature, base="brut", taux=Decimal(taux),
                    plafond=Decimal(plafond), ordre=ordre, source=source, reference_texte=ref,
                ),
            )
        BaremeImpot.objects.get_or_create(
            code="IRPP", date_effet=EFFET,
            defaults=dict(
                label="IRPP — retenue mensuelle (barème DGI 2026 ÷ 12)", tranches=TRANCHES_MENSUELLES,
                abattement_pct=Decimal("20"), cotisations_deductibles=True,
                source="https://www.atekbot.space/blog/irpp-gabon-2026-bareme-calcul-et-declaration-dgi-le-guide-complet",
                reference_texte=(
                    "CGI art. 174 et loi de finances n°041/2025 du 29/12/2025 (à confirmer) ; abattement 20 % si base "
                    "< 4 166 666 FCFA/an, sinon forfait 833 333 : le forfait n'est pas géré, à confirmer"
                ),
            ),
        )
        for code, label, valeur, unite, source, ref in PARAMETRES:
            ParametrePaie.objects.get_or_create(
                code=code, date_effet=EFFET,
                defaults=dict(label=label, valeur=Decimal(valeur), unite=unite, source=source, reference_texte=ref),
            )
        self.stdout.write(self.style.WARNING(
            "Barèmes de paie PROVISOIRES chargés (sources secondaires) : à faire confirmer par ETSL / le cabinet de paie."
        ))
