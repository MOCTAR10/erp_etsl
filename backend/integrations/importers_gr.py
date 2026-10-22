"""Échanges GLOBAL RENTAL par fichiers (décision D25 : accès au système GR incertain → fichiers CSV / XML).

Trois gabarits RÉCURRENTS (et non de reprise ponctuelle), servis par le même moteur que la reprise (`/reprise`,
`importers_migration.executer_lot`) : validation à blanc, transaction par fichier, rapport d'anomalies, seuil
d'erreur, rejeu d'un fichier déjà chargé refusé sauf forçage, clé métier par ligne (doublon = ligne ignorée) :

- `gr_lectures_compteurs` : lectures de compteur des prestations GR (BCI_GR) — mêmes règles que l'API
  `/api/integrations/gr/compteurs/` (prestation active, jamais en baisse, date non future) → compteur du parc + M8 ;
- `gr_bl` : réceptions de BL GR (une ligne de fichier = une ligne de prestation livrée) → `receptionner_bl`
  (écarts, escalade M12 au-delà du seuil) ;
- `gr_factures` : factures GLOBAL RENTAL → facture fournisseur M2 sur le BC GR de la prestation (compte 618, tiers
  `is_global_rental` obligatoire), rapprochée du montant attendu (`rapprocher_facture`, tolérance paramétrée).

Formats provisoires, à confirmer ou modifier par ETSL (QUE 152 : qui fournit les fichiers, fréquence, format).
"""

from datetime import date

from .importers_migration import Colonne as C, Gabarit, LigneErreur, _bool, _choix, _date, _dec, _req, _txt
from config.i18n import tr


def _service(fonction, *args, **kwargs):
    """Appelle un service métier (qui lève la `ValidationError` DRF) : l'anomalie devient une erreur de ligne."""
    from rest_framework.exceptions import ValidationError

    try:
        return fonction(*args, **kwargs)
    except ValidationError as exc:
        detail = exc.detail
        if isinstance(detail, dict):
            detail = [str(v) if k == "detail" else f"{k} : {v}"
                      for k, vs in detail.items() for v in (vs if isinstance(vs, list) else [vs])]
        raise LigneErreur(" ".join(str(x) for x in (detail if isinstance(detail, list) else [detail])))


def _location_gr(row):
    from logistique.models import LocationGR

    code = _req(row, "location", 20)
    location = LocationGR.objects.select_for_update(of=("self",)).select_related("partenaire", "equipement").filter(code=code).first()
    if location is None:
        raise LigneErreur(tr("Prestation %(code)s inconnue.") % {"code": code})
    if not location.partenaire.is_global_rental:
        raise LigneErreur("partenaire de la prestation non marqué GLOBAL RENTAL (compte 618).")
    return location


# --------------------------------------------------------------------------------------------- lectures de compteur
def _gr_lectures(row, ctx):
    from logistique.models import LectureCompteur

    location = _location_gr(row)
    jour, valeur = _date(row, "date", obligatoire=True), _dec(row, "valeur", obligatoire=True)
    cle = f"{location.code}/{jour:%Y-%m-%d}/{valeur}"
    if location.lectures.filter(date=jour, valeur=valeur).exists():
        return "doublon", cle
    type_lecture = _choix(row, "type_lecture", [c for c in LectureCompteur.TypeLecture.choices if c[0] != "finale"],
                          defaut=LectureCompteur.TypeLecture.PERIODIQUE)
    from logistique.services import enregistrer_lecture_gr

    _service(enregistrer_lecture_gr, location, jour, valeur, type_lecture, ctx.user)
    return "creee", cle


# --------------------------------------------------------------------------------------------- BL GR
def _gr_bl(row, ctx):
    """Une ligne de fichier = une ligne de prestation livrée ; toutes les lignes d'un même BL sont traitées ensemble,
    à la première rencontrée (la réception calcule les écarts sur l'ensemble des lignes de la prestation)."""
    from logistique.models import ReceptionBLGR
    from logistique.services import receptionner_bl

    location = _location_gr(row)
    reference = _req(row, "reference_bl", 40)
    cle = f"{location.code}/{reference}"
    traites = ctx.memo.setdefault("bl_traites", {})
    if cle in traites:
        return "maj", f"{cle} → {traites[cle]}"
    existante = ReceptionBLGR.objects.filter(location=location, reference_bl=reference).first()
    if existante is not None:
        return "doublon", f"{cle} → {existante.code}"
    groupe = [r for r in (ctx.lignes or [row])
              if _txt(r, "location") == location.code and _txt(r, "reference_bl") == reference] or [row]
    lignes = list(location.lignes.all())
    for r in groupe:
        designation = _txt(r, "ligne", 200)
        if designation:
            cible = [x for x in lignes if x.designation.strip().lower() == designation.lower()]
        else:
            cible = lignes if len(lignes) == 1 else []
        if len(cible) != 1:
            raise LigneErreur(tr("ligne de prestation introuvable ou ambiguë (%(ligne)s) : précisez la colonne « ligne » (désignation exacte).") % {"ligne": designation or "vide"})
        quantite = _dec(r, "quantite_livree")
        if quantite is not None:
            cible[0].quantite_livree = quantite
            cible[0].save(update_fields=["quantite_livree"])
    jour = _date(row, "date_reception", obligatoire=True)
    if jour > date.today():
        raise LigneErreur("date_reception dans le futur.")
    reception = _service(receptionner_bl, location, ctx.user, reference, jour,
                                reserves=" ".join(_txt(r, "reserves", 500) for r in groupe).strip()[:2000],
                                litige=any(_bool(r, "litige", False) for r in groupe))
    traites[cle] = reception.code
    return "creee", f"{cle} → {reception.code}"


# --------------------------------------------------------------------------------------------- factures GR
def _gr_factures(row, ctx):
    from achats.models import PurchaseInvoice, PurchaseInvoiceLine
    from logistique.services import rapprocher_facture

    location = _location_gr(row)
    numero = _req(row, "numero", 100)
    cle = f"{location.partenaire.code}/{numero}"
    if PurchaseInvoice.objects.filter(supplier=location.partenaire, invoice_ref=numero).exists():
        return "doublon", cle
    bc = location.bon_commande_achat
    if bc is None or not bc.is_global_rental:
        raise LigneErreur(tr("aucun BC GLOBAL RENTAL lié à la prestation %(code)s : générez-le depuis la location (Achats).") % {"code": location.code})
    ligne_bc = bc.lines.order_by("pk").first()
    if ligne_bc is None:
        raise LigneErreur(tr("BC %(code)s sans ligne.") % {"code": bc.code})
    montant = _dec(row, "montant_ht", obligatoire=True)
    if montant <= 0:
        raise LigneErreur("montant_ht doit être strictement positif.")
    facture = PurchaseInvoice.objects.create(
        purchase_order=bc, supplier=location.partenaire, invoice_ref=numero, invoice_date=_date(row, "date", obligatoire=True),
        currency=bc.currency,
    )
    PurchaseInvoiceLine.objects.create(invoice=facture, purchase_order_line=ligne_bc, quantity=1, unit_price=montant)
    _service(rapprocher_facture, location, facture)
    return "creee", f"{cle} → {facture.code}"


# --------------------------------------------------------------------------------------------- catalogue
NOTE_D25 = "Échange récurrent GLOBAL RENTAL (D25) — format provisoire, à confirmer ou modifier par ETSL (QUE 152). "

GABARITS_GR = [
    Gabarit("gr_lectures_compteurs", "GLOBAL RENTAL — lectures de compteur des prestations", "D25", "location + date + valeur", [
        C("location", True, "Code de la prestation GR (LocationGR)", "LGR-0001"), C("date", True, "AAAA-MM-JJ", "2026-11-30"),
        C("valeur", True, "Heures / km (jamais en baisse)", "1320"),
        C("type_lecture", False, "periodique / initiale", "periodique"),
    ], _gr_lectures, cercle="gr",
        note=NOTE_D25 + "Mêmes règles que l'API GR : prestation active, date non future, compteur jamais en baisse ; "
                        "le compteur du parc et les seuils préventifs M8 sont mis à jour."),
    Gabarit("gr_bl", "GLOBAL RENTAL — réceptions de BL", "D25", "location + reference_bl", [
        C("location", True, "Code de la prestation GR", "LGR-0001"), C("reference_bl", True, "N° du BL GR", "BL-GR-2026-118"),
        C("date_reception", True, "AAAA-MM-JJ", "2026-11-05"),
        C("ligne", False, "Désignation exacte de la ligne de prestation (vide si une seule ligne)", ""),
        C("quantite_livree", False, "Vide = quantité commandée", "1"),
        C("reserves", False, "Réserves à la réception", ""), C("litige", False, "oui / non (escalade M12)", "non"),
    ], _gr_bl, cercle="gr",
        note=NOTE_D25 + "Une ligne de fichier par ligne de prestation livrée ; un BL déjà réceptionné est ignoré. "
                        "Écart global au-delà du seuil paramétré (Logistique) = litige escaladé en M12."),
    Gabarit("gr_factures", "GLOBAL RENTAL — factures (compte 618)", "D25", "partenaire GR + numero", [
        C("location", True, "Code de la prestation GR", "LGR-0001"), C("numero", True, "N° de facture GR", "FGR-2026-0412"),
        C("date", True, "Date de facture AAAA-MM-JJ", "2026-11-30"), C("montant_ht", True, "Montant HT", "4500000"),
    ], _gr_factures, cercle="compta",
        note=NOTE_D25 + "Facture fournisseur créée sur le BC GLOBAL RENTAL de la prestation (tiers is_global_rental, "
                        "compte 618), rapprochée du montant attendu (tolérance paramétrée) ; comptabilisation par le "
                        "circuit habituel des Achats / de la Comptabilité."),
]
