"""Test fonctionnel rapide de la matrice de lecture (verifie via l'API)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.test.utils import setup_test_environment, teardown_test_environment  # noqa: E402
from django.test.runner import DiscoverRunner  # noqa: E402

setup_test_environment()
runner = DiscoverRunner(verbosity=0, interactive=False)
old_config = runner.setup_databases()

from django.contrib.auth import get_user_model  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402
from users.rbac import modules_for_role  # noqa: E402

User = get_user_model()

URLS = {
    "commercial": "/api/commercial/opportunities/",
    "achats": "/api/achats/orders/",
    "operations": "/api/operations/ordres/",
    "logistique": "/api/logistique/demandes/",
    "stocks": "/api/stocks/depots/",
    "qualite": "/api/qualite/soudeurs/",
    "hse": "/api/hse/incidents/",
    "maintenance": "/api/maintenance/actifs/",
    "rh_paie": "/api/rh-paie/employes/",
    "comptabilite": "/api/comptabilite/engagements/",
    "controle_gestion": "/api/controle-gestion/budgets/",
    "juridique": "/api/juridique/contentieux/",
}

ROLES = ["finance", "rh", "qaqc", "chef_service", "logistique", "admin"]
errors = []

for role in ROLES:
    User.objects.filter(role=role).delete()
    u = User.objects.create_user(
        email=f"{role}@smoke.local", password="x", role=role, is_active=True
    )
    c = APIClient()
    c.force_authenticate(u)
    allowed = set(modules_for_role(role))
    row = []
    for app, url in URLS.items():
        code = c.get(url).status_code
        expect_allow = app in allowed
        got_allow = code not in (401, 403)
        mark = "ok" if got_allow == expect_allow else "KO"
        if mark == "KO":
            errors.append(f"{role} {app}: HTTP {code} (attendu {'200' if expect_allow else '403'})")
        row.append(f"{app[:4]}:{code}{'' if mark == 'ok' else '!'}")
    print(f"{role:14} {len(allowed):>2} attendus | " + " ".join(row))

print()
if errors:
    print(f"{len(errors)} ECART(S) :")
    for e in errors:
        print("  -", e)
else:
    print("MATRICE APPLIQUEE CONFORMEMENT (tous les codes HTTP sont ceux attendus)")

runner.teardown_databases(old_config)
teardown_test_environment()
