"""Matrice des droits (§3.3 SPEC) et ACL (RF-33, RF-57/58/59).

Règle métier RF-33 : si type = paie (is_restricted_rh) → accès restreint RH.
Le statut admin/staff voit tout, quelle que soit l'ACL.
"""

from django.db.models import Q

from users.models import User

from .models import Document, Dossier, DocumentAccess, DossierAccess

# Matrice §3.3 : écriture sur les documents courants (12 fonctions + admin).
# EXCLUSIONS volontaires : RH (lecture seule sur la paie, RF-33) et DIRECTION
# (hérité : doit recevoir un droit explicite, cf. tests ACL).
WRITE_ROLES = (
    User.Role.ADMIN,
    User.Role.SECRETAIRE_GENERAL,
    User.Role.CHEF_SERVICE,
    User.Role.COMPTABLE,
    User.Role.FINANCE,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.QAQC,
    User.Role.HSE,
    User.Role.LOGISTIQUE,
    User.Role.MAINTENANCE,
    User.Role.CHEF_ATELIER,
)

# RF-33 : rôles autorisés sur un type restreint (paie).
RESTRICTED_ROLES = (User.Role.ADMIN, User.Role.RH)

# RF-59 : rôles autorisés à voir le montant (chef_service volontairement exclu).
AMOUNT_ROLES = (
    User.Role.ADMIN,
    User.Role.COMPTABLE,
    User.Role.FINANCE,
    User.Role.DIRECTION,
    User.Role.PDG,
    User.Role.DGA,
)


def is_admin_or_staff(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser or user.role == User.Role.ADMIN)


def can_see_amount(user):
    if is_admin_or_staff(user):
        return True
    return user.role in AMOUNT_ROLES


def _denied_subtree_ids(user):
    """Ensemble des dossiers du sous-arbre dont l'utilisateur est exclu (RF-58)."""
    roots = DossierAccess.objects.filter(user=user, permission=DossierAccess.Permission.DENY).values_list(
        "dossier_id", flat=True
    )
    if not roots:
        return set()
    denied = set(roots)
    changed = True
    while changed:
        changed = False
        for dossier_id, parent_id in Dossier.objects.filter(
            parent_id__in=denied
        ).values_list("id", "parent_id"):
            if dossier_id not in denied:
                denied.add(dossier_id)
                changed = True
    return denied


def visible_documents(user):
    """Queryset des documents accessibles en lecture (list + retrieve)."""
    if is_admin_or_staff(user):
        return Document.objects.all()

    base = Q(type__isnull=True) | Q(type__is_restricted_rh=False)
    if user.role == User.Role.RH:
        base |= Q(type__is_restricted_rh=True)

    denied_ids = DocumentAccess.objects.filter(
        user=user, permission=DocumentAccess.Permission.DENY
    ).values_list("document_id", flat=True)

    return (
        Document.objects.filter(base)
        .exclude(id__in=denied_ids)
        .exclude(dossier_id__in=_denied_subtree_ids(user))
    )


def visible_dossiers(user):
    """Queryset des dossiers accessibles (exclut les sous-arbres refusés)."""
    if is_admin_or_staff(user):
        return Dossier.objects.all()
    return Dossier.objects.exclude(id__in=_denied_subtree_ids(user))


def _dossier_acl_for(user, dossier):
    """Entrée ACL la plus proche (soi-même ou ancêtre) pour ce dossier (RF-58)."""
    node = dossier
    while node is not None:
        acl = DossierAccess.objects.filter(dossier=node, user=user).first()
        if acl:
            return acl
        node = node.parent
    return None


def _document_acl_for(user, document):
    return DocumentAccess.objects.filter(document=document, user=user).first()


def can_read_document(user, document):
    if is_admin_or_staff(user):
        return True
    # RF-33 : type restreint → RH uniquement.
    if document.type_id and document.type.is_restricted_rh and user.role != User.Role.RH:
        return False
    acl = _document_acl_for(user, document)
    if acl:
        return acl.permission != DocumentAccess.Permission.DENY
    # RF-58 : exclusion héritée d'un dossier.
    if document.dossier_id:
        dossier_acl = _dossier_acl_for(user, document.dossier)
        if dossier_acl and dossier_acl.permission == DossierAccess.Permission.DENY:
            return False
    return True


def can_write_document(user, document):
    if is_admin_or_staff(user):
        return True
    # RF-33 : écriture paie réservée à l'admin (RH = lecture seule).
    if document.type_id and document.type.is_restricted_rh:
        return False
    acl = _document_acl_for(user, document)
    if acl:
        return acl.permission == DocumentAccess.Permission.WRITE
    if document.created_by_id == user.id:
        return True
    if user.role in WRITE_ROLES:
        return True
    # RF-58 : droit d'écriture hérité d'un dossier.
    if document.dossier_id:
        dossier_acl = _dossier_acl_for(user, document.dossier)
        return bool(dossier_acl and dossier_acl.permission == DossierAccess.Permission.WRITE)
    return False


def can_write_dossier(user, dossier):
    if is_admin_or_staff(user):
        return True
    acl = _dossier_acl_for(user, dossier)
    if acl:
        return acl.permission == DossierAccess.Permission.WRITE
    return user.role in WRITE_ROLES


def can_manage_acl(user, document=None, dossier=None):
    """Droits de gestion des ACL : admin/staff ou créateur de l'objet."""
    if is_admin_or_staff(user):
        return True
    if document is not None and document.created_by_id == user.id:
        return True
    if dossier is not None and dossier.created_by_id == user.id:
        return True
    return False
