"""Registre central des paramètres ETSL (écarts transverses) : un seul écran pour TOUS les paramètres provisoires.

Chaque module porte ses propres modèles `Parametre*` et ses propres endpoints d'édition / de confirmation, avec ses
propres droits. Ce registre ne les modifie pas : il les **recense** (lecture seule) et, pour lister, réutilise le
ViewSet de l'application (ses permissions de lecture et son `get_queryset`, qui crée les défauts manquants). L'écran
`/parametres` appelle ensuite l'endpoint EXISTANT de l'application pour modifier ou confirmer : les droits restent
ceux du module (un refus s'affiche tel quel).

`users/test_ecarts_tr.py` échoue si une classe `Parametre*` d'une application n'est pas enregistrée ici.
"""

import json
from dataclasses import dataclass, field
from datetime import date

from django.apps import apps
from django.utils import timezone
from django.utils.module_loading import import_string
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

MODULES = {
    "users": "Socle — transverse",
    "documents": "Socle — GED (rétention)",
    "commercial": "M1 Commercial",
    "achats": "M2 Achats",
    "operations": "M3 Opérations",
    "logistique": "M4 Logistique",
    "stocks": "M5 Stocks",
    "qualite": "M6 Qualité",
    "hse": "M7 HSE",
    "maintenance": "M8 Maintenance",
    "rh_paie": "M9 RH & Paie",
    "comptabilite": "M10 Comptabilité",
    "controle_gestion": "M11 Contrôle de gestion",
    "juridique": "M12 Juridique",
    "analytics": "Couche D — cubes",
    "integrations": "Reprise et interfaces (SAGE)",
}


@dataclass(frozen=True)
class Registre:
    modele: str  # "app.Modele"
    viewset: str  # chemin du ViewSet de l'application (droits + get_queryset réutilisés)
    api: str  # base de l'endpoint de l'application
    ecran: str  # écran du module où le paramètre est utilisé
    cle: str = "code"
    libelle: str = "label"
    valeur: str = "valeur"
    type_valeur: str = "decimal"  # decimal | entier | json | texte
    edition: str = "patch"  # patch | modifier | definir-retention | paie
    champ: str = "valeur"
    confirmation: str = "confirmer"
    groupe: str = ""  # attribut de regroupement éventuel (ex. table RGM_*)
    champs_json: tuple = ()  # paramètre composite (gabarit) : ces champs forment la valeur JSON, PATCH champ par champ
    extra: dict = field(default_factory=dict)

    @property
    def app(self):
        return self.modele.split(".")[0]


def _std(modele, viewset, api, ecran, **kw):
    return Registre(modele=modele, viewset=viewset, api=api, ecran=ecran, **kw)


REGISTRE = (
    _std("users.ParametreTransverse", "users.parametres.ParametreTransverseViewSet", "/api/users/parametres/", "/parametres"),
    _std("documents.DocumentType", "documents.views.DocumentTypeViewSet", "/api/documents/types/", "/documents",
         valeur="retention_years", type_valeur="entier", edition="definir-retention", champ="retention_years",
         confirmation="confirmer-retention", extra={"unite": "ans"}),
    _std("commercial.ParametreCommercial", "commercial.views.ParametreCommercialViewSet", "/api/commercial/parametres/", "/pipeline"),
    _std("achats.ParametreAchats", "achats.views_ecarts.ParametreAchatsViewSet", "/api/achats/parametres/", "/purchases"),
    _std("operations.ParametreOperations", "operations.views.ParametreOperationsViewSet", "/api/operations/parametres/", "/operations"),
    _std("logistique.ParametreLogistique", "logistique.views.ParametreLogistiqueViewSet", "/api/logistique/parametres/", "/logistique"),
    _std("stocks.ParametreStock", "stocks.views.ParametreStockViewSet", "/api/stocks/parametres/", "/stocks"),
    _std("qualite.ParametreQualite", "qualite.views.ParametreQualiteViewSet", "/api/qualite/parametres/", "/qualite"),
    _std("hse.ParametreHse", "hse.views.ParametreHseViewSet", "/api/hse/parametres/", "/hse"),
    _std("maintenance.ParametreMaintenance", "maintenance.views.ParametreMaintenanceViewSet", "/api/maintenance/parametres/", "/maintenance"),
    _std("rh_paie.ParametrePaie", "rh_paie.views.ParametrePaieViewSet", "/api/rh-paie/parametres-paie/", "/rh-paie", edition="paie"),
    _std("comptabilite.ParametreCompta", "comptabilite.views.ParametreComptaViewSet", "/api/comptabilite/parametres/", "/comptabilite"),
    _std("controle_gestion.ParametreGestion", "controle_gestion.views.ParametreGestionViewSet", "/api/controle-gestion/parametres/",
         "/controle-gestion", groupe="table"),
    _std("juridique.ParametreJuridique", "juridique.views.ParametreJuridiqueViewSet", "/api/juridique/parametres/", "/juridique",
         cle="cle", libelle="libelle", type_valeur="json", edition="modifier"),
    _std("analytics.ParametreCube", "analytics.views.ParametreCubeViewSet", "/api/analytics/cubes/parametres/", "/direction"),
    _std("integrations.ParametreReprise", "integrations.views_migration.ParametreRepriseViewSet",
         "/api/integrations/migration/parametres/", "/reprise"),
    # Gabarit de lecture des exports SAGE (SAGE_GL…) : séparateurs, encodage, format de date, colonnes.
    _std("integrations.GabaritImport", "integrations.views.GabaritImportViewSet", "/api/integrations/gabarits/", "/reprise",
         valeur="colonnes", type_valeur="json", champ="*",
         champs_json=("separateur", "encodage", "format_date", "separateur_decimal", "colonnes")),
)


def classes_parametres():
    """Toutes les classes concrètes `Parametre*` des applications installées (contrôle de couverture du registre)."""
    return sorted(m._meta.label for m in apps.get_models() if m.__name__.startswith("Parametre"))


def _provisoire(obj):
    if hasattr(obj, "statut_valeur"):
        return obj.statut_valeur != "confirme"
    if hasattr(obj, "provisoire"):
        return bool(obj.provisoire)
    if hasattr(obj, "retention_confirmee_le"):
        return obj.retention_confirmee_le is None
    return True


def _confirmation(obj):
    if hasattr(obj, "retention_confirmee_le"):
        le, par = obj.retention_confirmee_le, obj.retention_confirmee_par
    else:
        le, par = getattr(obj, "confirme_le", None), getattr(obj, "confirme_par", None)
    return le, getattr(par, "email", None)


def _valeur_texte(entry, obj):
    if entry.champs_json:
        return json.dumps({c: getattr(obj, c) for c in entry.champs_json}, ensure_ascii=False), "json"
    v = getattr(obj, entry.valeur)
    # Paramètre à valeur texte (transverse, M1, cubes…) : la valeur affichée et éditée est le texte.
    if getattr(obj, "texte", ""):
        return obj.texte, "texte"
    if entry.type_valeur == "json":
        return json.dumps(v, ensure_ascii=False), "json"
    if v is None:
        return "", entry.type_valeur
    return str(v), entry.type_valeur


def _vue(entry, request):
    """ViewSet de l'application, prêt à lister : ses permissions de lecture sont vérifiées telles quelles."""
    cls = import_string(entry.viewset)
    vue = cls()
    vue.request, vue.args, vue.kwargs, vue.format_kwarg = request, (), {}, None
    vue.action, vue.action_map = "retrieve", {"get": "retrieve"}
    vue.check_permissions(request)
    return vue


def _queryset(entry, vue):
    qs = vue.get_queryset()
    if entry.edition == "paie":  # versions en vigueur seulement
        today = date.today()
        qs = qs.filter(date_effet__lte=today).exclude(date_fin__lt=today)
    return qs


def _ligne(entry, obj):
    valeur, type_valeur = _valeur_texte(entry, obj)
    provisoire = _provisoire(obj)
    le, par = _confirmation(obj)
    base = f"{entry.api}{obj.pk}/"
    edit = {"method": "PATCH", "path": base, "champ": entry.champ, "extra": {}}
    if entry.edition == "modifier":
        edit = {"method": "POST", "path": f"{base}modifier/", "champ": "valeur", "extra": {}}
    elif entry.edition == "definir-retention":
        edit = {"method": "POST", "path": f"{base}definir-retention/", "champ": entry.champ, "extra": {}}
    elif entry.edition == "paie" and not provisoire:
        # Valeur légale confirmée : nouvelle version datée (l'ancienne est close la veille).
        edit = {"method": "POST", "path": f"{base}reviser/", "champ": "valeur",
                "extra": {"date_effet": timezone.localdate().isoformat()}}
    if type_valeur == "texte" and hasattr(obj, "texte"):
        edit["champ"] = "texte"
    return {
        "id": str(obj.pk),
        "module": entry.app,
        "module_label": MODULES.get(entry.app, entry.app),
        "modele": entry.modele,
        "code": str(getattr(obj, entry.cle)),
        "label": str(getattr(obj, entry.libelle)),
        "groupe": str(getattr(obj, entry.groupe, "") or "") if entry.groupe else "",
        "valeur": valeur,
        "unite": getattr(obj, "unite", "") or entry.extra.get("unite", ""),
        "type_valeur": type_valeur,
        "provisoire": provisoire,
        "confirme_le": le.isoformat() if le else None,
        "confirme_par": par,
        "edition": edit,
        "confirmation": f"{base}{entry.confirmation}/",
        "ecran": entry.ecran,
    }


def collecter(request, module="", statut="", recherche=""):
    """Lignes lisibles par l'utilisateur (modules dont l'application refuse la lecture : omis)."""
    lignes = []
    for entry in REGISTRE:
        if module and entry.app != module:
            continue
        if not apps.is_installed(entry.app):
            continue
        try:
            vue = _vue(entry, request)
        except (PermissionDenied, NotAuthenticated):
            continue
        for obj in _queryset(entry, vue):
            ligne = _ligne(entry, obj)
            if statut == "provisoire" and not ligne["provisoire"]:
                continue
            if statut == "confirme" and ligne["provisoire"]:
                continue
            if recherche and recherche.lower() not in f"{ligne['code']} {ligne['label']} {ligne['groupe']}".lower():
                continue
            lignes.append(ligne)
    return lignes


COLONNES_EXPORT = [
    ("module_label", "Module"), ("code", "Code"), ("label", "Libellé"), ("groupe", "Table / groupe"),
    ("valeur", "Valeur"), ("unite", "Unité"), ("statut", "Statut"), ("confirme_par", "Confirmé par"),
    ("confirme_le", "Confirmé le"), ("a_confirmer", "Valeur retenue par ETSL (à remplir)"),
]


class ParametresEtslView(APIView):
    """`GET /api/parametres-etsl/` : tous les paramètres lisibles (filtres `module`, `statut`, `search` ;
    `?export=xlsx|pdf|csv` pour transmettre la liste à ETSL)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        p = request.query_params
        lignes = collecter(request, p.get("module", ""), p.get("statut", ""), p.get("search", "").strip())
        fmt = p.get("export")
        if fmt in ("csv", "xlsx", "pdf"):
            from .exports import export_response

            for ligne in lignes:
                ligne["statut"] = "Provisoire — à confirmer ou modifier par ETSL" if ligne["provisoire"] else "Confirmé"
                ligne["a_confirmer"] = ""
            return export_response(
                lignes, COLONNES_EXPORT, fmt, "Paramètres ETSL", "parametres_etsl",
                sous_titre=f"{sum(1 for x in lignes if x['provisoire'])} paramètre(s) provisoire(s) à confirmer par ETSL",
            )
        return Response({
            "count": len(lignes),
            "provisoires": sum(1 for x in lignes if x["provisoire"]),
            "modules": [{"module": k, "label": v} for k, v in MODULES.items()],
            "results": lignes,
        })


class ParametresEtslResumeView(APIView):
    """`GET /api/parametres-etsl/resume/` : compteur « N paramètres provisoires à confirmer par ETSL » par module."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        par_module = {}
        for ligne in collecter(request):
            m = par_module.setdefault(
                ligne["module"], {"module": ligne["module"], "label": ligne["module_label"], "total": 0, "provisoires": 0}
            )
            m["total"] += 1
            m["provisoires"] += int(ligne["provisoire"])
        return Response({
            "total": sum(m["total"] for m in par_module.values()),
            "provisoires": sum(m["provisoires"] for m in par_module.values()),
            "par_module": list(par_module.values()),
        })
