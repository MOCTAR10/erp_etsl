"""Recette du lot de suivi inter-modules côté M3 : marge à terminaison reçue par M11 (outbox), réservation physique
des besoins matière en stock (M5) et libération, flux M4 (machines, compteurs, BL) lisible depuis /operations."""

from datetime import date
from decimal import Decimal

from commercial.models import Affaire
from outbox.tasks import dispatch_outbox
from stocks.models import MouvementStock, ReservationStock, StockQuant
from stocks.services import apply_move
from users.models import User

from .models import BesoinMatiere, PointageChantier
from .test_ecarts_m3b import AUJ, _Base


class MargeVersM11Tests(_Base):
    def test_evenement_outbox_integre_par_le_controle_de_gestion(self):
        finance = User.objects.create_user(email="fin@etls.ga", password="x-Ecarts-2026", role=User.Role.FINANCE)
        affaire = Affaire.objects.create(title="Pipeline B", contract_amount=Decimal("1000000"))
        of = self.of(affaire=affaire, calculated_hours=Decimal("100"))
        PointageChantier.objects.create(ordre=of, worker_name="X", date=AUJ, hours=Decimal("50"))
        self.assertEqual(self.post("/api/operations/ordres/publier-marges/").json()["publiees"], 1)
        self.client.force_authenticate(finance)
        r = self.client.get("/api/controle-gestion/marges-terminaison/").json()
        self.assertEqual((r["rows"], r["en_attente"]), ([], 1))
        self.assertEqual(self.client.post("/api/controle-gestion/marges-terminaison/integrer/").status_code, 200)
        r = self.client.get("/api/controle-gestion/marges-terminaison/").json()
        ligne = r["rows"][0]
        self.assertEqual((ligne["affaire_code"], Decimal(ligne["marge_a_terminaison"])), (affaire.code, Decimal("400000")))
        self.assertEqual(r["en_attente"], 0)
        # Republication : la ligne de l'affaire est remplacée, pas dupliquée.
        self.client.force_authenticate(self.dir)
        self.post("/api/operations/ordres/publier-marges/")
        dispatch_outbox()
        self.client.force_authenticate(finance)
        self.assertEqual(len(self.client.get("/api/controle-gestion/marges-terminaison/").json()["rows"]), 1)
        # Hors cercle des montants : le chef d'atelier ne lit pas M11.
        self.client.force_authenticate(self.chef)
        self.assertEqual(self.client.get("/api/controle-gestion/marges-terminaison/").status_code, 403)

    def test_balance_agee_m10_lisible_en_m11(self):
        finance = User.objects.create_user(email="fin2@etls.ga", password="x-Ecarts-2026", role=User.Role.FINANCE)
        self.client.force_authenticate(finance)
        r = self.client.get("/api/controle-gestion/balance-agee/")
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertIn("clients", body)
        self.assertIn("fournisseurs", body)
        self.assertEqual(body["clients"]["lignes"][-1]["tiers"], "TOTAL")
        self.assertEqual(self.client.get("/api/controle-gestion/balance-agee/?date=pas-une-date").status_code, 400)


class ReservationStockTests(_Base):
    def consommer(self, of, quantite):
        return apply_move(MouvementStock.objects.create(
            type_mouvement=MouvementStock.Type.CONSOMMATION, article=self.tube, quantite=Decimal(quantite),
            source=self.depot, ordre=of, date=date.today(),
        ))

    def test_reservation_physique_consommation_et_annulation(self):
        StockQuant.objects.create(depot=self.depot, article=self.tube, quantity=Decimal("10"))
        of1, of2 = self.of(), self.of(label="Spool 2")
        b1 = BesoinMatiere.objects.create(ordre=of1, article=self.tube, quantite=Decimal("8"))
        self.post(f"/api/operations/ordres/{of1.pk}/verifier-besoins/")
        resa = ReservationStock.objects.get(besoin_id=b1.pk)
        self.assertEqual((resa.statut, resa.quantite), ("active", Decimal("8.00")))
        # Idempotent : un second contrôle ne crée pas de seconde réservation.
        self.post(f"/api/operations/ordres/{of1.pk}/verifier-besoins/")
        self.assertEqual(ReservationStock.objects.filter(besoin_id=b1.pk).count(), 1)
        # Un autre OF ne peut pas entamer le stock réservé (paramètre provisoire bloquant par défaut).
        with self.assertRaises(ValueError):
            self.consommer(of2, "5")
        self.consommer(of2, "2")
        # L'OF réservataire consomme : réservation soldée, besoin servi.
        self.consommer(of1, "8")
        resa.refresh_from_db()
        b1.refresh_from_db()
        self.assertEqual((resa.statut, b1.statut), ("consommee", "servi"))

    def test_annulation_de_l_of_libere_la_reservation(self):
        StockQuant.objects.create(depot=self.depot, article=self.tube, quantity=Decimal("10"))
        of = self.of()
        b = BesoinMatiere.objects.create(ordre=of, article=self.tube, quantite=Decimal("4"))
        self.post(f"/api/operations/ordres/{of.pk}/verifier-besoins/")
        self.assertEqual(self.post(f"/api/operations/ordres/{of.pk}/annuler/").status_code, 200)
        self.assertEqual(ReservationStock.objects.get(besoin_id=b.pk).statut, "liberee")

    def test_ecran_stocks_disponibilites_et_liberation_manuelle(self):
        StockQuant.objects.create(depot=self.depot, article=self.tube, quantity=Decimal("10"))
        of = self.of()
        b = BesoinMatiere.objects.create(ordre=of, article=self.tube, quantite=Decimal("3"))
        self.post(f"/api/operations/ordres/{of.pk}/verifier-besoins/")
        admin = User.objects.create_user(email="adm@etls.ga", password="x-Ecarts-2026", role=User.Role.ADMIN, is_staff=True)
        self.client.force_authenticate(admin)
        dispo = self.client.get("/api/stocks/reservations/disponibilites/").json()
        self.assertEqual((dispo["rows"][0]["reserve"], dispo["rows"][0]["disponible"]), ("3.00", "7.00"))
        resa = ReservationStock.objects.get(besoin_id=b.pk)
        r = self.post(f"/api/stocks/reservations/{resa.pk}/liberer/", {"motif": "Besoin reporté"})
        self.assertEqual(r.json()["statut"], "liberee")
        self.assertEqual(self.post(f"/api/stocks/reservations/{resa.pk}/liberer/").status_code, 400)
        b.refresh_from_db()
        self.assertEqual(b.statut, "a_verifier")


class FluxM4Tests(_Base):
    def test_flux_m4_lisible_par_les_roles_operations(self):
        from logistique.models import AffectationParc, EquipementParc

        affaire = Affaire.objects.create(title="Chantier C")
        eq = EquipementParc.objects.create(label="Grue mobile")
        AffectationParc.objects.create(equipement=eq, affaire=affaire, date_debut=AUJ)
        self.client.force_authenticate(self.chef)
        r = self.client.get("/api/operations/flux-m4/")
        self.assertEqual(r.status_code, 200, r.content)
        bloc = next(b for b in r.json()["rows"] if b["affaire"] == affaire.code)
        self.assertEqual(bloc["machines"][0]["label"], "Grue mobile")
        self.assertEqual(self.client.get(f"/api/operations/flux-m4/?affaire={affaire.pk}").json()["rows"][0]["affaire"], affaire.code)
        self.assertEqual(self.client.get("/api/operations/flux-m4/?affaire=x").status_code, 400)
