#!/usr/bin/env bash
# Campagne de performance ETSL (CDC §8.2, CL-OM-01) — base de RECETTE / CI uniquement (jamais la production).
# Prérequis : base migrée + `seed_all_demo` ; backend servi sur PERF_HOST (gunicorn conseillé) ;
# `pip install -r perf/requirements-perf.txt`. Depuis backend/ :  bash perf/run_perf.sh
set -euo pipefail
cd "$(dirname "$0")/.."
HOST="${PERF_HOST:-http://127.0.0.1:8000}"
USERS="${PERF_USERS:-25}"
DUREE="${PERF_DUREE:-5m}"
OUT=perf/resultats
mkdir -p "$OUT"

python manage.py seed_volumetrie
locust -f perf/locustfile.py --headless -u "$USERS" -r 5 -t "$DUREE" --host "$HOST" --csv "$OUT/locust" --only-summary || true
python perf/chrono_traitements.py --sortie "$OUT/chrono.json" || true
python perf/rapport.py --resultats "$OUT"
