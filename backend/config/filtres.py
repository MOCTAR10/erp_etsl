"""Filtre multicritère générique des listes API (EX-G-09).

Une vue l'active en déclarant `champs_filtrables` (noms de champs du modèle) ; le type de chaque critère est déduit
du champ :

| Type    | Champ du modèle                      | Paramètres acceptés                                  |
|---------|--------------------------------------|------------------------------------------------------|
| choix   | champ à `choices`                    | `champ=a` ou `champ=a,b` (plusieurs valeurs)         |
| fk      | clé étrangère                        | `champ=<id>` ou `champ=<id1>,<id2>`                  |
| date    | `DateField` / `DateTimeField`        | `champ__gte=AAAA-MM-JJ`, `champ__lte=AAAA-MM-JJ`     |
| nombre  | entier / décimal                     | `champ`, `champ__gte`, `champ__lte`                  |
| bool    | `BooleanField`                       | `champ=true|false` (1/0, oui/non acceptés)           |
| texte   | autre champ texte                    | `champ=<fragment>` (contient, sans casse)            |

Les critères se cumulent (ET). Une valeur invalide (date, choix, nombre, identifiant) renvoie **400** avec un message
explicite, jamais 500. Le backend est branché par défaut (`DEFAULT_FILTER_BACKENDS`) mais inerte tant que la vue ne
déclare pas `champs_filtrables`. `config.filtres_vues.FiltresMulticriteresMixin` ajoute `GET <liste>/filtres/` : la description des
critères (type, libellé, choix traduits) qui alimente le composant `FilterBar` du SPA.

Ne jamais déclarer un champ de montant masqué (RF-59) : filtrer par montant révélerait la valeur.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from rest_framework.exceptions import ValidationError
from rest_framework.filters import BaseFilterBackend

from .i18n import tr

VRAI = {"1", "true", "oui", "yes", "vrai"}
FAUX = {"0", "false", "non", "no", "faux"}


def type_champ(field):
    if getattr(field, "choices", None):
        return "choix"
    if isinstance(field, models.ForeignKey):
        return "fk"
    if isinstance(field, (models.DateField, models.DateTimeField)):
        return "date"
    if isinstance(field, models.BooleanField):
        return "bool"
    if isinstance(field, (models.IntegerField, models.DecimalField, models.FloatField)):
        return "nombre"
    return "texte"


def _convertir(field, brut, nom):
    try:
        return field.to_python(brut)
    except (DjangoValidationError, ValueError, TypeError):
        raise ValidationError({nom: tr("Valeur de filtre invalide.") + f" ({brut})"})


def _date(brut, nom):
    try:
        return models.DateField().to_python(brut)
    except DjangoValidationError:
        raise ValidationError({nom: tr("Date invalide (format attendu AAAA-MM-JJ).") + f" ({brut})"})


def _valeurs(brut):
    return [v.strip() for v in str(brut).split(",") if v.strip()]


def appliquer_filtres(queryset, params, champs):
    """Applique les critères de `params` (QueryDict) pour les `champs` déclarés du modèle de `queryset`."""
    model = queryset.model
    for nom in champs:
        field = model._meta.get_field(nom)
        genre = type_champ(field)
        brut = params.get(nom, "")
        if genre in ("choix", "fk") and brut:
            valeurs = _valeurs(brut)
            if genre == "choix":
                admis = {str(c[0]) for c in field.flatchoices}
                inconnus = [v for v in valeurs if v not in admis]
                if inconnus:
                    raise ValidationError({nom: tr("Choix invalide.") + f" ({', '.join(inconnus)})"})
                queryset = queryset.filter(**{f"{nom}__in": valeurs})
            else:
                cible = field.target_field
                ids = [_convertir(cible, v, nom) for v in valeurs]
                queryset = queryset.filter(**{f"{field.attname}__in": ids})
        elif genre == "bool" and brut:
            v = str(brut).strip().lower()
            if v not in VRAI | FAUX:
                raise ValidationError({nom: tr("Valeur de filtre invalide.") + f" ({brut})"})
            queryset = queryset.filter(**{nom: v in VRAI})
        elif genre == "texte" and brut:
            queryset = queryset.filter(**{f"{nom}__icontains": str(brut).strip()})
        elif genre == "nombre" and brut:
            queryset = queryset.filter(**{nom: _convertir(field, brut, nom)})
        for borne in ("gte", "lte"):
            valeur = params.get(f"{nom}__{borne}", "")
            if not valeur or genre not in ("date", "nombre"):
                continue
            cle = f"{nom}__{borne}"
            if genre == "date":
                valeur = _date(valeur, cle)
                if isinstance(field, models.DateTimeField):
                    cle = f"{nom}__date__{borne}"
            else:
                valeur = _convertir(field, valeur, cle)
            queryset = queryset.filter(**{cle: valeur})
    return queryset


def decrire_filtres(model, champs, libelles=None):
    """Description des critères pour l'écran (libellés et choix dans la langue de la requête) ; `libelles` remplace
    le `verbose_name` d'un champ (ex. `created_at`)."""
    resultat = []
    for nom in champs:
        field = model._meta.get_field(nom)
        genre = type_champ(field)
        libelle = (libelles or {}).get(nom) or str(field.verbose_name)
        description = {"champ": nom, "type": genre, "libelle": tr(libelle)}
        if genre == "choix":
            description["choix"] = [{"valeur": str(v), "libelle": tr(str(lib))} for v, lib in field.flatchoices]
        elif genre == "fk" and hasattr(field.related_model, "choix_filtre"):  # petit référentiel (ex. sites ETSL)
            description["choix"] = field.related_model.choix_filtre()
        if genre in ("date", "nombre"):
            description["parametres"] = [f"{nom}__gte", f"{nom}__lte"]
        else:
            description["parametres"] = [nom]
        resultat.append(description)
    return resultat


class FiltreMulticritere(BaseFilterBackend):
    """Backend DRF : inerte tant que la vue ne déclare pas `champs_filtrables`."""

    def filter_queryset(self, request, queryset, view):
        # EX-G-03 : restriction de lecture par site (paramètre transverse, désactivé par défaut), listes ET détail.
        if champ_site := getattr(view, "champ_site", None):
            from referentiels.sites import restreindre_par_site

            queryset = restreindre_par_site(request, queryset, champ_site)
        champs = getattr(view, "champs_filtrables", None)
        if not champs or getattr(view, "detail", False):  # actions de détail : pas de filtrage de liste
            return queryset
        return appliquer_filtres(queryset, request.query_params, champs)

    def get_schema_operation_parameters(self, view):
        return []

