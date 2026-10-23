"""Vitrine — terrain : consommations de stock imputées aux affaires (M5), parc et maintenance (M4 / M8), HSE (M7),
qualité (M6).

Consommations : API réelle (mouvement de stock imputé à l'OF et au compte analytique de l'affaire). Les autres objets
de terrain (OT, inspections, incidents, permis, causeries, contrôles, NC, PV) sont posés par l'ORM avec les mêmes
champs et statuts que les seeds par module, datés sur 12 mois (codes servis par les séquences dans `save()`).
"""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction

from hse.models import ActionHse, FormationSecurite, Incident, PermisTravail
from logistique.models import EquipementParc
from maintenance.models import Actif, Inspection, OrdreTravail
from operations.models import OrdreFabrication
from qualite.models import ActionCorrective, ControleQualite, NonConformite, PvControle, Soudeur
from stocks.models import MouvementStock, StockQuant

from .donnees import ACTIFS
from .outils import MOIS, ajouter_mois, alea, antidater, debut_mois, fin_mois, instant, jour_du_mois, ouvre

LOG = "logistique@etls.local"

# Incidents HSE des 12 derniers mois : (mois avant, jour, type, gravité, conséquence, jours d'arrêt, lieu, description)
INCIDENTS = [
    (11, 14, "quasi_accident", "mineure", "aucune", 0, "Atelier Port-Gentil", "Chute d'une élingue non verrouillée lors d'un levage de spool"),
    (11, 24, "accident", "majeure", "arret", 6, "Chantier manifold Banio", "Entorse à la cheville en descendant d'un échafaudage"),
    (10, 6, "situation_dangereuse", "mineure", "aucune", 0, "Chantier réseau Ogooué", "Tranchée non balisée en bordure de piste"),
    (9, 22, "blessure", "mineure", "premiers_secours", 0, "Atelier Port-Gentil", "Coupure superficielle à la main lors d'un meulage"),
    (8, 11, "dommage_materiel", "mineure", "aucune", 0, "Chantier manifold Banio", "Chute d'un outil depuis un échafaudage, sans blessé"),
    (7, 3, "quasi_accident", "mineure", "aucune", 0, "Dépôt Port-Gentil", "Chariot télescopique en marche arrière sans guide"),
    (6, 19, "deversement", "majeure", "aucune", 0, "Base logistique Libreville", "Déversement de 60 L de gasoil lors d'un dépotage"),
    (5, 8, "dommage_materiel", "mineure", "aucune", 0, "Atelier Port-Gentil", "Choc d'un pont roulant contre un rack de stockage"),
    (4, 27, "quasi_accident", "mineure", "aucune", 0, "Chantier dépôt d'Akanda", "Bouteille d'oxygène non arrimée sur le plateau"),
    (3, 15, "depart_feu", "majeure", "aucune", 0, "Chantier unité de traitement de gaz", "Départ de feu sur bâche de protection lors d'un soudage"),
    (2, 2, "blessure", "mineure", "premiers_secours", 0, "Chantier unité de traitement de gaz", "Projection de laitier sur l'avant-bras, soins sur place"),
    (1, 18, "situation_dangereuse", "mineure", "aucune", 0, "Atelier Libreville", "Rallonge électrique endommagée sur poste de meulage"),
    (0, 9, "quasi_accident", "mineure", "aucune", 0, "Chantier réseau Ogooué", "Glissement d'un tube lors du bardage"),
]

PERMIS_TYPES = ("chaud", "hauteur", "levage", "confine", "electrique", "atex")
CAUSERIES = ("Travaux à chaud et vigie incendie", "Levage : élingage et zone d'exclusion", "Chutes de plain-pied",
             "Port du harnais et points d'ancrage", "Risques électriques sur chantier", "Fatigue et chaleur",
             "Espaces confinés : détection gaz", "Conduite d'engins et circulation", "Rangement et propreté",
             "Gestes et postures", "EPI : état et remplacement", "Retour d'expérience des incidents du mois")


class VitrineTerrain:
    # -- stocks ------------------------------------------------------------------------------------------------
    def consommations(self):
        for k in range(MOIS - 1, -1, -1):
            mois = debut_mois(self.today, k)
            for affaire in self.affaires_vitrine.values():
                if affaire.is_global_rental or not (affaire.start_date <= fin_mois(mois) and affaire.end_date >= mois):
                    continue
                ref = f"Vitrine conso {affaire.code} {mois:%Y-%m}"
                if MouvementStock.objects.filter(document_reference=ref).exists():
                    continue
                of = OrdreFabrication.objects.filter(affaire=affaire).first()
                quants = list(StockQuant.objects.filter(quantity__gte=4, article__code__in=(
                    "TUB-API5L-6", "TUB-INOX-4", "COU-6-90", "BRI-6-300", "ELE-E7018", "FIL-ER70S", "GAZ-ARGON", "PEI-EPOXY"))
                    .exclude(lot__certificats__date_validation__isnull=True)
                    .exclude(lot__certificats__conforme=False)
                    .order_by("-quantity", "article__code")[:6])
                if not quants or of is None:
                    continue
                quant = quants[(k + len(ref)) % len(quants)]
                quantite = max(1, int(quant.quantity * Decimal("0.45")))
                jour = min(ouvre(fin_mois(mois) - timedelta(days=3)), self.today - timedelta(days=1))
                data = {
                    "type_mouvement": "consommation", "article": str(quant.article_id), "quantite": str(quantite),
                    "source": str(quant.depot_id), "ordre": str(of.pk), "document_reference": ref, "date": str(jour),
                }
                if quant.lot_id:
                    data["lot"] = str(quant.lot_id)
                if affaire.analytic_id:
                    data["analytic"] = str(affaire.analytic_id)
                self.call(LOG, "post", "/api/stocks/mouvements/", data)

    # -- parc et maintenance -----------------------------------------------------------------------------------
    def maintenance(self):
        maint = self.user("maintenance@etls.local")
        actifs = []
        with transaction.atomic():
            for i, (designation, categorie, fabricant, modele, site, age, compteur) in enumerate(ACTIFS):
                actif = Actif.objects.filter(designation=designation).first()
                if actif is None:
                    service = ajouter_mois(self.today, -12 * age - i)
                    actif = Actif.objects.create(
                        designation=designation, categorie=categorie, fabricant=fabricant, modele=modele, site=site,
                        numero_serie=f"{fabricant[:2].upper()}-{24000 + 137 * i}", date_mise_en_service=service,
                        garanti_jusqu=self.today + timedelta(days=35 + 10 * i) if i in (1, 11) else ajouter_mois(service, 24),
                        compteur_type=compteur, compteur_value=Decimal(0 if compteur == "aucun" else 1800 * age + 95 * i),
                    )
                    antidater(Actif, actif.pk, created_at=instant(self.today - timedelta(days=365)))
                actifs.append(actif)
            self._parc()
        for i, actif in enumerate(actifs):
            with transaction.atomic():
                self._ordres_travail(i, actif, maint)
                self._inspections(i, actif, maint)
        # Deux arrêts en cours : un compresseur en panne (OT critique ouvert), un camion en maintenance.
        Actif.objects.filter(designation=ACTIFS[3][0], statut=Actif.Statut.OPERATIONNEL).update(statut=Actif.Statut.EN_PANNE)
        Actif.objects.filter(designation=ACTIFS[7][0], statut=Actif.Statut.OPERATIONNEL).update(statut=Actif.Statut.EN_MAINTENANCE)

    def _parc(self):
        for i, (label, categorie, statut, compteur, site) in enumerate((
            ("Grue mobile 50 t (parc)", "levage", "affecte", "heures", "Chantiers clients"),
            ("Camion plateau grue 10 t (parc)", "transport", "disponible", "km", "Base logistique Libreville"),
            ("Chariot télescopique 4 t (parc)", "engin", "affecte", "heures", "Dépôt Port-Gentil"),
            ("Nacelle articulée 16 m (parc)", "levage", "disponible", "heures", "Dépôt Port-Gentil"),
            ("Pick-up double cabine 4x4 n°3", "transport", "affecte", "km", "Port-Gentil"),
            ("Pick-up double cabine 4x4 n°4", "transport", "maintenance", "km", "Libreville"),
            ("Conteneur atelier mobile 20 pieds", "atelier", "affecte", "forfait", "Chantiers clients"),
        )):
            if not EquipementParc.objects.filter(label=label).exists():
                EquipementParc.objects.create(
                    label=label, categorie=categorie, statut=statut, compteur_type=compteur, site=site,
                    registration=f"{3100 + 41 * i} G{'AB'[i % 2]} {('01', '02')[i % 2]}" if categorie == "transport" else "",
                    compteur_value=Decimal(0 if compteur == "forfait" else 4200 + 870 * i),
                )

    def _ordres_travail(self, i, actif, maint):
        if OrdreTravail.objects.filter(actif=actif, description__startswith="[Vitrine]").exists():
            return
        r = alea(f"ot-{actif.designation}")
        ots = []
        pas = 2 if actif.compteur_type != "aucun" else 4
        for k in range(MOIS - 1 - i % pas, -1, -pas):  # préventif périodique
            ots.append((k, "preventif", "moyenne", "Maintenance préventive périodique (vidange, filtres, contrôle général)", ""))
        for k in sorted(r.sample(range(0, MOIS), 1 + (i % 3 == 0)), reverse=True):  # pannes
            ots.append((k, "correctif", r.choice(("haute", "moyenne")), r.choice((
                "Panne d'alimentation : remplacement du contacteur principal",
                "Fuite hydraulique sur vérin : remplacement des joints",
                "Défaut de démarrage : remplacement de la batterie et du démarreur",
                "Usure des balais et du collecteur : remise en état")), "Usure normale constatée"))
        if i == 3:
            ots.append((0, "urgence", "critique", "Arrêt compresseur sur chantier : surchauffe et perte de pression", ""))
        for n, (k, nature, priorite, description, cause) in enumerate(ots):
            demande = ouvre(jour_du_mois(self.today, k, 4 + (7 * n + 3 * i) % 22))
            clos = k >= 1 or (k == 0 and n % 3 == 0 and nature == "preventif")
            statut = OrdreTravail.Statut.CLOTURE if clos else (
                OrdreTravail.Statut.EN_COURS if nature != "preventif" else OrdreTravail.Statut.PLANIFIE)
            heures = Decimal(r.choice((3, 4, 6, 8, 12)) if nature != "preventif" else r.choice((2, 3, 4)))
            ot = OrdreTravail.objects.create(
                actif=actif, type_ot=nature, priorite=priorite, description=f"[Vitrine] {description}", cause=cause,
                demandeur=maint, technicien=maint, date_demande=demande, date_planifiee=demande + timedelta(days=2),
                date_debut=instant(demande + timedelta(days=2), 8) if statut != OrdreTravail.Statut.PLANIFIE else None,
                date_fin=instant(demande + timedelta(days=3), 16) if clos else None,
                heures_mo=heures if clos else Decimal(0), tarif_horaire=Decimal(9500),
                cout_pieces=Decimal(r.choice((0, 45_000, 120_000, 380_000))) if clos else Decimal(0),
                rapport="Intervention réalisée, essais satisfaisants, remise en service." if clos else "",
                statut=statut, created_by=maint,
            )
            antidater(OrdreTravail, ot.pk, created_at=instant(demande, 8))

    def _inspections(self, i, actif, maint):
        if actif.categorie != "levage" or Inspection.objects.filter(actif=actif, type_inspection="levage").exists():
            return
        derniere = self.today - timedelta(days=345 - 30 * i % 60)
        Inspection.objects.create(
            actif=actif, type_inspection="levage", date_inspection=derniere, prochaine_inspection=derniere + timedelta(days=365),
            organisme="tiers", organisme_libelle="Organisme de contrôle agréé", resultat="conforme",
            constat="Vérification générale périodique satisfaisante.", intervenant=maint, statut="realisee",
        )

    # -- HSE -----------------------------------------------------------------------------------------------------
    def hse(self):
        hse = self.user("hse@etls.local")
        with transaction.atomic():
            for k, jour, nature, gravite, consequence, arret, lieu, description in INCIDENTS:
                if Incident.objects.filter(description=description).exists():
                    continue
                quand = instant(jour_du_mois(self.today, k, jour), 10 + jour % 6)
                clos = k >= 2
                incident = Incident.objects.create(
                    type_incident=nature, gravite=gravite, date_evenement=quand, lieu=lieu, description=description,
                    consequence_humaine=consequence, jours_arret=arret,
                    cause_immediate="Analyse sur le terrain par l'animateur HSE.",
                    statut=Incident.Statut.CLOTURE if clos else (Incident.Statut.EN_ENQUETE if k == 1 else Incident.Statut.DECLARE),
                    archive=clos, declared_by=hse, enqueteur=hse if k <= 1 or clos else None,
                    date_ouverture_enquete=quand + timedelta(days=1), date_rapport=(quand + timedelta(days=9)).date() if clos else None,
                    rapport="Causes analysées (arbre des causes), actions engagées et vérifiées." if clos else "",
                )
                antidater(Incident, incident.pk, created_at=quand)
                ActionHse.objects.create(
                    incident=incident, type="corrective", description=f"Action corrective : {description[:120]}",
                    responsable=hse, echeance=(quand + timedelta(days=20)).date(),
                    statut=ActionHse.Statut.CLOTUREE if clos else ActionHse.Statut.EN_COURS,
                )
            demandeur = self.user("atelier@etls.local")
            for k in range(MOIS - 1, -1, -1):
                for n in range(3):
                    description = f"Permis {PERMIS_TYPES[(k + n) % 6]} - intervention {debut_mois(self.today, k):%m/%Y} n°{n + 1}"
                    if PermisTravail.objects.filter(description=description).exists():
                        continue
                    debut = ouvre(jour_du_mois(self.today, k, 5 + 8 * n))
                    actif = k == 0 and n < 2
                    permis = PermisTravail.objects.create(
                        type_permis=PERMIS_TYPES[(k + n) % 6], emplacement=("Atelier Port-Gentil", "Chantier client", "Base Libreville")[n],
                        description=description, mesures="Analyse de risques, balisage, EPI spécifiques, surveillant",
                        demandeur=demandeur, validateur=hse, date_debut=debut, date_fin=debut + timedelta(days=3 if not actif else 20),
                        statut=PermisTravail.Statut.ACTIF if actif else PermisTravail.Statut.CLOTURE,
                        date_validation=instant(debut, 7), date_cloture=None if actif else instant(debut + timedelta(days=3), 17),
                    )
                    antidater(PermisTravail, permis.pk, created_at=instant(debut - timedelta(days=1), 15))
                theme = f"Causerie sécurité - {CAUSERIES[k % len(CAUSERIES)]}"
                quand = ouvre(jour_du_mois(self.today, k, 2))
                if not FormationSecurite.objects.filter(theme=theme, date_session=quand).exists():
                    FormationSecurite.objects.create(
                        type_session="causerie", theme=theme, formateur="Animatrice HSE", date_session=quand, duree_heures=1,
                        nb_participants=18 + (k * 7) % 15, evalue=True, statut=FormationSecurite.Statut.REALISEE,
                    )
            prochaine = self.today + timedelta(days=9)
            if not FormationSecurite.objects.filter(theme="Recyclage sauveteurs secouristes du travail").exists():
                FormationSecurite.objects.create(
                    type_session="recyclage", theme="Recyclage sauveteurs secouristes du travail", formateur="Croix-Rouge gabonaise",
                    date_session=prochaine, duree_heures=7, statut=FormationSecurite.Statut.PLANIFIEE,
                )

    # -- qualité -------------------------------------------------------------------------------------------------
    def qualite(self):
        qa = self.user("qaqc@etls.local")
        soudeurs = list(Soudeur.objects.filter(employe__isnull=False).order_by("code"))
        for affaire in self.affaires_vitrine.values():
            if affaire.is_global_rental:
                continue
            of = OrdreFabrication.objects.filter(affaire=affaire).first()
            if ControleQualite.objects.filter(affaire=affaire, point_controle__startswith="[Vitrine]").exists():
                continue
            r = alea(f"qualite-{affaire.code}")
            with transaction.atomic():
                mois = debut_mois(affaire.start_date, 0)
                n = 0
                while mois <= self.today and mois <= affaire.end_date:
                    for type_controle, methode in (("visuel", ""), ("cnd", r.choice(("RT", "UT", "PT", "MT"))), ("dimensionnel", "")):
                        n += 1
                        jour = min(ouvre(mois.replace(day=8 + (n * 5) % 18)), self.today - timedelta(days=1))
                        resultat = "non_conforme" if r.random() < 0.08 else ("reserve" if r.random() < 0.08 else "conforme")
                        recent = jour > self.today - timedelta(days=10)
                        ctrl = ControleQualite.objects.create(
                            type_controle=type_controle, methode_cnd=methode,
                            organisme="agrege" if type_controle == "cnd" else "interne",
                            organisme_libelle="CND Afrique Centrale" if type_controle == "cnd" else "",
                            affaire=affaire, ordre=of, point_controle=f"[Vitrine] {type_controle.upper()} joints lot {n:02d}",
                            date_controle=jour, **({} if recent else {"resultat": resultat}),
                            statut=ControleQualite.Statut.EN_COURS if recent else ControleQualite.Statut.VALIDE, created_by=qa,
                        )
                        antidater(ControleQualite, ctrl.pk, created_at=instant(jour, 10))
                        if resultat == "non_conforme" and not recent:
                            self._non_conformite(ctrl, jour, qa, soudeurs, r)
                    mois = ajouter_mois(mois, 1)
                if affaire.status == "cloturee" and not PvControle.objects.filter(affaire=affaire).exists():
                    PvControle.objects.create(
                        affaire=affaire, ordre=of, intitule=f"PV de réception {affaire.title}"[:200], date_pv=affaire.end_date,
                        statut=PvControle.Statut.RECEPTIONNE, resultat="conforme", levee_reserve=affaire.end_date,
                        validated_by=qa, notes="Réception prononcée sans réserve.",
                    )

    def _non_conformite(self, ctrl, jour, qa, soudeurs, r):
        ancien = jour < self.today - timedelta(days=45)
        nc = NonConformite.objects.create(
            controle=ctrl, source="controle", gravite=r.choice(("mineure", "majeure", "majeure", "critique")),
            description=f"Défaut constaté au contrôle {ctrl.get_type_controle_display().lower()} : "
                        + r.choice(("porosités en passe de finition", "manque de pénétration localisé",
                                    "écart dimensionnel hors tolérance", "caniveau en pied de cordon")),
            traitement=r.choice(("reprise", "reparation")),
            statut=NonConformite.Statut.CLOTUREE if ancien else NonConformite.Statut.EN_TRAITEMENT,
            decided_by=qa, date_decision=jour + timedelta(days=1), archive=ancien,
        )
        antidater(NonConformite, nc.pk, created_at=instant(jour, 15))
        ActionCorrective.objects.create(
            non_conformite=nc, type="corrective", description="Reprise du joint et recontrôle par la même méthode.",
            responsable=qa, echeance=jour + timedelta(days=10),
            statut=ActionCorrective.Statut.CLOTUREE if ancien else ActionCorrective.Statut.EN_COURS,
            efficace=True if ancien else None, closed_at=instant(jour + timedelta(days=9), 16) if ancien else None,
        )
