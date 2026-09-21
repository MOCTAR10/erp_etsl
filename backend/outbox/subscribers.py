"""Registre des souscripteurs outbox (décorateur `subscriber`)."""

SUBSCRIBERS = {}


def subscriber(topic):
    """Enregistre une fonction comme gestionnaire de `topic`.

    Exemple :
        @subscriber("accounting.move.posted")
        def on_move_posted(event):
            ...
    """

    def decorate(func):
        SUBSCRIBERS.setdefault(topic, []).append(func)
        return func

    return decorate