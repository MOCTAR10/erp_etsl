"""Lot D du seed « parcours démo » : budget par affaire et écarts (M11), contrats signés + avenant + dossier GR liés (M12),
cubes de pilotage reconstruits (Couche D).

Même méthode que les lots A à C : API réelle, comptes démo. À lancer APRÈS les lots A et B (il budgète l'affaire chantier
dont la situation a été facturée au lot B). Idempotent. Valeurs = DONNÉES DE DÉMONSTRATION. ASCII-safe en sortie.
"""

import hashlib
from datetime import timedelta

from django.core.files.base import ContentFile
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from accounting_kernel.models import Period
from commercial.management.commands.seed_parcours_demo import PREFIXE, Command as ParcoursA
from commercial.models import Affaire, Contract
from controle_gestion.models import AnalyseEcart, Budget
from documents.models import Document, DocumentType, SignatureRequest, Version
from juridique.models import DossierGlobalRental, LienDocument
from referentiels.models import Currency, Partner
from users.models import User


class Command(ParcoursA):
    help = "Seed parcours demo lot D : budget par affaire et ecarts M11, contrats + avenant + dossier GR M12, cubes (via API)."

    def handle(self, *args, **options):
        with override_settings(ALLOWED_HOSTS=["testserver", "localhost"]):
            self._run()

    def _run(self):
        from analytics import cubes
        from users.management.commands.seed_all_demo import _sync_sequences

        _sync_sequences()
        self.clients = {}
        self.today = timezone.localdate()
        self.parcours_budget()
        self.parcours_juridique()
        # Cubes : reconstruits depuis le grand livre (idempotent), puis lisibles à l'écran Direction.
        cubes.alimenter_cube(self.today.strftime("%Y-%m"))
        self.stdout.write(self.style.SUCCESS("Parcours demo lot D pret."))

    def _affaire(self, titre):
        affaire = Affaire.objects.filter(title=PREFIXE + titre).first()
        if affaire is None:
            raise CommandError(f"Affaire « {PREFIXE}{titre} » absente : lancer seed_parcours_demo avant seed_parcours_d.")
        return affaire

    # -- M11 : budget de produits par affaire, versions scellées, écarts à analyser -------------------------
    def parcours_budget(self):
        affaire = self._affaire("Montage tuyauterie chantier")
        label = f"Budget produits - {affaire.code} {affaire.title}"[:250]
        if Budget.objects.filter(label=label).exists():
            return
        analytic = affaire.assurer_compte_analytique()
        annee = self.today.year
        periodes = {p.number: p for p in Period.objects.filter(fiscal_year__year=annee)}
        budget = self.call("finance@etls.local", "post", "/api/controle-gestion/budgets/", {
            "label": label, "type_budget": "produit", "fiscal_year": str(periodes[self.today.month].fiscal_year_id),
            "analytic": str(analytic.pk), "montant": "100000000",
        })
        # Trois mois écoulés budgétés à 10 M (réalisé nul : écart -100 %) et le mois courant à 30 M (situation facturée).
        for offset, montant in ((3, 10_000_000), (2, 10_000_000), (1, 10_000_000), (0, 30_000_000)):
            numero = self.today.month - offset
            if numero >= 1:
                self.call("finance@etls.local", "post", "/api/controle-gestion/budget-lignes/", {
                    "budget": budget["id"], "period": str(periodes[numero].pk), "montant": str(montant),
                })
        # Double visa : DAF (finance) puis CG (une autre personne) ; la version V0 entre alors en vigueur.
        self.call("finance@etls.local", "post", f"/api/controle-gestion/budgets/{budget['id']}/approuver/", {"visa": "daf"})
        self.call("pdg@etls.local", "post", f"/api/controle-gestion/budgets/{budget['id']}/approuver/", {"visa": "cg"})
        self.call("finance@etls.local", "post", "/api/controle-gestion/analyses-ecart/detecter/")
        # Une analyse rendue (explication + actions), les autres restent à analyser avec leur échéance J+5.
        premiere = AnalyseEcart.objects.filter(budget_id=budget["id"]).order_by("period__number").first()
        if premiere is not None:
            self.call("finance@etls.local", "post", f"/api/controle-gestion/analyses-ecart/{premiere.pk}/analyser/", {
                "analyse": "Demarrage du chantier decale : aucune situation emise avant le mois courant (demo).",
                "actions": "Recaler le planning de facturation sur l'avancement reel (demo).",
            })

    # -- M12 : contrats signés en GED, avenant, dossier GR lié ---------------------------------------------
    def _document_signe(self, titre):
        """Document GED conservé 10 ans, version courante signée (signature avancée achevée sur son empreinte)."""
        doc = Document.objects.filter(title=titre).first()
        if doc is not None:
            return doc
        type_doc, _ = DocumentType.objects.get_or_create(
            code="contrats-10-ans", defaults={"label": "Contrats (10 ans)", "retention_years": 10},
        )
        auteur = User.objects.get(email="admin@etls.local")
        contenu = f"{titre} - document de demonstration".encode()
        doc = Document.objects.create(title=titre, status=Document.Status.DRAFT, type=type_doc, counterparty="Client (demo)")
        version = Version.objects.create(
            document=doc, number=1, file=ContentFile(contenu, name="contrat-demo.pdf"),
            sha256=hashlib.sha256(contenu).hexdigest(), size=len(contenu), original_filename="contrat-demo.pdf", created_by=auteur,
        )
        doc.current_version = version
        doc.save(update_fields=["current_version"])
        SignatureRequest.objects.create(
            version=version, document_sha256=version.sha256, created_by=auteur, status=SignatureRequest.Status.COMPLETED,
            expires_at=timezone.now() + timedelta(days=5), completed_at=timezone.now(),
        )
        return doc

    def _contrat(self, affaire, montant, mois, profile="marche_travaux", gr=False):
        contrat = Contract.objects.filter(affaire=affaire).first()
        if contrat is None:
            contrat = Contract.objects.get(pk=self.call("admin@etls.local", "post", "/api/commercial/contracts/", {
                "affaire": str(affaire.pk), "client": str(affaire.client_id), "profile": profile,
                "start_date": str(self.today), "end_date": str(self.today + timedelta(days=30 * mois)), "months": mois,
                "amount_initial": str(montant), "currency": str(Currency.objects.get(code="XAF").pk),
                "is_global_rental": gr,
            })["id"])
        if contrat.status == Contract.Status.BROUILLON:
            doc = self._document_signe(f"Contrat signe {contrat.code} (demo)")
            self.call("admin@etls.local", "post", f"/api/commercial/contracts/{contrat.pk}/activer/", {"document": str(doc.pk)})
            contrat.refresh_from_db()
        return contrat

    def parcours_juridique(self):
        chantier = self._affaire("Montage tuyauterie chantier")
        gr_affaire = self._affaire("Prestation GLOBAL RENTAL")
        contrat = self._contrat(chantier, 140_000_000, 12)
        contrat_gr = self._contrat(gr_affaire, 60_000_000, 6, gr=True)
        # Avenant n1 : extension de périmètre, signé avec son propre document (rallonge la date de fin du contrat).
        if not contrat.avenants.exists():
            av = self.call("admin@etls.local", "post", "/api/commercial/avenants/", {
                "contract": str(contrat.pk), "objet": "Extension de perimetre : lignes annexes (demo)",
                "delta_montant": "15000000", "nouvelle_date_fin": str(self.today + timedelta(days=30 * 15)),
            })
            doc = self._document_signe(f"Avenant 1 {contrat.code} (demo)")
            self.call("admin@etls.local", "post", f"/api/commercial/avenants/{av['id']}/signer/", {"document": str(doc.pk)})
        # Recherche juridique interconnectée : le document signé est lié à son contrat.
        contrat.refresh_from_db()
        contrat_gr.refresh_from_db()
        for objet in (contrat, contrat_gr):
            if not LienDocument.objects.filter(objet_type="commercial.contract", objet_id=str(objet.pk)).exists():
                self.call("admin@etls.local", "post", "/api/juridique/liens/", {
                    "document": str(objet.document_id), "objet_type": "commercial.contract", "objet_id": str(objet.pk),
                    "note": "Contrat signe (demo)",
                })
        # Dossier GLOBAL RENTAL (618) lié au contrat GR et à l'affaire GR, puis ouvert.
        if not DossierGlobalRental.objects.filter(affaire=gr_affaire).exists():
            dossier = self.call("admin@etls.local", "post", "/api/juridique/dossiers-gr/", {
                "partenaire_gr": str(Partner.objects.get(code="GR-2000").pk), "affaire": str(gr_affaire.pk),
                "reference_contrat": contrat_gr.code, "objet": "Location d'equipement intra-groupe (demo)",
                "montant_estime": "60000000", "signe_618": True, "date_debut": str(self.today - timedelta(days=12)),
                "date_fin": str(self.today + timedelta(days=170)),
            })
            self.call("admin@etls.local", "post", f"/api/juridique/dossiers-gr/{dossier['id']}/ouvrir/")
