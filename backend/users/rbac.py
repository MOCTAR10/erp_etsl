"""Matrice de lecture par module ERP (ACL fines).

Référentiel : `ARCHITECTURE_ERP_ETSL.md` §2.2 (table « Fonctions ETSL (MANUEL
ch.2) ↔ modules ») et `SPECIFICATION_SYSTEME_ETSL.md` §3.3 (« ACL fines par
module »).

Deuxonds plans distincts, à ne pas confondre :

* la **lecture** de ce fichier (quelles pages un rôle peut consulter) ;
* les **droits d'écriture**, qui restent portés par les tuples
  `*_WRITE_ROLES` / `*_VALIDATION_ROLES` de chaque `services.py` ;
* le **masquage des montants** (`has_amount_access`), purement serializer.

Le socle (GED, workflow, registres, référentiels, analytically) reste accessible
à tout utilisateur authentifié : ses ACL sont objet par objet
(`documents.services.visible_documents`). `analytics` (Couche D) reste en
lecture ouverte et sans modèle : les montants y sont filtrés par
`AMOUNT_ROLES`.
"""

from .models import User

#: Modules ERP dont la lecture est restreinte au rôle (M1..M12).
ERP_APPS = (
    "commercial",
    "achats",
    "operations",
    "logistique",
    "stocks",
    "qualite",
    "hse",
    "maintenance",
    "rh_paie",
    "comptabilite",
    "controle_gestion",
    "juridique",
)

#: Rôles de gouvernance : accès transverse à tous les modules.
FULL_ACCESS_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
)

_R = User.Role

#: Rôle → modules lisibles.
#:
#: Base = la table « Fonctions ETSL ↔ modules » (§2.2). Les droits de validation
#: croisés déjà codés dans les tuples `*_VALIDATION_ROLES` / `*_AMOUNT_ROLES` sont
#: conservés, sinon une approbation existante deviendrait inatteignable.
#:
#: Un rôle absent n'a accès à aucun module métier (socle seul).
ROLE_MODULES: dict[str, tuple[str, ...]] = {
    # — Encadrement transverse
    _R.SECRETAIRE_GENERAL: (
        "juridique",
        "commercial",
        "achats",
        "comptabilite",
        "controle_gestion",
        "rh_paie",
    ),
    _R.DIRECTEUR_PROJETS: (
        "commercial",
        "achats",
        "operations",
        "comptabilite",
        "juridique",
        "stocks",
        "qualite",
        "hse",
        "maintenance",
        "logistique",
        "rh_paie",
    ),
    _R.DIRECTEUR_OPERATIONS: (
        "operations",
        "stocks",
        "qualite",
        "maintenance",
        "achats",
        "logistique",
        "hse",
        "comptabilite",
        "juridique",
        "rh_paie",
    ),
    # — Fonctions support
    _R.RH: ("rh_paie", "hse"),
    # Le DAF porte M10/M11 et valide M2 ; il accède au reste de M1 pour le
    # chiffre d'affaires et à M9 pour la masse salariale (`PAIE_AMOUNT_ROLES`).
    _R.FINANCE: (
        "comptabilite",
        "controle_gestion",
        "achats",
        "commercial",
        "rh_paie",
        "juridique",
        "logistique",
        "maintenance",
        "operations",
        "stocks",
        "qualite",  # coût de non-qualité : comptabilisation (CNQ_VALIDATION_ROLES, lot a3)
    ),
    _R.COMPTABLE: (
        "comptabilite",
        "controle_gestion",
        "achats",
        "commercial",
        "rh_paie",
        "juridique",
        "logistique",
        "maintenance",
        "operations",
        "stocks",
        "qualite",  # coût de non-qualité : comptabilisation (CNQ_VALIDATION_ROLES, lot a3)
    ),
    _R.QAQC: ("qualite", "operations", "achats"),
    _R.HSE: ("hse", "operations", "qualite", "maintenance", "achats"),
    _R.LOGISTIQUE: (
        "achats",
        "logistique",
        "stocks",
        "operations",
        "maintenance",
        "hse",
    ),
    _R.MAINTENANCE: (
        "maintenance",
        "stocks",
        "operations",
        "qualite",
        "hse",
        "logistique",
    ),
    # `chef_atelier` : exécution M3/M5/M6/M8 (§2.2), plus M2 : un atelier saisit
    # des demandes d'approvisionnement tout en restant hors du cercle des
    # montants achats (`ACHAT_AMOUNT_ROLES`) — cas couvert par `e2e/rbac.spec.ts`.
    _R.CHEF_ATELIER: (
        "operations",
        "stocks",
        "qualite",
        "maintenance",
        "achats",
        "hse",
        "logistique",
        "rh_paie",
    ),
    # — Consommateurs de la Couche D (écarts a4). Lecture seule : aucun tuple d'écriture des modules ne les cite
    #   encore (à ouvrir par chaque module si ETSL le demande). Périmètre PROVISOIRE, à confirmer par ETSL.
    # Chargé d'affaires : suit ses affaires de l'offre à la livraison (M1 pipe / contrats, M3 OF, M2 achats de
    # l'affaire, M4 parc mobilisé, M6 qualité livrée, M12 contrats) ; montants selon les cercles de chaque module.
    _R.CHARGE_AFFAIRES: (
        "commercial",
        "operations",
        "achats",
        "logistique",
        "qualite",
        "juridique",
    ),
    # Contrôleur de gestion : M11 (budgets, marges, clôture de gestion) et ses sources de coûts (M10, M1, M2, M3,
    # M4, M5, M8, M9 — salaires masqués hors `CanManagePaie`).
    _R.CONTROLEUR_GESTION: (
        "controle_gestion",
        "comptabilite",
        "commercial",
        "achats",
        "operations",
        "logistique",
        "stocks",
        "maintenance",
        "rh_paie",
    ),
    # Rôle hérité « Direction » : présent dans les 12 tuples d'écriture, il
    # conserve donc la lecture transverse (restriction impossible sans casser
    # ses droits existants).
    _R.DIRECTION: ERP_APPS,
    # `chef_service` n'écrit que dans le socle GED (`documents.WRITE_ROLES`) :
    # aucun module métier ne lui est ouvert.
    _R.CHEF_SERVICE: (),
}


def modules_for_role(role: str) -> tuple[str, ...]:
    """Modules ERP lisibles par `role` (tuple vide si aucun)."""
    if not role:
        return ()
    if role in FULL_ACCESS_ROLES:
        return ERP_APPS
    return ROLE_MODULES.get(role, ())


def can_read_app(user, app: str) -> bool:
    """`user` peut-il lire le module `app` ?"""
    if user is None or not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    if app not in ERP_APPS:
        return True
    return app in modules_for_role(user.role)
