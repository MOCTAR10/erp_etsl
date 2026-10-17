"""Audit lot 10 (2026-10-17) — les règles métier des modèles (`clean()`) s'appliquent aussi via l'API.

DRF n'appelle pas `Model.clean()` : sur 14 modèles, les règles écrites dans `clean()` n'étaient vérifiées que dans
l'admin Django, jamais à la saisie API (double affectation d'un équipement en location, partenaire non GLOBAL RENTAL,
avancement > 100 %, compteurs / quantités négatifs, dates de fin avant le début…). `config.serializers.ModelCleanMixin`
rejoue `clean()` dans la validation du sérialiseur.
"""

from datetime import date, timedelta

from rest_framework.test import APITestCase

from logistique.models import EquipementParc, LocationGR
from referentiels.models import Partner

from .models import User


class ModelCleanViaApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.ga", password="x-Audit-2026", role=User.Role.ADMIN, is_staff=True
        )
        self.client.force_authenticate(self.admin)
        self.today = date.today()

    def post(self, url, data):
        return self.client.post(url, data, format="json")

    def assert_refuse(self, url, data, champ):
        r = self.post(url, data)
        self.assertEqual(r.status_code, 400, (url, r.status_code, r.content[:300]))
        self.assertIn(champ, r.data, r.data)

    def test_affaire_fin_avant_debut(self):
        self.assert_refuse("/api/commercial/affaires/", {"title": "Spool", "start_date": str(self.today),
                                                         "end_date": str(self.today - timedelta(days=5))}, "end_date")

    def test_affectation_d_un_equipement_en_location_gr(self):
        eq = EquipementParc.objects.create(label="Grue 80 t", statut=EquipementParc.Statut.EN_LOCATION)
        self.assert_refuse("/api/logistique/affectations/", {"equipement": str(eq.pk), "date_debut": str(self.today)},
                           "equipement")

    def test_location_chez_un_partenaire_non_global_rental(self):
        p = Partner.objects.create(code="F-LOC", name="Loueur lambda", kind="fournisseur", is_global_rental=False)
        eq = EquipementParc.objects.create(label="Nacelle")
        self.assert_refuse("/api/logistique/locations/", {"partenaire": str(p.pk), "equipement": str(eq.pk)}, "partenaire")

    def test_lecture_compteur_negative(self):
        gr = Partner.objects.create(code="GR", name="GLOBAL RENTAL", kind="fournisseur", is_global_rental=True)
        loc = LocationGR.objects.create(partenaire=gr, equipement=EquipementParc.objects.create(label="Chargeuse"))
        self.assert_refuse("/api/logistique/lectures/", {"location": str(loc.pk), "date": str(self.today), "valeur": "-5"},
                           "valeur")

    def test_situation_avancement_superieur_a_100(self):
        self.assert_refuse("/api/operations/situations/", {"label": "S1", "period_start": str(self.today - timedelta(days=30)),
                                                           "period_end": str(self.today), "progress": "150"}, "progress")

    def test_bc_global_rental_chez_un_fournisseur_non_gr(self):
        f = Partner.objects.create(code="F-1", name="Quincaillerie", kind="fournisseur", is_global_rental=False)
        self.assert_refuse("/api/achats/orders/", {"supplier": str(f.pk), "is_global_rental": True}, "supplier")


class ModelCleanSweepTests(APITestCase):
    """Garde-fou : tout modèle doté d'un `clean()` métier a des sérialiseurs qui l'appliquent."""

    def test_clean_applique_par_tous_les_serialiseurs(self):
        import inspect

        from config.serializers import ModelCleanMixin

        from .test_authorship_sweep import project_serializers

        oublis = []
        for label, cls in project_serializers():
            model = cls.Meta.model
            if "clean" not in model.__dict__:
                continue
            source = inspect.getsource(cls)
            appelle = issubclass(cls, ModelCleanMixin) or any(
                k in source for k in ("full_clean", "_apply_and_validate", ".clean()")
            )
            if not appelle and not all(f.read_only for f in cls().fields.values()):
                oublis.append(f"{label} ({model.__name__}.clean)")
        self.assertEqual(oublis, [], "clean() ignoré par : " + ", ".join(oublis))
