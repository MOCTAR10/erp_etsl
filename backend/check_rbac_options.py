"""Compare les deux matrices de lecture possibles et chiffre l'ecart.

A) derivee des tuples existants (WRITE|AMOUNT|VALIDATION) : ne supprime aucune
   droit existant, mais restrictit peu.
B) stricte MANUEL §2.2 : restrictit fortement, mais supprime des droits
   aujourd'hui deliberement accordes (cf. check_rbac_coherence.py).
"""

import os
import re
import sys
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from users.models import User  # noqa: E402
from users.rbac import ERP_APPS, FULL_ACCESS_ROLES, modules_for_role  # noqa: E402

R = User.Role
TUPLE_RE = re.compile(r"^([A-Z_]+_ROLES)\s*=\s*\((.*?)\)\s*$", re.S | re.M)
base = os.path.dirname(os.path.abspath(__file__))

derived = {app: set() for app in ERP_APPS}
for path in sorted(glob.glob(os.path.join(base, "*", "services.py"))) + sorted(
    glob.glob(os.path.join(base, "*", "permissions.py"))
):
    rel = os.path.relpath(path, base)
    app = rel.split(os.sep)[0]
    if app not in derived:
        continue
    src = open(path, encoding="utf-8").read()
    for m in TUPLE_RE.finditer(src):
        name = m.group(1)
        if not any(k in name for k in ("WRITE", "AMOUNT", "VALIDATION")):
            continue
        for role in set(re.findall(r"User\.Role\.(\w+)", m.group(2))):
            derived[app].add(getattr(R, role).value)

for role in FULL_ACCESS_ROLES:
    for app in ERP_APPS:
        derived[app].add(role)

print(f"{'role':22} {'A (dérivée)':>12} {'B (§2.2)':>10}   modules perdus par B")
print("-" * 100)
total_lost = 0
for r in R.values:
    a = sorted(app for app in ERP_APPS if r in derived[app])
    b = list(modules_for_role(r))
    lost = sorted(set(a) - set(b))
    total_lost += len(lost)
    fa = "TOUT" if len(a) == 12 else str(len(a))
    fb = "TOUT" if len(b) == 12 else str(len(b))
    print(f"{r:22} {fa:>12} {fb:>10}   {', '.join(lost) if lost else '-'}")

print("-" * 100)
print(f"total de (role, module) perdus si on applique B : {total_lost}")
