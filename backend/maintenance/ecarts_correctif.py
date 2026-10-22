"""Lot correctif — une seule charge 618 pour la maintenance d'un équipement GLOBAL RENTAL.

Deux voies pouvaient porter la même prestation au 618000 : l'OD passée par M8 à la clôture d'un OT GR
(`ecarts_m5m8.comptabiliser_ot`) et la facture d'achat GLOBAL RENTAL comptabilisée par M2 (Dr 618 / Cr 401100).
Règle unique (même principe que les locations M4 / BC GR) : **la facture d'achat GR porte la charge**. Un OT GR
rattaché à un BC GR (`OrdreTravail.bc_gr`) ne passe pas d'OD à la clôture ; s'il a déjà été clôturé et comptabilisé,
le rattachement extourne l'OD (contre-écriture datée du jour, jamais de suppression). Le coût de l'OT reste suivi
analytiquement (centre, coûts annuels, événement outbox M11) sans charge comptable. Un OT GR sans BC rattaché garde
l'OD 618 (prestation non facturée par GLOBAL RENTAL).
"""

from django.core.exceptions import ValidationError
from django.utils import timezone

from .ecarts_m5m8 import est_gr
from config.i18n import tr


def bc_gr_candidats():
    from achats.models import PurchaseOrder

    qs = (PurchaseOrder.objects.filter(is_global_rental=True).exclude(status=PurchaseOrder.Status.ANNULEE)
          .select_related("supplier").order_by("-created_at")[:200])
    return [{"id": str(bc.pk), "code": bc.code, "fournisseur": bc.supplier.name if bc.supplier_id else "",
             "statut": bc.status} for bc in qs]


def lier_bc_gr(ot, bc_id, user=None):
    """Rattache un BC GR à l'OT GR (verrouillé par l'appelant) ; extourne l'OD 618 déjà passée. Retourne l'OT."""
    from accounting_kernel.models import AccountMove
    from accounting_kernel.services import reverse_move
    from achats.models import PurchaseOrder

    if not est_gr(ot.actif):
        raise ValidationError("Seul un OT sur un équipement GLOBAL RENTAL (ou signé 618) se rattache à un BC GR.")
    try:
        bc = PurchaseOrder.objects.get(pk=bc_id) if bc_id else None
    except (PurchaseOrder.DoesNotExist, ValueError, ValidationError):
        bc = None
    if bc is None:
        raise ValidationError("BC introuvable.")
    if not bc.is_global_rental:
        raise ValidationError(tr("Le BC %(bc_code)s n'est pas un BC GLOBAL RENTAL (compte 618).") % {"bc_code": bc.code})
    if bc.status == PurchaseOrder.Status.ANNULEE:
        raise ValidationError(tr("Le BC %(bc_code)s est annulé.") % {"bc_code": bc.code})
    if ot.bc_gr_id:
        raise ValidationError(tr("OT déjà rattaché au BC %(bc_gr_code)s.") % {"bc_gr_code": ot.bc_gr.code})
    ot.bc_gr = bc
    champs = ["bc_gr", "updated_at"]
    if ot.ecriture_id and ot.ecriture.status == AccountMove.Status.POSTED:
        extourne = reverse_move(
            ot.ecriture, user=user, date=timezone.localdate(), reference=f"Extourne {ot.ecriture.number}",
            label=f"Extourne coût OT {ot.code} : charge 618 portée par la facture GR du BC {bc.code}"[:200],
        )
        ot.motif_ecriture = (f"OD {ot.ecriture.number} extournée ({extourne.number}) : charge 618 portée par la "
                             f"facture GLOBAL RENTAL du BC {bc.code}.")[:255]
        champs.append("motif_ecriture")
    elif ot.statut in ot.STATUTS_SCELLES:  # clôturé sans OD (motif conservé) : la facture GR portera la charge
        ot.motif_ecriture = (f"Charge 618 portée par la facture GLOBAL RENTAL du BC {bc.code} : "
                             "pas d'écriture OD (pas de double charge).")[:255]
        champs.append("motif_ecriture")
    ot.save(update_fields=champs)
    return ot
