"""EX-G-07 (lot a6) : messages des applications métier et du socle traduits en anglais selon `Accept-Language`.

Le catalogue `locale/en/LC_MESSAGES/django.po` porte les messages (msgid = texte français exact du code) ; le
middleware `config.i18n.TraductionReponsesMiddleware` les traduit sans modifier les vues.
"""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.utils import translation
from rest_framework.test import APITestCase

from config.i18n import tr, traduire
from documents.management.commands.compiler_traductions import lire_po
from integrations.models import ImportBatch
from users.models import User

PWD = "Etls#Demo2026"

# Un message par application : (texte français du code, traduction attendue).
ECHANTILLON = {
    "accounting_kernel": ("Une écriture doit comporter au moins deux lignes.", "An entry must have at least two lines."),
    "achats": ("Facture déjà comptabilisée.", "Invoice already posted."),
    "analytics": ("Une archive de cube est immuable.", "A cube archive is immutable."),
    "commercial": ("Offre émise : version scellée.", "Quotation issued: version sealed."),
    "comptabilite": ("Période déjà clôturée.", "Period already closed."),
    "controle_gestion": ("Seul un budget brouillon peut être approuvé.", "Only a draft budget can be approved."),
    "documents": ("Piste d'audit ETSL", "ETSL audit trail"),
    "hse": ("Le demandeur ne peut pas valider son propre permis.", "The requester cannot validate their own permit."),
    "integrations": ("XML refusé : DTD / entités interdites.", "XML rejected: DTD / entities not allowed."),
    "juridique": ("Contentieux déjà clôturé.", "Litigation already closed."),
    "logistique": ("Seule une location active peut être clôturée.", "Only an active rental can be closed."),
    "maintenance": ("Seul un OT en cours peut être terminé.", "Only an in-progress work order can be completed."),
    "operations": ("Un pointage ne peut dépasser 24 h.", "A timesheet cannot exceed 24 h."),
    "qualite": ("ITP déjà approuvé.", "ITP already approved."),
    "registres": ("format invalide (csv/xlsx)", "invalid format (csv/xlsx)"),
    "reports": ("format invalide (csv/xlsx/pdf)", "invalid format (csv/xlsx/pdf)"),
    "rh_paie": ("Seul un bulletin brouillon peut être validé.", "Only a draft payslip can be validated."),
    "stocks": ("Lot déjà en quarantaine.", "Batch already in quarantine."),
    "users": ("Vous ne pouvez pas modifier votre propre rôle.", "You cannot change your own role."),
    "workflow": ("Le motif de rejet est obligatoire (RF-39).", "A rejection reason is required (RF-39)."),
}


def catalogue():
    return lire_po(Path(settings.LOCALE_PATHS[0]) / "en" / "LC_MESSAGES" / "django.po")


class CatalogueAppsTests(SimpleTestCase):
    def test_chaque_entree_du_catalogue_est_servie_en_anglais(self):
        entrees = {k: v for k, v in catalogue().items() if k}
        self.assertGreater(len(entrees), 900)
        with translation.override("en"):
            manquants = [k for k, v in entrees.items() if tr(k) != v]
        self.assertEqual(manquants, [])

    def test_echantillon_par_application(self):
        with translation.override("en"):
            for app, (fr, en) in ECHANTILLON.items():
                with self.subTest(app=app):
                    self.assertEqual(traduire({"detail": fr}), {"detail": en})
                    self.assertEqual(traduire({"champ": [fr]}), {"champ": [en]})
        with translation.override("fr"):
            fr, _ = ECHANTILLON["achats"]
            self.assertEqual(traduire({"detail": fr}), {"detail": fr})


class MessagesApiAnglaisTests(APITestCase):
    """Requêtes réelles : même erreur en `fr` puis en `en`, message traduit par le middleware."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(email="admin.a6@etls.ga", password=PWD, role=User.Role.ADMIN, is_staff=True)

    def _deux_langues(self, methode, url, attendu_fr, attendu_en, **kw):
        self.client.force_authenticate(self.admin)
        appel = getattr(self.client, methode)
        fr = appel(url, HTTP_ACCEPT_LANGUAGE="fr", **kw)
        en = appel(url, HTTP_ACCEPT_LANGUAGE="en", **kw)
        self.assertEqual((fr.status_code, en.status_code), (400, 400), (fr.content, en.content))
        self.assertIn(attendu_fr, str(fr.json()))
        self.assertIn(attendu_en, str(en.json()))
        self.assertNotIn(attendu_fr, str(en.json()))

    def test_maintenance(self):
        self._deux_langues("get", "/api/maintenance/ordres/couts-annuels/?annee=26",
                           "Année sur 4 chiffres attendue.", "4-digit year expected.")

    def test_comptabilite(self):
        self._deux_langues("get", "/api/comptabilite/etats/liasse/?exercice=abc",
                           "Année attendue (AAAA).", "Year expected (YYYY).")

    def test_noyau_comptable(self):
        self._deux_langues("get", "/api/accounting/moves/taux-saisie-manuelle/?exercice=ab",
                           "Année attendue.", "Year expected.")

    def test_operations(self):
        self._deux_langues("get", "/api/operations/ordres/rapport-periodique/?periode=x",
                           "hebdo ou mensuel.", "weekly or monthly.")

    def test_stocks(self):
        self._deux_langues("get", "/api/stocks/mouvements/tracabilite/",
                           "Paramètre `article` ou `lot` requis.", "Parameter `article` or `lot` required.")

    def test_qualite(self):
        self._deux_langues("get", "/api/qualite/instruments/?a_etalonner=x",
                           "Nombre de jours attendu.", "Number of days expected.")

    def test_controle_gestion(self):
        self._deux_langues("get", "/api/controle-gestion/clotures/?fiscal_year=x",
                           "Paramètre `fiscal_year` doit être un entier.", "Parameter `fiscal_year` must be an integer.")

    def test_achats(self):
        self._deux_langues("post", "/api/achats/requests/depuis-affaire/", "Affaire introuvable.",
                           "Project not found.", data={}, format="json")

    def test_integrations(self):
        self._deux_langues("post", "/api/integrations/import/", "fichier requis (champ « file »).",
                           'file required ("file" field).', data={"connector": ImportBatch.Connector.values[0]})

    def test_users_mot_de_passe(self):
        donnees = {"ancien": "faux", "nouveau": "Autre#Mdp2026x", "confirmation": "Autre#Mdp2026x"}
        self._deux_langues("post", "/api/users/me/mot-de-passe/", "Mot de passe actuel incorrect.",
                           "Current password incorrect.", data=donnees, format="json")
