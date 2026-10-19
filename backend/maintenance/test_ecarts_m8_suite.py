"""Écarts M8, suite (2026-10-19) — tests de recette (matrice CDC × code, §13.2, §13.4, §13.8, §13.10).

- Habilitation du technicien (amont M9) : exigences par catégorie d'équipement / type d'OT, saisies par ETSL ;
  planification et démarrage refusés sans qualification RH valide.
- Seuils de fiabilité (disponibilité, MTBF) paramétrables et provisoires ; machines sous seuil signalées et notifiées.
- Pré-alerte préventive notifiée une seule fois par échéance.
- Inspections réglementaires : échéances dans les alertes transverses J-90 / J-30 / J-15 / J-0 et notifiées.
- Archivage réglementaire via M12 : l'OT archivé produit un rapport PDF scellé en GED (10 ans), lié à l'OT.
"""

import hashlib
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from analytics.services import alertes_agregees
from analytics.tasks import notifier_echeances
from documents.models import Document
from juridique.models import LienDocument
from rh_paie.models import Employe, Qualification
from users.models import User
from workflow.models import Notification

from .models import Actif, ExigenceHabilitationMaintenance, Inspection, OrdreTravail, ParametreMaintenance, PlanPreventif
from .services import fiabilite_actifs, get_param_maintenance, notifier_maintenance


class _Base(APITestCase):
    def setUp(self):
        self.maint = User.objects.create_user(email="maint@etls.ga", password="x-Audit-2026", role=User.Role.MAINTENANCE)
        self.tech = User.objects.create_user(email="tech@etls.ga", password="x-Audit-2026", role=User.Role.MAINTENANCE)
        self.client.force_authenticate(self.maint)
        self.actif = Actif.objects.create(designation="Poste à souder MIG", categorie="machine")

    def regler(self, code, valeur):
        get_param_maintenance(code)
        ParametreMaintenance.objects.filter(code=code).update(valeur=Decimal(str(valeur)))


class HabilitationTechnicienTests(_Base):
    def setUp(self):
        super().setUp()
        ExigenceHabilitationMaintenance.objects.create(categorie_actif="machine", mot_cle="électrique")
        self.ot = OrdreTravail.objects.create(actif=self.actif, description="Carte de puissance HS")

    def planifier(self):
        return self.client.post(f"/api/maintenance/ordres/{self.ot.pk}/planifier/", {"technicien": str(self.tech.pk)}, format="json")

    def test_technicien_sans_fiche_ni_qualification_refuse(self):
        r = self.planifier()
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("fiche salarié", str(r.data))
        emp = Employe.objects.create(code="EMP-T", nom="Ndong", prenom="Ali", statut=Employe.Statut.ACTIF, user=self.tech)
        Qualification.objects.create(employe=emp, intitule="Habilitation électrique B2V", date_validite=date.today() - timedelta(days=1))
        r = self.planifier()
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("électrique", str(r.data))

    def test_qualification_valide_autorise_et_demarrage_controle(self):
        emp = Employe.objects.create(code="EMP-T", nom="Ndong", prenom="Ali", statut=Employe.Statut.ACTIF, user=self.tech)
        q = Qualification.objects.create(employe=emp, intitule="Habilitation électrique B2V", date_validite=date.today() + timedelta(days=30))
        self.assertEqual(self.planifier().status_code, 200)
        q.date_validite = date.today() - timedelta(days=1)
        q.save()
        r = self.client.post(f"/api/maintenance/ordres/{self.ot.pk}/demarrer/", {}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(OrdreTravail.objects.get(pk=self.ot.pk).statut, "planifie")

    def test_demarrage_sans_technicien_refuse_si_exigence(self):
        r = self.client.post(f"/api/maintenance/ordres/{self.ot.pk}/demarrer/", {}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("technicien non désigné", str(r.data))

    def test_exigence_hors_perimetre_sans_effet_et_saisie_par_api(self):
        engin = Actif.objects.create(designation="Chargeuse", categorie="engin")
        ot = OrdreTravail.objects.create(actif=engin, description="Graissage")
        r = self.client.post(f"/api/maintenance/ordres/{ot.pk}/demarrer/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        r = self.client.post("/api/maintenance/exigences-habilitation/", {"categorie_actif": "levage", "mot_cle": "CACES"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)


class SeuilsFiabiliteTests(_Base):
    def test_machine_sous_seuil_signalee_et_notifiee_une_fois_par_mois(self):
        debut = timezone.now() - timedelta(days=2)
        Actif.objects.filter(pk=self.actif.pk).update(date_mise_en_service=date.today() - timedelta(days=10))
        OrdreTravail.objects.create(actif=self.actif, description="Panne", type_ot="correctif", statut="termine",
                                    date_debut=debut, date_fin=debut + timedelta(hours=48))
        row = next(r for r in fiabilite_actifs()["rows"] if r["actif"] == self.actif.code)
        self.assertTrue(any("disponibilité" in a for a in row["alertes"]), row)
        self.assertTrue(any("MTBF" in a for a in row["alertes"]), row)
        notifier_maintenance()
        notifier_maintenance()
        self.assertEqual(Notification.objects.filter(user=self.maint, subject__startswith="Fiabilité").count(), 1)

    def test_seuils_provisoires_et_reglables(self):
        self.regler("SEUIL_DISPONIBILITE_PCT", 0)
        self.regler("SEUIL_MTBF_H", 0)
        data = fiabilite_actifs()
        self.assertEqual(data["seuil_disponibilite_pct"], Decimal("0"))
        self.assertTrue(all(not r["alertes"] for r in data["rows"]))
        self.assertTrue(data["provisoire"])


class PrealerteNotifieeTests(_Base):
    def test_prealerte_notifiee_une_seule_fois_par_echeance(self):
        PlanPreventif.objects.create(actif=self.actif, libelle="Vidange", periodicite_jours=30,
                                     derniere_date=date.today() - timedelta(days=27))
        notifier_maintenance()
        notifier_maintenance()
        sujets = list(Notification.objects.filter(user=self.maint).values_list("subject", flat=True))
        self.assertEqual(len([s for s in sujets if s.startswith("Pré-alerte préventive")]), 1)


class InspectionsReglementairesTests(_Base):
    def test_prochaine_inspection_dans_les_alertes_et_notifiee_au_palier(self):
        Inspection.objects.create(actif=self.actif, type_inspection="levage", date_inspection=date.today() - timedelta(days=350),
                                  prochaine_inspection=date.today() + timedelta(days=15), statut="realisee", resultat="conforme")
        items = [i for i in alertes_agregees()["maintenance"] if i["type"] == "inspection_reglementaire"]
        self.assertEqual(len(items), 1)
        self.assertEqual((items[0]["jours"], items[0]["bande"]), (15, "j15"))
        notifier_echeances()
        self.assertTrue(Notification.objects.filter(user=self.maint, subject__contains="J-15").exists())

    def test_inspection_plus_recente_remplace_l_echeance(self):
        Inspection.objects.create(actif=self.actif, type_inspection="atex", date_inspection=date.today() - timedelta(days=400),
                                  prochaine_inspection=date.today() - timedelta(days=35), statut="realisee", resultat="conforme")
        Inspection.objects.create(actif=self.actif, type_inspection="atex", date_inspection=date.today() - timedelta(days=30),
                                  prochaine_inspection=date.today() + timedelta(days=335), statut="realisee", resultat="conforme")
        items = [i for i in alertes_agregees()["maintenance"] if i["type"] == "inspection_reglementaire"]
        self.assertEqual(items, [])


class ArchivageGedTests(_Base):
    def test_ot_archive_scelle_son_rapport_en_ged_10_ans(self):
        ot = OrdreTravail.objects.create(actif=self.actif, description="Remplacement torche", statut="cloture",
                                         rapport="Torche remplacée, essais conformes.")
        r = self.client.post(f"/api/maintenance/ordres/{ot.pk}/archiver/")
        self.assertEqual(r.status_code, 200, r.content)
        ot.refresh_from_db()
        doc = Document.objects.get(pk=ot.document_id)
        self.assertEqual((doc.status, doc.reference, doc.type.retention_years), (Document.Status.ARCHIVED, ot.code, 10))
        version = doc.current_version
        version.file.open("rb")
        self.assertEqual(hashlib.sha256(version.file.read()).hexdigest(), doc.sha256)
        self.assertTrue(LienDocument.objects.filter(document=doc, objet_type="maintenance.ordretravail", objet_id=str(ot.pk)).exists())
        self.assertEqual(r.data["document_titre"], doc.title)
