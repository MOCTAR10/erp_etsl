"""Libellés et codes hérités des jeux de démonstration : remise au propre rejouable des bases déjà chargées.

Les seeds écrivent désormais les libellés définitifs ; ces fonctions renomment les lignes posées par les versions
précédentes, comme le faisait le nettoyage du préfixe « [Vitrine] » : suffixe « (demo) » et mots sans accents
(constat B03), codes à tiret « BUD-00001 » hors séquence (B20), titres GED « … — archivage (…) » (A-15), seuils
compteur bruts « 900.00 ≥ 890.00 » (B13), cibles « Cible du KPI KP-M11-01 » sans nom d'indicateur (B06), tiers GLOBAL RENTAL en double.

UPDATE ciblés (pas de save()) : aucun signal, aucune règle métier rejouée, aucune pièce comptable touchée.
Idempotent : une base déjà propre n'est pas modifiée. Les situations du parcours B « Situation n1 (demo) - … » deviennent
« Situation n°1 - … » (situation, objet et ligne de la facture, pièces GED) ; le contrat E2E `parcours-demo.spec.ts`
recherche le nouveau libellé.
"""

import re

from django.apps import apps
from django.db.models import Q, Value
from django.db.models.functions import Replace

SUFFIXE_DEMO = " (demo)"
# Mots sans accents des anciens seeds (sortie ASCII) → orthographe correcte.
ACCENTS = (
    ("Contrat signe ", "Contrat signé "),
    ("Avenant 1 CTT", "Avenant n°1 CTT"),
    ("Equipe tuyauterie", "Équipe tuyauterie"),
    ("Evacuation incendie", "Évacuation incendie"),
    ("Ecart de tarif de location facture", "Écart de tarif de location facturé"),
    ("Certificats matiere non conformes sur 4 pieces", "Certificats matière non conformes sur 4 pièces"),
    ("Livraison partielle constatee a la reception", "Livraison partielle constatée à la réception"),
)
# (modèle, champ) des libellés posés par les seeds « parcours » (lots A à D).
CHAMPS_DEMO = (
    ("rh_paie.Qualification", "intitule"),
    ("documents.Document", "title"),
    ("operations.Equipe", "label"),
    ("achats.LitigeFournisseur", "description"),
    ("maintenance.PlanPreventif", "libelle"),
    ("maintenance.OrdreTravail", "description"),
    ("hse.Duer", "perimetre"),
    ("hse.AuditHse", "zone"),
    ("hse.PlanUrgence", "intitule"),
)


def libelle_propre(texte):
    for ancien, nouveau in ACCENTS:
        texte = texte.replace(ancien, nouveau)
    return texte.replace(SUFFIXE_DEMO, "")


# Situations du parcours B (seed_parcours_b) : anciens libellés → libellés définitifs.
SITUATIONS_PARCOURS = (
    ("Situation n1 (demo) - installation", "Situation n°1 - installation"),
    ("Situation n2 (demo) - tuyauterie principale", "Situation n°2 - tuyauterie principale"),
    ("Situation n3 (demo) - essais", "Situation n°3 - essais"),
    ("Situation n4 (demo) - parachevement", "Situation n°4 - parachèvement"),
)


def situations_parcours():
    """« Situation n1 (demo) - installation » → « Situation n°1 - installation » : la situation, l'objet et la ligne de
    sa facture client (« AFF00003 — Situation n1 (demo) … »), les pièces GED qui reprennent le libellé."""
    from comptabilite.models import FactureClient, LigneFactureClient
    from documents.models import Document
    from operations.models import SituationTravaux

    n = 0
    for ancien, nouveau in SITUATIONS_PARCOURS:
        n += SituationTravaux.objects.filter(label=ancien).update(label=nouveau)
        n += FactureClient.objects.filter(objet__contains=ancien).update(objet=Replace("objet", Value(ancien), Value(nouveau)))
        n += LigneFactureClient.objects.filter(designation__contains=ancien).update(
            designation=Replace("designation", Value(ancien), Value(nouveau))
        )
        n += Document.objects.filter(title__contains=ancien).update(title=Replace("title", Value(ancien), Value(nouveau)))
    return n


def renommer_libelles_herites():
    """« Vidange et graissage (demo) » → « Vidange et graissage », « Contrat signe » → « Contrat signé »…"""
    n = situations_parcours()
    for nom_modele, champ in CHAMPS_DEMO:
        modele = apps.get_model(nom_modele)
        filtre = Q(**{f"{champ}__contains": SUFFIXE_DEMO})
        for ancien, _ in ACCENTS:
            filtre |= Q(**{f"{champ}__contains": ancien})
        for pk, valeur in modele.objects.filter(filtre).values_list("pk", champ):
            propre = libelle_propre(valeur)
            if propre != valeur:
                modele.objects.filter(pk=pk).update(**{champ: propre})
                n += 1
    return n


# -- codes à tiret hors séquence (B20) ----------------------------------------------------------------------
# (modèle, préfixe, modèle de séquence, type de séquence)
CODES_SEQUENCES = (
    ("commercial.Affaire", "AFF", "commercial.CommercialSequence", "AFF"),
    ("commercial.Contract", "CTT", "commercial.CommercialSequence", "CTT"),
    ("controle_gestion.Budget", "BUD", "controle_gestion.ControleGestionSequence", "BUD"),
    ("controle_gestion.ClotureGestion", "CLO", "controle_gestion.ControleGestionSequence", "CLO"),
)


def normaliser_codes():
    """« BUD-00001 » (code forcé par un ancien seed) → prochain code de la séquence (« BUD00012 »).

    Le compte analytique d'une affaire porte son code : renommé avec elle ; la référence de contrat d'un dossier
    GLOBAL RENTAL aussi. Renvoie {ancien: nouveau}.
    """
    from juridique.models import DossierGlobalRental
    from referentiels.models import AnalyticAccount

    renommes = {}
    for nom_modele, prefixe, nom_sequence, kind in CODES_SEQUENCES:
        modele, sequence = apps.get_model(nom_modele), apps.get_model(nom_sequence)
        motif = re.compile(rf"^{prefixe}-\d+$")
        for pk, code in modele.objects.filter(code__startswith=f"{prefixe}-").order_by("code").values_list("pk", "code"):
            if not motif.match(code):
                continue
            nouveau = sequence.next_for(kind, prefixe)
            modele.objects.filter(pk=pk).update(code=nouveau)
            renommes[code] = nouveau
            if nom_modele == "commercial.Affaire":
                AnalyticAccount.objects.filter(code=code, affaires__pk=pk).update(code=nouveau)
            if nom_modele == "commercial.Contract":
                DossierGlobalRental.objects.filter(reference_contrat=code).update(reference_contrat=nouveau)
    return renommes


# -- titres GED des fiches archivées (A-15) -----------------------------------------------------------------
MARQUE_ARCHIVAGE = " — archivage ("


def titres_ged():
    """« PV00007 — PV de réception … — archivage (receptionne) » → « PV de réception … » (code en référence)."""
    from documents.models import Document

    n = 0
    for pk, titre, reference in Document.objects.filter(title__contains=MARQUE_ARCHIVAGE).values_list(
        "pk", "title", "reference"
    ):
        nom, _, statut = titre.partition(MARQUE_ARCHIVAGE)
        statut = statut[:-1] if statut.endswith(")") else statut
        if reference and nom.startswith(f"{reference} — "):
            nom = nom[len(reference) + 3:]
        # Statut lisible (« Signé (en cours de validité) ») gardé s'il apporte une information ; code brut abandonné.
        if statut and not re.fullmatch(r"[a-z_]+", statut) and statut not in nom:
            nom = f"{nom} — {statut}"
        Document.objects.filter(pk=pk).update(title=nom[:255])
        n += 1
    return n


# -- seuils compteur des OT préventifs (B13) -----------------------------------------------------------------
SEUIL_BRUT = re.compile(r"(seuil compteur atteint \()(\d+(?:\.\d+)?) ≥ (\d+(?:\.\d+)?)( )")


def messages_compteur():
    """« seuil compteur atteint (900.00 ≥ 890.00 heures) » → « (900 ≥ 890 heures) »."""
    from config.nombres import nombre_fr
    from maintenance.models import OrdreTravail

    n = 0
    for pk, description in OrdreTravail.objects.filter(description__contains="seuil compteur atteint (").values_list(
        "pk", "description"
    ):
        propre = SEUIL_BRUT.sub(lambda m: f"{m[1]}{nombre_fr(m[2])} ≥ {nombre_fr(m[3])}{m[4]}", description)
        if propre != description:
            OrdreTravail.objects.filter(pk=pk).update(description=propre)
            n += 1
    return n


# -- libellés des cibles de KPI (B06) -------------------------------------------------------------------------
def libelles_kpi():
    """Paramètres KPI_xx déjà créés avec « Cible du KPI KP-M11-xx » : nom de l'indicateur et unité."""
    from controle_gestion.models import ParametreGestion
    from controle_gestion.services import KPI_NOMS, libelle_cible_kpi

    n = 0
    for num, (_, unite) in KPI_NOMS.items():
        n += ParametreGestion.objects.filter(code=f"KPI_{num}", label=f"Cible du KPI KP-M11-{num}").update(
            label=libelle_cible_kpi(num), unite=unite
        )
    return n


# -- tiers GLOBAL RENTAL en double -----------------------------------------------------------------------------
GR_CANONIQUE = "GR-0001"


def doublons_global_rental():
    """Anciens seeds : quatre tiers « GLOBAL RENTAL » (GR-01, GR-1000, GR-2000 en plus de GR-0001). Les seeds n'en
    créent plus qu'un (GR-0001) ; sur une base existante, les doublons portent des pièces scellées (BC confirmé,
    convention signée, versions de tarif) qu'on ne réaffecte pas : ils sont désactivés, donc absents des listes de
    saisie (filtre « actifs »), et gardent leur historique."""
    from referentiels.models import Partner

    if not Partner.objects.filter(code=GR_CANONIQUE).exists():
        return 0
    return Partner.objects.filter(is_global_rental=True, is_active=True, name__istartswith="GLOBAL RENTAL").exclude(
        code=GR_CANONIQUE
    ).update(is_active=False)


def tout_nettoyer():
    """Toutes les remises au propre ci-dessus ; renvoie le nombre de lignes modifiées par nature."""
    return {
        "libelles": renommer_libelles_herites(),
        "codes": len(normaliser_codes()),
        "titres_ged": titres_ged(),
        "seuils_compteur": messages_compteur(),
        "kpi": libelles_kpi(),
        "tiers_gr": doublons_global_rental(),
    }
