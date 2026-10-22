"""Registre des souscripteurs outbox (décorateur `subscriber`)."""

SUBSCRIBERS = {}


def subscriber(topic):
    """Enregistre une fonction comme gestionnaire de `topic`.

    Exemple :
        @subscriber("operations.marge_terminaison")
        def recevoir_marge_terminaison(event):
            ...
    """

    def decorate(func):
        SUBSCRIBERS.setdefault(topic, []).append(func)
        return func

    return decorate

#: Sujets publiés SANS abonné interne, volontairement (écart E3 de ETSL-ERP-INT) : les modules consommateurs lisent
#: déjà la donnée à la source (M11 lit les écritures analytiques et `ValorisationMensuelle`) ; ces sujets restent
#: diffusables aux webhooks déclarés par l'administrateur (abonné « * » `integrations.gr.fanout_webhooks`).
#: Un nouveau `publish(...)` doit avoir un abonné (`@subscriber`) ou figurer ici (garde-fou : `outbox/tests.py`).
SUJETS_SANS_ABONNE_INTERNE = {
    "gr.location.demarree": "webhook GLOBAL RENTAL (EXT-10)",
    "gr.location.cloturee": "webhook GLOBAL RENTAL (EXT-10)",
    "maintenance.ot.cout": "M11 lit l'écriture de coût d'OT (axe analytique) directement",
    "stocks.valorisation.figee": "M11 lit ValorisationMensuelle directement",
    "analytics.cube.archive": "traçabilité / webhook",
    "analytics.marts.scelles": "traçabilité / webhook",
    "analytics.archives.purgees": "traçabilité / webhook",
}
