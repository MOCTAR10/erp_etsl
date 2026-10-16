"""Regression transverse : balayage d'autorisation de TOUTE l'API (schema OpenAPI).

- anonyme : chaque route (hors allowlist) doit repondre 401/403, jamais 200/5xx ;
- role sans module metier (`chef_service`) : aucune lecture 200 sur M1..M12,
  aucune reponse 5xx sur les listes GET.

Le schema est la source de verite des routes : un nouveau ViewSet est couvert
automatiquement, sans toucher a ce test.
"""

import re

from django.test import TestCase
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient

from users.models import User
from users.rbac import ERP_APPS

ANON_ALLOWLIST = (
    "/api/health/",
    "/api/users/token/",
    "/api/users/token/refresh/",
    "/api/schema/",
)
MODULE_PREFIXES = tuple(
    "/api/" + app.replace("_", "-") + "/" for app in ERP_APPS
)
METHODS = ("get", "post", "put", "patch", "delete")


def _routes():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    return {p: ops for p, ops in schema["paths"].items() if p.startswith("/api/")}


NIL_UUID = "00000000-0000-0000-0000-000000000000"


def _concrete(path: str, op: dict | None = None) -> str:
    """Remplace les paramètres de chemin par une valeur du bon type (sinon un `<uuid:pk>` donne 404)."""
    types = {p["name"]: p.get("schema", {}) for p in (op or {}).get("parameters", []) if p.get("in") == "path"}

    def value(match):
        schema = types.get(match.group(1), {})
        if schema.get("type") == "integer":
            return "1"
        return NIL_UUID if schema.get("format") == "uuid" else "1"

    return re.sub(r"\{([^}]+)\}", value, path)


class AuthzSweepTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.routes = _routes()
        cls.low = User.objects.create_user(
            email="sweep.service@etls.local",
            password="x-Sweep-2026",
            role=User.Role.CHEF_SERVICE,
            first_name="Sweep",
        )

    def test_schema_non_vide(self):
        self.assertGreater(len(self.routes), 100)

    def test_anonyme_refuse_partout(self):
        client = APIClient()
        leaks = []
        for path, ops in self.routes.items():
            if path in ANON_ALLOWLIST or path.startswith(ANON_ALLOWLIST):
                continue
            for method in METHODS:
                if method not in ops:
                    continue
                resp = getattr(client, method)(_concrete(path, ops[method]), {}, format="json")
                if resp.status_code not in (401, 403):
                    leaks.append((method.upper(), path, resp.status_code))
        self.assertEqual(leaks, [], f"routes accessibles sans authentification : {leaks}")

    def test_role_sans_module_ne_lit_aucun_module_et_pas_de_5xx(self):
        client = APIClient()
        client.force_authenticate(self.low)
        readable, errors = [], []
        for path, ops in self.routes.items():
            if "get" not in ops or "{" in path:
                continue
            resp = client.get(path)
            if resp.status_code >= 500:
                errors.append((path, resp.status_code))
            if path.startswith(MODULE_PREFIXES) and resp.status_code == 200:
                readable.append(path)
        self.assertEqual(errors, [], f"5xx : {errors}")
        self.assertEqual(readable, [], f"modules metier lisibles sans droit : {readable}")
