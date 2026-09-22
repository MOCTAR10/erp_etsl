from django.contrib import admin

from .models import (
    BulletinLigne,
    BulletinPaie,
    ContratTravail,
    DemandeRecrutement,
    DemandesConge,
    Employe,
    Formation,
    Qualification,
    RhPaieSequence,
    RubriquePaie,
    SaisieTemps,
    Sanction,
)

admin.site.register(
    Employe,
    list_display=("code", "nom", "prenom", "categorie", "departement", "statut", "date_embauche"),
    list_filter=("statut", "categorie", "departement"),
    search_fields=("code", "nom", "prenom"),
)
admin.site.register(
    ContratTravail,
    list_display=("code", "employe", "type", "statut", "date_debut", "date_fin"),
    list_filter=("type", "statut"),
)
admin.site.register(Qualification, list_display=("code", "employe", "type", "intitule", "date_validite"))
admin.site.register(
    DemandeRecrutement,
    list_display=("code", "poste", "type", "statut", "created_at"),
    list_filter=("type", "statut"),
)
admin.site.register(
    Formation,
    list_display=("code", "theme", "organisme", "date_session", "type"),
    list_filter=("type",),
)
admin.site.register(
    DemandesConge,
    list_display=("code", "employe", "type", "date_debut", "date_fin", "nb_jours", "statut"),
    list_filter=("type", "statut"),
)
admin.site.register(
    Sanction,
    list_display=("code", "employe", "type", "date_constat", "statut"),
    list_filter=("type", "statut"),
)
admin.site.register(
    SaisieTemps,
    list_display=("code", "employe", "date", "heures", "type", "statut"),
    list_filter=("type", "statut"),
)
admin.site.register(RubriquePaie, list_display=("code", "label", "nature", "base", "taux", "ordre"))
admin.site.register(
    BulletinPaie,
    list_display=("code", "employe", "periode", "brut", "net", "statut"),
    list_filter=("periode", "statut"),
)
admin.site.register(
    BulletinLigne,
    list_display=("bulletin", "rubrique", "libelle", "montant"),
)
admin.site.register(RhPaieSequence, list_display=("kind", "prefix", "padding", "next_number"))