"""Rattachement automatique au site ETSL (EX-G-03) : texte libre reconnu, OF héritant du site de son affaire."""

from django.db.models.signals import pre_save
from django.dispatch import receiver

from .sites import site_pour_texte


def _par_texte(sender, instance, **kwargs):
    if getattr(instance, "site_etsl_id", None) is None and getattr(instance, "site", ""):
        instance.site_etsl_id = site_pour_texte(instance.site)


def brancher():
    from django.apps import apps

    for label in ("stocks.Depot", "logistique.EquipementParc", "maintenance.Actif", "rh_paie.Employe"):
        pre_save.connect(_par_texte, sender=apps.get_model(label), dispatch_uid=f"site_etsl_{label}")

    @receiver(pre_save, sender=apps.get_model("operations.OrdreFabrication"), dispatch_uid="site_etsl_of")
    def _of(sender, instance, **kwargs):
        if instance.site_etsl_id is None and instance.affaire_id:
            instance.site_etsl_id = (
                apps.get_model("commercial.Affaire").objects.filter(pk=instance.affaire_id).values_list("site_etsl", flat=True).first()
            )
