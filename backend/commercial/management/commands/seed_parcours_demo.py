"""Lot A du seed « parcours démo » : affaire confirmée -> OF -> équipes / présences -> pointages -> paie (M1, M3, M9).

Contrairement aux seeds par module (instantanés posés par l'ORM), ce seed PILOTE LE WORKFLOW par l'API réelle
(DRF APIClient authentifié comme les comptes démo) : statuts via actions, attestations posées côté serveur, RBAC,
séparation des tâches, blocages HSE / qualité sont ceux de la production. À lancer APRÈS les seeds par module.

Idempotent : chaque parcours est repéré par son titre ; un parcours déjà présent n'est pas rejoué.
Toutes les valeurs sont des DONNÉES DE DÉMONSTRATION (jamais des valeurs ETSL confirmées). ASCII-safe en sortie.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from commercial.models import Affaire, ClientProfile
from documents.models import Document
from juridique.models import Reunion
from operations.models import CapaciteAtelier, OrdreFabrication
from referentiels.models import Currency
from rh_paie.models import Employe, Qualification
from users.models import User

PREFIXE = "Parcours demo - "
MDP = "Etls#Demo2026"

# (email, prénom, nom, code Employe rattaché) : opérateurs de terrain avec compte lié à une fiche salarié,
# condition du transfert pointage -> paie et du contrôle d'habilitation chantier.
OPERATEURS = [
    ("op.soudeur@etls.local", "Jean", "Moussavou", "EMP00002"),
    ("op.tuyauteur@etls.local", "Paul", "Ndong", "EMP00003"),
]


class Command(BaseCommand):
    help = "Seed parcours demo lot A : affaires M1 -> OF M3 -> equipes, presences, pointages, paie M9 (via API)."

    def handle(self, *args, **options):
        # Le client de test appelle l'hôte « testserver » ; ALLOWED_HOSTS vient de l'env (vide par défaut).
        with override_settings(ALLOWED_HOSTS=["testserver", "localhost"]):
            self._run()

    def _run(self):
        # Les seeds par module posent des codes explicites sans avancer les compteurs : sans réalignement préalable,
        # le premier code généré par l'API (AFF00001, OF00001…) entre en collision (409).
        from users.management.commands.seed_all_demo import _sync_sequences

        _sync_sequences()
        self.clients = {}
        self.today = timezone.localdate()
        self._operateurs()
        self._capacites()
        self.parcours_atelier()
        self.parcours_chantier()
        self.parcours_gr()
        self.stdout.write(self.style.SUCCESS("Parcours demo lot A pret."))

    # -- infra -------------------------------------------------------------------------------------------
    def api(self, email):
        if email not in self.clients:
            client = APIClient()
            client.force_authenticate(User.objects.get(email=email))
            self.clients[email] = client
        return self.clients[email]

    def call(self, email, method, url, data=None, ok=(200, 201, 204)):
        resp = getattr(self.api(email), method)(url, data or {}, format="json")
        if resp.status_code not in ok:
            raise CommandError(f"{method.upper()} {url} ({email}) -> {resp.status_code} {getattr(resp, 'data', '')}")
        return resp.data

    # -- données de base --------------------------------------------------------------------------------
    def _operateurs(self):
        """Comptes opérateurs liés à une fiche salarié + une habilitation chantier valide (provisoire/démo)."""
        for email, prenom, nom, code in OPERATEURS:
            user, created = User.objects.get_or_create(
                email=email, defaults={"first_name": prenom, "last_name": nom, "role": User.Role.CHEF_SERVICE},
            )
            if created:
                user.set_password(MDP)
                user.save()
            employe = Employe.objects.get(code=code)
            if employe.user_id != user.id:
                employe.user = user
                employe.save(update_fields=["user"])
            Qualification.objects.get_or_create(
                employe=employe, type=Qualification.Type.HABILITATION, intitule="Habilitation chantier (demo)",
                defaults={"organisme": "Organisme demo", "date_obtention": self.today - timedelta(days=365),
                          "date_validite": self.today + timedelta(days=365)},
            )

    def _capacites(self):
        """Capacités hebdomadaires RH (démo) : l'atelier est volontairement sous-dimensionné pour montrer la surcharge."""
        for scope, heures in ((OrdreFabrication.Scope.ATELIER, 120), (OrdreFabrication.Scope.CHANTIER, 200)):
            CapaciteAtelier.objects.get_or_create(scope=scope, resource=CapaciteAtelier.Resource.RH, defaults={"hours_per_week": heures})

    # -- chaîne commune M1 -> M3 -----------------------------------------------------------------------
    def _affaire_confirmee(self, titre, affaire_type, montant, jours, global_rental=False):
        titre = PREFIXE + titre
        affaire = Affaire.objects.filter(title=titre).first()
        if affaire is None:
            profil = ClientProfile.objects.filter(partner__code="PGR-001").first() or ClientProfile.objects.first()
            data = self.call("admin@etls.local", "post", "/api/commercial/affaires/", {
                "client": str(profil.pk), "title": titre, "affaire_type": affaire_type,
                "currency": str(Currency.objects.get(code="XAF").pk), "contract_amount": montant, "margin": montant // 10,
                "start_date": str(self.today), "end_date": str(self.today + timedelta(days=jours)),
                "is_global_rental": global_rental,
            })
            affaire = Affaire.objects.get(pk=data["id"])
        if affaire.status == Affaire.Status.BROUILLON:
            revue = self.call("admin@etls.local", "post", "/api/commercial/revues-commande/", {
                "affaire": str(affaire.pk), "montant_offre": montant, "montant_commande": montant,
                "delai_offre_jours": jours, "delai_commande_jours": jours,
            })
            self.call("admin@etls.local", "post", f"/api/commercial/revues-commande/{revue['id']}/valider/")
            self.call("admin@etls.local", "post", f"/api/commercial/affaires/{affaire.pk}/confirmer/")
            affaire.refresh_from_db()
        return affaire

    def _demarrer_affaire(self, affaire):
        """CRRL tenu + compte-rendu en GED, puis démarrage (CDC M1 §3.6)."""
        if affaire.status != Affaire.Status.CONFIRMEE:
            return
        doc, _ = Document.objects.get_or_create(
            title=f"CRRL {affaire.code} (demo)", defaults={"reference": f"CRRL-{affaire.code}", "counterparty": "ETSL"},
        )
        existante = Reunion.objects.filter(affaire=affaire, type=Reunion.Type.LANCEMENT).first()
        if existante is None:
            existante = Reunion.objects.get(pk=self.call("admin@etls.local", "post", "/api/juridique/reunions/", {
                "type": Reunion.Type.LANCEMENT, "objet": f"Reunion de lancement {affaire.code}",
                "date_reunion": timezone.now().isoformat(), "lieu": "Libreville", "affaire": str(affaire.pk),
            })["id"])
        # `tenir` (API) affecte l'id brut au FK : defaut connu, le compte-rendu est donc rattache par PATCH.
        self.call("admin@etls.local", "patch", f"/api/juridique/reunions/{existante.pk}/", {"compte_rendu": str(doc.pk)})
        if existante.statut == Reunion.Statut.PLANIFIEE:
            self.call("admin@etls.local", "post", f"/api/juridique/reunions/{existante.pk}/tenir/")
        self.call("admin@etls.local", "post", f"/api/commercial/affaires/{affaire.pk}/demarrer/")

    def _of(self, affaire, heures, lancer=True):
        of = OrdreFabrication.objects.get(affaire=affaire)
        self.call("atelier@etls.local", "patch", f"/api/operations/ordres/{of.pk}/", {
            "calculated_hours": heures, "responsible": str(User.objects.get(email="atelier@etls.local").pk),
        }, ok=(200,))
        of.refresh_from_db()
        if lancer and of.status == OrdreFabrication.Status.PREVU:
            self.call("atelier@etls.local", "post", f"/api/operations/ordres/{of.pk}/lancer/")
            of.refresh_from_db()
        return of

    def _equipe(self, label, metier, membres, chef):
        existante = self.call("atelier@etls.local", "get", "/api/operations/equipes/", {"search": label})
        lignes = existante.get("results", existante) if isinstance(existante, dict) else existante
        for ligne in lignes:
            if ligne["label"] == label:
                return ligne
        return self.call("atelier@etls.local", "post", "/api/operations/equipes/", {
            "label": label, "metier": metier, "chef": str(chef.pk), "membres": [str(Employe.objects.get(user=m).pk) for m in membres],
        })

    # -- parcours ----------------------------------------------------------------------------------------
    def parcours_atelier(self):
        affaire = self._affaire_confirmee("Fabrication spools atelier", "atelier", 85_000_000, 21)
        self._demarrer_affaire(affaire)
        # 700 h sur ~4 semaines (~175 h/sem) contre 120 h/sem de capacité atelier : surcharge visible dans /operations.
        of = self._of(affaire, 700)
        if of.status == OrdreFabrication.Status.LANCE:
            self.call("atelier@etls.local", "post", f"/api/operations/ordres/{of.pk}/demarrer/")
        soudeur = User.objects.get(email="op.soudeur@etls.local")
        if not of.pointages.exists():
            for i, heures in enumerate((8, 8, 6)):
                self.call("atelier@etls.local", "post", "/api/operations/pointages/", {
                    "ordre": str(of.pk), "worker": str(soudeur.pk),
                    "date": str(self.today - timedelta(days=3 - i)), "hours": heures, "hours_type": "normal",
                })
            saisis = list(of.pointages.order_by("date"))
            # saisi (reste en l'état) / validé par un tiers / validé puis transféré en paie M9 (SaisieTemps)
            self.call("admin@etls.local", "post", f"/api/operations/pointages/{saisis[1].pk}/valider/")
            self.call("admin@etls.local", "post", f"/api/operations/pointages/{saisis[0].pk}/valider/")
            self.call("admin@etls.local", "post", f"/api/operations/pointages/{saisis[0].pk}/transferer-paie/")

    def parcours_chantier(self):
        affaire = self._affaire_confirmee("Montage tuyauterie chantier", "chantier", 140_000_000, 60)
        self._demarrer_affaire(affaire)
        of = self._of(affaire, 600)
        ops = [User.objects.get(email=e) for e, *_ in OPERATEURS]
        if of.status == OrdreFabrication.Status.LANCE:
            self._permis_chantier(of)
            self.call("atelier@etls.local", "post", f"/api/operations/ordres/{of.pk}/demarrer/")
        equipe = self._equipe("Equipe tuyauterie A (demo)", "tuyauteur", ops, ops[1])
        if not of.affectations.exists():
            aff = self.call("atelier@etls.local", "post", "/api/operations/affectations/", {
                "equipe": equipe["id"], "ordre": str(of.pk), "date_debut": str(self.today),
                "date_fin": str(self.today + timedelta(days=30)), "effectif": len(ops),
            })
            self.call("atelier@etls.local", "post", f"/api/operations/affectations/{aff['id']}/mobiliser/")
        if not of.presences.exists():
            # (opérateur, décalage en jours, statut, motif) : présent, retard et absence motivés
            releves = ((0, 0, "present", ""), (1, 0, "present", ""), (0, -1, "retard", "Transport (demo)"),
                       (1, -1, "absent", "Maladie (demo)"))
            for idx, decalage, statut, motif in releves:
                self.call("atelier@etls.local", "post", "/api/operations/presences/", {
                    "ordre": str(of.pk), "employe": str(Employe.objects.get(user=ops[idx]).pk),
                    "date": str(self.today + timedelta(days=decalage)), "statut": statut, "motif": motif,
                })

    def _permis_chantier(self, of):
        """Permis à 3 visas (superviseur / HSE / DG), signataires distincts, lié à l'OF chantier."""
        permis = self.call("admin@etls.local", "post", "/api/hse/permis/", {
            "type_permis": "hauteur", "affaire": str(of.affaire_id), "ordre": str(of.pk),
            "emplacement": "Site client (demo)", "description": f"Montage tuyauterie {of.code}",
            "mesures": "Harnais, balisage, surveillant (demo)",
            "date_debut": str(self.today), "date_fin": str(self.today + timedelta(days=60)),
        })
        for email in ("atelier@etls.local", "hse@etls.local", "pdg@etls.local"):
            self.call(email, "post", f"/api/hse/permis/{permis['id']}/valider/")
        self.call("hse@etls.local", "post", f"/api/hse/permis/{permis['id']}/demarrer/")

    def parcours_gr(self):
        affaire = self._affaire_confirmee("Prestation GLOBAL RENTAL", "fourniture", 60_000_000, 90, global_rental=True)
        self._demarrer_affaire(affaire)
        self._of(affaire, 80, lancer=True)
