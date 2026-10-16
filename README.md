# ETSL ERP

ERP sur mesure pour ETSL (Gabon) : GED / archivage, workflows de validation et
12 modules métier (M1–M12) + couche BI. Sources des besoins :
`SPECIFICATION_SYSTEME_ETSL.md` (`RF-xx`) et `ARCHITECTURE_ERP_ETSL.md`
(`RF-ERP-xx`), dans le dossier parent `archi/`.

## Stack

| Couche | Technologie |
|---|---|
| Backend | Python 3.13 / Django 5 + DRF + Celery (+ beat) |
| Base de données | PostgreSQL 16 |
| Stockage objets | MinIO (S3) — ou `STORAGE_BACKEND=local` |
| Cache / broker | Redis 7 |
| Frontend | SPA web React 19 + TypeScript (Vite) + Motion v13 |
| Desktop (scan uniquement) | Tauri — réservé au scan RICOH / GED hors ligne |
| BI | dbt + Apache Superset sur réplica lecture |
| Orchestration | Docker Compose (dev) / `docker-compose.prod.yml` (stateless) |

## Prérequis

- Docker Desktop (WSL2). Si `docker` n'est pas reconnu, ajouter
  `C:\Users\user\AppData\Local\Programs\DockerDesktop\resources\bin` au PATH.
- Python 3.13, Node 22.

## Infrastructure (dev)

```powershell
Copy-Item .env.example .env
docker compose up -d     # postgres:16 + minio + redis
docker compose ps        # attendre "healthy"
```

- PostgreSQL : port hôte **5433** (5432 est pris par un PostgreSQL Windows natif).
- MinIO : API http://localhost:9000, console http://localhost:9001.
- Redis : 6379.

## Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
Copy-Item ../.env .env
python manage.py migrate
python manage.py seed_all_demo     # données de démo (20 seeds, comptes @etls.local)
python manage.py runserver
```

Vérification : `GET http://localhost:8000/api/health/`. Documentation OpenAPI :
`/api/schema/`, `/api/schema/swagger-ui/`, `/api/schema/redoc/`.

## Frontend

```powershell
cd frontend
npm ci
npm run dev          # http://localhost:5173, proxy /api -> 127.0.0.1:8000
npm run typecheck && npm run build
npm run test:unit    # vitest
npm run test:e2e     # Playwright (backend sur la base etls_e2e requis)
```

## Tests et CI

- Backend : `python manage.py test <apps> --keepdb --noinput` (liste complète
  des apps dans `.github/workflows/regression.yml`).
- CI GitHub Actions (`regression.yml`) : backend + frontend + e2e à chaque push
  sur `master` et chaque nuit (23h UTC).
- Droits de lecture par module : `backend/users/rbac.py` ; vérifier la cohérence
  avec les droits d'écriture via `python check_rbac_coherence.py`.
