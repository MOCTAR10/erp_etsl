"""Écarts M7-D (2026-10-19) — tests de recette : permis (M7-11), alertes SMS (CDC M7 « web services d'alerte »), coûts HSE (M11).

- Permis créé à l'écran par un chef d'atelier (demandeur), intervenants ajoutés, photo / plan joints (formats contrôlés).
- Le signataire du visa suivant est prévenu (notification + SMS si la passerelle est configurée).
- Permis échu → « expiré » par la tâche quotidienne, figé, demandeur et HSE prévenus ; clôture encore possible.
- Charges comptabilisées sur les centres HSE → coûts HSE par centre et par mois dans M11, masqués hors RF-59.
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from accounting_kernel.models import AccountMove, AccountMoveLine, FiscalYear, Journal, Period
from analytics.tasks import notifier_echeances
from referentiels.models import Account
from rh_paie.models import Employe
from users.models import User
from workflow.models import Notification

from .models import PermisTravail
from .services import centres_hse, couts_hse


def _user(email, role, **kw):
    return User.objects.create_user(email=email, password="x-Audit-2026", role=role, **kw)


@override_settings(HSE_PERMIS_NIVEAUX=["superviseur", "hse"])
class PermisEcranTests(APITestCase):
    def setUp(self):
        self.atelier = _user("atelier@etls.ga", User.Role.CHEF_ATELIER)
        self.atelier2 = _user("atelier2@etls.ga", User.Role.CHEF_ATELIER)
        self.hse = _user("hse@etls.ga", User.Role.HSE)
        Employe.objects.create(code="EMP-9", nom="Mba", prenom="Eric", statut=Employe.Statut.ACTIF,
                               telephone="+24177000000", user=self.atelier2)
        self.emp = Employe.objects.create(code="EMP-1", nom="Ndong", prenom="Paul", statut=Employe.Statut.ACTIF)

    @override_settings(SMS_GATEWAY_URL="https://sms.example/send", SMS_GATEWAY_TOKEN="t")
    def test_demande_a_l_ecran_intervenant_pieces_et_alerte_sms(self):
        self.client.force_authenticate(self.atelier)
        with mock.patch("workflow.sms.urllib.request.urlopen") as envoi, self.captureOnCommitCallbacks(execute=True):
            envoi.return_value.__enter__.return_value.status = 200
            r = self.client.post("/api/hse/permis/", {"type_permis": "hauteur", "emplacement": "Rack 4",
                                                       "description": "Chemin de câbles", "date_debut": date.today().isoformat()},
                                 format="json")
        self.assertEqual(r.status_code, 201, r.content)
        pid = r.data["id"]
        self.assertEqual(r.data["demandeur"], self.atelier.pk)
        # Le superviseur suivant (autre chef d'atelier, pas le demandeur) est prévenu, y compris par SMS.
        self.assertTrue(Notification.objects.filter(user=self.atelier2, subject__startswith="Permis").exists())
        self.assertFalse(Notification.objects.filter(user=self.atelier, subject__startswith="Permis").exists())
        self.assertEqual(envoi.call_count, 1)
        self.assertIn(b"+24177000000", envoi.call_args.args[0].data)

        r = self.client.post(f"/api/hse/permis/{pid}/ajouter-intervenant/", {"employe": str(self.emp.pk)}, format="json")
        self.assertEqual((r.status_code, r.data["intervenants_noms"]), (200, [str(self.emp)]))
        exe = SimpleUploadedFile("zone.exe", b"MZ", content_type="application/octet-stream")
        self.assertEqual(self.client.post(f"/api/hse/permis/{pid}/joindre-photo/", {"fichier": exe}, format="multipart").status_code, 400)
        photo = SimpleUploadedFile("zone.jpg", b"\xff\xd8\xff", content_type="image/jpeg")
        r = self.client.post(f"/api/hse/permis/{pid}/joindre-photo/", {"fichier": photo}, format="multipart")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("zone", r.data["photo"])
        plan = SimpleUploadedFile("plan.pdf", b"%PDF-1.4", content_type="application/pdf")
        self.assertEqual(self.client.post(f"/api/hse/permis/{pid}/joindre-plan/", {"fichier": plan}, format="multipart").status_code, 200)
        # Visa superviseur → le HSE est prévenu à son tour.
        self.client.force_authenticate(self.atelier2)
        self.assertEqual(self.client.post(f"/api/hse/permis/{pid}/valider/").status_code, 200)
        self.assertTrue(Notification.objects.filter(user=self.hse, subject__contains="visa HSE").exists())

    def test_sans_passerelle_aucun_sms(self):
        self.client.force_authenticate(self.atelier)
        with mock.patch("workflow.sms.urllib.request.urlopen") as envoi, self.captureOnCommitCallbacks(execute=True):
            self.client.post("/api/hse/permis/", {"type_permis": "levage", "emplacement": "Baie 2", "description": "Levage",
                                                   "date_debut": date.today().isoformat()}, format="json")
        envoi.assert_not_called()

    def test_permis_echu_expire_fige_et_cloturable(self):
        hier = date.today() - timedelta(days=1)
        permis = PermisTravail.objects.create(type_permis="chaud", emplacement="Atelier", description="Soudure",
                                              date_debut=hier - timedelta(days=2), date_fin=hier, statut="actif",
                                              demandeur=self.atelier)
        en_cours = PermisTravail.objects.create(type_permis="chaud", emplacement="Atelier", description="Soudure",
                                                date_debut=hier, date_fin=date.today(), statut="valide", demandeur=self.atelier)
        notifier_echeances()
        permis.refresh_from_db()
        en_cours.refresh_from_db()
        self.assertEqual((permis.statut, en_cours.statut), ("expire", "valide"))
        self.assertTrue(Notification.objects.filter(user=self.hse, subject=f"Permis {permis.code} expiré").exists())
        self.assertTrue(Notification.objects.filter(user=self.atelier, subject=f"Permis {permis.code} expiré").exists())
        self.client.force_authenticate(self.hse)
        self.assertEqual(self.client.post(f"/api/hse/permis/{permis.pk}/demarrer/").status_code, 400)
        r = self.client.post(f"/api/hse/permis/{permis.pk}/ajouter-intervenant/", {"employe": str(self.emp.pk)}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.post(f"/api/hse/permis/{permis.pk}/cloturer/").status_code, 200)


class CoutsHseTests(APITestCase):
    def test_charges_imputees_aux_centres_hse_lues_par_m11(self):
        centres = {c.code: c for c in centres_hse()}
        self.assertEqual(len(centres_hse()), 6)  # idempotent
        charge = Account.objects.create(code="604500", label="Achats EPI", account_class=6, account_type=Account.AccountType.EXPENSE)
        tiers = Account.objects.create(code="401000", label="Fournisseurs", account_class=4, account_type=Account.AccountType.LIABILITY)
        journal = Journal.objects.create(code="HA", label="Achats")
        fy = FiscalYear.objects.create(year=2026, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        periode = Period.objects.filter(fiscal_year=fy, start_date__lte=date(2026, 3, 10), end_date__gte=date(2026, 3, 10)).first()             or Period.objects.create(fiscal_year=fy, number=3, start_date=date(2026, 3, 1), end_date=date(2026, 3, 31))
        move = AccountMove.objects.create(journal=journal, period=periode, date=date(2026, 3, 10), label="Casques")
        AccountMoveLine.objects.create(move=move, account=charge, debit=Decimal("150000"), analytic_account=centres["HSE-EPI"])
        AccountMoveLine.objects.create(move=move, account=tiers, credit=Decimal("150000"), order=1)
        brouillon = couts_hse(2026)
        self.assertEqual(brouillon["total"], 0)  # seules les écritures comptabilisées comptent
        AccountMove.objects.filter(pk=move.pk).update(status=AccountMove.Status.POSTED)
        r = couts_hse(2026)
        epi = next(x for x in r["rows"] if x["centre"] == "HSE-EPI")
        self.assertEqual((epi["mois"][2], epi["total"], r["total"]), (Decimal("150000"), Decimal("150000"), Decimal("150000")))

        finance = _user("fin@etls.ga", User.Role.FINANCE)
        self.client.force_authenticate(finance)
        rep = self.client.get("/api/controle-gestion/couts-hse/?annee=2026")
        self.assertEqual((rep.status_code, rep.data["total"]), (200, "150000.00"), rep.content)
        hse = _user("hse2@etls.ga", User.Role.HSE)
        self.client.force_authenticate(hse)
        self.assertEqual(self.client.get("/api/controle-gestion/couts-hse/?annee=2026").status_code, 403)
