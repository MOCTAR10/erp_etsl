"""Cohérence de la matrice de lecture : aucun droit d'écriture ne doit
devenir inatteignable parce que la lecture serait refusée."""

import re
import glob
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()


from users.models import User  # noqa: E402
from users.rbac import ERP_APPS, modules_for_role  # noqa: E402

R = User.Role

TUPLE_RE = re.compile(r"^([A-Z_]+_ROLES)\s*=\s*\((.*?)\)\s*$", re.S | re.M)

problems = []
base = os.path.dirname(os.path.abspath(__file__))

for path in sorted(glob.glob(os.path.join(base, "*", "services.py"))) + sorted(
    glob.glob(os.path.join(base, "*", "permissions.py"))
):
    rel = os.path.relpath(path, base)
    app = rel.split(os.sep)[0]
    if app not in ERP_APPS:
        continue
    src = open(path, encoding="utf-8").read()
    for m in TUPLE_RE.finditer(src):
        name = m.group(1)
        if "WRITE" not in name and "AMOUNT" not in name and "VALIDATION" not in name:
            continue
        for role in set(re.findall(r"User\.Role\.(\w+)", m.group(2))):
            value = getattr(R, role).value
            if app not in modules_for_role(value):
                problems.append(f"{rel}: {name} contient {role} mais lecture '{app}' refusée")

print(f"modules ERP : {len(ERP_APPS)}")
for r in R.values:
    mods = modules_for_role(r)
    flag = "TOUT" if len(mods) == len(ERP_APPS) else (str(len(mods)) if mods else "AUCUN")
    print(f"  {r:22} {flag:>5}  {', '.join(mods) if mods else '-'}")

if problems:
    print(f"\n{len(problems)} INCOHERENCE(S) :")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("\nMATRICE COHERENTE (aucun droit d/ecriture perdu)")
