"""Tranches d'échéance communes à tous les modules (CDC EX-G-05 : alertes J-90 / J-60 / J-30 / J-15 / J-0).

Une seule source de vérité pour les créneaux affichés (juridique, contrats, RH, GED, cockpit Direction) et pour
les paliers de notification (`paliers()`), lus par TOUS les modules : M1 (offres, contrats, avenants), M12
(conventions, cautions, assurances…), Couche D (`analytics.tasks.notifier_echeances`, alertes calendaires).

Harmonisation (2026-10) : les paliers sont UN paramètre provisoire central, `paliers_notification` (écran Juridique
› « Paramètres juridiques » et écran central `/parametres`, confirmation Direction Générale). Les anciens paramètres
spécifiques (M1 `ECHEANCE_PALIER_1..3`, Couche D `PALIER_ALERTE_J60`) sont supprimés : aucune surcharge par module.
"""

BANDES = ("expiree", "j0", "j15", "j30", "j60", "j90")
#: Paliers par défaut (provisoires, modifiables par ETSL) : J-90 / J-60 / J-30 / J-15 / J-0.
PALIERS_DEFAUT = (90, 60, 30, 15, 0)
PALIERS_NOTIFICATION = PALIERS_DEFAUT  # rétrocompatibilité
PARAMETRE_PALIERS = "paliers_notification"


def paliers():
    """Paliers d'alerte en vigueur (jours, ordre décroissant), lus dans le paramètre central."""
    from juridique.ecarts import parametre

    return tuple(sorted({int(j) for j in parametre(PARAMETRE_PALIERS)}, reverse=True))


def paliers_provisoires():
    """Vrai tant qu'ETSL n'a pas confirmé les paliers (bandeau « provisoire »)."""
    from juridique.ecarts import parametre_obj

    return bool(parametre_obj(PARAMETRE_PALIERS).provisoire)


def bande(jours):
    """Créneau d'une échéance à `jours` jours (négatif = dépassée, None = sans échéance)."""
    if jours is None:
        return "en_cours"
    if jours < 0:
        return "expiree"
    if jours == 0:
        return "j0"
    for seuil, nom in ((15, "j15"), (30, "j30"), (60, "j60"), (90, "j90")):
        if jours <= seuil:
            return nom
    return "en_cours"
