"""Sites ETSL (EX-G-03) : rattachement du texte libre, restriction de lecture par site, répartition des ressources.

- `meilleur_site` est une fonction PURE (aussi appelée par les migrations de données des applications) : le mot-clé
  le plus long contenu (mot entier, sans accents ni casse) dans le texte libre désigne le site.
- Restriction de lecture : paramètre transverse `SITES_LECTURE_RESTREINTE` (0 = désactivée, défaut provisoire). Activée,
  un compte rattaché à un site ne lit, sur les listes qui déclarent `champ_site`, que les fiches de son site et les
  fiches non rattachées ; les rôles de `users.rbac.ROLES_TOUS_SITES` lisent tout. Appliquée par
  `config.filtres.FiltreMulticritere` (listes ET détail).
"""

import unicodedata

from django.db.models import Count, Q

CODE_RESTRICTION = "SITES_LECTURE_RESTREINTE"

#: Ressources rattachables : clé de l'écran, modèle, champ texte libre historique (ou None).
RESSOURCES = (
    ("depots", "stocks.Depot", "site"),
    ("equipements", "logistique.EquipementParc", "site"),
    ("actifs", "maintenance.Actif", "site"),
    ("salaries", "rh_paie.Employe", "site"),
    ("affaires", "commercial.Affaire", None),
    ("ordres", "operations.OrdreFabrication", None),
    ("utilisateurs", "users.User", None),
)


def normaliser(texte):
    s = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode().lower()
    for c in "-'/_().,;":
        s = s.replace(c, " ")
    return " ".join(s.split())


def mots_cles(code, libelle, alias):
    mots = {normaliser(code), normaliser(libelle), *(normaliser(a) for a in str(alias or "").split(","))}
    return sorted(m for m in mots if m)


def meilleur_site(texte, candidats):
    """`candidats` : itérable de (pk, [mots-clés normalisés]). Renvoie le pk du site reconnu ou None."""
    t = f" {normaliser(texte)} "
    if not t.strip():
        return None
    retenu, longueur = None, 0
    for pk, mots in candidats:
        for m in mots:
            if f" {m} " in t and len(m) > longueur:
                retenu, longueur = pk, len(m)
    return retenu


def candidats(site_model):
    return [(s.pk, mots_cles(s.code, s.libelle, s.alias)) for s in site_model.objects.filter(actif=True)]


def site_pour_texte(texte):
    from .models import Site

    return meilleur_site(texte, candidats(Site)) if str(texte or "").strip() else None


def rattacher_existants(site_model, modele, champ_texte="site"):
    """Rattache les fiches non rattachées dont le texte libre est reconnu (migrations, bouton « Rattacher »)."""
    cands = candidats(site_model)
    n = 0
    for obj in modele.objects.filter(site_etsl__isnull=True).exclude(**{champ_texte: ""}).only("pk", champ_texte):
        pk = meilleur_site(getattr(obj, champ_texte), cands)
        if pk:
            modele.objects.filter(pk=obj.pk).update(site_etsl_id=pk)
            n += 1
    return n


def rattacher_tout():
    from django.apps import apps

    from .models import Site

    return {cle: rattacher_existants(Site, apps.get_model(label), champ) for cle, label, champ in RESSOURCES if champ}


def restriction_active():
    from users.parametres import valeur_transverse

    return valeur_transverse(CODE_RESTRICTION) == 1


def site_de_lecture(user):
    """Site auquel la lecture du compte est limitée, ou None (aucune limite)."""
    from users.rbac import lecture_tous_sites

    if not user or not user.is_authenticated or lecture_tous_sites(user) or not getattr(user, "site_etsl_id", None):
        return None
    return user.site_etsl_id if restriction_active() else None


def restreindre_par_site(request, queryset, champ):
    site = site_de_lecture(getattr(request, "user", None))
    if site is None:
        return queryset
    return queryset.filter(Q(**{champ: site}) | Q(**{f"{champ}__isnull": True}))


def repartition():
    """Nombre de ressources par site (et non rattachées) : indicateur « affectation des ressources par site »."""
    from django.apps import apps

    from .models import Site

    vide = {cle: 0 for cle, _, _ in RESSOURCES}
    lignes = {s.pk: {"site": s.pk, "code": s.code, "libelle": s.libelle, "actif": s.actif, **vide}
              for s in Site.objects.order_by("code")}
    lignes[None] = {"site": None, "code": "", "libelle": "", "actif": True, **vide}
    for cle, label, _ in RESSOURCES:
        for row in apps.get_model(label).objects.values("site_etsl").annotate(n=Count("pk")).order_by():
            if row["site_etsl"] in lignes:
                lignes[row["site_etsl"]][cle] = row["n"]
    return {"ressources": [cle for cle, _, _ in RESSOURCES], "lignes": list(lignes.values())}
