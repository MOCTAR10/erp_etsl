"""Lot C du seed « parcours démo » : GLOBAL RENTAL (grille versionnée, retour en retard + pénalité) -> préventif M8 ;
qualité M6 (ITP, joints, CND, instruments, libération d'OF) ; HSE M7 (exigences d'habilitation, DUER, audit) ; stocks.

Même méthode que les lots A et B : API réelle, comptes démo. À lancer APRÈS `seed_parcours_demo`.
Idempotent (repérage par libellé / affaire / équipement). Valeurs = DONNÉES DE DÉMONSTRATION. ASCII-safe en sortie.
"""

from datetime import timedelta

from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from commercial.management.commands.seed_parcours_demo import PREFIXE, Command as ParcoursA
from commercial.models import Affaire
from logistique.models import EquipementParc, LocationGR, TarifGR
from maintenance.models import Actif, OrdreTravail, PlanPreventif
from referentiels.models import Currency, Partner


class Command(ParcoursA):
    help = "Seed parcours demo lot C : GR (grille, penalite, preventif M8), qualite M6, HSE M7, stocks (via API)."

    def handle(self, *args, **options):
        with override_settings(ALLOWED_HOSTS=["testserver", "localhost"]):
            self._run()

    def _run(self):
        from users.management.commands.seed_all_demo import _sync_sequences

        _sync_sequences()
        self.clients = {}
        self.today = timezone.localdate()
        self.parcours_gr()
        self.parcours_qualite()
        self.parcours_hse()
        self.parcours_stocks()
        self.stdout.write(self.style.SUCCESS("Parcours lot C pret."))

    # -- M4 -> M8 : grille GR, retour en retard, préventif ---------------------------------------------------
    def _tarif(self, partenaire, equipement, jours_effet, tarif, penalite):
        date_effet = self.today - timedelta(days=jours_effet)
        if TarifGR.objects.filter(partenaire=partenaire, equipement=equipement, date_effet=date_effet).exists():
            return
        self.call("logistique@etls.local", "post", "/api/logistique/tarifs-gr/", {
            "partenaire": str(partenaire.pk), "equipement": str(equipement.pk), "periodicite": "jour",
            "tarif": str(tarif), "penalite_jour": str(penalite), "date_effet": str(date_effet),
        })

    def _actif_gr(self, equipement):
        actif = Actif.objects.filter(equipement_gr=equipement).first()
        if actif is None:
            actif = Actif.objects.get(pk=self.call("atelier@etls.local", "post", "/api/maintenance/actifs/", {
                "designation": f"{equipement.label} (actif GR)", "categorie": "engin", "is_global_rental": True,
                "equipement_gr": str(equipement.pk), "compteur_type": "heures", "site": equipement.site or "Libreville",
            })["id"])
        return actif

    def _plan(self, actif, libelle, **kw):
        if PlanPreventif.objects.filter(actif=actif, libelle=libelle).exists():
            return
        self.call("atelier@etls.local", "post", "/api/maintenance/plans/", {
            "actif": str(actif.pk), "libelle": libelle, **{k: str(v) for k, v in kw.items()},
        })

    def parcours_gr(self):
        partenaire = Partner.objects.get(code="GR-2000")
        equipement = EquipementParc.objects.get(code="PAR00009")
        affaire = Affaire.objects.filter(title=PREFIXE + "Prestation GLOBAL RENTAL").first()
        if affaire is None:
            raise CommandError("Affaire GR du lot A absente : lancer seed_parcours_demo avant seed_parcours_c.")
        # Grille versionnée : la v2 (plus récente) est retenue pour une location démarrée après sa date d'effet.
        self._tarif(partenaire, equipement, 90, 150_000, 25_000)
        self._tarif(partenaire, equipement, 30, 165_000, 30_000)
        actif = self._actif_gr(equipement)
        # Seuil compteur : 840 h au départ, intervalle 50 h -> le retour à 900 h déclenche l'OT préventif (M4 -> M8).
        self._plan(actif, "Vidange et graissage (demo)", intervalle_compteur=50, dernier_compteur=840,
                   derniere_date=self.today - timedelta(days=20))
        if not LocationGR.objects.filter(equipement=equipement, affaire=affaire).exists():
            loc = self.call("logistique@etls.local", "post", "/api/logistique/locations/", {
                "partenaire": str(partenaire.pk), "equipement": str(equipement.pk), "affaire": str(affaire.pk),
                "periodicite": "jour", "devise": str(Currency.objects.get(code="XAF").pk), "imputation_618": True,
                "date_debut": str(self.today - timedelta(days=12)), "date_fin": str(self.today - timedelta(days=6)),
            })
            base = f"/api/logistique/locations/{loc['id']}"
            self.call("logistique@etls.local", "post", f"{base}/demarrer/", {"lecture_initiale": "840"})
            # Retour 3 jours après la date de fin prévue : pénalité = 3 x pénalité journalière de la version retenue.
            self.call("logistique@etls.local", "post", f"{base}/cloturer/", {
                "lecture_finale": "900", "date_retour": str(self.today - timedelta(days=3)),
            })
        # OT préventif auto-généré par le relevé de retour : planifié et laissé visible.
        for ot in OrdreTravail.objects.filter(actif=actif, type_ot="preventif", statut="demande"):
            self.call("atelier@etls.local", "post", f"/api/maintenance/ordres/{ot.pk}/planifier/", {
                "date_planifiee": str(self.today + timedelta(days=2)),
            })

    # -- M6 : instruments, ITP, joints, CND, épreuve, libération de l'OF atelier ------------------------------
    def _instrument(self, designation, serie, jours_echeance):
        from qualite.models import InstrumentMesure

        inst = InstrumentMesure.objects.filter(numero_serie=serie).first()
        if inst is None:
            data = self.call("qaqc@etls.local", "post", "/api/qualite/instruments/", {
                "designation": designation, "numero_serie": serie,
                "date_etalonnage": str(self.today - timedelta(days=365 - jours_echeance)),
                "echeance_etalonnage": str(self.today + timedelta(days=jours_echeance)),
            })
            inst = InstrumentMesure.objects.get(pk=data["id"])
        return inst

    def parcours_qualite(self):
        from operations.models import OrdreFabrication
        from qualite.models import ControleQualite, Soudeur, WpsWpqr

        qa = "qaqc@etls.local"
        # Affaire dediee : l'OF des spools du lot A reste ouvert (demonstration de la surcharge de capacite).
        affaire = self._affaire_confirmee("Fabrication supports atelier", "atelier", 30_000_000, 14)
        self._demarrer_affaire(affaire)
        of = self._of(affaire, 40)
        if of.status == OrdreFabrication.Status.LANCE:
            self.call("atelier@etls.local", "post", f"/api/operations/ordres/{of.pk}/demarrer/")
        if of.joints.exists():
            return
        # Instruments : un en service (échéance lointaine), un à étalonner sous 30 j, un bloqué (hors tolérance).
        manometre = self._instrument("Manomètre 0-100 bar", "MAN-DEMO-001", 180)
        self._instrument("Pied à coulisse 300 mm", "PAC-DEMO-002", 20)
        bloque = self._instrument("Jauge de soudure", "JAU-DEMO-003", 60)
        if bloque.statut == "actif":
            self.call(qa, "post", f"/api/qualite/instruments/{bloque.pk}/etalonner/", {"conforme": False, "certificat": "CERT-DEMO-NC"})
        wps = WpsWpqr.objects.filter(statut="valide", type="wps").first()
        if wps is None:
            wps = WpsWpqr.objects.filter(type="wps").first()
            # Un WPS se valide sur un WPQR (PQR) validé.
            wpqr = self.call(qa, "post", "/api/qualite/wps/", {
                "type": "wpqr", "reference": f"PQR-{wps.reference or wps.code}", "norme": wps.norme, "procede": wps.procede,
                "materiau": wps.materiau, "position": wps.position, "epaisseur": wps.epaisseur,
            })
            self.call(qa, "post", f"/api/qualite/wps/{wpqr['id']}/valider/")
            self.call(qa, "patch", f"/api/qualite/wps/{wps.pk}/", {"wpqr": wpqr["id"]})
            self.call(qa, "post", f"/api/qualite/wps/{wps.pk}/valider/")
        self.call(qa, "post", f"/api/qualite/wps/{wps.pk}/diffuser/", {"ordre": str(of.pk)})
        # ITP : 3 points (arret / observation / arret) -> approbation -> levée dans l'ordre.
        itp = self.call(qa, "post", "/api/qualite/controles/", {
            "type_controle": "itp", "affaire": str(of.affaire_id), "ordre": str(of.pk), "point_controle": f"ITP spools {of.code}",
        })
        for n, (desc, typ) in enumerate((("Vérification matière et coulées", "arret"), ("Fit-up avant soudage", "observation"),
                                         ("Contrôle final dimensionnel", "arret")), start=1):
            self.call(qa, "post", "/api/qualite/points-inspection/", {"controle": itp["id"], "ordre": n, "description": desc, "type_point": typ})
        self.call(qa, "post", f"/api/qualite/controles/{itp['id']}/approuver/")
        # Joints soudés (registre en inscription seule) : exigent l'ITP approuvé et un soudeur qualifié.
        soudeur = Soudeur.objects.get(code="SOU00001")
        from qualite.ecarts import qualification_couvrante

        if qualification_couvrante(soudeur, wps) is None:
            # Le soudeur se qualifie dans le domaine du WPS (procédé / position) avant de souder.
            self.call(qa, "post", "/api/qualite/qualifications/", {
                "soudeur": str(soudeur.pk), "norme": wps.norme, "procede": wps.procede, "position": wps.position or "6G",
                "date_qualification": str(self.today - timedelta(days=30)),
                "date_validite": str(self.today + timedelta(days=700)), "certificat": "QUAL-DEMO-WPS",
            })
        for n in (1, 2):
            self.call(qa, "post", "/api/qualite/joints/", {
                "ordre": str(of.pk), "repere": f"J-{n:03d}", "soudeur": str(soudeur.pk), "wps": str(wps.pk),
                "numero_coulee": f"COUL-DEMO-{n}", "consommable": "Électrode E7018",
            })
        for point in ControleQualite.objects.get(pk=itp["id"]).points.order_by("ordre"):
            self.call(qa, "post", f"/api/qualite/points-inspection/{point.pk}/lever/", {"resultat": "conforme", "commentaire": "OK"})
        self.call(qa, "patch", f"/api/qualite/controles/{itp['id']}/", {"statut": "valide", "resultat": "conforme"})
        # CND radiographie (RT) sur les joints, avec l'instrument en service.
        cnd = self.call(qa, "post", "/api/qualite/controles/", {
            "type_controle": "cnd", "methode_cnd": "RT", "affaire": str(of.affaire_id), "ordre": str(of.pk),
            "instrument": str(manometre.pk), "point_controle": "Radiographie joints J-001/J-002", "wps": str(wps.pk),
        })
        self.call(qa, "patch", f"/api/qualite/controles/{cnd['id']}/", {"statut": "valide", "resultat": "conforme"})
        # Épreuve hydraulique : 60 bar maintenus 30 min, chute max 2 bar.
        ep = self.call(qa, "post", "/api/qualite/epreuves/", {
            "ordre": str(of.pk), "instrument": str(manometre.pk), "type_epreuve": "hydraulique",
            "pression_essai": "60", "duree_minutes": 30, "chute_max": "2",
        })
        for minute, pression in ((0, "60.0"), (15, "59.6"), (30, "59.2")):
            self.call(qa, "post", f"/api/qualite/epreuves/{ep['id']}/releve/", {"minute": minute, "pression": pression, "temperature": "28"})
        self.call(qa, "post", f"/api/qualite/epreuves/{ep['id']}/conclure/")
        # Libération : l'OF est terminé puis libéré, seulement si tous les contrôles sont validés conformes.
        self.call("atelier@etls.local", "post", f"/api/operations/ordres/{of.pk}/terminer/")
        self.call("atelier@etls.local", "post", f"/api/operations/ordres/{of.pk}/liberer/")
        # Réception interne : PV prononcé sans réserve -> dossier qualité de l OF scellé en GED (10 ans).
        pv = self.call(qa, "post", "/api/qualite/pvs/", {
            "affaire": str(of.affaire_id), "ordre": str(of.pk), "intitule": f"Réception interne spools {of.code}",
        })
        self.call(qa, "post", f"/api/qualite/pvs/{pv['id']}/levee-reserve/", {"reserve": False})

    # -- M7 : exigences d'habilitation, DUER, audit, plan d'urgence ------------------------------------------
    def parcours_hse(self):
        from hse.models import AuditHse, Duer, ExigenceHabilitation, PlanUrgence

        hse, pdg = "hse@etls.local", "pdg@etls.local"
        # Exigences : un permis « à chaud » exige une qualification de soudage, « électrique » une habilitation électrique.
        for type_permis, mot in (("chaud", "soudage"), ("electrique", "habilitation electrique")):
            if not ExigenceHabilitation.objects.filter(type_permis=type_permis, mot_cle=mot).exists():
                self.call(pdg, "post", "/api/hse/exigences-habilitation/", {"type_permis": type_permis, "mot_cle": mot})
        annee = self.today.year
        if not Duer.objects.filter(annee=annee, perimetre="Atelier Libreville (demo)").exists():
            duer = self.call(pdg, "post", "/api/hse/duer/", {"annee": annee, "perimetre": "Atelier Libreville (demo)"})
            for lieux, activite, desc, proba, gravite, mesure in (
                ("Atelier soudure", "Soudage", "Projections et fumées de soudage", 4, 3, "Écrans, aspiration, EPI soudeur"),
                ("Zone de levage", "Manutention", "Chute de charge lors du levage de spools", 2, 5, "Élingues vérifiées, balisage, plan de levage"),
                ("Stockage", "Stockage", "Encombrement des allées", 2, 1, ""),
            ):
                self.call(hse, "post", "/api/hse/evaluations-risques/", {
                    "duer": duer["id"], "lieux": lieux, "activite": activite, "description": desc,
                    "probabilite": proba, "gravite": gravite, "mesure": mesure,
                })
            self.call(pdg, "post", f"/api/hse/duer/{duer['id']}/approuver/")
        if not AuditHse.objects.filter(zone="Atelier Libreville (demo)").exists():
            # Audit réalisé avec un écart traité par une action corrective clôturée, puis clôturé ; un second reste planifié.
            audit = self.call(hse, "post", "/api/hse/audits/", {
                "type_audit": "audit", "zone": "Atelier Libreville (demo)", "referentiel": "ISO 45001",
                "date_prevue": str(self.today - timedelta(days=10)),
            })
            self.call(hse, "post", f"/api/hse/audits/{audit['id']}/realiser/", {"score": 82})
            action = self.call(hse, "post", "/api/hse/actions/", {
                "type": "corrective", "description": "Reprendre le marquage au sol des allées",
                "echeance": str(self.today + timedelta(days=15)),
            })
            self.call(hse, "post", f"/api/hse/actions/{action['id']}/cloturer/", {"efficace": True})
            self.call(hse, "post", "/api/hse/constats-audit/", {
                "audit": audit["id"], "description": "Marquage au sol effacé", "gravite": "mineur", "action": action["id"],
            })
            self.call(hse, "post", "/api/hse/constats-audit/", {"audit": audit["id"], "description": "Extincteurs à jour", "gravite": "conforme"})
            self.call(hse, "post", f"/api/hse/audits/{audit['id']}/cloturer/")
            self.call(hse, "post", "/api/hse/audits/", {
                "type_audit": "inspection", "zone": "Chantier tuyauterie (demo)", "referentiel": "ISO 45001",
                "date_prevue": str(self.today + timedelta(days=20)),
            })
        if not PlanUrgence.objects.filter(intitule="Evacuation incendie atelier (demo)").exists():
            plan = self.call(hse, "post", "/api/hse/plans-urgence/", {
                "type_plan": "incendie", "intitule": "Evacuation incendie atelier (demo)", "perimetre": "Atelier Libreville",
                "periodicite_mois": 6,
            })
            self.call(hse, "post", "/api/hse/exercices-urgence/", {
                "plan": plan["id"], "date_exercice": str(self.today - timedelta(days=40)), "participants": 24,
                "resultat": "satisfaisant", "observations": "Évacuation en 4 min",
            })

    # -- M5 : transfert vers le chantier, consommation imputée à l'affaire ------------------------------------
    def parcours_stocks(self):
        from operations.models import OrdreFabrication
        from referentiels.models import Article
        from stocks.models import Depot, LotMatiere, MouvementStock

        email = "logistique@etls.local"
        tube = Article.objects.get(code="TUBE-01")
        lot = LotMatiere.objects.get(code="LOT-TUBE-001")
        central, chantier = Depot.objects.get(code="DEP-LBV"), Depot.objects.get(code="DEP-PGN")
        of = OrdreFabrication.objects.get(affaire__title=PREFIXE + "Fabrication supports atelier")
        if not MouvementStock.objects.filter(document_reference="Parcours demo - transfert").exists():
            self.call(email, "post", "/api/stocks/mouvements/", {
                "type_mouvement": "transfert", "article": str(tube.pk), "quantite": "10", "lot": str(lot.pk), "source": str(central.pk),
                "destination": str(chantier.pk), "document_reference": "Parcours demo - transfert", "date": str(self.today),
            })
        if not MouvementStock.objects.filter(document_reference="Parcours demo - consommation").exists():
            data = {
                "type_mouvement": "consommation", "article": str(tube.pk), "quantite": "25", "lot": str(lot.pk), "source": str(central.pk),
                "ordre": str(of.pk), "document_reference": "Parcours demo - consommation", "date": str(self.today),
            }
            if of.affaire.analytic_id:
                data["analytic"] = str(of.affaire.analytic_id)
            self.call(email, "post", "/api/stocks/mouvements/", data)
