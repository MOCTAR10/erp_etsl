"""Amont M6 → M9 : chaque qualification soudeur d'un salarié est recopiée dans son dossier RH."""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from qualite.models import QualificationSoudeur, Soudeur


@receiver(post_save, sender=QualificationSoudeur, dispatch_uid="m9c_sync_qualif_soudeur")
def _sync_qualif(sender, instance, raw=False, **kwargs):
    if raw:
        return
    from .formation_m9c import synchroniser_qualification_soudeur

    synchroniser_qualification_soudeur(instance)


@receiver(post_save, sender=Soudeur, dispatch_uid="m9c_sync_soudeur")
def _sync_soudeur(sender, instance, raw=False, **kwargs):
    if raw:
        return
    from .formation_m9c import synchroniser_soudeur

    synchroniser_soudeur(instance)


@receiver(post_delete, sender=QualificationSoudeur, dispatch_uid="m9c_suppr_qualif_soudeur")
def _suppr_qualif(sender, instance, **kwargs):
    from .models import Qualification

    Qualification.objects.filter(source=Qualification.Source.M6, source_ref=str(instance.pk)).delete()
