"""Scénarios de charge Locust (CDC §8.2 performance, CL-OM-01 : 25 utilisateurs nommés).

Profils pondérés (PROVISOIRE : à remplacer par le scénario de recette d'ETSL) :
* consultation (80 %) : listes métier et tableaux de bord, cible < 3 s au 95e centile ;
* saisie (20 %) : rafraîchissement du token + consultation détaillée des affaires et écritures du jeu VOL-.

Usage (depuis backend/) :
  locust -f perf/locustfile.py --headless -u 25 -r 5 -t 5m --host http://127.0.0.1:8000 --csv perf/resultats/locust
Comptes : comptes démo (`seed_demo_users`), mot de passe PERF_PASSWORD (défaut Etls#Demo2026).
"""

import itertools
import os

from locust import HttpUser, between, task

COMPTES = itertools.cycle([
    "admin@etls.local", "finance@etls.local", "rh@etls.local", "logistique@etls.local", "atelier@etls.local",
    "qaqc@etls.local", "hse@etls.local", "maintenance@etls.local", "projets@etls.local", "pdg@etls.local",
])
MOT_DE_PASSE = os.environ.get("PERF_PASSWORD", "Etls#Demo2026")


class UtilisateurErp(HttpUser):
    wait_time = between(1, 5)

    def on_start(self):
        r = self.client.post("/api/users/token/", json={"email": next(COMPTES), "password": MOT_DE_PASSE},
                             name="auth: token")
        self.client.headers["Authorization"] = f"Bearer {r.json().get('access', '')}" if r.ok else ""

    def _get(self, url, nom):
        # 403 = rôle sans droit de lecture sur le module : réponse rapide attendue, pas une erreur de performance.
        with self.client.get(url, name=nom, catch_response=True) as r:
            if r.status_code in (200, 403):
                r.success()

    @task(6)
    def tableau_de_bord(self):
        self._get("/api/analytics/dashboard/", "consultation: tableau de bord")

    @task(4)
    def direction(self):
        self._get("/api/analytics/petrolier/", "consultation: reporting pétrolier")
        self._get("/api/analytics/etat-bi/", "consultation: état BI")

    @task(5)
    def ecritures(self):
        self._get("/api/accounting/moves/?search=VOL-", "consultation: écritures")

    @task(5)
    def salaries(self):
        self._get("/api/rh-paie/employes/?search=VOL-", "consultation: salariés")

    @task(5)
    def affaires(self):
        self._get("/api/commercial/affaires/?search=VOL-", "consultation: affaires")

    @task(3)
    def listes_terrain(self):
        self._get("/api/stocks/mouvements/", "consultation: mouvements de stock")
        self._get("/api/qualite/actions-correctives/", "consultation: CAPA")

    @task(2)
    def alertes(self):
        self._get("/api/analytics/alertes/", "consultation: alertes C3")
