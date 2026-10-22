"""Rapport de la campagne de performance : résultats Locust + chronométrages comparés aux seuils (`seuils.json`).

Usage (depuis backend/) : `python perf/rapport.py [--resultats perf/resultats] [--sortie perf/resultats/rapport.md]`.
Écrit un rapport Markdown (artefact CI et résumé du job) ; code de sortie 0 même en dépassement (job non bloquant),
sauf `--strict` (sortie 1 si un seuil est dépassé).
"""

import argparse
import csv
import json
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent


def lire_locust(dossier):
    f = dossier / "locust_stats.csv"
    if not f.exists():
        return []
    with f.open(encoding="utf-8") as h:
        return list(csv.DictReader(h))


def evaluer(seuils, locust, chrono):
    lignes = []  # (mesure, valeur, seuil, conforme)
    for r in locust:
        if r.get("Name") == "Aggregated" or not r.get("Name", "").startswith("consultation"):
            continue
        p95 = float(r.get("95%") or 0)
        lignes.append((f"{r['Name']} — p95 (ms)", p95, seuils["consultation_p95_ms"], p95 <= seuils["consultation_p95_ms"]))
    total = next((r for r in locust if r.get("Name") == "Aggregated"), None)
    if total and float(total.get("Request Count") or 0):
        taux = 100 * float(total["Failure Count"]) / float(total["Request Count"])
        lignes.append(("Taux d'erreur global (%)", round(taux, 2), seuils["taux_erreur_max_pct"],
                       taux <= seuils["taux_erreur_max_pct"]))
        lignes.append(("Débit moyen (requêtes/s)", round(float(total.get("Requests/s") or 0), 2), None, None))
    if chrono:
        lignes.append(("Paie complète du mois (s)", chrono["paie_complete_s"], seuils["paie_complete_s"],
                       chrono["paie_complete_s"] <= seuils["paie_complete_s"] and not chrono["paie"]["erreurs"]))
        lignes.append(("PDF des bulletins (s)", chrono["bulletins_pdf_s"], seuils["bulletins_pdf_s"],
                       chrono["bulletins_pdf_s"] <= seuils["bulletins_pdf_s"]))
        for nom, val in chrono.get("traitements", {}).items():
            lignes.append((f"Traitement lourd {nom}", val, seuils["traitement_lourd_s"], val <= seuils["traitement_lourd_s"]))
    return lignes


def rendre(seuils, lignes, chrono):
    vol = seuils["volumetrie"]
    out = [
        "# Campagne de performance ETSL (CDC §8.2, CL-OM-01)",
        "",
        f"Seuils : {seuils['_statut']}.",
        f"Volumétrie : {vol['salaries']} salariés, {vol['affaires']} affaires, {vol['ecritures_mois']} écritures / mois, "
        f"{vol['utilisateurs_simultanes']} utilisateurs simultanés.",
        "",
        "| Mesure | Valeur | Seuil | Verdict |",
        "|---|---|---|---|",
    ]
    for mesure, val, seuil, ok in lignes:
        verdict = "—" if ok is None else ("conforme" if ok else "**DÉPASSÉ**")
        out.append(f"| {mesure} | {val} | {'—' if seuil is None else seuil} | {verdict} |")
    if chrono and chrono["paie"]["erreurs"]:
        out += ["", f"Bulletins en erreur : {chrono['paie']['erreurs']} — {'; '.join(chrono['paie']['exemples_erreurs'])}"]
    if not lignes:
        out += ["", "Aucun résultat (Locust ou chronométrage absents)."]
    return "\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resultats", default=str(ICI / "resultats"))
    parser.add_argument("--sortie", default=None)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    dossier = Path(args.resultats)
    seuils = json.loads((ICI / "seuils.json").read_text(encoding="utf-8"))
    f_chrono = dossier / "chrono.json"
    chrono = json.loads(f_chrono.read_text(encoding="utf-8")) if f_chrono.exists() else None
    lignes = evaluer(seuils, lire_locust(dossier), chrono)
    texte = rendre(seuils, lignes, chrono)
    sortie = Path(args.sortie) if args.sortie else dossier / "rapport.md"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(texte, encoding="utf-8")
    sys.stdout.write(texte)
    depasse = any(ok is False for *_, ok in lignes)
    return 1 if (args.strict and depasse) else 0


if __name__ == "__main__":
    sys.exit(main())
