"""Vitrine — tiers, articles, pipeline M1 et chaîne affaire complète : opportunité → offre → affaire → revue de
commande → OF → CRRL → contrat signé → situations mensuelles (M3) → factures émises (M10) → encaissements lettrés.

Le workflow passe par l'API réelle (statuts, attestations, contrôles) ; seules les dates d'audit sont ramenées à la
date métier (`antidater`) et les factures brouillon sont datées de la fin du mois de la situation avant émission.
"""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction

from accounting_kernel.models import AccountMoveLine
from commercial.models import Affaire, ClientProfile, Contract, Estimate, Opportunity
from comptabilite.models import CompteBancaire, FactureClient, Paiement
from documents.models import Document
from juridique.models import Reunion
from operations.models import OrdreFabrication, SituationTravaux
from referentiels.models import Account, Article, Currency, Partner, Site, UnitOfMeasure

from .donnees import AFFAIRES, ARTICLES, CLIENTS, FOURNISSEURS, PIPELINE
from .outils import (
    ajouter_mois, alea, antidater, arrondi, dater_documents, debut_mois, fin_mois, instant, jour_du_mois, libelle_mois,
    ouvre,
)

ADMIN, FIN, ATL, HSE, PDG = (
    "admin@etls.local", "finance@etls.local", "atelier@etls.local", "hse@etls.local", "pdg@etls.local",
)
# Délai de règlement observé par client (jours) : un payeur chroniquement en retard rend la balance âgée parlante.
DELAI_REGLEMENT = {"CLT-104": 100, "CLT-109": 80, "CLT-106": 35, "CLT-101": 42, "CLT-110": 60}
SITE_PAR_VILLE = {"Port-Gentil": "POG-ATELIER", "Libreville": "LBV-BASE"}


class VitrineCommercial:
    # -- référentiel --------------------------------------------------------------------------------------------
    def tiers_et_articles(self):
        xaf = Currency.objects.get(code="XAF")
        self.xaf = xaf
        for i, (code, nom, segment, scoring, origine, ville) in enumerate(CLIENTS):
            partner, _ = Partner.objects.get_or_create(code=code, defaults={
                "name": nom, "kind": Partner.Kind.CLIENT, "currency": xaf, "address": f"BP {1200 + 37 * i}, {ville}, Gabon",
                "phone": f"+241 01 {55 + i:02d} {10 + 3 * i:02d} {20 + i:02d}", "tax_id": f"NIF-VT{740100 + 13 * i}",
            })
            ClientProfile.objects.get_or_create(partner=partner, defaults={
                "segment": segment, "scoring": scoring, "origin": origine,
                "last_contact": self.today - timedelta(days=5 + 3 * i),
                "next_contact": self.today + timedelta(days=10 + 2 * i),
                "contacts": {"commercial": "Direction des achats", "technique": "Chef de projet client"},
            })
        fin_agrement = self.today + timedelta(days=330)
        for i, (code, nom, ville) in enumerate(FOURNISSEURS):
            # Deux agréments arrivent à échéance sous 60 jours : alertes calendaires « agrément fournisseur ».
            echeance = self.today + timedelta(days=25 + 20 * i) if i in (6, 9) else fin_agrement
            Partner.objects.get_or_create(code=code, defaults={
                "name": nom, "kind": Partner.Kind.FOURNISSEUR, "currency": xaf, "address": f"{ville}, Gabon",
                "tax_id": f"NIF-VF{520300 + 17 * i}", "agree_qualite_jusqu": echeance, "agree_hse_jusqu": echeance,
            })
        self.gr = Partner.objects.get(code="GR-0001")
        unites = {u.code: u for u in UnitOfMeasure.objects.all()}
        for code, libelle, nature, unite, prix, stockable in ARTICLES:
            Article.objects.get_or_create(code=code, defaults={
                "label": libelle, "article_type": nature, "unit": unites.get(unite) or unites.get("U"),
                "purchase_price": Decimal(prix), "sale_price": Decimal(prix) * Decimal("1.35"), "is_stockable": stockable,
            })
        # Comptes de tiers lettrables (paramétrage de référence : lettrage client / fournisseur).
        Account.objects.filter(code__in=["411000", "411100", "401000", "401100"]).update(reconcile=True)
        self.banque = CompteBancaire.objects.filter(is_active=True).order_by("code").first()

    # -- pipeline commercial (opportunités ouvertes et perdues) ---------------------------------------------------
    def pipeline(self):
        for objet, client, etape, montant, proba, mois, origine, motif in PIPELINE:
            if Opportunity.objects.filter(subject=objet).exists():
                continue
            profil = ClientProfile.objects.get(partner__code=client)
            cree = jour_du_mois(self.today, mois, 6)
            data = self.call(ADMIN, "post", "/api/commercial/opportunities/", {
                "client": str(profil.pk), "subject": objet, "stage": etape, "amount": montant, "probability": proba,
                "expected_close": str(ajouter_mois(cree, 3)), "origin": origine, "lost_reason": motif,
                "description": "Opportunité de démonstration (jeu vitrine).",
            })
            antidater(Opportunity, data["id"], created_at=instant(cree))
            if etape in ("offre", "negociation", "perdu"):
                offre = self._offre(objet, profil, montant, cree + timedelta(days=12), opportunite=data["id"])
                if etape == "perdu":
                    self.call(ADMIN, "post", f"/api/commercial/estimates/{offre}/perdre/", {"motif": motif})

    def _offre(self, titre, profil, montant, quand, opportunite=None, gr=False, gagnee=False):
        """Offre chiffrée (option retenue) puis soumise ; gagnée sur demande. Retourne son id."""
        data = self.call(ADMIN, "post", "/api/commercial/estimates/", {
            "opportunity": opportunite, "client": str(profil.pk), "title": f"Offre - {titre}"[:200],
            "currency": str(self.xaf.pk), "valid_until": str(quand + timedelta(days=60)), "is_global_rental": gr,
            "taux_marge_cible": "22",
        })
        self.call(ADMIN, "post", "/api/commercial/estimate-options/", {
            "estimate": data["id"], "label": "Offre de base", "amount": montant, "duration_months": 6, "is_selected": True,
        })
        self.call(ADMIN, "post", f"/api/commercial/estimates/{data['id']}/soumettre/")
        if gagnee:
            self.call(ADMIN, "post", f"/api/commercial/estimates/{data['id']}/gagner/")
        antidater(Estimate, data["id"], created_at=instant(quand), soumise_le=instant(quand + timedelta(days=2)),
                  **({"decision_le": instant(quand + timedelta(days=20))} if gagnee else {}))
        return data["id"]

    # -- affaires ---------------------------------------------------------------------------------------------
    def affaires(self):
        self.affaires_vitrine = {}
        for spec in AFFAIRES:
            with transaction.atomic():
                self.affaires_vitrine[spec[0]] = self._affaire(*spec)

    def _affaire(self, cle, titre, client, nature, montant, debut, duree, ville, gr, cloturee):
        debut_j = ouvre(jour_du_mois(self.today, debut, 4))
        fin_j = ajouter_mois(debut_j, duree) - timedelta(days=1)
        profil = ClientProfile.objects.get(partner__code=client)
        affaire = Affaire.objects.filter(title=titre).first()
        if affaire is None:
            cree = debut_j - timedelta(days=75)
            opp = self.call(ADMIN, "post", "/api/commercial/opportunities/", {
                "client": str(profil.pk), "subject": titre, "stage": "gagne", "amount": montant, "probability": 100,
                "expected_close": str(debut_j - timedelta(days=15)), "origin": profil.origin,
            })
            antidater(Opportunity, opp["id"], created_at=instant(cree), won_date=debut_j - timedelta(days=20))
            self._offre(titre, profil, montant, cree + timedelta(days=10), opportunite=opp["id"], gr=gr, gagnee=True)
            site = Site.objects.filter(code="CHANTIERS" if nature == "chantier" else SITE_PAR_VILLE[ville]).first()
            data = self.call(ADMIN, "post", "/api/commercial/affaires/", {
                "opportunity": opp["id"], "client": str(profil.pk), "title": titre, "affaire_type": nature,
                "currency": str(self.xaf.pk), "contract_amount": montant, "margin": arrondi(montant * Decimal("0.21")),
                "start_date": str(debut_j), "end_date": str(fin_j), "is_global_rental": gr,
                "description": f"Affaire de démonstration ({ville}).", **({"site_etsl": site.pk} if site else {}),
            })
            affaire = Affaire.objects.get(pk=data["id"])
            antidater(Affaire, affaire.pk, created_at=instant(debut_j - timedelta(days=12)))
        if affaire.status == Affaire.Status.BROUILLON:
            self._confirmer(affaire, montant, duree, debut_j)
            affaire.refresh_from_db()
        self._demarrer(affaire, debut_j)
        of = self._of_vitrine(affaire, montant, debut_j, fin_j)
        contrat = self._contrat_vitrine(affaire, montant, debut_j, fin_j, duree, gr, nature)
        self._situations(affaire, client, montant, debut, duree, gr)
        if cloturee:
            with dater_documents(fin_j):
                self._cloturer(affaire, of, contrat)
        affaire.refresh_from_db()
        return affaire

    def _confirmer(self, affaire, montant, duree, debut_j):
        """Revue de commande validée (PV archivé en GED) puis confirmation : l'OF est généré."""
        with dater_documents(debut_j - timedelta(days=10)):
            revue = self.call(ADMIN, "post", "/api/commercial/revues-commande/", {
                "affaire": str(affaire.pk), "montant_offre": montant, "montant_commande": montant,
                "delai_offre_jours": 30 * duree, "delai_commande_jours": 30 * duree,
            })
            self.call(ADMIN, "post", f"/api/commercial/revues-commande/{revue['id']}/valider/")
            self.call(ADMIN, "post", f"/api/commercial/affaires/{affaire.pk}/confirmer/")

    def _demarrer(self, affaire, debut_j):
        if affaire.status != Affaire.Status.CONFIRMEE:
            return
        doc, cree = Document.objects.get_or_create(
            title=f"Compte-rendu de réunion de lancement {affaire.code}",
            defaults={"reference": f"CRRL-{affaire.code}", "counterparty": affaire.client.partner.name if affaire.client_id else "",
                      "project": affaire.code, "document_date": debut_j - timedelta(days=3)},
        )
        if cree:
            antidater(Document, doc.pk, created_at=instant(debut_j - timedelta(days=3), 16))
        reunion = Reunion.objects.filter(affaire=affaire, type=Reunion.Type.LANCEMENT).first()
        if reunion is None:
            reunion = Reunion.objects.get(pk=self.call(ADMIN, "post", "/api/juridique/reunions/", {
                "type": Reunion.Type.LANCEMENT, "objet": f"Réunion de lancement {affaire.code}",
                "date_reunion": instant(debut_j - timedelta(days=3), 10).isoformat(),
                "lieu": "Base ETSL", "affaire": str(affaire.pk),
            })["id"])
        self.call(ADMIN, "patch", f"/api/juridique/reunions/{reunion.pk}/", {"compte_rendu": str(doc.pk)})
        if reunion.statut == Reunion.Statut.PLANIFIEE:
            self.call(ADMIN, "post", f"/api/juridique/reunions/{reunion.pk}/tenir/")
        self.call(ADMIN, "post", f"/api/commercial/affaires/{affaire.pk}/demarrer/")

    def _of_vitrine(self, affaire, montant, debut_j, fin_j):
        of = OrdreFabrication.objects.get(affaire=affaire)
        if of.status == OrdreFabrication.Status.PREVU:
            heures = arrondi(montant / 60_000, 10)  # ~60 000 FCFA de chiffre d'affaires par heure de main-d'œuvre
            self.call(ATL, "patch", f"/api/operations/ordres/{of.pk}/", {
                "calculated_hours": heures, "responsible": str(self.user(ATL).pk),
            }, ok=(200,))
            self.call(ATL, "post", f"/api/operations/ordres/{of.pk}/lancer/")
            of.refresh_from_db()
        if of.status == OrdreFabrication.Status.LANCE:
            if of.scope == OrdreFabrication.Scope.CHANTIER:
                self._permis_vitrine(of, debut_j, fin_j)
            self.call(ATL, "post", f"/api/operations/ordres/{of.pk}/demarrer/")
            antidater(OrdreFabrication, of.pk, created_at=instant(debut_j - timedelta(days=8)))
            of.refresh_from_db()
        return of

    def _permis_vitrine(self, of, debut_j, fin_j):
        """Permis de travail en hauteur à trois visas (superviseur, HSE, Direction), lié à l'OF chantier."""
        from hse.models import PermisTravail

        if PermisTravail.objects.filter(ordre=of).exists():
            return
        permis = self.call(ADMIN, "post", "/api/hse/permis/", {
            "type_permis": "hauteur", "affaire": str(of.affaire_id), "ordre": str(of.pk),
            "emplacement": "Site client", "description": f"Travaux de tuyauterie {of.code}",
            "mesures": "Harnais, balisage, surveillant, plan de levage",
            "date_debut": str(max(debut_j, self.today)), "date_fin": str(max(fin_j, self.today + timedelta(days=30))),
        })
        for email in (ATL, HSE, PDG):
            self.call(email, "post", f"/api/hse/permis/{permis['id']}/valider/")
        self.call(HSE, "post", f"/api/hse/permis/{permis['id']}/demarrer/")
        antidater(PermisTravail, permis["id"], created_at=instant(debut_j - timedelta(days=2)))

    def _contrat_vitrine(self, affaire, montant, debut_j, fin_j, duree, gr, nature):
        contrat = Contract.objects.filter(affaire=affaire).first()
        if contrat is None:
            contrat = Contract.objects.get(pk=self.call(ADMIN, "post", "/api/commercial/contracts/", {
                "affaire": str(affaire.pk), "client": str(affaire.client_id),
                "profile": "maintenance" if nature in ("maintenance", "fourniture") else "marche_travaux",
                "start_date": str(debut_j), "end_date": str(fin_j), "months": duree, "amount_initial": str(montant),
                "currency": str(self.xaf.pk), "is_global_rental": gr,
                "sla": "Intervention sous 24 h, disponibilité des équipements 98 %" if nature in ("maintenance", "fourniture") else "",
            })["id"])
        if contrat.status == Contract.Status.BROUILLON:
            doc = self._document_signe(f"Contrat signé {contrat.code} - {affaire.title}"[:250])
            antidater(Document, doc.pk, created_at=instant(debut_j - timedelta(days=6), 15))
            self.call(ADMIN, "post", f"/api/commercial/contracts/{contrat.pk}/activer/", {"document": str(doc.pk)})
            contrat.refresh_from_db()
        return contrat

    # -- situations, factures, encaissements -------------------------------------------------------------------
    @staticmethod
    def _poids(duree, gr):
        if gr or duree <= 2:
            return [Decimal(1)] * duree
        return [Decimal("0.6")] + [Decimal("1.1")] * (duree - 2) + [Decimal("0.7")]

    def _situations(self, affaire, client, montant, debut, duree, gr):
        poids = self._poids(duree, gr)
        total = sum(poids)
        cumul = Decimal(0)
        delai = DELAI_REGLEMENT.get(client, 50)
        ordres = [str(o.pk) for o in affaire.ordres_fabrication.all()]
        for i, p in enumerate(poids):
            k = debut - i
            if k < 0:
                break
            part = Decimal(montant) - cumul if i == len(poids) - 1 else Decimal(arrondi(Decimal(montant) * p / total))
            cumul += part
            mois = debut_mois(self.today, k)
            label = f"Situation n°{i + 1} - {libelle_mois(mois)}"
            situation = SituationTravaux.objects.filter(affaire=affaire, label=label).first()
            if situation is None:
                situation = SituationTravaux.objects.get(pk=self.call(ATL, "post", "/api/operations/situations/", {
                    "affaire": str(affaire.pk), "label": label, "period_start": str(mois),
                    "period_end": str(min(fin_mois(mois), self.today)), "amount": int(part),
                    "progress": min(100, int(cumul * 100 / Decimal(montant))), "ordres": ordres,
                })["id"])
                antidater(SituationTravaux, situation.pk, created_at=instant(min(fin_mois(mois), self.today - timedelta(days=1)), 11))
            if k == 0:
                # Mois courant : situation en préparation (brouillon) ou soumise au visa, pas encore facturée.
                if i % 2 and situation.status == SituationTravaux.Status.BROUILLON:
                    self.call(ATL, "post", f"/api/operations/situations/{situation.pk}/soumettre/")
                continue
            with dater_documents(ouvre(fin_mois(mois))):
                self._facturer(situation, fin_mois(mois), delai)

    def _facturer(self, situation, fin, delai):
        jour = ouvre(fin)
        situation.refresh_from_db()
        if situation.status == SituationTravaux.Status.BROUILLON:
            self.call(ATL, "post", f"/api/operations/situations/{situation.pk}/soumettre/")
            situation.refresh_from_db()
        if situation.status == SituationTravaux.Status.SOUMISE:
            self.call(ADMIN, "post", f"/api/operations/situations/{situation.pk}/validate/")
            antidater(SituationTravaux, situation.pk, validated_at=instant(jour - timedelta(days=2), 15))
        facture = FactureClient.objects.filter(situation=situation, nature="facture").first()
        if facture is None:
            data = self.call(FIN, "post", "/api/comptabilite/factures-clients/depuis-situation/", {"situation": str(situation.pk)})
            facture = FactureClient.objects.get(pk=data["id"])
        if facture.statut == FactureClient.Statut.BROUILLON:
            # Brouillon daté de la fin du mois de la situation : l'écriture VTE tombe dans la bonne période.
            FactureClient.objects.filter(pk=facture.pk).update(date=jour, echeance=jour + timedelta(days=45))
            self.call(FIN, "post", f"/api/comptabilite/factures-clients/{facture.pk}/emettre/")
            facture.refresh_from_db()
            antidater(FactureClient, facture.pk, created_at=instant(jour, 10), emise_le=instant(jour, 17))
            antidater(SituationTravaux, situation.pk, facture_le=jour)
            if getattr(facture, "document_id", None):
                antidater(Document, facture.document_id, created_at=instant(jour, 17))
        encaissement = jour + timedelta(days=delai + alea(facture.code).randint(-6, 9))
        if encaissement < self.today:
            self._encaisser(facture, encaissement)

    def _encaisser(self, facture, quand):
        reference = f"Encaissement {facture.code}"
        paiement = Paiement.objects.filter(reference=reference).first()
        if paiement is None:
            data = self.call(FIN, "post", "/api/comptabilite/paiements/", {
                "sens": "entree", "mode": "virement", "montant": str(facture.montant_ttc - facture.montant_retenue),
                "date": str(quand), "compte_bancaire": str(self.banque.pk), "tiers": str(facture.client_id),
                "reference": reference,
            })
            paiement = Paiement.objects.get(pk=data["id"])
            antidater(Paiement, paiement.pk, created_at=instant(quand, 9))
        if paiement.statut == Paiement.Statut.BROUILLON:
            self.call(FIN, "post", f"/api/comptabilite/paiements/{paiement.pk}/comptabiliser/")
            paiement.refresh_from_db()
        lignes = AccountMoveLine.objects.filter(account__code="411000", partner=facture.client).filter(
            move__in=[facture.move_id, paiement.move_id]
        )
        if lignes.count() == 2 and not lignes.filter(lettrage_actif__isnull=False).exists():
            self.call(FIN, "post", "/api/comptabilite/lettrages/", {"lignes": [str(l.pk) for l in lignes]})

    def _cloturer(self, affaire, of, contrat):
        from hse.models import PermisTravail

        for permis in PermisTravail.objects.filter(ordre=of, statut=PermisTravail.Statut.ACTIF):
            self.call(HSE, "post", f"/api/hse/permis/{permis.pk}/cloturer/")
        of.refresh_from_db()
        if of.status == OrdreFabrication.Status.EN_COURS:
            self.call(ATL, "post", f"/api/operations/ordres/{of.pk}/terminer/")
        affaire.refresh_from_db()
        if affaire.status == Affaire.Status.EN_COURS:
            self.call(ADMIN, "post", f"/api/commercial/affaires/{affaire.pk}/cloturer/")
