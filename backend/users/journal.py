"""Journal des accès (EX-G-10, CDC §8.2 « journalisation des accès conservée 5 ans ») — lot 15b.

`journaliser` écrit une entrée inaltérable ; `JournalExportsMiddleware` trace tout téléchargement de données
(réponse « Content-Disposition: attachment ») sans avoir à instrumenter chaque vue d'export.
"""

from .models import JournalAcces


def ip_client(request):
    transmise = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (transmise.split(",")[0].strip() or request.META.get("REMOTE_ADDR") or "")[:45]


def journaliser(request, evenement, user=None, email="", details=None):
    if user is not None and not getattr(user, "is_authenticated", False):
        user = None
    return JournalAcces.objects.create(
        evenement=evenement,
        user=user,
        email=(email or getattr(user, "email", "") or "")[:254],
        ip=ip_client(request) or None,
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        chemin=request.path[:255],
        details=details or {},
    )


class JournalExportsMiddleware:
    """Trace chaque export / téléchargement (réponse en pièce jointe) avec son auteur et ses paramètres."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        disposition = response.get("Content-Disposition", "") if hasattr(response, "get") else ""
        if response.status_code == 200 and "attachment" in disposition.lower():
            user = getattr(request, "user", None)
            journaliser(request, JournalAcces.Evenement.EXPORT, user=user, details={
                "fichier": disposition.split("filename=")[-1].strip('"') if "filename=" in disposition else "",
                "parametres": {k: v for k, v in request.GET.items()},
            })
        return response
