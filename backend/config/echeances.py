"""Tranches d'échéance communes à tous les modules (CDC EX-G-05 : alertes J-90 / J-30 / J-15 / J-0).

Une seule source de vérité pour les créneaux affichés (juridique, contrats, RH, GED, cockpit Direction) et pour
les paliers de notification quotidienne (`analytics.tasks.notifier_echeances`).
"""

BANDES = ("expiree", "j0", "j15", "j30", "j60", "j90")
PALIERS_NOTIFICATION = (90, 30, 15, 0)


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
