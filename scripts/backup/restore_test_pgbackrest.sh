#!/usr/bin/env bash
# Test de restauration pgBackRest + stockage S3 (fichiers GED) — CL-OM-11, CDC §8.2 (sauvegarde / PRA).
#
# OBJET
#   Prouver, sur un serveur de TEST (jamais sur le primaire de production), que :
#     1. la dernière sauvegarde pgBackRest se restaure dans un répertoire jetable et démarre (RTO mesuré) ;
#     2. la base restaurée est cohérente : volumes des tables clés, écritures comptables équilibrées, versions GED ;
#     3. les fichiers GED référencés par la base restaurée sont présents dans le bucket S3 de sauvegarde et leur
#        SHA-256 est identique à l'empreinte scellée en base (échantillon tiré au hasard, verify_ged_s3.py).
#   Un rapport JSON horodaté est écrit dans scripts/backup/reports/.
#
# NE PAS EXÉCUTER EN PRODUCTION SUR LE PRIMAIRE : la restauration se fait dans RESTORE_DIR, sur un port dédié,
# avec archive_mode=off (le serveur restauré n'écrit JAMAIS dans le dépôt pgBackRest).
#
# PRÉREQUIS (serveur de test ayant accès au dépôt pgBackRest en lecture et au bucket S3 de sauvegarde)
#   - pgbackrest, pg_ctl / psql de la même version majeure que la production (PostgreSQL 16) ;
#   - /etc/pgbackrest/pgbackrest.conf déclarant la stanza (repo1-path ou repo1-s3-*) ;
#   - python3 avec psycopg et boto3 (le venv du backend convient : backend/.venv/bin/python).
#
# VARIABLES
#   STANZA=etls                 stanza pgBackRest
#   BACKUP_SET=                 libellé d'une sauvegarde précise (vide = la plus récente)
#   RESTORE_DIR=/var/tmp/etls_restore_test   répertoire jetable (supprimé à la fin sauf KEEP=1)
#   PGPORT_TEST=5499            port du serveur restauré (socket Unix dans RESTORE_DIR, aucune écoute réseau)
#   PGUSER_TEST=etls  PGDB_TEST=etls
#   GED_SAMPLE=50               nombre de fichiers GED vérifiés dans S3
#   S3_ENDPOINT, S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY   bucket S3 de SAUVEGARDE des fichiers GED (réplique)
#   PYTHON=python3
#
# USAGE
#   scripts/backup/restore_test_pgbackrest.sh --dry-run     # affiche le plan, n'exécute rien
#   sudo -u postgres -E scripts/backup/restore_test_pgbackrest.sh
#   GED seul (à blanc sur l'environnement de dev, sans pgBackRest) :
#     DATABASE_URL=postgres://etls:...@127.0.0.1:5433/etls S3_ENDPOINT=http://127.0.0.1:9000 S3_BUCKET=etls-documents \
#     S3_ACCESS_KEY=... S3_SECRET_KEY=... backend/.venv/bin/python scripts/backup/verify_ged_s3.py --sample 5
#
# CIBLES (PLAN_SAUVEGARDE_PRA) : RPO ≤ 24 h, RTO ≤ 8 h ; un écart = incident à tracer au registre PRA.

set -euo pipefail

STANZA=${STANZA:-etls}
BACKUP_SET=${BACKUP_SET:-}
RESTORE_DIR=${RESTORE_DIR:-/var/tmp/etls_restore_test}
PGPORT_TEST=${PGPORT_TEST:-5499}
PGUSER_TEST=${PGUSER_TEST:-etls}
PGDB_TEST=${PGDB_TEST:-etls}
GED_SAMPLE=${GED_SAMPLE:-50}
PYTHON=${PYTHON:-python3}
KEEP=${KEEP:-0}
HERE="$(cd "$(dirname "$0")" && pwd)"
REPORTS="$HERE/reports"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
REPORT="$REPORTS/restore_pgbackrest_$STAMP.json"
DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

run() {
  echo "+ $*"
  if [[ $DRY -eq 0 ]]; then "$@"; fi
}

psql_test() {
  psql -h "$RESTORE_DIR" -p "$PGPORT_TEST" -U "$PGUSER_TEST" -d "$PGDB_TEST" -At -c "$1"
}

if [[ -d "$RESTORE_DIR" && -n "$(ls -A "$RESTORE_DIR" 2>/dev/null)" && $DRY -eq 0 ]]; then
  echo "RESTORE_DIR=$RESTORE_DIR n'est pas vide : refus (protection contre un répertoire de données réel)." >&2
  exit 2
fi
if [[ $DRY -eq 0 ]] && pg_isready -h 127.0.0.1 -p "$PGPORT_TEST" >/dev/null 2>&1; then
  echo "Port $PGPORT_TEST déjà utilisé : choisissez PGPORT_TEST." >&2
  exit 2
fi
mkdir -p "$REPORTS"

echo "1/5 Inventaire du dépôt pgBackRest (stanza $STANZA)"
run pgbackrest --stanza="$STANZA" info

echo "2/5 Restauration dans $RESTORE_DIR"
T0=$(date +%s)
SET_OPT=()
[[ -n "$BACKUP_SET" ]] && SET_OPT=(--set="$BACKUP_SET")
run mkdir -p "$RESTORE_DIR"
run chmod 700 "$RESTORE_DIR"
# --type=immediate : arrêt à la fin de la sauvegarde (cohérente) puis promotion ; aucun écrasement du primaire
# (--pg1-path pointe le répertoire jetable).
run pgbackrest --stanza="$STANZA" --pg1-path="$RESTORE_DIR" "${SET_OPT[@]}" \
  --type=immediate --target-action=promote --log-level-console=info restore
if [[ $DRY -eq 0 && ! -f "$RESTORE_DIR/postgresql.conf" ]]; then
  # Disposition Debian (configuration dans /etc/postgresql) : configuration minimale locale.
  printf "listen_addresses = ''\nmax_connections = 20\n" > "$RESTORE_DIR/postgresql.conf"
  printf "local all all trust\n" > "$RESTORE_DIR/pg_hba.conf"
fi

echo "3/5 Démarrage isolé (port $PGPORT_TEST, socket $RESTORE_DIR, archive_mode=off)"
run pg_ctl -D "$RESTORE_DIR" -l "$RESTORE_DIR/restore.log" -w -t 3600 start \
  -o "-p $PGPORT_TEST -c listen_addresses='' -c unix_socket_directories='$RESTORE_DIR' -c archive_mode=off -c hba_file='$RESTORE_DIR/pg_hba.conf'"
if [[ $DRY -eq 0 ]]; then
  for _ in $(seq 1 720); do
    [[ "$(psql_test 'select pg_is_in_recovery()' 2>/dev/null || echo t)" == "f" ]] && break
    sleep 5
  done
fi
T1=$(date +%s)
RTO=$((T1 - T0))

echo "4/5 Contrôles de cohérence"
TABLES="users_user documents_document documents_version accounting_kernel_accountmove accounting_kernel_accountmoveline rh_paie_employe rh_paie_bulletinpaie stocks_mouvementstock integrations_lotreprise"
COMPTES="{}"
DESEQ=-1
DERNIERE=""
if [[ $DRY -eq 0 ]]; then
  COMPTES="{"
  for t in $TABLES; do
    n=$(psql_test "select count(*) from $t" 2>/dev/null || echo "-1")
    COMPTES="$COMPTES\"$t\": $n,"
  done
  COMPTES="${COMPTES%,}}"
  DESEQ=$(psql_test "select count(*) from (select move_id from accounting_kernel_accountmoveline group by move_id having sum(debit) <> sum(credit)) x")
  DERNIERE=$(psql_test "select coalesce(max(created_at)::text, '') from accounting_kernel_accountmove")
fi

echo "5/5 Fichiers GED : présence et SHA-256 dans le bucket S3 de sauvegarde (échantillon $GED_SAMPLE)"
GED_JSON="{}"
if [[ $DRY -eq 0 ]]; then
  GED_JSON=$(DATABASE_URL="postgresql://$PGUSER_TEST@/$PGDB_TEST?host=$RESTORE_DIR&port=$PGPORT_TEST" \
    "$PYTHON" "$HERE/verify_ged_s3.py" --sample "$GED_SAMPLE" --json || true)
else
  echo "+ $PYTHON $HERE/verify_ged_s3.py --sample $GED_SAMPLE --json"
fi

if [[ $DRY -eq 0 ]]; then
  run pg_ctl -D "$RESTORE_DIR" -m fast -w stop
  [[ "$KEEP" == "1" ]] || rm -rf "$RESTORE_DIR"
  OK=true
  [[ "$DESEQ" == "0" ]] || OK=false
  echo "$GED_JSON" | grep -q '"resultat": "OK"' || OK=false
  cat > "$REPORT" <<JSON
{
  "date": "$(date -u +%FT%TZ)",
  "stanza": "$STANZA",
  "sauvegarde": "${BACKUP_SET:-derniere}",
  "rto_mesure_s": $RTO,
  "derniere_ecriture_restauree": "$DERNIERE",
  "volumes": $COMPTES,
  "ecritures_desequilibrees": $DESEQ,
  "ged": $GED_JSON,
  "resultat": "$($OK && echo OK || echo ECHEC)",
  "cibles": "RPO <= 24 h ; RTO <= 8 h (CL-OM-11)"
}
JSON
  echo "Rapport : $REPORT"
  $OK || exit 1
else
  echo "(à blanc) aucun changement effectué ; rapport non écrit."
fi
