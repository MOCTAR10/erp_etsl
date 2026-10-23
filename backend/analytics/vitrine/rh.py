"""Vitrine — RH & paie (M9) et pointages (M3) : 35 salariés, contrats, qualifications, soudeurs qualifiés (M6),
pointages mensuels transférés en paie, bulletins préparés / validés / comptabilisés sur 12 mois.

Pointages : posés validés par l'ORM puis publiés vers la paie par le service `operations.cloture.transferer_paie`
(saisie temps + valorisation). Paie : `preparer_bulletin` puis `comptabiliser_bulletin` (journal PAI, charges
ventilées par affaire au prorata des heures) — mêmes services que les actions de l'écran Paie.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction

from operations.models import OrdreFabrication, PointageChantier
from qualite.models import QualificationSoudeur, Soudeur
from rh_paie.models import BulletinPaie, ContratTravail, Employe, Qualification

from .donnees import EMPLOYES
from .outils import MOIS, ajouter_mois, alea, antidater, debut_mois, fin_mois, instant


class VitrineRH:
    def salaries(self):
        self.employes = []
        with transaction.atomic():
            for i, (nom, prenom, sexe, fonction, categorie, dept, site, salaire, embauche, terrain) in enumerate(EMPLOYES):
                self.employes.append(self._salarie(i, nom, prenom, sexe, fonction, categorie, dept, site, salaire, embauche, terrain))

    def _salarie(self, i, nom, prenom, sexe, fonction, categorie, dept, site, salaire, embauche, terrain):
        if embauche > 1900:
            entree = date(embauche, 1 + (i * 5) % 12, 1 + (i * 7) % 27)
        else:
            entree = ajouter_mois(debut_mois(self.today, -embauche), 0).replace(day=1 + (i % 10))
        employe = Employe.objects.filter(nom=nom, prenom=prenom).first()
        if employe is None:
            employe = Employe.objects.create(
                civilite=sexe, nom=nom, prenom=prenom, fonction=fonction, categorie=categorie, departement=dept, site=site,
                date_naissance=date(1972 + (i * 3) % 28, 1 + (i * 4) % 12, 1 + (i * 9) % 27), nationalite="Gabonaise",
                date_embauche=entree, telephone=f"+241 07{30 + i:02d}{4100 + 17 * i:04d}",
                statut=Employe.Statut.CONGE if nom in ("ELLA", "OVONO") else Employe.Statut.ACTIF,
            )
            antidater(Employe, employe.pk, created_at=instant(min(entree, self.today)))
        if not ContratTravail.objects.filter(employe=employe).exists():
            recent = embauche < 1900
            # Embauches de l'année en CDD ; deux CDD arrivent à échéance sous 90 jours (alertes RH J-90 / J-30).
            fin = None
            if recent:
                fin = self.today + timedelta(days=(25, 70)[i % 2]) if i % 3 == 0 else ajouter_mois(entree, 12) - timedelta(days=1)
            contrat = ContratTravail.objects.create(
                employe=employe, type="cdd" if recent else ("chantier" if i % 9 == 4 else "cdi"), date_debut=entree,
                date_fin=fin, salaire_base=Decimal(salaire), lieu_affectation=site, statut=ContratTravail.Statut.ACTIF,
            )
            antidater(ContratTravail, contrat.pk, created_at=instant(min(entree, self.today)))
        self._qualifications(i, employe, fonction, entree)
        employe.terrain = terrain
        return employe

    def _qualifications(self, i, employe, fonction, entree):
        quals = [("habilitation", "Passeport sécurité site pétrolier", "Organisme agréé HSE", 24)]
        if "Soudeur" in fonction:
            quals.append(("certificat", f"Qualification soudeur ISO 9606-1 {fonction.split()[-1]}", "Bureau de contrôle agréé", 24))
        if fonction in ("Tuyauteur", "Monteur ajusteur", "Chef de chantier"):
            quals.append(("habilitation", "Travail en hauteur et port du harnais", "Centre de formation Port-Gentil", 36))
        if fonction in ("Grutier", "Conducteur d'engins"):
            quals.append(("permis", "CACES engins de chantier / grue mobile", "Centre de formation Port-Gentil", 60))
        if "HSE" in fonction:
            quals.append(("certificat", "Sauveteur secouriste du travail", "Croix-Rouge gabonaise", 24))
        for n, (nature, intitule, organisme, mois) in enumerate(quals):
            if Qualification.objects.filter(employe=employe, intitule=intitule).exists():
                continue
            obtention = max(entree, ajouter_mois(self.today, -(4 + (i * 5 + n * 3) % 20)))
            validite = ajouter_mois(obtention, mois)
            if (i + n) % 11 == 3:  # quelques échéances proches : alertes J-90 / J-30 de l'écran Direction
                validite = self.today + timedelta(days=12 + 9 * (i % 7))
            Qualification.objects.create(
                employe=employe, type=nature, intitule=intitule, organisme=organisme,
                date_obtention=obtention, date_validite=validite,
            )
        if "Soudeur" in fonction and not Soudeur.objects.filter(employe=employe).exists():
            soudeur = Soudeur.objects.create(
                nom=employe.nom, prenoms=employe.prenom, matricule=employe.code, employe=employe,
                qualification=f"{fonction} - tube acier carbone / inox",
            )
            procede = "gtaw" if "TIG" in fonction else "smaw"
            qualif_le = ajouter_mois(self.today, -(3 + i % 14))
            QualificationSoudeur.objects.create(
                soudeur=soudeur, norme="iso9606", procede=procede, position="6G" if "6G" in fonction else "PF",
                groupe_materiaux="Acier carbone" if procede == "smaw" else "Acier inoxydable", epaisseur_min=Decimal("3"),
                epaisseur_max=Decimal("30"), gamme_diametre="2-24 pouces", date_qualification=qualif_le,
                date_validite=ajouter_mois(qualif_le, 24) if i % 5 else self.today + timedelta(days=40),
                certificat=f"ISO9606-VT-{4100 + i}",
            )

    # -- pointages (M3 -> M9) ------------------------------------------------------------------------------------
    def pointages(self):
        """Équipe de 3 à 5 salariés de terrain par affaire active et par mois, 5 à 7 jours pointés chacun."""
        from operations.cloture import transferer_paie

        terrain = [e for e in self.employes if e.terrain]
        valideur = self.user("atelier@etls.local")
        affaires = [a for a in self.affaires_vitrine.values() if not a.is_global_rental]
        for k in range(MOIS - 1, -1, -1):
            mois = debut_mois(self.today, k)
            for n, affaire in enumerate(affaires):
                if not (affaire.start_date <= fin_mois(mois) and affaire.end_date >= mois):
                    continue
                of = OrdreFabrication.objects.filter(affaire=affaire).first()
                if of is None or PointageChantier.objects.filter(ordre=of, date__gte=mois, date__lte=fin_mois(mois)).exists():
                    continue
                r = alea(f"pts-{affaire.code}-{mois}")
                equipe = r.sample(terrain, r.randint(3, 5))
                with transaction.atomic():
                    for employe in equipe:
                        jours = sorted(r.sample(range(1, 28), r.randint(5, 7)))
                        for j in jours:
                            jour = mois.replace(day=j)
                            if jour.weekday() >= 5 or jour >= self.today or jour < affaire.start_date:
                                continue
                            p = PointageChantier.objects.create(
                                ordre=of, employe=employe, worker_name=f"{employe.prenom} {employe.nom}", date=jour,
                                hours=Decimal(r.choice((8, 8, 9, 10))), hours_type="normal",
                                status=PointageChantier.Status.VALIDE, created_by=valideur, validated_by=valideur,
                                validated_at=instant(jour, 18),
                            )
                            if k > 0:  # le mois courant n'est pas encore transféré en paie
                                transferer_paie(p)
                            antidater(PointageChantier, p.pk, created_at=instant(jour, 17))

    # -- paie (M9) ------------------------------------------------------------------------------------------------
    def paie(self):
        from rh_paie.paie_m9a import preparer_bulletin
        from rh_paie.services import comptabiliser_bulletin

        comptable = self.user("finance@etls.local")
        for k in range(MOIS - 1, -1, -1):
            periode = debut_mois(self.today, k)
            with transaction.atomic():
                for employe in self.employes:
                    contrat = ContratTravail.objects.filter(employe=employe).first()
                    if contrat is None or contrat.date_debut > fin_mois(periode):
                        continue
                    bulletin = BulletinPaie.objects.filter(employe=employe, periode=periode).first()
                    if bulletin is None:
                        bulletin = BulletinPaie.objects.create(employe=employe, periode=periode)
                        preparer_bulletin(bulletin)
                        bulletin.refresh_from_db()
                    if bulletin.statut == BulletinPaie.Statut.BROUILLON:
                        # Validation (même transition que l'action « valider » de l'écran Paie).
                        bulletin.statut = BulletinPaie.Statut.VALIDE
                        bulletin.save(update_fields=["statut", "updated_at"])
                    if k > 0 and not bulletin.move_id:
                        comptabiliser_bulletin(bulletin, user=comptable)
                        bulletin.refresh_from_db()
                    if k > 1 and bulletin.statut == BulletinPaie.Statut.VALIDE:
                        bulletin.statut = BulletinPaie.Statut.CLOTURE
                        bulletin.save(update_fields=["statut", "updated_at"])
                    antidater(BulletinPaie, bulletin.pk, created_at=instant(min(fin_mois(periode), self.today) - timedelta(days=3)))
