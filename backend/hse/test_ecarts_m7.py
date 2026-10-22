"""Écarts M7 (2026-10-19) — tests de recette (matrice CDC × code, M7-01, M7-10, §9.4, §9.5, §9.6).

- Cycle incident : enquête → plan d'action (cause profonde + action) → clôture refusée tant qu'une action n'est pas
  soldée ; presque-accident clos avec un retour d'expérience ; zone atelier / chantier.
- Rapport d'incident PDF ; à la clôture, rapport scellé en GED (10 ans) et lié à l'incident.
- Registre OSHA (cas enregistrables) et synthèse, export CSV.
- NCR-HSE : variante du socle NC qualité (numérotation propre, rattachement obligatoire à un événement HSE).
- BSD traité archivé en GED (10 ans), puis non supprimable.
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from documents.models import Document
from juridique.models import LienDocument
from qualite.models import NonConformite
from users.models import User

from .models import ActionHse, BordereauDechet, Incident


class _Base(APITestCase):
    def setUp(self):
        self.hse = User.objects.create_user(email="hse@etls.ga", password="x-Audit-2026", role=User.Role.HSE)
        self.client.force_authenticate(self.hse)

    def incident(self, **kw):
        valeurs = {"type_incident": "accident", "gravite": "majeure", "date_evenement": timezone.now(), "lieu": "Atelier 2",
                   "description": "Chute de plain-pied", "declared_by": self.hse}
        valeurs.update(kw)
        return Incident.objects.create(**valeurs)

    def post(self, inc, action, data=None):
        return self.client.post(f"/api/hse/incidents/{inc.pk}/{action}/", data or {}, format="json")


class CycleIncidentTests(_Base):
    def test_plan_action_exige_cause_profonde_et_action(self):
        inc = self.incident()
        self.assertEqual(self.post(inc, "plan-action").status_code, 400)  # pas encore en enquête
        self.post(inc, "ouvrir-enquete")
        self.assertEqual(self.post(inc, "plan-action", {"cause_profonde": "Sol glissant"}).status_code, 400)  # aucune action
        ActionHse.objects.create(incident=inc, description="Revêtement antidérapant")
        r = self.post(inc, "plan-action", {"cause_profonde": "Sol glissant"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["statut"], "plan_action")
        self.assertIsNotNone(r.data["plan_action_le"])

    def test_cloture_refusee_tant_qu_une_action_n_est_pas_soldee(self):
        inc = self.incident()
        action = ActionHse.objects.create(incident=inc, description="Revêtement antidérapant")
        r = self.post(inc, "cloturer", {"rapport": "Sol glissant, revêtement posé."})
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn(action.code, str(r.data))
        self.client.post(f"/api/hse/actions/{action.pk}/cloturer/", {"efficace": True}, format="json")
        self.assertEqual(self.post(inc, "cloturer", {"rapport": "Sol glissant, revêtement posé."}).status_code, 200)

    def test_presque_accident_clos_avec_retour_d_experience_et_zone(self):
        r = self.client.post("/api/hse/incidents/", {
            "type_incident": "quasi_accident", "gravite": "mineure", "date_evenement": timezone.now().isoformat(),
            "lieu": "Baie de soudage", "zone": "atelier", "description": "Bouteille d'acétylène non arrimée",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        inc = Incident.objects.get(pk=r.data["id"])
        self.assertEqual(inc.zone, "atelier")
        self.assertEqual(self.post(inc, "cloturer").status_code, 400)
        r = self.post(inc, "cloturer", {"retour_experience": "Chaînes d'arrimage sur tous les râteliers."})
        self.assertEqual(r.status_code, 200, r.content)


class RapportEtArchivageTests(_Base):
    def test_rapport_pdf_et_archivage_ged_a_la_cloture(self):
        inc = self.incident()
        r = self.client.get(f"/api/hse/incidents/{inc.pk}/rapport-pdf/")
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "application/pdf"))
        self.assertTrue(r.content.startswith(b"%PDF"))
        r = self.post(inc, "cloturer", {"rapport": "Enquête : sol glissant."})
        self.assertEqual(r.status_code, 200, r.content)
        inc.refresh_from_db()
        doc = Document.objects.get(pk=inc.document_id)
        self.assertEqual((doc.status, doc.type.retention_years, doc.reference), (Document.Status.ARCHIVED, 10, inc.code))
        self.assertTrue(LienDocument.objects.filter(document=doc, objet_type="hse.incident", objet_id=str(inc.pk)).exists())

    def test_bsd_traite_archive_en_ged_puis_non_supprimable(self):
        from .models import PrestataireDechet

        prestataire = PrestataireDechet.objects.create(
            nom="Collecte agréée", numero_agrement="MIN-ENV-1", date_fin_validite=timezone.localdate() + timedelta(days=90),
        )
        bsd = BordereauDechet.objects.create(type_dechet="dib", quantite=2, prestataire=prestataire)
        r = self.client.patch(f"/api/hse/bordereaux-dechets/{bsd.pk}/", {"statut": "traite"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        bsd.refresh_from_db()
        self.assertIsNotNone(bsd.document_id)
        self.assertEqual(self.client.delete(f"/api/hse/bordereaux-dechets/{bsd.pk}/").status_code, 400)


class RegistreOshaTests(_Base):
    def test_cas_enregistrables_et_synthese(self):
        annee = timezone.now().year
        self.incident(consequence_humaine="arret", jours_arret=4)
        self.incident(consequence_humaine="soins_medicaux")
        self.incident(consequence_humaine="premiers_secours")  # non enregistrable
        r = self.client.get(f"/api/hse/incidents/registre-osha/?annee={annee}")
        self.assertEqual(r.status_code, 200, r.content)
        s = r.data["synthese"]
        self.assertEqual((s["cas_enregistrables"], s["arret"], s["autre_enregistrable"], s["jours_arret"]), (2, 1, 1, 4))
        r = self.client.get(f"/api/hse/incidents/registre-osha/?annee={annee}&export=csv")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r["Content-Type"])
        self.assertEqual(r.content.decode("utf-8-sig").count("\n"), 3)  # en-tête + 2 cas


class NcrHseTests(_Base):
    def test_ncr_hse_variante_du_socle_rattachee_a_un_evenement(self):
        inc = self.incident()
        qa = User.objects.create_user(email="qa@etls.ga", password="x-Audit-2026", role=User.Role.QAQC)
        self.client.force_authenticate(qa)
        r = self.client.post("/api/qualite/non-conformites/", {"type_ncr": "hse", "description": "Garde-corps absent"}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        r = self.client.post("/api/qualite/non-conformites/", {
            "type_ncr": "hse", "description": "Garde-corps absent", "incident_hse": str(inc.pk), "source": "interne",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.data["code"].startswith("NCR-HSE-"))
        self.assertEqual(r.data["incident_hse_code"], inc.code)
        self.assertEqual(NonConformite.objects.get(pk=r.data["id"]).statut, "signalee")

    def test_ncr_hse_ouverte_par_le_hse_depuis_l_incident(self):
        inc = self.incident()
        self.assertEqual(self.post(inc, "ncr-hse").status_code, 400)
        r = self.post(inc, "ncr-hse", {"description": "Échafaudage non réceptionné"})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.data["code"].startswith("NCR-HSE-"))
        self.assertEqual(self.client.get(f"/api/hse/incidents/{inc.pk}/").data["ncr_hse"], [f"{r.data['code']} (Signalée)"])
